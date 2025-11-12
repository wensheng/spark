"""Unit tests for spark.tools.executor module."""

import asyncio

import pytest

from spark.tools.decorator import tool
from spark.tools.executor import ToolCallExecutor, ToolExecutionConfig
from spark.tools.registry import ToolRegistry
from spark.tools.types import BaseTool, ToolSpec, ToolUse


class PositionalTool(BaseTool):
    """Tool used to test positional arguments."""

    @property
    def tool_name(self) -> str:
        return "positional"

    @property
    def tool_spec(self) -> ToolSpec:
        return {"name": "positional", "description": "Positional", "parameters": {"json": {"type": "object"}}}

    @property
    def tool_type(self) -> str:
        return "test"

    def __call__(self, payload: str) -> str:
        return f"POS:{payload}"


@pytest.mark.asyncio
async def test_executor_runs_sync_decorated_tool():
    registry = ToolRegistry()

    @tool
    def greet(name: str) -> str:
        return f"Hello {name}"

    registry.process_tools([greet])
    executor = ToolCallExecutor(registry)

    tool_use: ToolUse = {"name": "greet", "toolUseId": "use-1", "input": {"name": "Spark"}}
    result = await executor.execute_tool_use(tool_use)

    assert result["status"] == "success"
    assert "Hello Spark" in result["content"][0]["text"]
    assert result["toolUseId"] == "use-1"


@pytest.mark.asyncio
async def test_executor_runs_async_decorated_tool():
    registry = ToolRegistry()

    @tool
    async def async_tool(value: int) -> str:
        await asyncio.sleep(0)
        return f"Async {value}"

    registry.process_tools([async_tool])
    executor = ToolCallExecutor(registry)

    tool_use: ToolUse = {"name": "async_tool", "toolUseId": "use-2", "input": {"value": 5}}
    result = await executor.execute_tool_use(tool_use)

    assert result["status"] == "success"
    assert "Async 5" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_executor_timeout_error():
    registry = ToolRegistry()

    @tool
    async def slow_tool() -> str:
        await asyncio.sleep(0.05)
        return "done"

    registry.process_tools([slow_tool])
    executor = ToolCallExecutor(registry, ToolExecutionConfig(default_timeout=0.01))

    tool_use: ToolUse = {"name": "slow_tool", "toolUseId": "use-3", "input": {}}
    result = await executor.execute_tool_use(tool_use)

    assert result["status"] == "error"
    assert result["metadata"]["reason"] == "timeout"


@pytest.mark.asyncio
async def test_executor_handles_positional_input():
    registry = ToolRegistry()
    registry.register_tool(PositionalTool())
    executor = ToolCallExecutor(registry)

    tool_use: ToolUse = {"name": "positional", "toolUseId": "use-4", "input": "payload"}
    result = await executor.execute_tool_use(tool_use)

    assert result["status"] == "success"
    assert "POS:payload" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_executor_handles_tool_exceptions():
    registry = ToolRegistry()

    @tool
    def failing_tool() -> str:
        raise ValueError("boom")

    registry.process_tools([failing_tool])
    executor = ToolCallExecutor(registry)

    tool_use: ToolUse = {"name": "failing_tool", "toolUseId": "use-5", "input": {}}
    result = await executor.execute_tool_use(tool_use)

    assert result["status"] == "error"
    assert "failed" in result["content"][0]["text"]
