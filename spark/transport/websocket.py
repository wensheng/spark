"""Asyncio WebSocket transport for Spark envelopes."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import hmac
import importlib
import json
import os
import struct
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import urlparse

from ..core.identity import Envelope, SyndicateId
from ..runtime.results import DeliveryResult
from .codec import CodecError, EnvelopeCodec, PickleEnvelopeCodec

_FRAME_MAGIC = b"SPRKWS1"
_HEADER_SIZE = struct.Struct("!I")
_MAX_FRAME_SIZE = 64 * 1024 * 1024
_RELAY_ACK_TIMEOUT = 2.0
_WEBSOCKET_SCHEMES = frozenset({"ws", "wss"})
_INSTALL_MESSAGE = "websocket transport requires the optional 'websockets' dependency; install spark-actor[websocket]"


class WebSocketDependencyError(ImportError):
    """Raised when websocket support is used without the optional dependency."""


@dataclass(frozen=True, slots=True)
class _WebSocketsApi:
    connect: Callable[..., Any]
    serve: Callable[..., Any]
    connection_closed: type[BaseException]


_WEBSOCKETS_API: _WebSocketsApi | None = None


def _load_websockets() -> _WebSocketsApi:
    global _WEBSOCKETS_API
    if _WEBSOCKETS_API is not None:
        return _WEBSOCKETS_API
    try:
        client_module = cast(Any, importlib.import_module("websockets.asyncio.client"))
        server_module = cast(Any, importlib.import_module("websockets.asyncio.server"))
        exceptions_module = cast(Any, importlib.import_module("websockets.exceptions"))
    except ImportError as exc:
        raise WebSocketDependencyError(_INSTALL_MESSAGE) from exc

    _WEBSOCKETS_API = _WebSocketsApi(
        connect=cast(Callable[..., Any], client_module.connect),
        serve=cast(Callable[..., Any], server_module.serve),
        connection_closed=cast(type[BaseException], exceptions_module.ConnectionClosed),
    )
    return _WEBSOCKETS_API


@dataclass(frozen=True, slots=True)
class WebSocketTransportFrame:
    """One Spark websocket control or envelope frame."""

    kind: str
    source_syndicate_id: SyndicateId
    target_syndicate_id: SyndicateId | None = None
    payload: bytes = b""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reason: str | None = None
    auth: str | None = None


def encode_websocket_frame(frame: WebSocketTransportFrame) -> bytes:
    """Encode a websocket frame with JSON routing metadata and a binary payload."""
    metadata = {
        "version": 1,
        "kind": frame.kind,
        "source": frame.source_syndicate_id.uuid,
        "target": None if frame.target_syndicate_id is None else frame.target_syndicate_id.uuid,
        "frame_id": frame.frame_id,
        "reason": frame.reason,
        "auth": frame.auth,
    }
    header = json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode("utf-8")
    size = len(_FRAME_MAGIC) + _HEADER_SIZE.size + len(header) + len(frame.payload)
    if size > _MAX_FRAME_SIZE:
        raise CodecError("websocket frame is too large")
    return _FRAME_MAGIC + _HEADER_SIZE.pack(len(header)) + header + frame.payload


def decode_websocket_frame(message: object) -> WebSocketTransportFrame:
    """Decode a Spark websocket frame without decoding the envelope payload."""
    if not isinstance(message, bytes | bytearray | memoryview):
        raise CodecError("websocket frame must be binary")
    data = bytes(message)
    prefix_size = len(_FRAME_MAGIC) + _HEADER_SIZE.size
    if len(data) < prefix_size:
        raise CodecError("websocket frame is too short")
    if not data.startswith(_FRAME_MAGIC):
        raise CodecError("websocket frame has invalid magic")

    header_offset = len(_FRAME_MAGIC)
    header_size = _HEADER_SIZE.unpack(data[header_offset : header_offset + _HEADER_SIZE.size])[0]
    payload_offset = prefix_size + header_size
    if payload_offset > len(data):
        raise CodecError("websocket frame header is incomplete")
    if len(data) > _MAX_FRAME_SIZE:
        raise CodecError("websocket frame is too large")

    try:
        metadata = json.loads(data[prefix_size:payload_offset])
    except json.JSONDecodeError as exc:
        raise CodecError(f"websocket frame metadata is invalid JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise CodecError("websocket frame metadata must be an object")
    if metadata.get("version") != 1:
        raise CodecError("unsupported websocket frame version")

    kind = metadata.get("kind")
    if kind not in {"register", "envelope", "ack", "nack"}:
        raise CodecError("unsupported websocket frame kind")
    source = _syndicate_id_from_metadata(metadata, "source")
    if source is None:
        raise CodecError("websocket frame requires a source system id")
    target = _syndicate_id_from_metadata(metadata, "target", required=False)
    frame_id = metadata.get("frame_id")
    reason = metadata.get("reason")
    auth = metadata.get("auth")
    if not isinstance(frame_id, str) or not frame_id:
        raise CodecError("websocket frame requires a frame_id")
    if reason is not None and not isinstance(reason, str):
        raise CodecError("websocket frame reason must be a string")
    if auth is not None and not isinstance(auth, str):
        raise CodecError("websocket frame auth must be a string")
    if kind == "envelope" and target is None:
        raise CodecError("websocket envelope frame requires a target")
    return WebSocketTransportFrame(
        kind=kind,
        source_syndicate_id=source,
        target_syndicate_id=target,
        payload=data[payload_offset:],
        frame_id=frame_id,
        reason=reason,
        auth=auth,
    )


def _syndicate_id_from_metadata(metadata: dict[str, Any], key: str, *, required: bool = True) -> SyndicateId | None:
    value = metadata.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise CodecError(f"websocket frame requires a {key} system id")
    return SyndicateId(uuid=value)


def _validate_websocket_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme not in _WEBSOCKET_SCHEMES or not parsed.netloc:
        raise ValueError(f"invalid websocket URI: {uri!r}")
    return uri


def _uri_from_host_port(host: str, port: int) -> str:
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"ws://{display_host}:{port}"


def _is_websocket_send_failure(result: DeliveryResult) -> bool:
    return (
        not result.success and result.reason is not None and result.reason.startswith("remote websocket send failed:")
    )


def _sign_relay_registration(secret: str | bytes, syndicate_id: SyndicateId, frame_id: str) -> str:
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    payload = f"spark-relay-register:{syndicate_id.uuid}:{frame_id}".encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _is_loopback_host(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


@dataclass(slots=True, eq=False)
class _WebSocketConnection:
    websocket: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    peer_syndicate_id: SyndicateId | None = None
    uri: str | None = None
    reader_task: asyncio.Task[None] | None = None
    relay: bool = False


class AsyncWebSocketTransport:
    """System-level websocket transport implemented with asyncio."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        host: str,
        port: int,
        on_envelope: Callable[[Envelope], Awaitable[None]],
        codec: EnvelopeCodec | None = None,
        *,
        relay_ack_timeout: float = _RELAY_ACK_TIMEOUT,
    ) -> None:
        self.syndicate_id = syndicate_id
        self._host = host
        self._port = port
        self._on_envelope = on_envelope
        self._codec = codec or PickleEnvelopeCodec()
        self._routes: dict[SyndicateId, str] = {}
        self._connections: dict[SyndicateId, _WebSocketConnection] = {}
        self._connection_lock = asyncio.Lock()
        self._server: Any | None = None
        self._closed = False
        self._relay_uri: str | None = None
        self._relay_secret: str | bytes | None = None
        self._relay_connection: _WebSocketConnection | None = None
        self._relay_pending: dict[str, asyncio.Future[DeliveryResult]] = {}
        self._relay_ack_timeout = relay_ack_timeout
        self._tasks: set[asyncio.Task[None]] = set()
        self.address: tuple[str, int] | None = None
        self.uri: str | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        api = _load_websockets()
        self._closed = False
        self._server = await api.serve(self._handle_connection, self._host, self._port, max_size=_MAX_FRAME_SIZE)
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self.address = (str(host), int(port))
        self.uri = _uri_from_host_port(self.address[0], self.address[1])

    def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        """Add or replace a direct websocket route to another actor system."""
        self.connect_uri(syndicate_id, _uri_from_host_port(host, port))

    def connect_uri(self, syndicate_id: SyndicateId, uri: str) -> None:
        """Add or replace a direct websocket URI route."""
        self._routes[syndicate_id] = _validate_websocket_uri(uri)

    async def connect_relay(self, uri: str, *, secret: str | bytes | None = None) -> None:
        """Connect this system to a websocket relay."""
        self._relay_uri = _validate_websocket_uri(uri)
        self._relay_secret = secret
        await self._ensure_relay_connection()

    async def send(self, envelope: Envelope) -> DeliveryResult:
        if self._server is None:
            return DeliveryResult(success=False, reason="transport is not started")
        target_syndicate_id = envelope.target.syndicate_id

        direct_connection = self._connections.get(target_syndicate_id)
        if direct_connection is not None:
            result = await self._send_envelope_on_connection(direct_connection, envelope, wait_for_relay_ack=False)
            if result.success:
                return result

        route = self._routes.get(target_syndicate_id)
        if route is not None:
            try:
                connection = await self._ensure_direct_connection(target_syndicate_id, route)
            except Exception as exc:  # noqa: BLE001
                return DeliveryResult(success=False, reason=f"remote websocket send failed: {exc}")
            return await self._send_envelope_on_connection(connection, envelope, wait_for_relay_ack=False)

        if self._relay_uri is not None:
            try:
                relay = await self._ensure_relay_connection()
            except Exception as exc:  # noqa: BLE001
                return DeliveryResult(success=False, reason=f"relay websocket send failed: {exc}")
            result = await self._send_envelope_on_connection(relay, envelope, wait_for_relay_ack=True)
            if not _is_websocket_send_failure(result):
                return result
            try:
                relay = await self._ensure_relay_connection()
            except Exception as exc:  # noqa: BLE001
                return DeliveryResult(success=False, reason=f"relay websocket send failed: {exc}")
            return await self._send_envelope_on_connection(relay, envelope, wait_for_relay_ack=True)

        return DeliveryResult(success=False, reason="remote route not found")

    async def send_to(self, envelope: Envelope, host: str, port: int) -> DeliveryResult:
        if self._server is None:
            return DeliveryResult(success=False, reason="transport is not started")
        try:
            connection = await self._ensure_direct_connection(
                envelope.target.syndicate_id,
                _uri_from_host_port(host, port),
            )
        except Exception as exc:  # noqa: BLE001
            return DeliveryResult(success=False, reason=f"send to {host}:{port} failed: {exc}")
        return await self._send_envelope_on_connection(connection, envelope, wait_for_relay_ack=False)

    async def close(self) -> None:
        self._closed = True
        self._fail_relay_pending("transport is closed")

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        connections = set(self._connections.values())
        if self._relay_connection is not None:
            connections.add(self._relay_connection)
        await asyncio.gather(
            *(self._close_connection(connection) for connection in connections),
            return_exceptions=True,
        )
        self._connections.clear()
        self._relay_connection = None
        self.address = None
        self.uri = None

        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _ensure_direct_connection(self, syndicate_id: SyndicateId, uri: str) -> _WebSocketConnection:
        connection = self._connections.get(syndicate_id)
        if connection is not None:
            return connection
        async with self._connection_lock:
            connection = self._connections.get(syndicate_id)
            if connection is not None:
                return connection
            connection = await self._open_outgoing_connection(uri, peer_syndicate_id=syndicate_id, relay=False)
            self._connections[syndicate_id] = connection
            return connection

    async def _ensure_relay_connection(self) -> _WebSocketConnection:
        async with self._connection_lock:
            relay_connection = self._relay_connection
            if relay_connection is not None:
                return relay_connection
            if self._relay_uri is None:
                raise RuntimeError("relay URI is not configured")
            relay_connection = await self._open_outgoing_connection(
                self._relay_uri,
                peer_syndicate_id=None,
                relay=True,
            )
            self._relay_connection = relay_connection
            return relay_connection

    async def _open_outgoing_connection(
        self,
        uri: str,
        *,
        peer_syndicate_id: SyndicateId | None,
        relay: bool,
    ) -> _WebSocketConnection:
        api = _load_websockets()
        websocket = await api.connect(uri, max_size=_MAX_FRAME_SIZE)
        connection = _WebSocketConnection(
            websocket=websocket, peer_syndicate_id=peer_syndicate_id, uri=uri, relay=relay
        )
        connection.reader_task = self._create_reader_task(connection)
        register_frame = WebSocketTransportFrame(kind="register", source_syndicate_id=self.syndicate_id)
        if relay and self._relay_secret is not None:
            register_frame = WebSocketTransportFrame(
                kind="register",
                source_syndicate_id=self.syndicate_id,
                frame_id=register_frame.frame_id,
                auth=_sign_relay_registration(self._relay_secret, self.syndicate_id, register_frame.frame_id),
            )
        if relay:
            loop = asyncio.get_running_loop()
            pending = loop.create_future()
            self._relay_pending[register_frame.frame_id] = pending
            result = await self._send_frame(connection, register_frame, drop_on_error=True)
            if not result.success:
                self._relay_pending.pop(register_frame.frame_id, None)
                raise OSError(result.reason or "websocket relay registration failed")
            try:
                result = await asyncio.wait_for(pending, timeout=self._relay_ack_timeout)
            except TimeoutError as exc:
                self._relay_pending.pop(register_frame.frame_id, None)
                raise OSError("websocket relay registration timed out") from exc
        else:
            result = await self._send_frame(connection, register_frame, drop_on_error=True)
        if not result.success:
            raise OSError(result.reason or "websocket registration failed")
        return connection

    async def _send_envelope_on_connection(
        self,
        connection: _WebSocketConnection,
        envelope: Envelope,
        *,
        wait_for_relay_ack: bool,
    ) -> DeliveryResult:
        try:
            payload = self._codec.encode(envelope)
        except CodecError as exc:
            return DeliveryResult(success=False, reason=f"remote encode failed: {exc}")
        frame = WebSocketTransportFrame(
            kind="envelope",
            source_syndicate_id=self.syndicate_id,
            target_syndicate_id=envelope.target.syndicate_id,
            payload=payload,
            frame_id=envelope.message_id,
        )
        if not wait_for_relay_ack:
            return await self._send_frame(connection, frame, drop_on_error=True)

        loop = asyncio.get_running_loop()
        pending = loop.create_future()
        self._relay_pending[frame.frame_id] = pending
        result = await self._send_frame(connection, frame, drop_on_error=True)
        if not result.success:
            self._relay_pending.pop(frame.frame_id, None)
            return result
        try:
            return await asyncio.wait_for(pending, timeout=self._relay_ack_timeout)
        except TimeoutError:
            self._relay_pending.pop(frame.frame_id, None)
            return DeliveryResult(success=False, reason="relay acknowledgement timed out")

    async def _send_frame(
        self,
        connection: _WebSocketConnection,
        frame: WebSocketTransportFrame,
        *,
        drop_on_error: bool,
    ) -> DeliveryResult:
        try:
            payload = encode_websocket_frame(frame)
            async with connection.lock:
                await connection.websocket.send(payload)
        except (CodecError, OSError) as exc:
            if drop_on_error:
                await self._drop_connection(connection)
            return DeliveryResult(success=False, reason=f"remote websocket send failed: {exc}")
        except Exception as exc:  # noqa: BLE001
            if drop_on_error:
                await self._drop_connection(connection)
            return DeliveryResult(success=False, reason=f"remote websocket send failed: {exc}")
        return DeliveryResult(success=True)

    async def _handle_connection(self, websocket: Any) -> None:
        connection = _WebSocketConnection(websocket=websocket)
        try:
            await self._read_connection(connection)
        finally:
            await self._forget_connection(connection)

    def _create_reader_task(self, connection: _WebSocketConnection) -> asyncio.Task[None]:
        task = asyncio.create_task(self._read_connection(connection), name="spark-websocket-transport-reader")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _read_connection(self, connection: _WebSocketConnection) -> None:
        api = _load_websockets()
        try:
            async for message in connection.websocket:
                try:
                    frame = decode_websocket_frame(message)
                    await self._handle_frame(connection, frame)
                except CodecError:
                    break
        except api.connection_closed:
            return
        except Exception:  # noqa: BLE001
            return
        finally:
            await self._forget_connection(connection)

    async def _handle_frame(self, connection: _WebSocketConnection, frame: WebSocketTransportFrame) -> None:
        if frame.kind == "register":
            if not connection.relay:
                await self._remember_connection(frame.source_syndicate_id, connection)
            return
        if frame.kind in {"ack", "nack"}:
            self._complete_relay_ack(frame)
            return
        if frame.kind != "envelope":
            return
        if frame.target_syndicate_id != self.syndicate_id:
            return
        if not connection.relay:
            await self._remember_connection(frame.source_syndicate_id, connection)
        envelope = self._codec.decode(frame.payload)
        await self._on_envelope(envelope)

    async def _remember_connection(self, syndicate_id: SyndicateId, connection: _WebSocketConnection) -> None:
        if syndicate_id == self.syndicate_id:
            return
        prior = self._connections.get(syndicate_id)
        if prior is connection:
            return
        self._connections[syndicate_id] = connection
        connection.peer_syndicate_id = syndicate_id
        if prior is not None:
            await self._close_connection(prior)

    def _complete_relay_ack(self, frame: WebSocketTransportFrame) -> None:
        pending = self._relay_pending.pop(frame.frame_id, None)
        if pending is None or pending.done():
            return
        if frame.kind == "ack":
            pending.set_result(DeliveryResult(success=True))
        else:
            pending.set_result(DeliveryResult(success=False, reason=frame.reason or "relay delivery failed"))

    def _fail_relay_pending(self, reason: str) -> None:
        pending = list(self._relay_pending.values())
        self._relay_pending.clear()
        for future in pending:
            if not future.done():
                future.set_result(DeliveryResult(success=False, reason=reason))

    async def _drop_connection(self, connection: _WebSocketConnection) -> None:
        await self._forget_connection(connection)
        await self._close_connection(connection)

    async def _forget_connection(self, connection: _WebSocketConnection) -> None:
        for syndicate_id, current in list(self._connections.items()):
            if current is connection:
                self._connections.pop(syndicate_id, None)
        if self._relay_connection is connection:
            self._relay_connection = None
            self._fail_relay_pending("relay connection closed")

    async def _close_connection(self, connection: _WebSocketConnection) -> None:
        with contextlib.suppress(Exception):
            await connection.websocket.close()
        task = connection.reader_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


