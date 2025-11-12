"""Unit tests for spark.tools.tools module."""

import asyncio
from typing import Any
from unittest.mock import Mock

import pytest

from spark.tools.tools import (
    InvalidToolUseNameException,
    validate_tool_use,
    validate_tool_use_name,
    normalize_schema,
    normalize_tool_spec,
    PythonAgentTool,
    ToolFunc,
)
from spark.tools.types import ToolResult, ToolSpec, ToolUse


class TestInvalidToolUseNameException:
    """Test cases for InvalidToolUseNameException."""

    def test_exception_creation(self):
        """Test exception creation and message."""
        message = "Invalid tool name"
        exception = InvalidToolUseNameException(message)

        assert str(exception) == message
        assert isinstance(exception, Exception)


class TestValidateToolUse:
    """Test cases for validate_tool_use function."""

    def test_validate_tool_use_valid(self):
        """Test validating a valid tool use."""
        valid_tool: ToolUse = {
            "input": {"param": "value"},
            "name": "valid_tool_name",
            "toolUseId": "test-id-123"
        }

        # Should not raise any exceptions
        validate_tool_use(valid_tool)

    def test_validate_tool_use_missing_name(self):
        """Test validating tool use with missing name."""
        invalid_tool: ToolUse = {
            "input": {"param": "value"},
            # Missing "name"
            "toolUseId": "test-id-123"
        }

        with pytest.raises(InvalidToolUseNameException, match="tool name missing"):
            validate_tool_use(invalid_tool)


class TestValidateToolUseName:
    """Test cases for validate_tool_use_name function."""

    def test_validate_name_valid(self):
        """Test validating valid tool names."""
        valid_names = [
            "valid_tool",
            "ValidTool123",
            "tool-with-dashes",
            "tool_with_underscores",
            "a",  # Single character
            "A",  # Single uppercase character
            "tool123name",
        ]

        for name in valid_names:
            tool: ToolUse = {
                "input": {},
                "name": name,
                "toolUseId": "test-id"
            }

            # Should not raise any exceptions
            validate_tool_use_name(tool)

    def test_validate_name_invalid_characters(self):
        """Test validating tool names with invalid characters."""
        invalid_names = [
            "tool with spaces",
            "tool@withsymbols",
            "tool#hash",
            "tool.dot",
            "tool/slash",
            "tool\\backslash",
            "tool(parentheses)",
            "tool[brackets]",
            "tool{braces}",
            "tool+p lus",
            "tool*star",
            "tool%percent",
            "tool=equals",
            "tool|pipe",
            "tool?question",
            "tool!exclamation",
            "",  # Empty string
        ]

        for name in invalid_names:
            tool: ToolUse = {
                "input": {},
                "name": name,
                "toolUseId": "test-id"
            }

            with pytest.raises(InvalidToolUseNameException, match="invalid tool name pattern"):
                validate_tool_use_name(tool)

    def test_validate_name_too_long(self):
        """Test validating tool name that exceeds maximum length."""
        # Create a name longer than 64 characters
        long_name = "a" * 65

        tool: ToolUse = {
            "input": {},
            "name": long_name,
            "toolUseId": "test-id"
        }

        with pytest.raises(InvalidToolUseNameException, match="invalid tool name length"):
            validate_tool_use_name(tool)

    def test_validate_name_maximum_length(self):
        """Test validating tool name at maximum length (64 characters)."""
        max_length_name = "a" * 64

        tool: ToolUse = {
            "input": {},
            "name": max_length_name,
            "toolUseId": "test-id"
        }

        # Should not raise any exceptions
        validate_tool_use_name(tool)

    def test_validate_name_missing(self):
        """Test validating tool use with missing name field."""
        tool: ToolUse = {
            "input": {},
            # "name" field missing
            "toolUseId": "test-id"
        }

        with pytest.raises(InvalidToolUseNameException, match="tool name missing"):
            validate_tool_use_name(tool)


