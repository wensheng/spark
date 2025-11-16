"""Persistent mailbox abstractions for long-lived graph execution."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Iterable

from spark.graphs.graph_state import GraphState
from spark.nodes.base import BaseNode
from spark.nodes.channels import BaseChannel, ChannelClosed, ChannelMessage
from spark.nodes.types import NodeMessage


class PersistentMailbox(BaseChannel):
    """Channel implementation backed by GraphState for durability."""

    def __init__(
        self,
        *,
        graph_state: GraphState,
        mailbox_id: str,
        maxsize: int = 0,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name or f'persistent:{mailbox_id}')
        self._graph_state = graph_state
        self._mailbox_id = mailbox_id
        self._maxsize = maxsize
        self._queue: deque[ChannelMessage] = deque()
        self._condition = asyncio.Condition()
        self._initialized = False
        self._closed = False

    async def initialize(self) -> None:
        """Load persisted entries into the in-memory queue."""
        if self._initialized:
            return
        entries = await self._graph_state.load_mailbox_messages(self._mailbox_id)
        async with self._condition:
            for payload in entries:
                message = self._decode_message(payload)
                if message and not message.is_shutdown:
                    self._queue.append(message)
            self._initialized = True
            self._condition.notify_all()

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    async def send(self, message: ChannelMessage) -> None:
        await self._ensure_initialized()
        async with self._condition:
            if self._closed:
                raise ChannelClosed(f'Mailbox {self.name} is closed')
            while self._maxsize and len(self._queue) >= self._maxsize:
                await self._condition.wait()
            self._queue.append(message)
            snapshot = self._encode_queue_locked()
            self._condition.notify_all()
        await self._graph_state.persist_mailbox_messages(self._mailbox_id, snapshot)

    def send_nowait(self, message: ChannelMessage) -> None:
        asyncio.create_task(self.send(message))

    async def receive(self) -> ChannelMessage:
        await self._ensure_initialized()
        async with self._condition:
            while not self._queue:
                if self._closed:
                    raise ChannelClosed(f'Mailbox {self.name} is closed')
                await self._condition.wait()
            message = self._queue.popleft()
            snapshot = self._encode_queue_locked()
            self._condition.notify_all()
        await self._graph_state.persist_mailbox_messages(self._mailbox_id, snapshot)
        return message

    def empty(self) -> bool:
        return not self._queue

    def close(self) -> None:
        self._closed = True
        async def _flush_and_notify():
            async with self._condition:
                snapshot = self._encode_queue_locked()
                self._condition.notify_all()
            await self._graph_state.persist_mailbox_messages(self._mailbox_id, snapshot)

        asyncio.create_task(_flush_and_notify())

    def _encode_queue_locked(self) -> list[dict[str, Any]]:
        return [self._encode_message(message) for message in self._queue if not message.is_shutdown]

    def _encode_message(self, message: ChannelMessage) -> dict[str, Any]:
        payload = message.payload
        payload_kind = 'raw'
        if isinstance(payload, NodeMessage):
            payload_kind = 'node_message'
            payload = payload.model_dump(mode='json')
        return {
            'payload_kind': payload_kind,
            'payload': payload,
            'metadata': dict(message.metadata or {}),
            'is_shutdown': bool(message.is_shutdown),
        }

    def _decode_message(self, payload: Any) -> ChannelMessage | None:
        if not isinstance(payload, dict):
            return None
        data = dict(payload)
        payload_kind = data.get('payload_kind')
        message_payload: Any = data.get('payload')
        if payload_kind == 'node_message':
            try:
                message_payload = NodeMessage.model_validate(message_payload or {})
            except Exception:
                message_payload = NodeMessage()
        metadata = data.get('metadata') or {}
        is_shutdown = bool(data.get('is_shutdown'))
        return ChannelMessage(payload=message_payload, metadata=metadata, is_shutdown=is_shutdown)


class MailboxPersistenceManager:
    """Helper that swaps node mailboxes with persistent variants."""

    def __init__(
        self,
        graph_state: GraphState,
        nodes: Iterable[BaseNode],
        *,
        graph_id: str,
        maxsize: int = 0,
    ) -> None:
        self._graph_state = graph_state
        self._nodes = list(nodes)
        self._graph_id = graph_id
        self._maxsize = maxsize
        self._mailboxes: dict[str, PersistentMailbox] = {}
        self._original_mailboxes: dict[str, BaseChannel] = {}
        self._enabled = False

    def _mailbox_id_for(self, node: BaseNode) -> str:
        node_id = getattr(node, 'id', None) or node.__class__.__name__
        return f"{self._graph_id}:{node_id}"

    async def enable(self) -> None:
        """Replace all node mailboxes with persistent versions."""
        if self._enabled:
            return
        for node in self._nodes:
            existing = getattr(node, 'mailbox', None)
            if existing is None:
                continue
            node_id = getattr(node, 'id', None)
            if node_id is None:
                continue
            mailbox_id = self._mailbox_id_for(node)
            persistent = PersistentMailbox(
                graph_state=self._graph_state,
                mailbox_id=mailbox_id,
                maxsize=self._maxsize,
                name=getattr(existing, 'name', None),
            )
            await persistent.initialize()
            self._original_mailboxes[node_id] = existing
            node.mailbox = persistent
            self._mailboxes[node_id] = persistent
        self._enabled = True

    async def disable(self) -> None:
        """Restore original mailboxes and close durable channels."""
        if not self._enabled:
            return
        for node in self._nodes:
            node_id = getattr(node, 'id', None)
            if node_id is None:
                continue
            persistent = self._mailboxes.get(node_id)
            if persistent:
                persistent.close()
            original = self._original_mailboxes.get(node_id)
            if original is not None:
                node.mailbox = original
        self._mailboxes.clear()
        self._original_mailboxes.clear()
        self._enabled = False
