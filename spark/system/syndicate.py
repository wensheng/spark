"""Async-first public Syndicate API."""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar, cast

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.actor_spec import ActorExecution, ActorSpec
from ..core.exceptions import SyndicateError, UnsupportedBackendError
from ..core.identity import Envelope, SyndicateId
from ..core.message import Message
from ..core.messages import DeadLetter
from ..persistence import Journal
from ..runtime.async_backend import AsyncExternalEndpoint, AsyncInProcessBackend
from ..runtime.diagnostics import RuntimeDiagnostics
from ..runtime.events import RuntimeEvent
from ..runtime.results import DeliveryResult
from ..services import (
    DiagnosticsService,
    FederationAck,
    FederationAuthError,
    FederationHeartbeat,
    FederationJoinAccepted,
    FederationJoinRejected,
    FederationJoinRequest,
    FederationLeave,
    FederationManager,
    LocalFirstPlacementStrategy,
    LocalNameRegistry,
    PackageArtifactProvider,
    PlacementError,
    RemoteActorSpec,
    RemoteSpawnAccepted,
    RemoteSpawnError,
    RemoteSpawnRejected,
    RemoteSpawnRequest,
    StaticMembershipProvider,
    SystemDescriptor,
    SystemDiagnosticsSnapshot,
)
from ..transport.async_tcp import AsyncTcpTransport
from ..transport.codec import CBOR2EnvelopeCodec, EnvelopeCodec, PickleEnvelopeCodec
from ..transport.websocket import AsyncWebSocketTransport

_DEFAULT_LOGGER_NAME = "spark.system.syndicate"
_MISSING = object()
_T = TypeVar("_T")
_BACKEND_DEFAULT_EXECUTION: dict[str, ActorExecution] = {
    "inprocess": "inprocess",
    "threaded": "thread",
    "process": "process",
}
_BACKEND_TYPE: dict[str, str] = {
    "inprocess": "async-inprocess",
    "threaded": "async-hybrid-threaded",
    "process": "async-hybrid-process",
}
_SUPPORTED_TRANSPORT_CODECS = {"cbor2", "trusted-pickle"}


@dataclass(frozen=True, slots=True)
class _GlobalSyndicateConfig:
    name: str | None = None
    backend: str = "inprocess"
    remote: bool = False
    remote_host: str = "127.0.0.1"
    remote_port: int = 0
    remote_transport: str = "tcp"
    transport_codec: str = "cbor2"
    transport_secret: str | bytes | None = None
    transport_connect_timeout: float = 5.0
    transport_frame_timeout: float = 5.0
    transport_idle_timeout: float | None = 30.0
    allow_unsafe_pickle: bool = False
    federation: bool = False
    federation_secret: str | None = None
    federation_lease_seconds: float = 30.0
    system_capabilities: Mapping[str, Any] | None = None
    journal: Journal | None = None


def _make_transport_codec(name: str) -> EnvelopeCodec:
    if name == "trusted-pickle":
        return PickleEnvelopeCodec()
    if name == "cbor2":
        return CBOR2EnvelopeCodec()
    raise UnsupportedBackendError(f"unsupported transport_codec={name!r}")


