"""Unit tests for spark.tools.types module."""

import asyncio
from typing import Any

import pytest

from spark.tools.types import (
    ToolArgsConfig,
    ParametersSpec,
    ToolSpec,
    Tool,
    ToolUse,
    ToolResult,
    ToolRuntimeMetadata,
    BaseTool,
    ToolChoiceAuto,
    ToolChoiceAny,
    ToolChoiceTool,
    ToolChoiceAutoDict,
    ToolChoiceAnyDict,
    ToolChoiceToolDict,
    update_tool_runtime_metadata,
)


class TestToolArgsConfig:
    """Test cases for ToolArgsConfig."""

    def test_tool_args_config_basic(self):
        """Test basic ToolArgsConfig functionality."""
        config = ToolArgsConfig()
        assert config is not None

    def test_tool_args_config_with_extra_fields(self):
        """Test ToolArgsConfig allows extra fields."""
        config = ToolArgsConfig(extra_field="test_value", another_field=123)
        assert config.extra_field == "test_value"
        assert config.another_field == 123

    def test_tool_args_config_model_validation(self):
        """Test ToolArgsConfig model validation."""
        # Should accept any fields without validation errors
        config = ToolArgsConfig(
            description="Test description",
            type="string",
            min_length=1,
            max_length=100,
            custom_field="custom"
        )
        assert config.description == "Test description"
        assert config.custom_field == "custom"


class TestParametersSpec:
    """Test cases for ParametersSpec TypedDict."""

    def test_parameters_spec_creation(self):
        """Test ParametersSpec TypedDict creation."""
        spec: ParametersSpec = {
            "type": "object",
            "properties": {
                "name": ToolArgsConfig(description="User name"),
                "age": ToolArgsConfig(description="User age")
            },
            "required": ["name"]
        }
        assert spec["type"] == "object"
        assert "name" in spec["properties"]
        assert "age" in spec["properties"]
        assert spec["required"] == ["name"]

    def test_parameters_spec_with_extra_items(self):
        """Test ParametersSpec allows extra items."""
        spec: ParametersSpec = {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,  # Extra field
            "$schema": "http://json-schema.org/draft-07/schema#"  # Another extra field
        }
        assert spec["additionalProperties"] is False
        assert spec["$schema"] == "http://json-schema.org/draft-07/schema#"


class TestToolSpec:
    """Test cases for ToolSpec TypedDict."""

    def test_tool_spec_basic(self):
        """Test basic ToolSpec creation."""
        spec: ToolSpec = {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        assert spec["name"] == "test_tool"
        assert spec["description"] == "A test tool"
        assert "json" in spec["parameters"]

    def test_tool_spec_with_response_schema(self):
        """Test ToolSpec with optional response_schema."""
        spec: ToolSpec = {
            "name": "test_tool",
            "description": "A test tool with response schema",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            }
        }
        assert "response_schema" in spec
        assert spec["response_schema"]["properties"]["result"]["type"] == "string"

    def test_tool_spec_with_runtime_metadata(self):
        """Test ToolSpec with Spark runtime metadata."""
        spec: ToolSpec = {
            "name": "meta_tool",
            "description": "Includes metadata",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}},
            "x_spark": {"supports_async": True, "long_running": False},
        }
        metadata: ToolRuntimeMetadata = spec["x_spark"]
        assert metadata["supports_async"] is True


class TestTool:
    """Test cases for Tool TypedDict."""

    def test_tool_creation(self):
        """Test Tool TypedDict creation."""
        tool_spec: ToolSpec = {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
        }

        tool: Tool = {
            "toolSpec": tool_spec
        }
        assert tool["toolSpec"]["name"] == "test_tool"


class TestToolUse:
    """Test cases for ToolUse TypedDict."""

    def test_tool_use_creation(self):
        """Test ToolUse creation."""
        tool_use: ToolUse = {
            "input": {"param1": "value1", "param2": 42},
            "name": "test_tool",
            "toolUseId": "test-id-123"
        }
        assert tool_use["input"]["param1"] == "value1"
        assert tool_use["input"]["param2"] == 42
        assert tool_use["name"] == "test_tool"
        assert tool_use["toolUseId"] == "test-id-123"

    def test_tool_use_with_complex_input(self):
        """Test ToolUse with complex input data."""
        complex_input = {
            "text": "Hello",
            "numbers": [1, 2, 3],
            "nested": {
                "key": "value",
                "flag": True
            }
        }

        tool_use: ToolUse = {
            "input": complex_input,
            "name": "complex_tool",
            "toolUseId": "complex-id-456"
        }
        assert tool_use["input"]["nested"]["flag"] is True
        assert tool_use["input"]["numbers"] == [1, 2, 3]


