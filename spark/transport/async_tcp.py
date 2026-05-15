"""Asyncio TCP transport for Spark envelopes."""

from __future__ import annotations

import asyncio
import contextlib
import struct
from collections.abc import Awaitable, Callable

from ..core.identity import Envelope, SyndicateId
from ..runtime.results import DeliveryResult
from .codec import CodecError, EnvelopeCodec, PickleEnvelopeCodec

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_SIZE = 64 * 1024 * 1024


class AsyncTcpTransport:
    """System-level TCP transport implemented with asyncio streams."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        host: str,
        port: int,
        on_envelope: Callable[[Envelope], Awaitable[None]],
        codec: EnvelopeCodec | None = None,
    ) -> None:
        self.syndicate_id = syndicate_id
        self._host = host
        self._port = port
        self._on_envelope = on_envelope
        self._codec = codec or PickleEnvelopeCodec()
        self._routes: dict[SyndicateId, tuple[str, int]] = {}
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
        self._routes[syndicate_id] = (host, port)

    async def send(self, envelope: Envelope) -> DeliveryResult:
        route = self._routes.get(envelope.target.syndicate_id)
        if route is None:
            return DeliveryResult(success=False, reason="remote route not found")
        return await self.send_to(envelope, *route)

    async def send_to(self, envelope: Envelope, host: str, port: int) -> DeliveryResult:
        if self._server is None:
            return DeliveryResult(success=False, reason="transport is not started")
        try:
            reader, writer = await asyncio.open_connection(host, port)
            del reader
            payload = self._codec.encode(envelope)
            writer.write(_FRAME_HEADER.pack(len(payload)))
            writer.write(payload)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except OSError as exc:
            return DeliveryResult(success=False, reason=f"remote send failed: {exc}")
        except CodecError as exc:
            return DeliveryResult(success=False, reason=f"remote encode failed: {exc}")
        return DeliveryResult(success=True)

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            header = await reader.readexactly(_FRAME_HEADER.size)
            size = _FRAME_HEADER.unpack(header)[0]
            if size > _MAX_FRAME_SIZE:
                return
            payload = await reader.readexactly(size)
            envelope = self._codec.decode(payload)
            await self._on_envelope(envelope)
        except (asyncio.IncompleteReadError, OSError, CodecError):
            return
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
