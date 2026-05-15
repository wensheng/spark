"""System-level TCP transport for envelopes."""

from __future__ import annotations

import socket
import struct
import threading
from collections.abc import Callable

from ..core.identity import Envelope, SyndicateId
from ..runtime.results import DeliveryResult
from .codec import CodecError, EnvelopeCodec, PickleEnvelopeCodec

_FRAME_HEADER = struct.Struct("!I")
_MAX_FRAME_SIZE = 64 * 1024 * 1024


class TcpTransport:
    """Small system-level TCP transport carrying framed envelopes."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        host: str,
        port: int,
        on_envelope: Callable[[Envelope], None],
        codec: EnvelopeCodec | None = None,
    ) -> None:
        self.syndicate_id = syndicate_id
        self._on_envelope = on_envelope
        self._codec = codec or PickleEnvelopeCodec()
        self._routes: dict[SyndicateId, tuple[str, int]] = {}
        self._closed = False
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((host, port))
        self._server.listen()
        self._server.settimeout(0.2)
        bound_host, bound_port = self._server.getsockname()
        self.address = (str(bound_host), int(bound_port))
        self._thread = threading.Thread(
            target=self._accept_loop,
            name=f"spark-tcp-transport-{self.address[1]}",
            daemon=True,
        )
        self._thread.start()

    def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        """Add or replace a route to another actor system."""
        self._routes[syndicate_id] = (host, port)

    def send(self, envelope: Envelope) -> DeliveryResult:
        """Send envelope to its target system route."""
        route = self._routes.get(envelope.target.syndicate_id)
        if route is None:
            return DeliveryResult(success=False, reason="remote route not found")
        try:
            with socket.create_connection(route, timeout=2.0) as sock:
                self._send_frame(sock, self._codec.encode(envelope))
        except OSError as exc:
            return DeliveryResult(success=False, reason=f"remote send failed: {exc}")
        except CodecError as exc:
            return DeliveryResult(success=False, reason=f"remote encode failed: {exc}")
        return DeliveryResult(success=True)

    def send_to(self, envelope: Envelope, host: str, port: int) -> DeliveryResult:
        """Send envelope to an explicit host:port, bypassing the route table.

        Used by the federation provider for initial bootstrap handshake
        when the remote ``SyndicateId`` is not yet known.
        """
        if self._closed:
            return DeliveryResult(success=False, reason="transport is closed")
        try:
            with socket.create_connection((host, port), timeout=2.0) as sock:
                self._send_frame(sock, self._codec.encode(envelope))
        except OSError as exc:
            return DeliveryResult(success=False, reason=f"send to {host}:{port} failed: {exc}")
        except CodecError as exc:
            return DeliveryResult(success=False, reason=f"encode failed: {exc}")
        return DeliveryResult(success=True)

    def close(self) -> None:
        """Close the listener and stop the accept loop."""
        self._closed = True
        try:
            self._server.close()
        finally:
            self._thread.join(timeout=1.0)

    def _accept_loop(self) -> None:
        while not self._closed:
            try:
                conn, _addr = self._server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                name="spark-tcp-connection",
                daemon=True,
            ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            try:
                frame = self._recv_frame(conn)
                envelope = self._codec.decode(frame)
            except (OSError, EOFError, CodecError):
                return
        self._on_envelope(envelope)

    def _send_frame(self, sock: socket.socket, payload: bytes) -> None:
        sock.sendall(_FRAME_HEADER.pack(len(payload)))
        sock.sendall(payload)

    def _recv_frame(self, sock: socket.socket) -> bytes:
        header = self._recv_exact(sock, _FRAME_HEADER.size)
        size = _FRAME_HEADER.unpack(header)[0]
        if size > _MAX_FRAME_SIZE:
            raise EOFError("transport frame is too large")
        return self._recv_exact(sock, size)

    def _recv_exact(self, sock: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise EOFError("connection closed before frame completed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
