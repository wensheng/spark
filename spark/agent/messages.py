"""Messages used by LLM actors and providers."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ..core.identity import FrozenHeaders
from .tools import ToolCall, ToolResult

ChatRole = Literal["system", "developer", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One conversation message."""

    role: ChatRole
    content: str
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """Request to an LLM actor."""

    prompt: str
    instructions: str | None = None
    stream: bool = False
    timeout: float | None = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    max_tool_rounds: int = 8
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))
        if self.max_tool_rounds < 0:
            raise ValueError("max_tool_rounds must be non-negative")


@dataclass(frozen=True, slots=True)
class LLMCancelRequest:
    """Best-effort request to cancel queued or future work."""

    request_id: str


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    """One streamed content delta."""

    request_id: str
    content_delta: str = ""
    done: bool = False
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Final response from an LLM actor or provider."""

    request_id: str
    content: str
    history: tuple[ChatMessage, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))


@dataclass(frozen=True, slots=True)
class LLMErrorResponse:
    """Non-crashing LLM actor error response."""

    request_id: str
    error: str
    recoverable: bool = True
    metadata: Mapping[str, Any] = field(default_factory=FrozenHeaders)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenHeaders(self.metadata))
