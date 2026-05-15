"""Async-first public Syndicate API."""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from collections.abc import AsyncIterator, Callable, Coroutine
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from .actor.address import ActorAddress
from .actor.base import Actor
from .core.actor_spec import ActorExecution, ActorSpec
from .core.exceptions import SyndicateError, UnsupportedBackendError
from .core.identity import Envelope, SyndicateId
from .core.messages import DeadLetter
from .runtime.async_backend import AsyncExternalEndpoint, AsyncInProcessBackend
from .runtime.diagnostics import RuntimeDiagnostics
from .runtime.results import DeliveryResult
from .services import (
    DiagnosticsService,
    LocalFirstPlacementStrategy,
    LocalNameRegistry,
    PackageArtifactProvider,
    StaticMembershipProvider,
    SystemDescriptor,
    SystemDiagnosticsSnapshot,
)
from .transport.async_tcp import AsyncTcpTransport
from .transport.codec import CBOR2EnvelopeCodec, EnvelopeCodec, PickleEnvelopeCodec
from .transport.websocket import AsyncWebSocketTransport

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


@dataclass(frozen=True, slots=True)
class _GlobalSyndicateConfig:
    name: str | None = None
    backend: str = "inprocess"
    remote: bool = False
    remote_host: str = "127.0.0.1"
    remote_port: int = 0
    remote_transport: str = "tcp"
    transport_codec: str = "pickle"


def _make_transport_codec(name: str) -> EnvelopeCodec:
    if name == "pickle":
        return PickleEnvelopeCodec()
    if name == "cbor2":
        return CBOR2EnvelopeCodec()
    raise UnsupportedBackendError(f"unsupported transport_codec={name!r}")


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
        transport_codec: str = "pickle",
        logger: logging.Logger | None = None,
        **_unsupported: Any,
    ) -> None:
        if _unsupported:
            unsupported = ", ".join(sorted(_unsupported))
            raise TypeError(f"unsupported async Syndicate option(s): {unsupported}")
        if backend not in _BACKEND_DEFAULT_EXECUTION:
            raise UnsupportedBackendError(f"unsupported backend={backend!r}")
        self.syndicate_id = SyndicateId.from_name(name) if name is not None else SyndicateId()
        self.backend = AsyncInProcessBackend(
            self.syndicate_id,
            default_execution=_BACKEND_DEFAULT_EXECUTION[backend],
            backend_type=_BACKEND_TYPE[backend],
        )
        self.address = self.backend.address
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._owner_thread_id: int | None = None
        if remote_transport not in {"tcp", "websocket"}:
            raise UnsupportedBackendError(f"unsupported remote_transport={remote_transport!r}")
        codec = _make_transport_codec(transport_codec)
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
        self._logger = logger if logger is not None else logging.getLogger(_DEFAULT_LOGGER_NAME)
        self.name_registry = LocalNameRegistry()
        self.placement = LocalFirstPlacementStrategy(self.syndicate_id)
        self.artifact_provider = PackageArtifactProvider()
        self.diagnostics_service = DiagnosticsService()
        self.membership = StaticMembershipProvider([
            SystemDescriptor(
                syndicate_id=self.syndicate_id,
                address=self.address,
                remote_address=self.remote_address,
                capabilities={"backend": _BACKEND_TYPE[backend]},
                tags=frozenset({"local"}),
            )
        ])

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

    async def _start_local(self) -> None:
        if self._started:
            return
        await self.backend.start()
        if self._transport is not None:
            await self._transport.start()
            self.backend.set_remote_sender(self._transport.send)
        self._started = True

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a top-level actor."""
        return await self._run_on_owner_loop(lambda: self._create_actor_local(actor_class, *args, **kwargs))

    async def _create_actor_local(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        await self._start_local()
        return await self.backend.create_actor(actor_class, *args, **kwargs)

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        """Create a top-level actor from an explicit actor specification."""
        return await self._run_on_owner_loop(lambda: self._create_actor_from_spec_local(spec))

    async def _create_actor_from_spec_local(self, spec: ActorSpec) -> ActorAddress:
        await self._start_local()
        return await self.backend.create_actor_from_spec(spec)

    async def start_actor(self, actor: Actor) -> ActorAddress:
        """Start an existing top-level actor instance."""
        return await self._run_on_owner_loop(lambda: self._start_actor_local(actor))

    async def _start_actor_local(self, actor: Actor) -> ActorAddress:
        await self._start_local()
        return await self.backend.start_actor(actor)

    async def tell(self, target: ActorAddress | Any = _MISSING, message: Any = _MISSING) -> DeliveryResult:
        """Send a fire-and-forget message."""
        if message is _MISSING:
            if target is _MISSING:
                raise TypeError("tell() missing message")
            return await _global_tell(target)
        if target is _MISSING or target is None:
            return await _global_tell(message)
        return await self._tell_to_address(target, message)

    async def _tell_to_address(self, target: ActorAddress, message: Any) -> DeliveryResult:
        return await self._run_on_owner_loop(lambda: self._tell_local(target, message))

    async def _tell_local(self, target: ActorAddress, message: Any) -> DeliveryResult:
        await self._start_local()
        return await self.backend.tell(target, message)

    async def ask(
        self,
        target: ActorAddress | Any = _MISSING,
        message: Any = _MISSING,
        timeout: float | None = 5.0,
    ) -> Any:
        """Send a message and await the first reply."""
        if message is _MISSING:
            if target is _MISSING:
                raise TypeError("ask() missing message")
            return await _global_ask(target, timeout)
        if target is _MISSING or target is None:
            return await _global_ask(message, timeout)
        return await self._ask_address(target, message, timeout)

    async def _ask_address(self, target: ActorAddress, message: Any, timeout: float | None = 5.0) -> Any:
        return await self._run_on_owner_loop(lambda: self._ask_local(target, message, timeout))

    async def _ask_local(self, target: ActorAddress, message: Any, timeout: float | None = 5.0) -> Any:
        await self._start_local()
        return await self.backend.ask(target, message, timeout=timeout)

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

    async def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        """Add a system-level host:port route to a peer actor system."""
        await self._run_on_owner_loop(lambda: self._connect_local(syndicate_id, host, port))

    async def _connect_local(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        await self._start_local()
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        self._transport.connect(syndicate_id, host, port)

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

    async def connect_relay(self, uri: str) -> None:
        """Connect this actor system to a websocket relay."""
        await self._run_on_owner_loop(lambda: self._connect_relay_local(uri))

    async def _connect_relay_local(self, uri: str) -> None:
        await self._start_local()
        if self._transport is None:
            raise UnsupportedBackendError("remote transport is not enabled")
        connect_relay = getattr(self._transport, "connect_relay", None)
        if connect_relay is None:
            raise UnsupportedBackendError("remote transport does not support websocket relays")
        await connect_relay(uri)

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
    transport_codec: str = "pickle",
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