class TestNormalizeSchema:
    """Test cases for normalize_schema function."""

    def test_normalize_schema_empty(self):
        """Test normalizing empty schema."""
        schema = {}
        normalized = normalize_schema(schema)

        assert normalized["type"] == "object"
        assert normalized["properties"] == {}
        assert normalized["required"] == []

    def test_normalize_schema_with_existing_fields(self):
        """Test normalizing schema with existing fields."""
        schema = {
            "type": "object",
            "properties": {
                "existing_prop": {
                    "type": "string",
                    "description": "Existing property"
                }
            },
            "required": ["existing_prop"],
            "additionalField": "should_be_preserved"
        }

        normalized = normalize_schema(schema)

        assert normalized["type"] == "object"
        assert "existing_prop" in normalized["properties"]
        assert normalized["required"] == ["existing_prop"]
        assert normalized["additionalField"] == "should_be_preserved"

    def test_normalize_schema_with_properties(self):
        """Test normalizing schema with properties."""
        schema = {
            "properties": {
                "simple_prop": "string_value",  # Not a dict
                "object_prop": {
                    "type": "object",
                    "properties": {
                        "nested_prop": "nested_value"
                    }
                },
                "ref_prop": {
                    "$ref": "#/definitions/SomeType"
                }
            }
        }

        normalized = normalize_schema(schema)

        # Check simple property normalization
        assert normalized["properties"]["simple_prop"]["type"] == "string"
        assert normalized["properties"]["simple_prop"]["description"] == "Property simple_prop"

        # Check object property recursion
        assert normalized["properties"]["object_prop"]["type"] == "object"
        assert "nested_prop" in normalized["properties"]["object_prop"]["properties"]

        # Check $ref property preservation
        assert normalized["properties"]["ref_prop"]["$ref"] == "#/definitions/SomeType"

    def test_normalize_schema_nested_objects(self):
        """Test normalizing schema with nested objects."""
        schema = {
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": "final_value"
                            }
                        }
                    }
                }
            }
        }

        normalized = normalize_schema(schema)

        # Check deep nesting
        level1 = normalized["properties"]["level1"]
        level2 = level1["properties"]["level2"]
        level3 = level2["properties"]["level3"]

        assert level1["type"] == "object"
        assert level2["type"] == "object"
        assert level3["type"] == "string"
        assert level3["description"] == "Property level3"

    def test_normalize_schema_preserves_non_defaults(self):
        """Test that normalize_schema preserves non-default values."""
        schema = {
            "properties": {
                "custom_prop": {
                    "type": "integer",
                    "description": "Custom description",
                    "minimum": 0,
                    "maximum": 100,
                    "customField": "custom value"
                }
            }
        }

        normalized = normalize_schema(schema)

        prop = normalized["properties"]["custom_prop"]
        assert prop["type"] == "integer"  # Preserved
        assert prop["description"] == "Custom description"  # Preserved
        assert prop["minimum"] == 0  # Preserved
        assert prop["maximum"] == 100  # Preserved
        assert prop["customField"] == "custom value"  # Preserved


class TestNormalizeToolSpec:
    """Test cases for normalize_tool_spec function."""

    def test_normalize_tool_spec_without_parameters(self):
        """Test normalizing tool spec without parameters."""
        tool_spec: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool without parameters"
        }

        normalized = normalize_tool_spec(tool_spec)

        assert normalized["name"] == "test_tool"
        assert normalized["description"] == "Test tool without parameters"
        assert "parameters" not in normalized

    def test_normalize_tool_spec_with_json_parameters(self):
        """Test normalizing tool spec with json parameters already in correct format."""
        tool_spec: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool with json parameters",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string"}
                    },
                    "required": ["param1"]
                }
            }
        }

        normalized = normalize_tool_spec(tool_spec)

        # Should preserve the structure but normalize inner schema
        assert "json" in normalized["parameters"]
        assert normalized["parameters"]["json"]["type"] == "object"
        assert "param1" in normalized["parameters"]["json"]["properties"]

    def test_normalize_tool_spec_with_direct_parameters(self):
        """Test normalizing tool spec with direct parameters (not wrapped in json)."""
        tool_spec: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool with direct parameters",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string"}
                },
                "required": ["param1"]
            }
        }

        normalized = normalize_tool_spec(tool_spec)

        # Should wrap in json format
        assert "json" in normalized["parameters"]
        assert normalized["parameters"]["json"]["type"] == "object"
        assert "param1" in normalized["parameters"]["json"]["properties"]

    def test_normalize_tool_spec_preserves_other_fields(self):
        """Test that normalization preserves other tool spec fields."""
        tool_spec: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool with extra fields",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {}
                }
            },
            "response_schema": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            }
        }

        normalized = normalize_tool_spec(tool_spec)

        assert normalized["name"] == "test_tool"
        assert normalized["description"] == "Test tool with extra fields"
        assert "response_schema" in normalized
        assert normalized["response_schema"]["properties"]["result"]["type"] == "string"


