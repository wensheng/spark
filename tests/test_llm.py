from collections.abc import AsyncIterator, Mapping, Sequence
from types import SimpleNamespace
from typing import Any

import pytest

from spark import Syndicate
from spark.agent import (
    Agent,
    ChatMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    OpenAIResponsesProvider,
    Tool,
    ToolCall,
    ToolResult,
    ToolTrace,
)
from spark.core.message import Message
from spark.node import Node


class EchoProvider:
    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        return LLMResponse(
            request_id=request.request_id,
            content=f"echo:{request.prompt}",
            history=(*history, ChatMessage("assistant", f"echo:{request.prompt}")),
        )

    async def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        yield LLMStreamChunk(request_id=request.request_id, content_delta="hel")
        yield LLMStreamChunk(request_id=request.request_id, content_delta="lo")
        yield LLMStreamChunk(request_id=request.request_id, done=True)


class ToolProvider:
    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        if not tool_results:
            return LLMResponse(
                request_id=request.request_id,
                content="",
                history=tuple(history),
                tool_calls=(ToolCall(call_id="call-1", name="add", arguments={"left": 2, "right": 3}),),
            )
        return LLMResponse(
            request_id=request.request_id,
            content=f"tool:{tool_results[0].output}",
            history=(*history, ChatMessage("assistant", f"tool:{tool_results[0].output}")),
        )

    async def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        if False:
            yield LLMStreamChunk(request_id=request.request_id)


class ChainedToolProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                request_id=request.request_id,
                content="",
                history=tuple(history),
                tool_calls=(
                    ToolCall(call_id="call-1", name="find_user", arguments={"email": "alice@example.com"}),
                ),
            )
        if self.calls == 2:
            assert tool_results == (
                ToolResult(call_id="call-1", name="find_user", output='{"id": 1}'),
            )
            return LLMResponse(
                request_id=request.request_id,
                content="",
                history=tuple(history),
                tool_calls=(ToolCall(call_id="call-2", name="get_user_orders", arguments={"user_id": 1}),),
            )
        if self.calls == 3:
            assert tool_results == (
                ToolResult(call_id="call-2", name="get_user_orders", output='[{"order_id": 101}]'),
            )
            return LLMResponse(
                request_id=request.request_id,
                content="",
                history=tuple(history),
                tool_calls=(
                    ToolCall(
                        call_id="call-3",
                        name="update_order_status",
                        arguments={"order_id": 101, "new_status": "delivered"},
                    ),
                ),
            )
        assert tool_results == (
            ToolResult(call_id="call-3", name="update_order_status", output="updated"),
        )
        return LLMResponse(
            request_id=request.request_id,
            content="updated",
            history=(*history, ChatMessage("assistant", "updated")),
        )

    async def stream(
        self,
        request: LLMRequest,
        history: Sequence[ChatMessage],
        tools: Sequence[Tool] = (),
        tool_results: Sequence[ToolResult] = (),
    ) -> AsyncIterator[LLMStreamChunk]:
        if False:
            yield LLMStreamChunk(request_id=request.request_id)


class ManualAgent(Agent):
    __spark_auto_start__ = False


class ManualStartNode(Node):
    __spark_auto_start__ = False

    def process(self, message: Message) -> Any:
        return message.content


def add_handler(arguments: Mapping[str, Any]) -> int:
    return int(arguments["left"]) + int(arguments["right"])


def find_user_handler(arguments: Mapping[str, Any]) -> str:
    return '{"id": 1}' if arguments["email"] == "alice@example.com" else "not found"


def get_orders_handler(arguments: Mapping[str, Any]) -> str:
    return '[{"order_id": 101}]' if arguments["user_id"] == 1 else "[]"


def update_order_handler(arguments: Mapping[str, Any]) -> str:
    if arguments["order_id"] == 101 and arguments["new_status"] == "delivered":
        return "updated"
    return "not updated"


