"""Async LLM agent actor base class."""

from __future__ import annotations

from time import monotonic
from typing import Any

from ..actor.address import ActorAddress
from ..core.message import Message
from ..node.base import Node
from .history import ConversationHistory
from .messages import ChatMessage, LLMCancelRequest, LLMErrorResponse, LLMRequest, LLMResponse
from .providers.base import LLMProvider
from .tools import Tool, ToolCall, ToolRegistry, ToolResult, ToolTrace


class Agent(Node):
    """Actor that wraps an async LLM provider."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        instructions: str | None = None,
        tools: ToolRegistry | list[Tool] | tuple[Tool, ...] | None = None,
        history: ConversationHistory | None = None,
        max_history_messages: int | None = None,
    ) -> None:
        super().__init__()
        self.provider = provider
        self.instructions = instructions
        self.history = history or ConversationHistory(max_messages=max_history_messages)
        if isinstance(tools, ToolRegistry):
            self.tools = tools
        else:
            self.tools = ToolRegistry({tool.name: tool for tool in tools or ()})
        self._cancelled: set[str] = set()
        self._tool_traces: list[ToolTrace] = []

    def get_tool_traces(self) -> tuple[ToolTrace, ...]:
        """Return a complete snapshot of tool calls requested by the model."""
        return tuple(self._tool_traces)

    async def process(self, message: Message) -> LLMResponse | LLMErrorResponse | None:
        """Handle a prompt, request, or cancellation message."""
        payload = message.content
        sender = message.sender
        if isinstance(payload, LLMCancelRequest):
            self._cancelled.add(payload.request_id)
            return None
        if isinstance(payload, LLMRequest):
            request = payload
        elif isinstance(payload, (list, tuple)):
            request = LLMRequest(prompt="\n\n".join(str(item) for item in payload))
        else:
            request = LLMRequest(prompt=str(payload))
        if request.request_id in self._cancelled:
            return self._error_response(request, "request cancelled")
        if request.timeout is not None and request.timeout <= 0:
            return self._error_response(request, "request timed out")
        if request.stream:
            return await self._handle_stream(request, sender)
        return await self._handle_complete(request)

    async def _handle_complete(self, request: LLMRequest) -> LLMResponse | LLMErrorResponse:
        started_at = monotonic()
        history = self._history_with_user(request)
        try:
            response = await self.provider.complete(request, history, self.tools.list())
            provider_history = response.history or history
            tool_results: tuple[ToolResult, ...] = ()
            rounds = 0
            while response.tool_calls:
                if rounds >= request.max_tool_rounds:
                    self._record_tool_traces(request, rounds, response.tool_calls, ())
                    break
                round_results = tuple([await self.tools.execute(call) for call in response.tool_calls])
                self._record_tool_traces(request, rounds, response.tool_calls, round_results)
                tool_results = (*tool_results, *round_results)
                response = await self.provider.complete(request, provider_history, self.tools.list(), round_results)
                provider_history = response.history or provider_history
                rounds += 1
        except Exception as exc:
            return self._error_response(request, str(exc))
        if request.timeout is not None and monotonic() - started_at > request.timeout:
            return self._error_response(request, "request timed out")
        self._record_assistant(response.content)
        return self._final_response(response, tool_results)

    async def _handle_stream(
        self,
        request: LLMRequest,
        sender: ActorAddress | None,
    ) -> LLMResponse | LLMErrorResponse:
        content_parts: list[str] = []
        history = self._history_with_user(request)
        try:
            async for chunk in self.provider.stream(request, history, self.tools.list()):
                content_parts.append(chunk.content_delta)
                await self._reply(sender, chunk)
        except Exception as exc:
            return self._error_response(request, str(exc))
        content = "".join(content_parts)
        self._record_assistant(content)
        return LLMResponse(
            request_id=request.request_id,
            content=content,
            history=self.history.snapshot(),
        )

    def _history_with_user(self, request: LLMRequest) -> tuple[ChatMessage, ...]:
        if self.instructions is not None and not self.history.snapshot():
            self.history.add("developer", self.instructions)
        self.history.add("user", request.prompt)
        return self.history.snapshot()

    def _record_assistant(self, content: str) -> None:
        if content:
            self.history.add("assistant", content)

    def _record_tool_traces(
        self,
        request: LLMRequest,
        round_index: int,
        calls: tuple[ToolCall, ...],
        results: tuple[ToolResult, ...],
    ) -> None:
        results_by_call_id = {result.call_id: result for result in results}
        for call_index, call in enumerate(calls):
            self._tool_traces.append(
                ToolTrace(
                    request_id=request.request_id,
                    round_index=round_index,
                    call_index=call_index,
                    call=call,
                    result=results_by_call_id.get(call.call_id),
                )
            )

    def _final_response(self, response: LLMResponse, tool_results: tuple[ToolResult, ...]) -> LLMResponse:
        return LLMResponse(
            request_id=response.request_id,
            content=response.content,
            history=self.history.snapshot(),
            tool_calls=response.tool_calls,
            tool_results=tool_results or response.tool_results,
            metadata=response.metadata,
        )

    def _forward_message(self, result: Any, message: Message) -> Message:
        """Forward only assistant text so downstream agents receive a clean prompt."""

        if isinstance(result, LLMResponse):
            result = result.content
        return super()._forward_message(result, message)

    def _error_response(self, request: LLMRequest, error: str) -> LLMErrorResponse:
        return LLMErrorResponse(request_id=request.request_id, error=error)

    async def _reply_error(self, sender: ActorAddress | None, request: LLMRequest, error: str) -> None:
        await self._reply(sender, LLMErrorResponse(request_id=request.request_id, error=error))

    async def _reply(self, sender: ActorAddress | None, message: Any) -> None:
        if sender is not None:
            await self.tell(message, sender)