class TestToolResult:
    """Test cases for ToolResult TypedDict."""

    def test_tool_result_success(self):
        """Test successful ToolResult."""
        result: ToolResult = {
            "content": [{"text": "Operation completed successfully"}],
            "status": "success",
            "toolUseId": "tool-id-789"
        }
        assert result["status"] == "success"
        assert result["content"][0]["text"] == "Operation completed successfully"

    def test_tool_result_error(self):
        """Test error ToolResult."""
        result: ToolResult = {
            "content": [{"text": "Error: Invalid input"}],
            "status": "error",
            "toolUseId": "tool-id-error"
        }
        assert result["status"] == "error"
        assert result["content"][0]["text"] == "Error: Invalid input"

    def test_tool_result_multiple_content_items(self):
        """Test ToolResult with multiple content items."""
        result: ToolResult = {
            "content": [
                {"text": "First result"},
                {"image": {"url": "https://example.com/image.png"}},
                {"text": "Second result"}
            ],
            "status": "success",
            "toolUseId": "multi-content-id"
        }
        assert len(result["content"]) == 3
        assert result["content"][1]["image"]["url"] == "https://example.com/image.png"

    def test_tool_result_with_metadata(self):
        """Test ToolResult optional metadata fields."""
        result: ToolResult = {
            "content": [{"text": "Working..."}],
            "status": "in_progress",
            "toolUseId": "metadata-id",
            "metadata": {"attempt": 1},
            "started_at": "2024-01-01T00:00:00Z",
            "progress": 0.5
        }
        assert result["metadata"]["attempt"] == 1
        assert result["status"] == "in_progress"


class TestToolRuntimeMetadata:
    """Test cases for runtime metadata helper."""

    def test_update_tool_runtime_metadata_sets_flags(self):
        spec: ToolSpec = {
            "name": "meta",
            "description": "meta",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}},
        }

        update_tool_runtime_metadata(spec, supports_async=True, long_running=True)

        assert spec["x_spark"]["supports_async"] is True
        assert spec["x_spark"]["long_running"] is True

    def test_update_tool_runtime_metadata_partial(self):
        spec: ToolSpec = {
            "name": "partial",
            "description": "meta",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}},
        }

        update_tool_runtime_metadata(spec, supports_async=True)
        update_tool_runtime_metadata(spec, long_running=False)

        metadata = spec["x_spark"]
        assert metadata["supports_async"] is True
        assert metadata["long_running"] is False


class TestToolChoiceTypes:
    """Test cases for ToolChoice type variants."""

    def test_tool_choice_auto(self):
        """Test ToolChoiceAuto type."""
        auto_choice: ToolChoiceAuto = {}
        assert auto_choice == {}

    def test_tool_choice_any(self):
        """Test ToolChoiceAny type."""
        any_choice: ToolChoiceAny = {}
        assert any_choice == {}

    def test_tool_choice_tool(self):
        """Test ToolChoiceTool type."""
        tool_choice: ToolChoiceTool = {
            "name": "specific_tool"
        }
        assert tool_choice["name"] == "specific_tool"

    def test_tool_choice_auto_dict(self):
        """Test ToolChoiceAutoDict type."""
        auto_dict: ToolChoiceAutoDict = {
            "auto": {}
        }
        assert "auto" in auto_dict
        assert auto_dict["auto"] == {}

    def test_tool_choice_any_dict(self):
        """Test ToolChoiceAnyDict type."""
        any_dict: ToolChoiceAnyDict = {
            "any": {}
        }
        assert "any" in any_dict
        assert any_dict["any"] == {}

    def test_tool_choice_tool_dict(self):
        """Test ToolChoiceToolDict type."""
        tool_dict: ToolChoiceToolDict = {
            "tool": {"name": "required_tool"}
        }
        assert tool_dict["tool"]["name"] == "required_tool"


class TestBaseTool:
    """Test cases for BaseTool abstract class."""

    def test_base_tool_is_abstract(self):
        """Test that BaseTool cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTool()

    def test_base_tool_implementation(self):
        """Test a concrete implementation of BaseTool."""

        class ConcreteTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "concrete_tool"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "concrete_tool",
                    "description": "A concrete tool implementation",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
                }

            @property
            def tool_type(self) -> str:
                return "test"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return "tool executed"

        tool = ConcreteTool()
        assert tool.tool_name == "concrete_tool"
        assert tool.tool_spec["name"] == "concrete_tool"
        assert tool.tool_type == "test"
        assert tool() == "tool executed"
        assert tool.supports_async is False
        assert tool.is_long_running is False

    def test_base_tool_dynamic_properties(self):
        """Test BaseTool dynamic-related properties."""

        class TestTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "test_tool"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
                }

            @property
            def tool_type(self) -> str:
                return "test"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return None

        tool = TestTool()

        # Test default values
        assert tool.is_dynamic is False
        assert tool.supports_hot_reload is False
        assert tool.supports_async is False
        assert tool.is_long_running is False

        # Test marking as dynamic
        tool.mark_dynamic()
        assert tool.is_dynamic is True

        # Test marking async support and long running flag
        tool.mark_supports_async()
        tool.mark_long_running()
        assert tool.supports_async is True
        assert tool.is_long_running is True

    def test_base_tool_display_properties(self):
        """Test BaseTool get_display_properties method."""

        class TestTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "display_tool"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "display_tool",
                    "description": "Tool for testing display properties",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
                }

            @property
            def tool_type(self) -> str:
                return "display"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return None

        tool = TestTool()
        properties = tool.get_display_properties()

        assert "Name" in properties
        assert "Type" in properties
        assert properties["Name"] == "display_tool"
        assert properties["Type"] == "display"
        assert properties["Async"] == "no"
        assert properties["Long Running"] == "no"

    @pytest.mark.asyncio
    async def test_base_tool_default_acall_calls_sync(self):
        """Default acall should defer to __call__."""

        class TestTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "async_default"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "async_default",
                    "description": "Default acall",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
                }

            @property
            def tool_type(self) -> str:
                return "test"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return "sync result"

        tool = TestTool()
        result = await tool.acall()
        assert result == "sync result"
