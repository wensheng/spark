"""Asyncio TCP transport for Spark envelopes."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import secrets
import socket
import struct
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..core.identity import Envelope, SyndicateId
from ..runtime.results import DeliveryResult
from .codec import CodecError, EnvelopeCodec, PickleEnvelopeCodec

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_SIZE = 64 * 1024 * 1024
_HANDSHAKE_VERSION = 1
_SIGNATURE_SIZE = 32
_COUNTER = struct.Struct("!Q")


@dataclass(slots=True)
class _TcpClientConnection:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    frame_counter: int = 0
    peer_id: SyndicateId | None = None


@dataclass(slots=True)
class _TcpRoute:
    host: str
    port: int
    connection: _TcpClientConnection | None = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state: str = "disconnected"
    frames_sent: int = 0
    frames_received: int = 0
    connections_opened: int = 0
    last_success: float | None = None
    last_failure: str | None = None
    reconnect_attempts: int = 0
    next_connect_at: float = 0.0


class AsyncTcpTransport:
    """System-level TCP transport implemented with asyncio streams."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        host: str,
        port: int,
        on_envelope: Callable[[Envelope], Awaitable[None]],
        codec: EnvelopeCodec | None = None,
        *,
        codec_name: str = "trusted-pickle",
        shared_secret: str | bytes | None = None,
        connect_timeout: float = 5.0,
        frame_timeout: float = 5.0,
        idle_timeout: float | None = 30.0,
        replay_cache_size: int = 1024,
    ) -> None:
        self.syndicate_id = syndicate_id
        self._host = host
        self._port = port
        self._on_envelope = on_envelope
        self._codec = codec or PickleEnvelopeCodec()
        self._codec_name = codec_name
        self._shared_secret = shared_secret.encode() if isinstance(shared_secret, str) else shared_secret
        self._connect_timeout = connect_timeout
        self._frame_timeout = frame_timeout
        self._idle_timeout = idle_timeout
        self._replay_cache_size = replay_cache_size
        self._routes: dict[SyndicateId, _TcpRoute] = {}
        self._recent_messages: dict[SyndicateId, OrderedDict[str, None]] = {}
        self._inbound_writers: set[asyncio.StreamWriter] = set()
        self._server: asyncio.AbstractServer | None = None
        self.address: tuple[str, int] | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_connection, self._host, self._port)
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self.address = (str(host), int(port))

    def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        self._routes[syndicate_id] = _TcpRoute(host, port)

    async def send(self, envelope: Envelope) -> DeliveryResult:
        route = self._routes.get(envelope.target.syndicate_id)
        if route is None:
            return DeliveryResult(success=False, reason="remote route not found")
        return await self._send_route(envelope.target.syndicate_id, route, envelope)

    async def send_to(self, envelope: Envelope, host: str, port: int) -> DeliveryResult:
        return await self._send_route(envelope.target.syndicate_id, _TcpRoute(host, port), envelope)

    async def _send_route(self, syndicate_id: SyndicateId, route: _TcpRoute, envelope: Envelope) -> DeliveryResult:
        if self._server is None:
            return DeliveryResult(success=False, reason="transport is not started")
        async with route.send_lock:
            try:
                connection = await self._ensure_connection(syndicate_id, route)
                payload = self._codec.encode(envelope)
                connection.frame_counter += 1
                await self._write_frame(
                    connection.writer,
                    self._secure_payload(payload, connection.frame_counter),
                )
                await asyncio.wait_for(connection.writer.drain(), timeout=self._frame_timeout)
                route.frames_sent += 1
                route.state = "connected"
                route.last_success = time.time()
                route.last_failure = None
            except OSError as exc:
                await self._record_send_failure(route, str(exc), state="disconnected")
                return DeliveryResult(success=False, reason=f"remote send failed: {exc}")
            except TimeoutError as exc:
                await self._record_send_failure(route, "remote send timed out")
                return DeliveryResult(success=False, reason=f"remote send failed: {exc}")
            except CodecError as exc:
                route.state = "degraded"
                route.last_failure = str(exc)
                return DeliveryResult(success=False, reason=f"remote encode failed: {exc}")
            except ValueError as exc:
                await self._record_send_failure(route, str(exc))
                return DeliveryResult(success=False, reason=f"remote send failed: {exc}")
        return DeliveryResult(success=True)

    async def close(self) -> None:
        for route in self._routes.values():
            await self._drop_route_connection(route)
        for writer in tuple(self._inbound_writers):
            writer.close()
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    def route_health(self) -> dict[str, dict[str, object]]:
        return {
            route_id.uuid: {
                "state": route.state,
                "host": route.host,
                "port": route.port,
                "frames_sent": route.frames_sent,
                "frames_received": route.frames_received,
                "connections_opened": route.connections_opened,
                "last_success": route.last_success,
                "last_failure": route.last_failure,
                "reconnect_attempts": route.reconnect_attempts,
                "next_connect_at": route.next_connect_at,
            }
            for route_id, route in self._routes.items()
        }

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        frames_received = 0
        self._inbound_writers.add(writer)
        try:
            handshake_payload = await self._read_frame(reader)
            if handshake_payload is None:
                return
            peer_id = self._validate_handshake(handshake_payload)
            await self._write_frame(writer, self._handshake_payload())
            await asyncio.wait_for(writer.drain(), timeout=self._frame_timeout)
            expected_counter = 1
            while True:
                payload = await self._read_frame(reader, header_timeout=self._idle_timeout)
                if payload is None:
                    return
                payload = self._verify_payload(payload, expected_counter)
                expected_counter += 1
                envelope = self._codec.decode(payload)
                if envelope.sender is not None and envelope.sender.syndicate_id != peer_id:
                    raise ValueError("transport envelope sender does not match connection identity")
                if self._is_replayed_message(peer_id, envelope.message_id):
                    continue
                frames_received += 1
                route = self._routes.get(peer_id)
                if route is not None:
                    route.frames_received += 1
                    route.last_success = time.time()
                    route.last_failure = None
                await self._on_envelope(envelope)
        except (asyncio.IncompleteReadError, OSError, CodecError, TimeoutError, ValueError):
            return
        finally:
            self._inbound_writers.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _ensure_connection(self, syndicate_id: SyndicateId, route: _TcpRoute) -> _TcpClientConnection:
        if route.connection is not None and not route.connection.writer.is_closing():
            if self._idle_timeout is not None and route.last_success is not None:
                if time.time() - route.last_success >= self._idle_timeout:
                    await self._drop_route_connection(route)
                else:
                    return route.connection
            else:
                return route.connection
        now = time.time()
        if route.next_connect_at > now:
            await asyncio.sleep(route.next_connect_at - now)
        if route.connection is not None and not route.connection.writer.is_closing():
            return route.connection
        route.reconnect_attempts += 1
        route.state = "degraded"
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(route.host, route.port),
            timeout=self._connect_timeout,
        )
        self._enable_keepalive(writer)
        await self._write_frame(writer, self._handshake_payload())
        await asyncio.wait_for(writer.drain(), timeout=self._frame_timeout)
        handshake_payload = await self._read_frame(reader)
        if handshake_payload is None:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            raise ValueError("transport handshake was not acknowledged")
        peer_id = self._validate_handshake(handshake_payload, expected_syndicate_id=syndicate_id)
        route.connection = _TcpClientConnection(reader=reader, writer=writer, peer_id=peer_id)
        route.connections_opened += 1
        route.state = "connected"
        return route.connection

    async def _record_send_failure(self, route: _TcpRoute, reason: str, *, state: str = "degraded") -> None:
        await self._drop_route_connection(route)
        route.state = state
        route.last_failure = reason
        route.next_connect_at = time.time() + self._next_backoff(route.reconnect_attempts)

    def _next_backoff(self, attempts: int) -> float:
        base = min(2.0, float(0.05 * (2 ** max(0, attempts - 1))))
        jitter = float(secrets.randbelow(50)) / 1000.0
        return float(base + jitter)

    async def _drop_route_connection(self, route: _TcpRoute) -> None:
        connection = route.connection
        route.connection = None
        if connection is None:
            return
        connection.writer.close()
        with contextlib.suppress(Exception):
            await connection.writer.wait_closed()

    def _enable_keepalive(self, writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        if sock is None:
            return
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    async def _write_frame(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        writer.write(_FRAME_HEADER.pack(len(payload)))
        writer.write(payload)

    async def _read_frame(
        self,
        reader: asyncio.StreamReader,
        *,
        header_timeout: float | None = None,
    ) -> bytes | None:
        try:
            header = await self._read_exactly(reader, _FRAME_HEADER.size, header_timeout or self._frame_timeout)
        except asyncio.IncompleteReadError:
            return None
        size = _FRAME_HEADER.unpack(header)[0]
        if size > _MAX_FRAME_SIZE:
            raise ValueError("transport frame exceeds maximum size")
        return await self._read_exactly(reader, size, self._frame_timeout)

    async def _read_exactly(
        self,
        reader: asyncio.StreamReader,
        size: int,
        timeout: float | None,
    ) -> bytes:
        if timeout is None:
            return await reader.readexactly(size)
        return await asyncio.wait_for(reader.readexactly(size), timeout=timeout)

    def _handshake_payload(self) -> bytes:
        nonce = secrets.token_hex(16)
        system_id = self.syndicate_id.uuid
        codec_name = self._codec_name
        body = {
            "version": _HANDSHAKE_VERSION,
            "system_id": system_id,
            "codec": codec_name,
            "auth": "hmac-sha256" if self._shared_secret is not None else "none",
            "nonce": nonce,
            "capabilities": {
                "frame_integrity": self._shared_secret is not None,
                "persistent_connections": True,
            },
        }
        if self._shared_secret is not None:
            body["signature"] = self._handshake_signature(system_id, codec_name, nonce)
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    def _validate_handshake(
        self,
        payload: bytes,
        *,
        expected_syndicate_id: SyndicateId | None = None,
    ) -> SyndicateId:
        try:
            body = json.loads(payload.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid transport handshake: {exc}") from exc
        if body.get("version") != _HANDSHAKE_VERSION:
            raise ValueError("unsupported transport handshake version")
        if body.get("codec") != self._codec_name:
            raise ValueError("transport codec mismatch")
        system_id = body.get("system_id")
        if not isinstance(system_id, str) or not system_id:
            raise ValueError("transport handshake is missing system id")
        peer_id = SyndicateId(system_id)
        if expected_syndicate_id is not None and peer_id != expected_syndicate_id:
            raise ValueError("transport handshake system id mismatch")
        auth = body.get("auth")
        if self._shared_secret is None:
            if auth != "none":
                raise ValueError("unexpected authenticated transport handshake")
            return peer_id
        if auth != "hmac-sha256":
            raise ValueError("authenticated transport handshake required")
        expected = self._handshake_signature(system_id, str(body.get("codec")), str(body.get("nonce")))
        if not hmac.compare_digest(str(body.get("signature")), expected):
            raise ValueError("transport handshake signature mismatch")
        return peer_id

    def _handshake_signature(self, system_id: str, codec_name: str, nonce: str) -> str:
        assert self._shared_secret is not None
        message = f"{_HANDSHAKE_VERSION}:{system_id}:{codec_name}:{nonce}".encode()
        return hmac.new(self._shared_secret, message, hashlib.sha256).hexdigest()

    def _secure_payload(self, payload: bytes, counter: int) -> bytes:
        if self._shared_secret is None:
            return payload
        counter_bytes = _COUNTER.pack(counter)
        signature = hmac.new(self._shared_secret, counter_bytes + payload, hashlib.sha256).digest()
        return counter_bytes + signature + payload

    def _verify_payload(self, payload: bytes, expected_counter: int) -> bytes:
        if self._shared_secret is None:
            return payload
        if len(payload) < _COUNTER.size + _SIGNATURE_SIZE:
            raise ValueError("authenticated transport frame is too short")
        counter = _COUNTER.unpack(payload[: _COUNTER.size])[0]
        if counter != expected_counter:
            raise ValueError("transport frame counter mismatch")
        signature = payload[_COUNTER.size : _COUNTER.size + _SIGNATURE_SIZE]
        body = payload[_COUNTER.size + _SIGNATURE_SIZE :]
        expected = hmac.new(self._shared_secret, payload[: _COUNTER.size] + body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("transport frame signature mismatch")
        return body

    def _is_replayed_message(self, peer_id: SyndicateId, message_id: str) -> bool:
        if self._replay_cache_size <= 0:
            return False
        recent = self._recent_messages.setdefault(peer_id, OrderedDict())
        if message_id in recent:
            return True
        recent[message_id] = None
        while len(recent) > self._replay_cache_size:
            recent.popitem(last=False)
        return False