def _is_loopback_host(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


class _FederationActor(Actor):
    """Internal actor that receives federation control messages."""

    __spark_auto_start__ = False

    def __init__(self, system: Syndicate) -> None:
        super().__init__()
        self._system = system

    async def process(self, message: Message) -> Any:
        payload = message.content
        if isinstance(payload, FederationJoinRequest):
            return await self._system._handle_federation_join(payload)
        if isinstance(payload, FederationHeartbeat):
            return await self._system._handle_federation_heartbeat(payload)
        if isinstance(payload, FederationLeave):
            return await self._system._handle_federation_leave(payload)
        if isinstance(payload, RemoteSpawnRequest):
            return await self._system._handle_remote_spawn(payload)
        return FederationJoinRejected(f"unsupported federation message: {type(payload).__name__}")


class Syndicate:
    """Async-first entry point for creating actors and routing messages."""

    def __init__(
        self,
        name: str | None = None,
        backend: str = "inprocess",
        *,
        remote: bool = False,
        remote_host: str = "127.0.0.1",
        remote_port: int = 0,
        remote_transport: str = "tcp",
        transport_codec: str = "cbor2",
        transport_secret: str | bytes | None = None,
        transport_connect_timeout: float = 5.0,
        transport_frame_timeout: float = 5.0,
        transport_idle_timeout: float | None = 30.0,
        allow_unsafe_pickle: bool = False,
        federation: bool = False,
        federation_secret: str | None = None,
        federation_lease_seconds: float = 30.0,
        system_capabilities: Mapping[str, Any] | None = None,
        journal: Journal | None = None,
        dead_letter_capacity: int = 1024,
        event_capacity: int = 2048,
        logger: logging.Logger | None = None,
        **_unsupported: Any,
    ) -> None:
        if _unsupported:
            unsupported = ", ".join(sorted(_unsupported))
            raise TypeError(f"unsupported async Syndicate option(s): {unsupported}")
        if backend not in _BACKEND_DEFAULT_EXECUTION:
            raise UnsupportedBackendError(f"unsupported backend={backend!r}")
        self.syndicate_id = SyndicateId.from_name(name) if name is not None else SyndicateId()
        self._backend_type = _BACKEND_TYPE[backend]
        self._system_capabilities = dict(system_capabilities or {})
        self.backend = AsyncInProcessBackend(
            self.syndicate_id,
            default_execution=_BACKEND_DEFAULT_EXECUTION[backend],
            backend_type=self._backend_type,
            dead_letter_capacity=dead_letter_capacity,
            event_capacity=event_capacity,
            journal=journal,
        )
        self.address = self.backend.address
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._owner_thread_id: int | None = None
        if remote_transport not in {"tcp", "websocket"}:
            raise UnsupportedBackendError(f"unsupported remote_transport={remote_transport!r}")
        if transport_codec == "pickle":
            raise UnsupportedBackendError("transport_codec='pickle' was removed; use 'trusted-pickle' explicitly")
        if transport_codec not in _SUPPORTED_TRANSPORT_CODECS:
            raise UnsupportedBackendError(f"unsupported transport_codec={transport_codec!r}")
        if (
            remote
            and transport_codec == "trusted-pickle"
            and not _is_loopback_host(remote_host)
            and not allow_unsafe_pickle
        ):
            raise UnsupportedBackendError(
                "trusted-pickle remote transport is unsafe on non-loopback interfaces; "
                "use transport_codec='cbor2' or pass allow_unsafe_pickle=True"
            )
        codec = _make_transport_codec(transport_codec) if remote else None
        self._remote_transport = remote_transport
        self._transport_codec = transport_codec
        self._transport: AsyncTcpTransport | AsyncWebSocketTransport | None
        if remote and remote_transport == "tcp":
            self._transport = AsyncTcpTransport(
                self.syndicate_id,
                remote_host,
                remote_port,
                self._receive_remote_envelope,
                codec=codec,
                codec_name=transport_codec,
                shared_secret=transport_secret,
                connect_timeout=transport_connect_timeout,
                frame_timeout=transport_frame_timeout,
                idle_timeout=transport_idle_timeout,
            )
        elif remote and remote_transport == "websocket":
            self._transport = AsyncWebSocketTransport(
                self.syndicate_id,
                remote_host,
                remote_port,
                self._receive_remote_envelope,
                codec=codec,
            )
        else:
            self._transport = None
        self._started = False
        self._federation_enabled = federation
        self._federation_secret = federation_secret
        self._federation_lease_seconds = federation_lease_seconds
        self._federation_address: ActorAddress | None = None
        self._logger = logger if logger is not None else logging.getLogger(_DEFAULT_LOGGER_NAME)
        self.name_registry = LocalNameRegistry()
        self.placement = LocalFirstPlacementStrategy(self.syndicate_id)
        self.artifact_provider = PackageArtifactProvider()
        self.diagnostics_service = DiagnosticsService()
        self.membership = StaticMembershipProvider([self.local_descriptor])
        self.federation = FederationManager(
            self.syndicate_id,
            self.membership,
            self.artifact_provider,
            auth_secret=federation_secret,
            lease_seconds=federation_lease_seconds,
        )

    async def __aenter__(self) -> Syndicate:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.shutdown()

    @staticmethod
    def run(coro: Coroutine[Any, Any, Any]) -> Any:
        """Run a Spark async entrypoint from synchronous application code."""
        with asyncio.Runner() as runner:
            return runner.run(coro)

    async def _run_on_owner_loop(self, operation: Callable[[], Coroutine[Any, Any, _T]]) -> _T:
        running_loop = asyncio.get_running_loop()
        if self._owner_loop is None:
            self._owner_loop = running_loop
            self._owner_thread_id = threading.get_ident()
            return await operation()
        if running_loop is self._owner_loop:
            return await operation()
        if self._owner_loop.is_closed() or not self._owner_loop.is_running():
            raise SyndicateError("Syndicate owner event loop is closed")
        future: Future[_T] = asyncio.run_coroutine_threadsafe(operation(), self._owner_loop)
        return await asyncio.wrap_future(future)

    async def start(self) -> None:
        """Start runtime-owned async resources."""
        await self._run_on_owner_loop(self._start_local)

    @property
    def active(self) -> bool:
        """Return True if the Syndicate is running."""
        return self._started

    @property
    def federation_address(self) -> ActorAddress | None:
        """Return the internal federation actor address when federation is enabled."""
        return self._federation_address

    @property
    def local_descriptor(self) -> SystemDescriptor:
        """Return this system's current membership descriptor."""
        capabilities = {"backend": self._backend_type, **self._system_capabilities}
        endpoints: dict[str, str] = {}
        if self.remote_uri is not None:
            endpoints["websocket"] = self.remote_uri
        elif self.remote_address is not None:
            host, port = self.remote_address
            endpoints[self._remote_transport] = f"{host}:{port}"
        return SystemDescriptor(
            syndicate_id=self.syndicate_id,
            address=self.address,
            remote_address=self.remote_address,
            federation_address=self._federation_address,
            endpoints=endpoints,
            auth_identity=self.syndicate_id.uuid if self._federation_secret is not None else None,
            capabilities=capabilities,
            tags=frozenset({"local"}),
        )

    def _refresh_local_descriptor(self) -> None:
        self.membership.add_system(self.local_descriptor)

    async def _start_local(self) -> None:
        if self._started:
            return
        await self.backend.start()
        if self._transport is not None:
            await self._transport.start()
            self.backend.set_remote_sender(self._transport.send)
        if self._federation_enabled and self._federation_address is None:
            self._federation_address = await self.backend.create_actor(_FederationActor, self)
        self._refresh_local_descriptor()
        if self._federation_enabled:
            self.federation.configure(
                local_descriptor=self.local_descriptor,
                route_connector=self._connect_descriptor_route,
                local_spawner=self.backend.create_actor_from_spec,
            )
        self._started = True

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a top-level actor."""
        return await self._run_on_owner_loop(lambda: self._create_actor_local(actor_class, *args, **kwargs))

    async def _create_actor_local(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        await self._start_local()
        return await self.backend.create_actor(actor_class, *args, **kwargs)

    async def create_actor_from_spec(
        self,
        spec: ActorSpec,
        *,
        placement: str | SyndicateId | SystemDescriptor = "local",
        timeout: float | None = 5.0,
    ) -> ActorAddress:
        """Create a top-level actor from an explicit actor specification."""
        return await self._run_on_owner_loop(
            lambda: self._create_actor_from_spec_local(spec, placement=placement, timeout=timeout)
        )

    async def _create_actor_from_spec_local(
        self,
        spec: ActorSpec,
        *,
        placement: str | SyndicateId | SystemDescriptor = "local",
        timeout: float | None = 5.0,
    ) -> ActorAddress:
        await self._start_local()
        if placement != "local":
            descriptor = self._resolve_placement(spec, placement)
            if descriptor.syndicate_id != self.syndicate_id:
                return await self._create_remote_actor_from_spec(spec, descriptor, timeout=timeout)
        return await self.backend.create_actor_from_spec(spec)

    async def start_actor(self, actor: Actor) -> ActorAddress:
        """Start an existing top-level actor instance."""
        return await self._run_on_owner_loop(lambda: self._start_actor_local(actor))

    async def _start_actor_local(self, actor: Actor) -> ActorAddress:
        await self._start_local()
        return await self.backend.start_actor(actor)

    async def tell(
        self,
        message: Any = _MISSING,
        target: ActorAddress | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> DeliveryResult:
        """Send a fire-and-forget message."""
        if message is _MISSING:
            raise TypeError("tell() missing message")
        if target is None:
            target = self.address
        return await self._tell_to_address(target, message, ttl=ttl, deadline=deadline)

    async def _tell_to_address(
        self,
        target: ActorAddress,
        message: Any,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> DeliveryResult:
        return await self._run_on_owner_loop(lambda: self._tell_local(target, message, ttl=ttl, deadline=deadline))

    async def _tell_local(
        self,
        target: ActorAddress,
        message: Any,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> DeliveryResult:
        await self._start_local()
        return await self.backend.tell(message, target, ttl=ttl, deadline=deadline)

    async def ask(
        self,
        message: Any = _MISSING,
        target: ActorAddress | None = None,
        timeout: float | None = 5.0,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        """Send a message and await the first reply."""
        if message is _MISSING:
            raise TypeError("ask() missing message")
        if target is None:
            target = self.address
        return await self._ask_address(target, message, timeout, ttl=ttl, deadline=deadline)

    async def _ask_address(
        self,
        target: ActorAddress,
        message: Any,
        timeout: float | None = 5.0,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        return await self._run_on_owner_loop(
            lambda: self._ask_local(target, message, timeout, ttl=ttl, deadline=deadline)
        )

    async def _ask_local(
        self,
        target: ActorAddress,
        message: Any,
        timeout: float | None = 5.0,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        await self._start_local()
        return await self.backend.ask(message, target, timeout=timeout, ttl=ttl, deadline=deadline)

    async def ask_stream(
        self,
        message: Any = _MISSING,
        target: ActorAddress | None = None,
        timeout: float | None = 5.0,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        max_replies: int | None = None,
    ) -> AsyncIterator[Any]:
        """Send a message and yield zero or more replies until idle timeout or max replies."""
        if message is _MISSING:
            raise TypeError("ask_stream() missing message")
        if target is None:
            target = self.address
        await self._start_local()
        async for reply in self.backend.ask_stream(
            message,
            target,
            timeout=timeout,
            ttl=ttl,
            deadline=deadline,
            max_replies=max_replies,
        ):
            yield reply

    async def receive(self, timeout: float | None = None) -> Any:
        """Receive one message sent to this actor system's external inbox."""
        return await self._run_on_owner_loop(lambda: self._receive_local(timeout))

    async def _receive_local(self, timeout: float | None = None) -> Any:
        await self._start_local()
        return await self.backend.receive(timeout)

    async def listen(self) -> AsyncIterator[Any]:
        """Yield messages sent to this actor system's external inbox."""
        while True:
            yield await self.receive()

    def endpoint(self) -> _EndpointContext:
        """Create an isolated external endpoint for application tasks."""
        return _EndpointContext(self)

    async def stop(self, target: ActorAddress) -> None:
        """Stop an actor."""
        await self._run_on_owner_loop(lambda: self._stop_local(target))

    async def _stop_local(self, target: ActorAddress) -> None:
        await self._start_local()
        await self.backend.stop(target)

    async def link(self, left: ActorAddress, right: ActorAddress) -> None:
        """Link two local actors for bidirectional fate sharing."""
        await self._run_on_owner_loop(lambda: self._link_local(left, right))

    async def _link_local(self, left: ActorAddress, right: ActorAddress) -> None:
        await self._start_local()
        await self.backend.link(left, right)

    async def monitor(self, target: ActorAddress, watcher: ActorAddress | None = None) -> None:
        """Notify ``watcher`` when ``target`` exits; defaults to the system inbox."""
        if watcher is None:
            watcher = self.address
        await self._run_on_owner_loop(lambda: self._monitor_local(watcher, target))

    async def _monitor_local(self, watcher: ActorAddress, target: ActorAddress) -> None:
        await self._start_local()
        await self.backend.monitor(watcher, target)

    async def shutdown(self) -> None:
        """Shut down the actor system."""
        await self._run_on_owner_loop(self._shutdown_local)

    async def _shutdown_local(self) -> None:
        if self._transport is not None:
            await self._transport.close()
        await self.backend.shutdown()
        self._started = False

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        return self.backend.dead_letters

    @property
    def late_replies(self) -> tuple[DeadLetter, ...]:
        return self.backend.late_replies

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        return self.backend.events

    def diagnostics_snapshot(self) -> SystemDiagnosticsSnapshot:
        return self.diagnostics_service.snapshot(cast(Any, self))

    def diagnostics(self) -> RuntimeDiagnostics:
        return self.backend.diagnostics()

    @property
    def remote_address(self) -> tuple[str, int] | None:
        return None if self._transport is None else self._transport.address

    @property
    def remote_uri(self) -> str | None:
        return None if self._transport is None else getattr(self._transport, "uri", None)

    @property
    def transport_health(self) -> dict[str, dict[str, object]]:
        if self._transport is None:
            return {}
        route_health = getattr(self._transport, "route_health", None)
        if route_health is None:
            return {}
        return cast(dict[str, dict[str, object]], route_health())

    def register_name(self, name: str, address: ActorAddress, *, scope: str = "local") -> None:
        """Register an actor name in the local name registry."""
        self.name_registry.register(name, address, scope=cast(Any, scope))

    def resolve_name(self, name: str, *, scope: str = "local") -> ActorAddress | None:
        """Resolve an actor name from the local name registry."""
        return self.name_registry.resolve(name, scope=cast(Any, scope))

    async def join_federation(
        self,
        descriptor: SystemDescriptor,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> SystemDescriptor:
        """Join a peer federation through its federation actor."""
        return await self._run_on_owner_loop(
            lambda: self._join_federation_local(descriptor, token=token, timeout=timeout)
        )

    async def _join_federation_local(
        self,
        descriptor: SystemDescriptor,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> SystemDescriptor:
        await self._start_local()
        if not self._federation_enabled:
            raise UnsupportedBackendError("federation is not enabled")
        if descriptor.federation_address is None:
            raise SyndicateError("peer descriptor does not expose a federation address")
        await self._connect_descriptor_route(descriptor)
        request = FederationJoinRequest(
            self.local_descriptor,
            token=token if token is not None else self._federation_secret,
        )
        response = await self._ask_local(descriptor.federation_address, request, timeout)
        if isinstance(response, FederationJoinRejected):
            raise FederationAuthError(response.reason)
        if not isinstance(response, FederationJoinAccepted):
            raise SyndicateError(f"unexpected federation join response: {response!r}")
        await self.federation.add_member(response.descriptor)
        for member in response.members:
            await self.federation.add_member(member)
        return response.descriptor

    async def heartbeat_federation(
        self,
        syndicate_id: SyndicateId,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> None:
        """Send a federation heartbeat to one known peer."""
        await self._run_on_owner_loop(
            lambda: self._heartbeat_federation_local(syndicate_id, token=token, timeout=timeout)
        )

    async def _heartbeat_federation_local(
        self,
        syndicate_id: SyndicateId,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> None:
        await self._start_local()
        descriptor = self.membership.get_system(syndicate_id)
        if descriptor is None or descriptor.federation_address is None:
            raise SyndicateError("federation peer is not known")
        response = await self._ask_local(
            descriptor.federation_address,
            FederationHeartbeat(self.local_descriptor, token=token if token is not None else self._federation_secret),
            timeout,
        )
        if isinstance(response, FederationJoinRejected):
            raise FederationAuthError(response.reason)

    async def leave_federation(
        self,
        syndicate_id: SyndicateId,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> None:
        """Leave one known peer's federation membership view."""
        await self._run_on_owner_loop(lambda: self._leave_federation_local(syndicate_id, token=token, timeout=timeout))

    async def _leave_federation_local(
        self,
        syndicate_id: SyndicateId,
        *,
        token: str | None = None,
        timeout: float | None = 5.0,
    ) -> None:
        await self._start_local()
        descriptor = self.membership.get_system(syndicate_id)
        if descriptor is None or descriptor.federation_address is None:
            self.federation.remove_member(syndicate_id)
            return
        response = await self._ask_local(
            descriptor.federation_address,
            FederationLeave(self.syndicate_id, token=token if token is not None else self._federation_secret),
            timeout,
        )
        if isinstance(response, FederationJoinRejected):
            raise FederationAuthError(response.reason)
        self.federation.remove_member(syndicate_id)

    async def prune_federation(self, now: float | None = None) -> list[SystemDescriptor]:
        """Remove expired federation members."""
        return await self._run_on_owner_loop(lambda: self._prune_federation_local(now))

    async def _prune_federation_local(self, now: float | None = None) -> list[SystemDescriptor]:
        await self._start_local()
        return self.federation.prune_expired(now)

    async def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        """Add a system-level host:port route to a peer actor system."""
        await self._run_on_owner_loop(lambda: self._connect_local(syndicate_id, host, port))

    async def _connect_local(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        await self._start_local()
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        self._transport.connect(syndicate_id, host, port)

    async def _connect_descriptor_route(self, descriptor: SystemDescriptor) -> None:
        if descriptor.syndicate_id == self.syndicate_id:
            return
        if descriptor.remote_address is None:
            return
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        self._transport.connect(descriptor.syndicate_id, *descriptor.remote_address)

    async def connect_uri(self, syndicate_id: SyndicateId, uri: str) -> None:
        """Add a system-level websocket URI route to a peer actor system."""
        await self._run_on_owner_loop(lambda: self._connect_uri_local(syndicate_id, uri))

    async def _connect_uri_local(self, syndicate_id: SyndicateId, uri: str) -> None:
        await self._start_local()
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        connect_uri = getattr(self._transport, "connect_uri", None)
        if connect_uri is None:
            raise UnsupportedBackendError("remote transport does not support URI routes")
        connect_uri(syndicate_id, uri)

    async def connect_relay(self, uri: str, *, secret: str | bytes | None = None) -> None:
        """Connect this actor system to a websocket relay."""
        await self._run_on_owner_loop(lambda: self._connect_relay_local(uri, secret=secret))

    async def _connect_relay_local(self, uri: str, *, secret: str | bytes | None = None) -> None:
        await self._start_local()
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        connect_relay = getattr(self._transport, "connect_relay", None)
        if connect_relay is None:
            raise UnsupportedBackendError("remote transport does not support websocket relays")
        await connect_relay(uri, secret=secret)

    def _resolve_placement(
        self,
        spec: ActorSpec,
        placement: str | SyndicateId | SystemDescriptor,
    ) -> SystemDescriptor:
        if isinstance(placement, SystemDescriptor):
            return placement
        if isinstance(placement, SyndicateId):
            descriptor = self.membership.get_system(placement)
            if descriptor is None:
                raise PlacementError(f"unknown placement target {placement}")
            return descriptor
        if placement == "auto":
            return self.placement.choose(spec, self.membership.list_systems())
        if placement == "local":
            descriptor = self.membership.get_system(self.syndicate_id)
            return descriptor if descriptor is not None else self.local_descriptor
        raise PlacementError("placement must be 'local', 'auto', a SyndicateId, or a SystemDescriptor")

    async def _create_remote_actor_from_spec(
        self,
        spec: ActorSpec,
        descriptor: SystemDescriptor,
        *,
        timeout: float | None = 5.0,
    ) -> ActorAddress:
        if not self._federation_enabled:
            raise UnsupportedBackendError("remote actor spawn requires federation=True")
        if descriptor.federation_address is None:
            raise RemoteSpawnError("placement target does not expose a federation address")
        await self._connect_descriptor_route(descriptor)
        request = RemoteSpawnRequest(
            RemoteActorSpec.from_actor_spec(spec),
            token=self._federation_secret,
        )
        response = await self._ask_local(descriptor.federation_address, request, timeout)
        if isinstance(response, RemoteSpawnRejected):
            raise RemoteSpawnError(response.reason)
        if not isinstance(response, RemoteSpawnAccepted):
            raise RemoteSpawnError(f"unexpected remote spawn response: {response!r}")
        return response.address

    async def _handle_federation_join(
        self,
        request: FederationJoinRequest,
    ) -> FederationJoinAccepted | FederationJoinRejected:
        await self._start_local()
        await self._connect_descriptor_route(request.descriptor)
        return await self.federation.accept_join(request)

    async def _handle_federation_heartbeat(
        self,
        heartbeat: FederationHeartbeat,
    ) -> FederationAck | FederationJoinRejected:
        await self._start_local()
        return await self.federation.accept_heartbeat(heartbeat)

    async def _handle_federation_leave(self, leave: FederationLeave) -> FederationAck | FederationJoinRejected:
        await self._start_local()
        return await self.federation.accept_leave(leave)

    async def _handle_remote_spawn(self, request: RemoteSpawnRequest) -> RemoteSpawnAccepted | RemoteSpawnRejected:
        await self._start_local()
        return await self.federation.accept_spawn(request)

    async def _receive_remote_envelope(self, envelope: Envelope) -> None:
        if envelope.target.syndicate_id != self.syndicate_id:
            return
        await self.backend.deliver_envelope(envelope)


class _EndpointContext:
    def __init__(self, system: Syndicate) -> None:
        self._system = system
        self._endpoint: AsyncExternalEndpoint | None = None

    async def __aenter__(self) -> AsyncExternalEndpoint:
        await self._system.start()
        self._endpoint = self._system.backend.create_endpoint()
        return self._endpoint

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._endpoint is not None:
            self._system.backend.remove_endpoint(self._endpoint)
            self._endpoint = None


class _GlobalSyndicateRuntime:
    def __init__(self, config: _GlobalSyndicateConfig, logger: logging.Logger | None) -> None:
        self.config = config
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._shutdown_requested = False
        self._thread = threading.Thread(target=self._run, name="spark-global-syndicate", daemon=True)
        self._thread.start()
        self._ready.wait()
        try:
            self.system = self.submit(self._create_system(config, logger)).result()
        except BaseException:
            self.shutdown()
            raise

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.call_soon(self._ready.set)
        self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.close()

    async def _create_system(
        self,
        config: _GlobalSyndicateConfig,
        logger: logging.Logger | None,
    ) -> Syndicate:
        system = Syndicate(
            config.name,
            config.backend,
            remote=config.remote,
            remote_host=config.remote_host,
            remote_port=config.remote_port,
            remote_transport=config.remote_transport,
            transport_codec=config.transport_codec,
            transport_secret=config.transport_secret,
            transport_connect_timeout=config.transport_connect_timeout,
            transport_frame_timeout=config.transport_frame_timeout,
            transport_idle_timeout=config.transport_idle_timeout,
            allow_unsafe_pickle=config.allow_unsafe_pickle,
            federation=config.federation,
            federation_secret=config.federation_secret,
            federation_lease_seconds=config.federation_lease_seconds,
            system_capabilities=config.system_capabilities,
            journal=config.journal,
            logger=logger,
        )
        await system.start()
        system.backend.set_no_active_callback(self._handle_no_active_actors)
        return system

    def submit(self, coro: Coroutine[Any, Any, _T]) -> Future[_T]:
        if not self.loop.is_running():
            coro.close()
            raise SyndicateError("global Syndicate event loop is not running")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def start_actor(self, actor: Actor) -> ActorAddress:
        if threading.get_ident() == self._thread.ident:
            raise SyndicateError(
                "direct actor construction cannot auto-start from the global Syndicate event loop; "
                "use await self.create_actor(...) instead"
            )
        return self.submit(self.system.start_actor(actor)).result()

    def _handle_no_active_actors(self) -> None:
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        self.loop.create_task(self._shutdown_after_no_active())

    async def _shutdown_after_no_active(self) -> None:
        global _global_syndicate, _global_syndicate_config, _global_runtime
        if self.system.backend.running_actor_count() > 0 or self.system.backend.active_actor_count() > 0:
            self._shutdown_requested = False
            return
        with _global_syndicate_lock:
            if _global_runtime is not self:
                return
            _global_syndicate = None
            _global_syndicate_config = None
            _global_runtime = None
        await self.system.shutdown()
        self.loop.stop()

    def shutdown(self) -> None:
        self._shutdown_requested = True
        if threading.get_ident() == self._thread.ident:

            async def shutdown_then_stop() -> None:
                await self.system.shutdown()
                self.loop.stop()

            self.loop.create_task(shutdown_then_stop())
            return
        if self.loop.is_closed():
            return
        if self.loop.is_running():
            if hasattr(self, "system"):
                self.submit(self.system.shutdown()).result()
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread.is_alive():
            self._thread.join()


_global_syndicate_lock = threading.RLock()
_global_syndicate: Syndicate | None = None
_global_syndicate_config: _GlobalSyndicateConfig | None = None
_global_runtime: _GlobalSyndicateRuntime | None = None
_global_atexit_registered = False


def _register_global_shutdown() -> None:
    global _global_atexit_registered
    if not _global_atexit_registered:
        atexit.register(shutdown_global_syndicate)
        _global_atexit_registered = True


def get_global_syndicate(
    name: str | None = None,
    backend: str = "inprocess",
    *,
    remote: bool = False,
    remote_host: str = "127.0.0.1",
    remote_port: int = 0,
    remote_transport: str = "tcp",
    transport_codec: str = "cbor2",
    transport_secret: str | bytes | None = None,
    transport_connect_timeout: float = 5.0,
    transport_frame_timeout: float = 5.0,
    transport_idle_timeout: float | None = 30.0,
    allow_unsafe_pickle: bool = False,
    federation: bool = False,
    federation_secret: str | None = None,
    federation_lease_seconds: float = 30.0,
    system_capabilities: Mapping[str, Any] | None = None,
    journal: Journal | None = None,
    logger: logging.Logger | None = None,
    **_unsupported: Any,
) -> Syndicate:
    """Return the process-wide default Syndicate, creating it on first use."""
    if _unsupported:
        unsupported = ", ".join(sorted(_unsupported))
        raise TypeError(f"unsupported async Syndicate option(s): {unsupported}")

    config = _GlobalSyndicateConfig(
        name=name,
        backend=backend,
        remote=remote,
        remote_host=remote_host,
        remote_port=remote_port,
        remote_transport=remote_transport,
        transport_codec=transport_codec,
        transport_secret=transport_secret,
        transport_connect_timeout=transport_connect_timeout,
        transport_frame_timeout=transport_frame_timeout,
        transport_idle_timeout=transport_idle_timeout,
        allow_unsafe_pickle=allow_unsafe_pickle,
        federation=federation,
        federation_secret=federation_secret,
        federation_lease_seconds=federation_lease_seconds,
        system_capabilities=system_capabilities,
        journal=journal,
    )
    global _global_syndicate, _global_syndicate_config, _global_runtime
    stale_runtime: _GlobalSyndicateRuntime | None = None
    with _global_syndicate_lock:
        if _global_syndicate is not None and _global_syndicate_is_stale(_global_syndicate, _global_runtime):
            stale_runtime = _global_runtime
            _global_syndicate = None
            _global_syndicate_config = None
            _global_runtime = None

    if stale_runtime is not None:
        stale_runtime.shutdown()

    with _global_syndicate_lock:
        if _global_syndicate is None:
            runtime = _GlobalSyndicateRuntime(config, logger)
            _global_runtime = runtime
            _global_syndicate = runtime.system
            _global_syndicate_config = config
            _register_global_shutdown()
            return _global_syndicate
        if _global_syndicate_config != config:
            raise SyndicateError(
                "global Syndicate already exists with different configuration; "
                "call shutdown_global_syndicate() before creating another global Syndicate"
            )
        return _global_syndicate


def _global_syndicate_is_stale(system: Syndicate, runtime: _GlobalSyndicateRuntime | None) -> bool:
    if runtime is None:
        return True
    if runtime.loop.is_closed() or not runtime.loop.is_running():
        return True
    return not system.active or bool(getattr(system.backend, "_shutdown", False))


def get_existing_global_syndicate() -> Syndicate | None:
    """Return the process-wide default Syndicate if one already exists."""
    with _global_syndicate_lock:
        return _global_syndicate


def _get_or_create_global_syndicate() -> Syndicate:
    return get_global_syndicate()


def _start_global_actor(actor: Actor) -> ActorAddress:
    _get_or_create_global_syndicate()
    with _global_syndicate_lock:
        runtime = _global_runtime
    if runtime is None:
        raise SyndicateError("global Syndicate is not available")
    return runtime.start_actor(actor)


async def _global_tell(message: Any) -> DeliveryResult:
    system = _get_or_create_global_syndicate()
    return await system._tell_to_address(system.address, message)


async def _global_ask(message: Any, timeout: float | None) -> Any:
    system = _get_or_create_global_syndicate()
    return await system._ask_address(system.address, message, timeout)


def shutdown_global_syndicate() -> None:
    """Shut down and clear the process-wide default Syndicate, if it exists."""
    global _global_syndicate, _global_syndicate_config, _global_runtime
    with _global_syndicate_lock:
        runtime = _global_runtime
        _global_syndicate = None
        _global_syndicate_config = None
        _global_runtime = None
    if runtime is not None:
        runtime.shutdown()
