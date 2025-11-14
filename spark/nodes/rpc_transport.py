"""
Transport helpers for talking to remote JSON-RPC 2.0 services.

These transports are the building blocks for bridging a local Spark graph to
remote RpcNode instances over HTTP or WebSocket connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
import ssl
from itertools import count
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING, Union

import aiohttp
from aiohttp import ClientError, ClientSession, ClientTimeout
import websockets
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol
else:  # pragma: no cover - typing aid
    WebSocketClientProtocol = Any

JsonObject = Dict[str, Any]
JsonRpcPayload = Union[JsonObject, List[JsonObject]]
JsonRpcResponse = Union[JsonObject, List[JsonObject], None]
NotificationHandler = Callable[[JsonObject], Union[Awaitable[None], None]]

logger = logging.getLogger(__name__)


class JsonRpcTransportError(RuntimeError):
    """Base error for JSON-RPC transport failures."""


class JsonRpcTimeoutError(JsonRpcTransportError):
    """Raised when a request exceeds its timeout."""


class JsonRpcConnectionError(JsonRpcTransportError):
    """Raised when a transport cannot reach the remote server."""


class JsonRpcProtocolError(JsonRpcTransportError):
    """Raised when the remote server returns an invalid JSON-RPC payload."""


class JsonRpcTransport(Protocol):
    """Protocol implemented by JSON-RPC transports."""

    async def connect(self) -> None: ...

    async def close(self) -> None: ...

    async def request(self, payload: JsonRpcPayload, *, timeout: float | None = None) -> JsonRpcResponse: ...

    async def notify(self, payload: JsonRpcPayload) -> None: ...

    def register_notification_handler(self, handler: NotificationHandler) -> Callable[[], None]: ...

    def is_connected(self) -> bool: ...


class _NotificationMixin:
    """Provides notification handler registration helpers."""

    def __init__(self) -> None:
        self._notification_handlers: list[NotificationHandler] = []

    def register_notification_handler(self, handler: NotificationHandler) -> Callable[[], None]:
        """Register a callback invoked for server-side notifications."""

        self._notification_handlers.append(handler)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._notification_handlers.remove(handler)

        return _remove

    async def _emit_notification(self, message: JsonObject) -> None:
        """Send a notification to all registered handlers."""

        if not self._notification_handlers:
            return

        for handler in list(self._notification_handlers):
            try:
                result = handler(message)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("JSON-RPC notification handler failed")


class HttpJsonRpcTransport(_NotificationMixin):
    """
    JSON-RPC transport over HTTP POST requests.

    Suitable for synchronous request/response flows and notifications that do
    not require server push.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = 30.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        session: Optional[ClientSession] = None,
    ) -> None:
        super().__init__()
        self._endpoint = endpoint
        self._default_timeout = timeout
        self._headers = headers or {}
        self._ssl_context = ssl_context
        self._session = session
        self._owns_session = session is None

    async def connect(self) -> None:
        """Ensure an aiohttp session exists."""

        await self._ensure_session()

    def is_connected(self) -> bool:
        return self._session is not None and not self._session.closed

    async def close(self) -> None:
        """Close the underlying HTTP session."""

        if self._session and self._owns_session:
            await self._session.close()
        self._session = None

    async def request(self, payload: JsonRpcPayload, *, timeout: float | None = None) -> JsonRpcResponse:
        """Send a JSON-RPC request and return the decoded response."""

        return await self._post(payload, expect_response=True, timeout=timeout)

    async def notify(self, payload: JsonRpcPayload) -> None:
        """Send a JSON-RPC notification (fire-and-forget)."""

        await self._post(payload, expect_response=False)

    async def _post(
        self,
        payload: JsonRpcPayload,
        *,
        expect_response: bool,
        timeout: float | None = None,
    ) -> JsonRpcResponse:
        session = await self._ensure_session()
        effective_timeout = timeout if timeout is not None else self._default_timeout
        request_timeout = ClientTimeout(total=effective_timeout) if effective_timeout else None

        try:
            async with session.post(
                self._endpoint,
                json=payload,
                ssl=self._ssl_context,
                timeout=request_timeout,
                headers=self._headers or None,
            ) as response:
                if not expect_response:
                    await response.read()
                    return None

                if response.status == 204:
                    return None

                try:
                    return await response.json()
                except aiohttp.ContentTypeError as exc:
                    text = await response.text()
                    raise JsonRpcProtocolError(
                        f"Invalid JSON returned from {self._endpoint}: {text[:200]}"
                    ) from exc

        except asyncio.TimeoutError as exc:
            raise JsonRpcTimeoutError(f"HTTP JSON-RPC request timed out for {self._endpoint}") from exc
        except ClientError as exc:
            raise JsonRpcConnectionError(f"HTTP JSON-RPC request failed: {exc}") from exc

    async def _ensure_session(self) -> ClientSession:
        """Create a ClientSession when needed."""

        if self._session and not self._session.closed:
            return self._session

        if self._session and self._session.closed:
            if not self._owns_session:
                raise JsonRpcConnectionError("Provided aiohttp session is closed")
            self._session = None

        if self._session is None:
            timeout_cfg = ClientTimeout(total=self._default_timeout) if self._default_timeout else None
            self._session = ClientSession(timeout=timeout_cfg, headers=self._headers or None)

        return self._session