@pytest.mark.asyncio
async def test_llm_agent_complete_stream_and_tools_are_async_native() -> None:
    async with Syndicate("async-llm") as system:
        agent = await system.create_actor(Agent, EchoProvider(), instructions="be brief")
        reply = await system.ask(agent, "hello")
        assert isinstance(reply, LLMResponse)
        assert reply.content == "echo:hello"

        stream_agent = await system.create_actor(Agent, EchoProvider())
        request = LLMRequest("hello", stream=True)
        await system.tell(stream_agent, request)
        assert await system.receive(timeout=1.0) == LLMStreamChunk(
            request_id=request.request_id,
            content_delta="hel",
        )
        assert await system.receive(timeout=1.0) == LLMStreamChunk(
            request_id=request.request_id,
            content_delta="lo",
        )
        assert await system.receive(timeout=1.0) == LLMStreamChunk(request_id=request.request_id, done=True)
        final = await system.receive(timeout=1.0)
        assert isinstance(final, LLMResponse)
        assert final.content == "hello"

        tool = Tool(
            name="add",
            description="Add two integers.",
            parameters={
                "type": "object",
                "properties": {"left": {"type": "integer"}, "right": {"type": "integer"}},
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            handler=add_handler,
        )
        tool_agent = await system.create_actor(Agent, ToolProvider(), tools=[tool])
        tool_reply = await system.ask(tool_agent, LLMRequest("add two and three"))
        assert isinstance(tool_reply, LLMResponse)
        assert tool_reply.content == "tool:5"


@pytest.mark.asyncio
async def test_llm_agent_forwards_response_content_to_next_node() -> None:
    start = ManualStartNode()
    first = ManualAgent(EchoProvider())
    second = ManualAgent(EchoProvider())
    start >> first >> second

    async with Syndicate("llm-agent-graph-chain") as system:
        start_address = await system.start_actor(start)
        await system.start_actor(first)
        await system.start_actor(second)

        reply = await system.ask(start_address, Message("hello"), timeout=1.0)

    assert isinstance(reply, LLMResponse)
    assert reply.content == "echo:echo:hello"


@pytest.mark.asyncio
async def test_llm_agent_joins_list_payloads_into_prompt() -> None:
    agent = ManualAgent(EchoProvider())

    reply = await agent._process(Message(["first opinion", "second opinion"]))

    assert isinstance(reply, LLMResponse)
    assert reply.content == "echo:first opinion\n\nsecond opinion"


@pytest.mark.asyncio
async def test_llm_agent_records_tool_traces() -> None:
    tool = Tool(
        name="add",
        description="Add two integers.",
        parameters={
            "type": "object",
            "properties": {"left": {"type": "integer"}, "right": {"type": "integer"}},
            "required": ["left", "right"],
            "additionalProperties": False,
        },
        handler=add_handler,
    )

    async with Syndicate("llm-tool-traces") as system:
        agent = ManualAgent(ToolProvider(), tools=[tool])
        address = await system.start_actor(agent)
        request = LLMRequest("add two and three")
        reply = await system.ask(address, request)

    assert isinstance(reply, LLMResponse)
    assert reply.content == "tool:5"
    assert agent.get_tool_traces() == (
        ToolTrace(
            request_id=request.request_id,
            round_index=0,
            call_index=0,
            call=ToolCall(call_id="call-1", name="add", arguments={"left": 2, "right": 3}),
            result=ToolResult(call_id="call-1", name="add", output="5"),
        ),
    )


@pytest.mark.asyncio
async def test_llm_agent_records_unexecuted_tool_traces_when_round_limit_is_reached() -> None:
    async with Syndicate("llm-tool-traces-round-limit") as system:
        agent = ManualAgent(ToolProvider())
        address = await system.start_actor(agent)
        request = LLMRequest("add two and three", max_tool_rounds=0)
        reply = await system.ask(address, request)

    assert isinstance(reply, LLMResponse)
    assert agent.get_tool_traces() == (
        ToolTrace(
            request_id=request.request_id,
            round_index=0,
            call_index=0,
            call=ToolCall(call_id="call-1", name="add", arguments={"left": 2, "right": 3}),
        ),
    )


@pytest.mark.asyncio
async def test_llm_agent_default_tool_rounds_allow_chained_tools() -> None:
    tools = [
        Tool(name="find_user", description="Find user.", handler=find_user_handler),
        Tool(name="get_user_orders", description="Get orders.", handler=get_orders_handler),
        Tool(name="update_order_status", description="Update order.", handler=update_order_handler),
    ]

    async with Syndicate("llm-tool-chain") as system:
        provider = ChainedToolProvider()
        agent = ManualAgent(provider, tools=tools)
        address = await system.start_actor(agent)
        request = LLMRequest("Find Alice's orders and mark order 101 delivered.")
        reply = await system.ask(address, request)

    assert isinstance(reply, LLMResponse)
    assert reply.content == "updated"
    assert provider.calls == 4
    assert [trace.call.name for trace in agent.get_tool_traces()] == [
        "find_user",
        "get_user_orders",
        "update_order_status",
    ]
    assert [trace.result.output if trace.result else None for trace in agent.get_tool_traces()] == [
        '{"id": 1}',
        '[{"order_id": 101}]',
        "updated",
    ]


@pytest.mark.asyncio
async def test_openai_provider_accepts_async_client() -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            if kwargs.get("stream") is True:
                return [
                    SimpleNamespace(type="response.output_text.delta", delta="he"),
                    SimpleNamespace(type="response.completed"),
                ]
            return SimpleNamespace(output_text="hello", output=[])

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    client = FakeClient()
    provider = OpenAIResponsesProvider(client=client, model="gpt-test")
    result = await provider.complete(LLMRequest("hi"), [ChatMessage("user", "hi")])
    assert result.content == "hello"

    chunks = [chunk async for chunk in provider.stream(LLMRequest("hi", stream=True), [ChatMessage("user", "hi")])]
    assert chunks == [
        LLMStreamChunk(request_id=chunks[0].request_id, content_delta="he"),
        LLMStreamChunk(request_id=chunks[0].request_id, done=True),
    ]


@pytest.mark.asyncio
async def test_openai_tool_round_replays_function_call_before_output() -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(
                    output_text="",
                    output=[
                        {
                            "type": "function_call",
                            "id": "fc-1",
                            "call_id": "call-1",
                            "name": "get_weather",
                            "arguments": '{"location": "Chicago"}',
                            "status": "completed",
                        }
                    ],
                )
            return SimpleNamespace(output_text="sunny", output=[])

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    def weather_handler(arguments: Mapping[str, Any]) -> str:
        return f"{arguments['location']}: sunny"

    client = FakeClient()
    provider = OpenAIResponsesProvider(client=client, model="gpt-test")
    tool = Tool(
        name="get_weather",
        description="Get weather.",
        parameters={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
            "additionalProperties": False,
        },
        handler=weather_handler,
    )

    async with Syndicate("openai-tool-round") as system:
        agent = await system.create_actor(Agent, provider, tools=[tool])
        reply = await system.ask(agent, LLMRequest("What is the weather in Chicago?"))

    assert isinstance(reply, LLMResponse)
    assert reply.content == "sunny"
    assert len(client.responses.calls) == 2
    assert client.responses.calls[1]["input"] == [
        {"type": "message", "role": "user", "content": "What is the weather in Chicago?"},
        {
            "type": "function_call",
            "id": "fc-1",
            "call_id": "call-1",
            "name": "get_weather",
            "arguments": '{"location": "Chicago"}',
            "status": "completed",
        },
        {"type": "function_call_output", "call_id": "call-1", "output": "Chicago: sunny"},
    ]
