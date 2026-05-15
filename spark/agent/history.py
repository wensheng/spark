"""Conversation history owned by LLM actors."""

from __future__ import annotations

from collections.abc import Iterable

from .messages import ChatMessage, ChatRole


class ConversationHistory:
    """Mutable conversation history for one actor instance."""

    def __init__(self, messages: Iterable[ChatMessage] = (), max_messages: int | None = None) -> None:
        if max_messages is not None and max_messages <= 0:
            raise ValueError("max_messages must be positive")
        self.max_messages = max_messages
        self._messages: list[ChatMessage] = list(messages)
        self._trim()

    def append(self, message: ChatMessage) -> None:
        """Append one message and apply the configured retention limit."""
        self._messages.append(message)
        self._trim()

    def add(self, role: ChatRole, content: str, *, name: str | None = None) -> ChatMessage:
        """Append and return one message."""
        message = ChatMessage(role=role, content=content, name=name)
        self.append(message)
        return message

    def snapshot(self) -> tuple[ChatMessage, ...]:
        """Return an immutable snapshot."""
        return tuple(self._messages)

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    def _trim(self) -> None:
        if self.max_messages is not None and len(self._messages) > self.max_messages:
            del self._messages[: len(self._messages) - self.max_messages]
