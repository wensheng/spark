"""
Channel abstractions for node-to-node delivery.

These classes provide a richer transport than the bare asyncio.Queue
used previously, adding metadata support, instrumentation hooks, and
extension points for alternative backends.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional

AckCallable = Callable[[], Awaitable[None]]
ObserverCallable = Callable[['ChannelMessage', 'BaseChannel', str], None | Awaitable[None]]


class ChannelClosed(Exception):
    """Raised when sending or receiving on a closed channel."""


@dataclass(slots=True)
class ChannelMessage:
    """
    Envelope for channel payloads.

    The payload is the application data. Metadata travels alongside the
    payload to support tracing, routing, and debugging. Callers may
    attach an acknowledgement coroutine via `ack` if downstream
    consumers should trigger side effects after successful processing.
    """

    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    ack: Optional[AckCallable] = None
    is_shutdown: bool = False

    def clone(
        self,
        *,
        payload: Any | None = None,
        metadata: Optional[dict[str, Any]] = None,
        is_shutdown: Optional[bool] = None,
    ) -> 'ChannelMessage':
        """Return a shallow copy of this message with optional overrides."""
        merged_metadata = dict(self.metadata)
        if metadata:
            merged_metadata.update(metadata)
        return ChannelMessage(
            payload=self.payload if payload is None else payload,
            metadata=merged_metadata,
            ack=self.ack,
            is_shutdown=self.is_shutdown if is_shutdown is None else is_shutdown,
        )


class BaseChannel:
    """Interface for asynchronous message channels."""

    def __init__(self, *, name: str | None = None) -> None:
        self._name = name or self.__class__.__name__

    @property
    def name(self) -> str:
        """Return the channel name."""
        return self._name

    async def send(self, message: ChannelMessage) -> None:
        """Asynchronously enqueue a message."""
        raise NotImplementedError

    def send_nowait(self, message: ChannelMessage) -> None:
        """Enqueue a message without blocking."""
        raise NotImplementedError

    async def receive(self) -> ChannelMessage:
        """Asynchronously receive the next message."""
        raise NotImplementedError

    def empty(self) -> bool:
        """Return True if the channel has no pending messages."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the channel."""
        raise NotImplementedError


class InMemoryChannel(BaseChannel):
    """Channel backed by an asyncio.Queue."""

    def __init__(
        self,
        *,
        maxsize: int = 0,
        name: str | None = None,
        observers: Optional[list[ObserverCallable]] = None,
    ) -> None:
        super().__init__(name=name)
        self._queue: asyncio.Queue[ChannelMessage] = asyncio.Queue(maxsize=maxsize)
        self._closed = False
        self._observers: list[ObserverCallable] = observers or []

    async def send(self, message: ChannelMessage) -> None:
        if self._closed:
            raise ChannelClosed(f'Channel {self.name} is closed')
        await self._queue.put(message)
        await self._notify_observers(message, phase='send')

    def send_nowait(self, message: ChannelMessage) -> None:
        if self._closed:
            raise ChannelClosed(f'Channel {self.name} is closed')
        self._queue.put_nowait(message)
        asyncio.create_task(self._notify_observers(message, phase='send'))

    async def receive(self) -> ChannelMessage:
        if self._closed and self._queue.empty():
            raise ChannelClosed(f'Channel {self.name} is closed')
        message = await self._queue.get()
        await self._notify_observers(message, phase='receive')
        return message

    def empty(self) -> bool:
        return self._queue.empty()

    def close(self) -> None:
        self._closed = True

    async def _notify_observers(self, message: ChannelMessage, *, phase: str) -> None:
        if not self._observers:
            return
        for observer in self._observers:
            try:
                maybe_coro = observer(message, self, phase)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:
                # Observers must never crash the channel. Errors can be logged by the observer.
                continue


class ForwardingChannel(BaseChannel):
    """
    Channel wrapper that forwards messages to a downstream channel.

    Used for per-edge instrumentation without needing an intermediate
    consumer task. Metadata can be enriched before forwarding.
    """

    def __init__(
        self,
        downstream: BaseChannel,
        *,
        name: str | None = None,
        metadata_defaults: Optional[dict[str, Any]] = None,
        observers: Optional[list[ObserverCallable]] = None,
    ) -> None:
        super().__init__(name=name)
        self._downstream = downstream
        self._metadata_defaults = metadata_defaults or {}
        self._observers: list[ObserverCallable] = observers or []

    async def send(self, message: ChannelMessage) -> None:
        enriched = self._enrich(message)
        await self._notify_observers(enriched, phase='send')
        await self._downstream.send(enriched)

    def send_nowait(self, message: ChannelMessage) -> None:
        enriched = self._enrich(message)
        asyncio.create_task(self._notify_observers(enriched, phase='send'))
        self._downstream.send_nowait(enriched)

    async def receive(self) -> ChannelMessage:
        message = await self._downstream.receive()
        await self._notify_observers(message, phase='receive')
        return message

    def empty(self) -> bool:
        return self._downstream.empty()

    def close(self) -> None:
        self._downstream.close()

    def _enrich(self, message: ChannelMessage) -> ChannelMessage:
        if not self._metadata_defaults:
            return message
        merged = dict(self._metadata_defaults)
        merged.update(message.metadata)
        return message.clone(metadata=merged)

    async def _notify_observers(self, message: ChannelMessage, *, phase: str) -> None:
        if not self._observers:
            return
        for observer in self._observers:
            try:
                maybe_coro = observer(message, self, phase)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:
                continue


class QueueBridge:
    """
    Compatibility layer exposing a queue-like API for legacy code.

    Newly written code should use the channel interface directly.
    """

    def __init__(self, channel: BaseChannel) -> None:
        self._channel = channel

    async def put(self, payload: Any) -> None:
        await self._channel.send(ChannelMessage(payload=payload))

    def put_nowait(self, payload: Any) -> None:
        self._channel.send_nowait(ChannelMessage(payload=payload))

    async def get(self) -> Any:
        message = await self._channel.receive()
        return message.payload

    def empty(self) -> bool:
        return self._channel.empty()