class TestToolFunc:
    """Test cases for ToolFunc protocol."""

    def test_tool_func_protocol_compliance(self):
        """Test that a function complying with ToolFunc protocol works correctly."""

        def test_tool_func(*args: Any, **kwargs: Any) -> ToolResult:
            """Mock tool function."""
            return {
                "content": [{"text": "Tool executed"}],
                "status": "success",
                "toolUseId": kwargs.get("tool_use_id", "default-id")
            }

        # Should have required attributes
        assert hasattr(test_tool_func, "__name__")
        assert callable(test_tool_func)

        # Should be callable with ToolFunc signature
        result = test_tool_func(tool_use_id="test-123")
        assert result["status"] == "success"
        assert result["toolUseId"] == "test-123"

    def test_tool_func_with_attributes(self):
        """Test ToolFunc with additional attributes."""

        def decorated_tool(*args: Any, **kwargs: Any) -> ToolResult:
            """Decorated tool function."""
            return {
                "content": [{"text": "Decorated tool"}],
                "status": "success",
                "toolUseId": "decorated-id"
            }

        # Add additional attributes that might be set by decorators
        decorated_tool.tool_name = "decorated_tool"
        decorated_tool.tool_spec = {
            "name": "decorated_tool",
            "description": "A decorated tool",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
        }

        assert decorated_tool.tool_name == "decorated_tool"
        assert isinstance(decorated_tool.tool_spec, dict)


