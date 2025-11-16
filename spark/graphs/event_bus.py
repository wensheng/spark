"""
Event bus used by graphs to coordinate pub/sub style communication.

Nodes can publish named events and subscribe to topics without rewiring
graph edges, enabling observability and decoupled fan-out patterns.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, List, Optional

from spark.nodes.channels import BaseChannel, ChannelClosed, ChannelMessage, InMemoryChannel

ChannelFactory = Callable[[str], BaseChannel]


class EventSubscription:
    """Represents a subscription to a topic on the event bus."""

    def __init__(self, topic: str, channel: BaseChannel, remove_cb: Callable[[str, BaseChannel], None]) -> None:
        self._topic = topic
        self._channel = channel
        self._remove_cb = remove_cb
        self._closed = False

    @property
    def topic(self) -> str:
        return self._topic

    async def receive(self) -> ChannelMessage:
        """Await the next event for this subscription."""
        if self._closed:
            raise RuntimeError('Subscription is closed')
        try:
            return await self._channel.receive()
        except ChannelClosed as exc:
            raise StopAsyncIteration from exc

    async def close(self) -> None:
        """Stop receiving events and release the channel."""
        if self._closed:
            return
        self._closed = True
        self._remove_cb(self._topic, self._channel)
        self._channel.close()

    def __aiter__(self):
        return self

    async def __anext__(self) -> ChannelMessage:
        if self._closed:
            raise StopAsyncIteration
        return await self.receive()


class GraphEventBus:
    """
    Lightweight in-memory event bus for graphs.

    Topics are string keys. Special topic "*" receives all events.
    """

    def __init__(
        self,
        *,
        channel_factory: ChannelFactory | None = None,
        replay_buffer_size: int = 0,
    ) -> None:
        self._channel_factory = channel_factory or (lambda topic: InMemoryChannel(name=f'event:{topic}'))
        self._subscriptions: dict[str, list[BaseChannel]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._replay_buffer_size = replay_buffer_size
        self._replay_buffer: list[ChannelMessage] = []

    async def publish(self, topic: str, payload: Any, *, metadata: dict[str, Any] | None = None) -> None:
        """Publish an event to the specified topic."""
        message = ChannelMessage(payload=payload, metadata={'topic': topic, **(metadata or {})})
        if self._replay_buffer_size > 0:
            self._replay_buffer.append(message.clone())
            if len(self._replay_buffer) > self._replay_buffer_size:
                self._replay_buffer = self._replay_buffer[-self._replay_buffer_size :]
        async with self._lock:
            targets = list(self._subscriptions.get(topic, []))
            wildcards = list(self._subscriptions.get('*', []))
        if not targets and not wildcards:
            return

        async def _fanout(channel: BaseChannel, template: ChannelMessage) -> None:
            try:
                await channel.send(template.clone())
            except ChannelClosed:
                return

        await asyncio.gather(
            *(_fanout(channel, message) for channel in (*targets, *wildcards)),
            return_exceptions=False,
        )

    async def subscribe(self, topic: str) -> EventSubscription:
        """Subscribe to a topic; use '*' for all events."""
        channel = self._channel_factory(topic)
        async with self._lock:
            self._subscriptions[topic].append(channel)
            if self._replay_buffer_size > 0 and topic in ('*',):
                for message in self._replay_buffer:
                    await channel.send(message.clone())
        return EventSubscription(topic, channel, self._remove_subscription)

    async def replay(self, topic: str = '*') -> List[ChannelMessage]:
        """Return buffered events for inspection."""
        if self._replay_buffer_size <= 0:
            return []
        if topic == '*':
            return [msg.clone() for msg in self._replay_buffer]
        return [msg.clone() for msg in self._replay_buffer if msg.metadata.get('topic') == topic]

    def _remove_subscription(self, topic: str, channel: BaseChannel) -> None:
        channels = self._subscriptions.get(topic)
        if not channels:
            return
        try:
            channels.remove(channel)
        except ValueError:
            return
        if not channels:
            self._subscriptions.pop(topic, None)
