from __future__ import annotations

import pytest

from spark.agent import Tool, ToolCall, ToolRegistry, tool


@pytest.mark.asyncio
async def test_tool_decorator_builds_tool_from_function_signature() -> None:
    @tool
    def add(left: int, right: int = 1) -> int:
        """Add two integers."""
        return left + right

    assert isinstance(add, Tool)
    assert add.name == "add"
    assert add.description == "Add two integers."
    assert add.parameters == {
        "type": "object",
        "properties": {
            "left": {"type": "integer"},
            "right": {"type": "integer", "default": 1},
        },
        "additionalProperties": False,
        "required": ["left"],
    }

    registry = ToolRegistry({add.name: add})
    result = await registry.execute(ToolCall(call_id="call-1", name="add", arguments={"left": 2, "right": 3}))

    assert result.output == "5"
    assert result.error is None


@pytest.mark.asyncio
async def test_tool_decorator_accepts_custom_metadata_and_async_functions() -> None:
    @tool(name="weather", description="Return weather.", parameters={"type": "object"}, strict=False)
    async def get_weather(location: str) -> str:
        return f"{location}: sunny"

    assert get_weather.name == "weather"
    assert get_weather.description == "Return weather."
    assert get_weather.parameters == {"type": "object"}
    assert get_weather.strict is False

    registry = ToolRegistry({get_weather.name: get_weather})
    result = await registry.execute(
        ToolCall(call_id="call-1", name="weather", arguments={"location": "Chicago"})
    )

    assert result.output == "Chicago: sunny"


def test_tool_decorator_rejects_variadic_functions() -> None:
    with pytest.raises(ValueError, match="variadic"):

        @tool
        def collect(*values: int) -> int:
            return sum(values)