class WebSocketJsonRpcTransport(_NotificationMixin):
    """
    JSON-RPC transport over a persistent WebSocket connection.

    Supports bidirectional messaging so the remote server can push notifications
    that are forwarded to registered handlers.
    """

    def __init__(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        connect_timeout: float = 10.0,
        request_timeout: Optional[float] = 30.0,
        ping_interval: Optional[float] = None,
    ) -> None:
        super().__init__()
        self._url = url
        self._headers = headers or {}
        self._ssl_context = ssl_context
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout
        self._ping_interval = ping_interval

        self._ws: WebSocketClientProtocol | None = None
        self._receiver_task: asyncio.Task | None = None
        self._pending: dict[Any, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._closed = False
        self._id_sequence = count(1)

    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """Connect to the remote WebSocket endpoint."""

        if self.is_connected():
            return

        async with self._connect_lock:
            if self.is_connected():
                return

            try:
                self._ws = await websockets.connect(
                    self._url,
                    extra_headers=self._headers,
                    ssl=self._ssl_context,
                    open_timeout=self._connect_timeout,
                    ping_interval=self._ping_interval,
                )
                self._closed = False
            except Exception as exc:  # pragma: no cover - websockets raises different errors per platform
                raise JsonRpcConnectionError(f"Failed to open WebSocket to {self._url}: {exc}") from exc

            self._receiver_task = asyncio.create_task(self._receive_loop())

    async def close(self) -> None:
        """Close the WebSocket connection and cancel background tasks."""

        self._closed = True

        if self._receiver_task:
            self._receiver_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receiver_task
            self._receiver_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        await self._fail_pending(JsonRpcConnectionError("WebSocket transport closed"))

    async def request(self, payload: JsonRpcPayload, *, timeout: float | None = None) -> JsonRpcResponse:
        """Send a JSON-RPC request over WebSocket."""

        if isinstance(payload, list):
            raise ValueError("Batch JSON-RPC requests are not supported over WebSocket transport")

        await self.connect()
        assert self._ws is not None

        payload = dict(payload)
        request_id = payload.get("id")
        if request_id is None:
            request_id = next(self._id_sequence)
            payload["id"] = request_id

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        await self._send(payload)

        effective_timeout = timeout if timeout is not None else self._request_timeout
        try:
            if effective_timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout=effective_timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise JsonRpcTimeoutError(f"WebSocket JSON-RPC request timed out ({request_id})") from exc

    async def notify(self, payload: JsonRpcPayload) -> None:
        """Send a notification over the WebSocket connection."""

        await self.connect()
        await self._send(payload)

    async def _receive_loop(self) -> None:
        """Background task that routes responses/notifications."""

        assert self._ws is not None
        websocket = self._ws
        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Received invalid JSON over WebSocket: %s", raw)
                    continue

                await self._handle_message(message)
        except ConnectionClosed:
            logger.debug("WebSocket connection closed for %s", self._url)
        except Exception:
            logger.exception("Unexpected error in WebSocket receive loop")
        finally:
            if not self._closed:
                await self._fail_pending(
                    JsonRpcConnectionError(f"WebSocket connection lost for {self._url}")
                )
            self._ws = None

    async def _handle_message(self, message: Any) -> None:
        """Route a decoded message to pending requests or notification handlers."""

        if isinstance(message, list):
            for item in message:
                await self._handle_message(item)
            return

        if not isinstance(message, dict):
            logger.debug("Ignoring non-object WebSocket payload: %s", message)
            return

        message_id = message.get("id")
        if message_id is not None and message_id in self._pending:
            future = self._pending.pop(message_id)
            if not future.done():
                future.set_result(message)
            return

        await self._emit_notification(message)

    async def _send(self, payload: JsonRpcPayload) -> None:
        """Serialize and send payload across the WebSocket."""

        if not self.is_connected():
            raise JsonRpcConnectionError("WebSocket connection is not open")

        data = json.dumps(payload)
        async with self._send_lock:
            assert self._ws is not None
            await self._ws.send(data)

    async def _fail_pending(self, error: Exception) -> None:
        """Fail any pending requests with the provided error."""

        futures = list(self._pending.values())
        self._pending.clear()
        for future in futures:
            if not future.done():
                future.set_exception(error)