@dataclass(slots=True, eq=False)
class _RelayConnection:
    websocket: Any
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    syndicate_id: SyndicateId | None = None


class WebSocketRelay:
    """Small websocket relay that forwards Spark frames by target SyndicateId."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, *, auth_secret: str | bytes | None = None) -> None:
        self._host = host
        self._port = port
        self._auth_secret = auth_secret
        self._server: Any | None = None
        self._connections: dict[SyndicateId, _RelayConnection] = {}
        self._clients: set[_RelayConnection] = set()
        self._relay_syndicate_id = SyndicateId.from_name("spark-websocket-relay")
        self.address: tuple[str, int] | None = None
        self.uri: str | None = None

    @property
    def connected_systems(self) -> tuple[SyndicateId, ...]:
        return tuple(self._connections)

    async def __aenter__(self) -> WebSocketRelay:
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._server is not None:
            return
        api = _load_websockets()
        self._server = await api.serve(self._handle_connection, self._host, self._port, max_size=_MAX_FRAME_SIZE)
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self.address = (str(host), int(port))
        self.uri = _uri_from_host_port(self.address[0], self.address[1])

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        clients = list(self._clients)
        await asyncio.gather(*(self._close_client(client) for client in clients), return_exceptions=True)
        self._clients.clear()
        self._connections.clear()
        self.address = None
        self.uri = None

    async def _handle_connection(self, websocket: Any) -> None:
        client = _RelayConnection(websocket=websocket)
        self._clients.add(client)
        api = _load_websockets()
        try:
            async for message in websocket:
                try:
                    raw = bytes(message) if isinstance(message, bytes | bytearray | memoryview) else message
                    frame = decode_websocket_frame(raw)
                except CodecError:
                    break
                if frame.kind == "register":
                    if not await self._register(frame.source_syndicate_id, client, frame):
                        break
                elif frame.kind == "envelope":
                    await self._forward(frame, client, cast(bytes, raw))
        except api.connection_closed:
            return
        except Exception:  # noqa: BLE001
            return
        finally:
            await self._unregister(client)
            self._clients.discard(client)

    async def _register(
        self,
        syndicate_id: SyndicateId,
        client: _RelayConnection,
        frame: WebSocketTransportFrame,
    ) -> bool:
        if self._auth_secret is not None:
            expected = _sign_relay_registration(self._auth_secret, syndicate_id, frame.frame_id)
            if frame.auth is None or not hmac.compare_digest(expected, frame.auth):
                await self._send_relay_result(client, frame, success=False, reason="relay authentication failed")
                return False
        prior = self._connections.get(syndicate_id)
        if prior is not None and prior is not client:
            await self._close_client(prior)
        client.syndicate_id = syndicate_id
        self._connections[syndicate_id] = client
        await self._send_relay_result(client, frame, success=True)
        return True

    async def _forward(self, frame: WebSocketTransportFrame, source: _RelayConnection, raw: bytes) -> None:
        target_syndicate_id = frame.target_syndicate_id
        target = self._connections.get(target_syndicate_id) if target_syndicate_id is not None else None
        if target is None:
            await self._send_relay_result(source, frame, success=False, reason="relay route not found")
            return
        try:
            async with target.lock:
                await target.websocket.send(raw)
        except Exception as exc:  # noqa: BLE001
            await self._unregister(target)
            await self._send_relay_result(source, frame, success=False, reason=f"relay send failed: {exc}")
            return
        await self._send_relay_result(source, frame, success=True)

    async def _send_relay_result(
        self,
        client: _RelayConnection,
        frame: WebSocketTransportFrame,
        *,
        success: bool,
        reason: str | None = None,
    ) -> None:
        result = WebSocketTransportFrame(
            kind="ack" if success else "nack",
            source_syndicate_id=self._relay_syndicate_id,
            target_syndicate_id=frame.source_syndicate_id,
            frame_id=frame.frame_id,
            reason=reason,
        )
        with contextlib.suppress(Exception):
            async with client.lock:
                await client.websocket.send(encode_websocket_frame(result))

    async def _unregister(self, client: _RelayConnection) -> None:
        for syndicate_id, current in list(self._connections.items()):
            if current is client:
                self._connections.pop(syndicate_id, None)
        client.syndicate_id = None

    async def _close_client(self, client: _RelayConnection) -> None:
        await self._unregister(client)
        with contextlib.suppress(Exception):
            await client.websocket.close()


async def run_websocket_relay(
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    auth_secret: str | bytes | None = None,
) -> None:
    """Run a websocket relay until cancelled."""
    relay = WebSocketRelay(host=host, port=port, auth_secret=auth_secret)
    await relay.start()
    assert relay.uri is not None
    print(f"spark websocket relay listening on {relay.uri}", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await relay.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for ``spark-ws-relay``."""
    parser = argparse.ArgumentParser(description="Run a Spark websocket relay.")
    parser.add_argument("--host", default="127.0.0.1", help="Host/interface to bind.")
    parser.add_argument("--port", default=0, type=int, help="Port to bind.")
    parser.add_argument(
        "--auth-secret-env",
        help="Environment variable containing the shared relay registration secret.",
    )
    parser.add_argument(
        "--allow-unauthenticated-local",
        action="store_true",
        help="Allow unauthenticated relay registration for loopback-only local demos.",
    )
    args = parser.parse_args(argv)
    auth_secret = os.environ.get(args.auth_secret_env) if args.auth_secret_env else None
    if auth_secret is None:
        if not args.allow_unauthenticated_local:
            parser.error("set --auth-secret-env or pass --allow-unauthenticated-local for a loopback demo")
        if not _is_loopback_host(args.host):
            parser.error("--allow-unauthenticated-local is only valid with a loopback host")
    try:
        asyncio.run(run_websocket_relay(host=args.host, port=args.port, auth_secret=auth_secret))
    except KeyboardInterrupt:
        return 0
    return 0
