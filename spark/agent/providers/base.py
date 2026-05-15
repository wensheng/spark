"""LLM provider interfaces and OpenAI implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from ..messages import ChatMessage, LLMRequest, LLMResponse, LLMStreamChunk
from ..tools import Tool, ToolResult


class ProviderError(RuntimeError):
    """Raised when an LLM provider fails."""


class ProviderConfigurationError(ProviderError):
    """Raised when an LLM provider is not configured."""


class LLMProvider(Protocol):
    """Provider-neutral LLM completion interface."""

    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        """Return a complete response."""
        ...

    def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        """Yield streamed response chunks."""
        ...
