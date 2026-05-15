"""LLM provider interfaces and OpenAI implementation."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import os
from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from typing import Any

from ..messages import ChatMessage, LLMRequest, LLMResponse, LLMStreamChunk
from ..tools import Tool, ToolCall, ToolResult
from .base import ProviderConfigurationError, ProviderError

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
_OPENAI_INPUT_ITEMS_METADATA = "openai_input_items"


class OpenAIResponsesProvider:
    """OpenAI Responses API provider.

    The OpenAI client is imported lazily so Spark can be installed without the
    optional OpenAI dependency. Tests and enterprise gateways can inject any
    client object with a compatible ``responses.create`` method.
    """

    def __init__(
        self,
        model: str = DEFAULT_OPENAI_MODEL,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        response_options: Mapping[str, Any] | None = None,
    ) -> None:
        self.model = model
        self._client = client
        self._api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self._base_url = base_url if base_url is not None else os.getenv("OPENAI_BASE_URL")
        self._response_options = dict(response_options or {})

    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        """Create one non-streaming OpenAI response."""
        try:
            response = await self._create_response(self._request_kwargs(request, history, tools, tool_results))
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenAI response failed: {exc}") from exc
        content = self._response_text(response)
        tool_calls = self._extract_tool_calls(response)
        return LLMResponse(
            request_id=request.request_id,
            content=content,
            history=self._response_history(history, tool_results, response, content, tool_calls),
            tool_calls=tool_calls,
            metadata={"provider": "openai", "model": self.model},
        )

    async def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream text deltas from one OpenAI response."""
        try:
            stream = await self._create_response({
                **self._request_kwargs(request, history, tools, tool_results),
                "stream": True,
            })
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"OpenAI stream failed: {exc}") from exc
        if hasattr(stream, "__aiter__"):
            async for event in stream:
                chunk = self._stream_chunk(request, event)
                if chunk is not None:
                    yield chunk
            return
        for event in await asyncio.to_thread(list, stream):
            chunk = self._stream_chunk(request, event)
            if chunk is not None:
                yield chunk

    def _stream_chunk(self, request: LLMRequest, event: Any) -> LLMStreamChunk | None:
        event_type = self._field(event, "type")
        if event_type == "response.output_text.delta":
            delta = self._field(event, "delta")
            if isinstance(delta, str) and delta:
                return LLMStreamChunk(request_id=request.request_id, content_delta=delta)
        elif event_type in {"response.completed", "response.output_text.done"}:
            return LLMStreamChunk(request_id=request.request_id, done=True)
        return None

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            openai_module = importlib.import_module("openai")
        except ImportError as exc:
            raise ProviderConfigurationError(
                "install the optional 'openai' dependency to use OpenAIResponsesProvider"
            ) from exc
        openai_client = getattr(openai_module, "AsyncOpenAI", None) or openai_module.OpenAI
        kwargs: dict[str, Any] = {"api_key": self._api_key} if self._api_key is not None else {}
        kwargs["base_url"] = self._base_url if self._base_url is not None else None
        self._client = openai_client(**kwargs)
        return self._client

    async def _create_response(self, kwargs: Mapping[str, Any]) -> Any:
        create = self._client_or_create().responses.create
        if inspect.iscoroutinefunction(create):
            return await create(**kwargs)
        return await asyncio.to_thread(create, **kwargs)

    def _request_kwargs(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool],
        tool_results: Sequence[ToolResult],
    ) -> dict[str, Any]:
        kwargs = {
            "model": self.model,
            "input": self._input_items(history, tool_results),
            **self._response_options,
        }
        if request.instructions is not None:
            kwargs["instructions"] = request.instructions
        if tools:
            kwargs["tools"] = [self._tool_schema(tool) for tool in tools]
        return kwargs

    def _input_items(self, history: Sequence[ChatMessage], tool_results: Sequence[ToolResult]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in history:
            provider_items = message.metadata.get(_OPENAI_INPUT_ITEMS_METADATA)
            if provider_items is not None:
                items.extend(self._coerce_input_items(provider_items))
                continue
            if message.role == "tool":
                continue
            items.append({"type": "message", "role": message.role, "content": message.content})
        for result in tool_results:
            output = result.output if result.error is None else f"error: {result.error}"
            items.append({"type": "function_call_output", "call_id": result.call_id, "output": output})
        return items

    def _tool_schema(self, tool: Tool) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": dict(tool.parameters),
            "strict": tool.strict,
        }

    def _response_text(self, response: Any) -> str:
        output_text = self._field(response, "output_text")
        if isinstance(output_text, str):
            return output_text
        parts: list[str] = []
        for item in self._iter_output(response):
            if self._field(item, "type") != "message":
                continue
            content_items = self._field(item, "content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if self._field(content_item, "type") in {"output_text", "text"}:
                    text = self._field(content_item, "text")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts)

    def _extract_tool_calls(self, response: Any) -> tuple[ToolCall, ...]:
        calls: list[ToolCall] = []
        for item in self._iter_output(response):
            if self._field(item, "type") != "function_call":
                continue
            name = self._field(item, "name")
            if not isinstance(name, str):
                continue
            call_id = self._field(item, "call_id") or self._field(item, "id")
            raw_arguments = self._field(item, "arguments")
            calls.append(
                ToolCall(
                    call_id=str(call_id),
                    name=name,
                    arguments=self._decode_arguments(raw_arguments),
                    raw_arguments=raw_arguments if isinstance(raw_arguments, str) else None,
                )
            )
        return tuple(calls)

    def _iter_output(self, response: Any) -> Iterable[Any]:
        output = self._field(response, "output")
        if isinstance(output, list):
            return output
        return ()

    def _decode_arguments(self, raw_arguments: Any) -> Mapping[str, Any]:
        if isinstance(raw_arguments, Mapping):
            return raw_arguments
        if not isinstance(raw_arguments, str) or not raw_arguments:
            return {}
        try:
            decoded = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, Mapping) else {}

    def _response_history(
        self,
        history: Sequence[ChatMessage],
        tool_results: Sequence[ToolResult],
        response: Any,
        content: str,
        tool_calls: Sequence[ToolCall],
    ) -> tuple[ChatMessage, ...]:
        updated = self._append_tool_results(history, tool_results)
        response_items = self._response_input_items(response)
        if tool_calls and response_items:
            return (
                *updated,
                ChatMessage(
                    role="assistant",
                    content=content,
                    metadata={_OPENAI_INPUT_ITEMS_METADATA: tuple(response_items)},
                ),
            )
        if content:
            return (*updated, ChatMessage(role="assistant", content=content))
        return updated

    def _append_tool_results(
        self,
        history: Sequence[ChatMessage],
        tool_results: Sequence[ToolResult],
    ) -> tuple[ChatMessage, ...]:
        updated = tuple(history)
        for result in tool_results:
            output = result.output if result.error is None else f"error: {result.error}"
            updated = (
                *updated,
                ChatMessage(
                    role="tool",
                    content=output,
                    name=result.name,
                    metadata={
                        _OPENAI_INPUT_ITEMS_METADATA: (
                            {"type": "function_call_output", "call_id": result.call_id, "output": output},
                        )
                    },
                ),
            )
        return updated

    def _response_input_items(self, response: Any) -> tuple[dict[str, Any], ...]:
        return tuple(self._coerce_input_items(self._iter_output(response)))

    def _coerce_input_items(self, values: Any) -> list[dict[str, Any]]:
        if isinstance(values, Mapping):
            values = (values,)
        items: list[dict[str, Any]] = []
        for value in values:
            item = self._coerce_input_item(value)
            if item is not None:
                items.append(item)
        return items

    def _coerce_input_item(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, Mapping):
            return {key: item for key, item in value.items() if item is not None}
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump(exclude_none=True)
            return dumped if isinstance(dumped, dict) else None
        item_type = self._field(value, "type")
        if not isinstance(item_type, str):
            return None
        if item_type == "function_call":
            item = {
                "type": "function_call",
                "call_id": self._field(value, "call_id"),
                "name": self._field(value, "name"),
                "arguments": self._field(value, "arguments"),
            }
            item_id = self._field(value, "id")
            status = self._field(value, "status")
            if item_id is not None:
                item["id"] = item_id
            if status is not None:
                item["status"] = status
            return {key: item_value for key, item_value in item.items() if item_value is not None}
        return None

    def _field(self, value: Any, field: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(field)
        return getattr(value, field, None)