class TestPythonAgentTool:
    """Test cases for PythonAgentTool class."""

    def test_python_agent_tool_creation(self):
        """Test PythonAgentTool creation and basic properties."""

        def mock_tool_func(param: str, count: int = 1) -> ToolResult:
            """Mock Python tool function."""
            return {
                "content": [{"text": f"Processed {param} {count} times"}],
                "status": "success",
                "toolUseId": "python-tool-id"
            }

        tool_spec: ToolSpec = {
            "name": "python_tool",
            "description": "A Python-based tool",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "param": {"type": "string"},
                        "count": {"type": "integer", "default": 1}
                    },
                    "required": ["param"]
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="python_tool",
            tool_spec=tool_spec,
            tool_func=mock_tool_func
        )

        assert python_tool.tool_name == "python_tool"
        assert python_tool.tool_spec == tool_spec
        assert python_tool.tool_type == "python"
        assert python_tool.supports_hot_reload is True
        assert python_tool.is_dynamic is False
        assert python_tool.supports_async is False

    def test_python_agent_tool_call(self):
        """Test calling PythonAgentTool."""

        def mock_tool_func(message: str) -> ToolResult:
            """Mock tool function."""
            return {
                "content": [{"text": f"Python tool: {message}"}],
                "status": "success",
                "toolUseId": "call-test-id"
            }

        tool_spec: ToolSpec = {
            "name": "callable_tool",
            "description": "Tool for testing calls",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"}
                    },
                    "required": ["message"]
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="callable_tool",
            tool_spec=tool_spec,
            tool_func=mock_tool_func
        )

        # Test calling the tool
        result = python_tool("Hello World")
        assert result["status"] == "success"
        assert result["content"][0]["text"] == "Python tool: Hello World"

        # Test calling with keyword arguments
        result = python_tool(message="Keyword Args")
        assert result["content"][0]["text"] == "Python tool: Keyword Args"

    def test_python_agent_tool_inheritance(self):
        """Test that PythonAgentTool properly inherits from BaseTool."""

        def simple_func() -> ToolResult:
            return {
                "content": [{"text": "Simple"}],
                "status": "success",
                "toolUseId": "simple-id"
            }

        tool_spec: ToolSpec = {
            "name": "inheritance_tool",
            "description": "Tool for testing inheritance",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="inheritance_tool",
            tool_spec=tool_spec,
            tool_func=simple_func
        )

        # Test BaseTool methods
        assert hasattr(python_tool, 'get_display_properties')
        properties = python_tool.get_display_properties()
        assert "Name" in properties
        assert "Type" in properties
        assert properties["Name"] == "inheritance_tool"
        assert properties["Type"] == "python"
        assert properties["Async"] == "no"
        assert properties["Long Running"] == "no"

        # Test dynamic tool methods
        assert python_tool.is_dynamic is False
        python_tool.mark_dynamic()
        assert python_tool.is_dynamic is True

    def test_python_agent_tool_display_properties(self):
        """Test get_display_properties for PythonAgentTool."""

        def display_tool_func() -> ToolResult:
            return {
                "content": [{"text": "Display test"}],
                "status": "success",
                "toolUseId": "display-id"
            }

        tool_spec: ToolSpec = {
            "name": "display_properties_tool",
            "description": "Tool for testing display properties",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="display_properties_tool",
            tool_spec=tool_spec,
            tool_func=display_tool_func
        )

        properties = python_tool.get_display_properties()

        # Should include base properties
        assert "Name" in properties
        assert "Type" in properties
        assert properties["Name"] == "display_properties_tool"
        assert properties["Type"] == "python"
        assert properties["Async"] == "no"
        assert properties["Long Running"] == "no"

        # Should not include Function property (that's specific to DecoratedFunctionTool)
        assert "Function" not in properties

    @pytest.mark.asyncio
    async def test_python_agent_tool_acall_async_function(self):
        """Async functions should be awaited via acall."""

        async def async_tool_func(message: str) -> ToolResult:
            return {
                "content": [{"text": f"Async says: {message}"}],
                "status": "success",
                "toolUseId": "async-id"
            }

        tool_spec: ToolSpec = {
            "name": "async_tool",
            "description": "An async Python tool",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"]
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="async_tool",
            tool_spec=tool_spec,
            tool_func=async_tool_func
        )

        assert python_tool.supports_async is True
        result = await python_tool.acall("hello")
        assert result["toolUseId"] == "async-id"
        assert "Async says: hello" in result["content"][0]["text"]
        assert python_tool.tool_spec["x_spark"]["supports_async"] is True

    @pytest.mark.asyncio
    async def test_python_agent_tool_calling_async_sync_context_in_running_loop(self):
        """Calling async tool synchronously inside a running loop should fail."""

        async def async_tool_func() -> ToolResult:
            return {
                "content": [{"text": "hi"}],
                "status": "success",
                "toolUseId": "async-loop-id"
            }

        tool_spec: ToolSpec = {
            "name": "loop_tool",
            "description": "Loop test",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}}
        }

        python_tool = PythonAgentTool(
            tool_name="loop_tool",
            tool_spec=tool_spec,
            tool_func=async_tool_func
        )

        with pytest.raises(RuntimeError, match="acall"):
            python_tool()

    @pytest.mark.asyncio
    async def test_python_agent_tool_acall_sync_function_runs_in_thread(self):
        """acall should support sync functions by running them in a thread."""
        call_counter = {"count": 0}

        def sync_tool_func(value: str) -> ToolResult:
            call_counter["count"] += 1
            return {
                "content": [{"text": value.upper()}],
                "status": "success",
                "toolUseId": "sync-id"
            }

        tool_spec: ToolSpec = {
            "name": "sync_tool",
            "description": "Sync tool",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"]
                }
            }
        }

        python_tool = PythonAgentTool(
            tool_name="sync_tool",
            tool_spec=tool_spec,
            tool_func=sync_tool_func
        )

        result = await python_tool.acall("abc")
        assert result["content"][0]["text"] == "ABC"
        assert call_counter["count"] == 1
        assert python_tool.supports_async is False

    def test_python_agent_tool_long_running_metadata(self):
        """Long running flag should propagate to metadata."""

        def tool_func() -> ToolResult:
            return {"content": [{"text": "ok"}], "status": "success", "toolUseId": "lr"}

        tool_spec: ToolSpec = {
            "name": "long_runner",
            "description": "LR",
            "parameters": {"json": {"type": "object", "properties": {}, "required": []}},
        }

        python_tool = PythonAgentTool(
            tool_name="long_runner",
            tool_spec=tool_spec,
            tool_func=tool_func,
            long_running=True,
        )

        assert python_tool.is_long_running is True
        assert python_tool.tool_spec["x_spark"]["long_running"] is True
