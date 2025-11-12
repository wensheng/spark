"""Unit tests for spark.tools.decorator module."""

import pytest
import inspect
from typing import Any
from unittest.mock import Mock, patch

from spark.tools.decorator import (
    ToolContext,
    FunctionToolMetadata,
    DecoratedFunctionTool,
    tool,
)
from spark.tools.types import ToolSpec, ToolUse


class TestToolContext:
    """Test cases for ToolContext dataclass."""

    def test_tool_context_creation(self):
        """Test ToolContext creation and attributes."""
        tool_use: ToolUse = {
            "input": {"param": "value"},
            "name": "test_tool",
            "toolUseId": "test-id-123"
        }
        invocation_state = {"user": "test_user", "session": "abc123"}

        context = ToolContext(tool_use=tool_use, invocation_state=invocation_state)

        assert context.tool_use == tool_use
        assert context.invocation_state == invocation_state
        assert context.tool_use["toolUseId"] == "test-id-123"
        assert context.invocation_state["user"] == "test_user"

    def test_tool_context_empty_invocation_state(self):
        """Test ToolContext with empty invocation state."""
        tool_use: ToolUse = {
            "input": {},
            "name": "test_tool",
            "toolUseId": "test-id-456"
        }

        context = ToolContext(tool_use=tool_use, invocation_state={})

        assert context.tool_use["name"] == "test_tool"
        assert context.invocation_state == {}


class TestFunctionToolMetadata:
    """Test cases for FunctionToolMetadata class."""

    def test_simple_function_metadata(self):
        """Test metadata extraction for a simple function."""

        def simple_func(name: str, count: int = 1) -> str:
            """A simple test function.

            Args:
                name: The name to process
                count: Number of times to process (default: 1)

            Returns:
                A processed string
            """
            return f"Processed {name} {count} times"

        metadata = FunctionToolMetadata(simple_func)

        # Test basic attributes
        assert metadata.func == simple_func
        assert metadata._context_param is None

        # Test signature parsing
        assert "name" in metadata.signature.parameters
        assert "count" in metadata.signature.parameters

        # Test type hints
        assert metadata.type_hints["name"] == str
        assert metadata.type_hints["count"] == int
        assert metadata.type_hints["return"] == str

        # Test parameter descriptions
        assert "name" in metadata.param_descriptions
        assert "count" in metadata.param_descriptions
        assert "The name to process" in metadata.param_descriptions["name"]
        assert "Number of times to process" in metadata.param_descriptions["count"]

    def test_function_no_docstring(self):
        """Test metadata extraction for function without docstring."""

        def no_doc_func(param: int) -> bool:
            return param > 0

        metadata = FunctionToolMetadata(no_doc_func)

        # Should handle missing docstring gracefully
        assert metadata.func == no_doc_func
        assert metadata.doc.short_description is None
        assert metadata.param_descriptions == {}

    def test_function_with_context_param(self):
        """Test metadata extraction with context parameter."""

        def context_func(data: str, tool_context: ToolContext) -> str:
            """Function with tool context parameter.

            Args:
                data: Input data to process
                tool_context: The tool context
            """
            return f"Processed {data}"

        metadata = FunctionToolMetadata(context_func, context_param="tool_context")

        assert metadata._context_param == "tool_context"

        # Test input model creation excludes special parameters
        input_model = metadata.input_model
        model_fields = input_model.model_fields
        assert "data" in model_fields
        assert "tool_context" not in model_fields  # Should be excluded

    def test_method_with_self_parameter(self):
        """Test metadata extraction for class method."""

        class TestClass:
            def method_func(self, value: str) -> str:
                """Instance method.

                Args:
                    value: The value to process
                """
                return f"Method processed {value}"

        metadata = FunctionToolMetadata(TestClass.method_func)

        # 'self' should be recognized as special parameter
        assert metadata._is_special_parameter("self")
        assert not metadata._is_special_parameter("value")

    def test_create_input_model_no_params(self):
        """Test input model creation for function with no parameters."""

        def no_params_func() -> str:
            """Function with no parameters."""
            return "result"

        metadata = FunctionToolMetadata(no_params_func)
        input_model = metadata.input_model

        # Should create a model even with no parameters
        assert input_model is not None
        assert len(input_model.model_fields) == 0

    def test_create_input_model_with_defaults(self):
        """Test input model creation with default values."""

        def defaults_func(
            required: str,
            optional: int = 10,
            flag: bool = True
        ) -> str:
            """Function with default values.

            Args:
                required: Required parameter
                optional: Optional parameter with default
                flag: Boolean flag with default
            """
            return f"{required}-{optional}-{flag}"

        metadata = FunctionToolMetadata(defaults_func)
        input_model = metadata.input_model

        # Test field creation
        fields = input_model.model_fields
        assert "required" in fields
        assert "optional" in fields
        assert "flag" in fields

        # Test that defaults are preserved
        # Note: Pydantic stores default info in field objects
        # The actual default values would be accessible through field.default

    def test_extract_metadata(self):
        """Test metadata extraction to ToolSpec."""

        def extract_func(name: str, age: int) -> str:
            """Function for metadata extraction.

            Args:
                name: Person's name
                age: Person's age

            Returns:
                A formatted string
            """
            return f"{name} is {age} years old"

        metadata = FunctionToolMetadata(extract_func)
        tool_spec = metadata.extract_metadata()

        # Test ToolSpec structure
        assert isinstance(tool_spec, dict)
        assert tool_spec["name"] == "extract_func"
        assert "Function for metadata extraction" in tool_spec["description"]
        assert "parameters" in tool_spec
        assert "json" in tool_spec["parameters"]

        # Test JSON schema structure
        json_schema = tool_spec["parameters"]["json"]
        assert json_schema["type"] == "object"
        assert "properties" in json_schema
        assert "required" in json_schema

    def test_clean_pydantic_schema(self):
        """Test Pydantic schema cleanup."""

        def cleanup_func(data: str, optional: int = None) -> str:
            """Function for schema cleanup testing.

            Args:
                data: Input data
                optional: Optional integer parameter
            """
            return data

        metadata = FunctionToolMetadata(cleanup_func)
        tool_spec = metadata.extract_metadata()

        # Get the schema and verify cleanup
        json_schema = tool_spec["parameters"]["json"]

        # Should not have Pydantic-specific metadata
        assert "title" not in json_schema
        assert "additionalProperties" not in json_schema

    def test_validate_input_success(self):
        """Test successful input validation."""

        def validate_func(name: str, count: int = 1) -> str:
            """Function for validation testing.

            Args:
                name: Name parameter
                count: Count parameter with default
            """
            return f"{name} x {count}"

        metadata = FunctionToolMetadata(validate_func)

        # Test valid input
        valid_input = {"name": "test", "count": 5}
        validated = metadata.validate_input(valid_input)
        assert validated["name"] == "test"
        assert validated["count"] == 5

        # Test input with default value
        input_with_default = {"name": "test"}
        validated = metadata.validate_input(input_with_default)
        assert validated["name"] == "test"
        assert validated["count"] == 1  # Should use default

    def test_validate_input_failure(self):
        """Test input validation failure."""

        def validate_func(name: str, count: int) -> str:
            """Function requiring both parameters."""
            return f"{name} x {count}"

        metadata = FunctionToolMetadata(validate_func)

        # Test missing required parameter
        invalid_input = {"name": "test"}  # Missing required 'count'
        with pytest.raises(ValueError, match="Validation failed"):
            metadata.validate_input(invalid_input)

        # Test wrong type
        wrong_type_input = {"name": "test", "count": "not_a_number"}
        with pytest.raises(ValueError, match="Validation failed"):
            metadata.validate_input(wrong_type_input)

    def test_inject_special_parameters(self):
        """Test special parameter injection."""

        def inject_func(data: str, tool_context: ToolContext) -> str:
            """Function with context injection."""
            return data

        metadata = FunctionToolMetadata(inject_func, context_param="tool_context")

        tool_use: ToolUse = {
            "input": {},
            "name": "inject_func",
            "toolUseId": "inject-123"
        }
        invocation_state = {"user": "test_user"}

        validated_input = {"data": "test_data"}

        # Test injection
        metadata.inject_special_parameters(validated_input, tool_use, invocation_state)

        assert "tool_context" in validated_input
        assert isinstance(validated_input["tool_context"], ToolContext)
        assert validated_input["tool_context"].tool_use["toolUseId"] == "inject-123"

    def test_is_special_parameter(self):
        """Test special parameter detection."""

        def special_func(self, cls, agent, tool_context, normal_param) -> None:
            pass

        metadata = FunctionToolMetadata(special_func, context_param="tool_context")

        # Test recognized special parameters
        assert metadata._is_special_parameter("self")
        assert metadata._is_special_parameter("cls")
        assert metadata._is_special_parameter("agent")
        assert metadata._is_special_parameter("tool_context")
        assert not metadata._is_special_parameter("normal_param")

        # Test without context parameter
        metadata_no_context = FunctionToolMetadata(special_func)
        assert metadata_no_context._is_special_parameter("self")
        assert not metadata_no_context._is_special_parameter("tool_context")


class TestDecoratedFunctionTool:
    """Test cases for DecoratedFunctionTool class."""

    def test_decorated_function_tool_creation(self):
        """Test DecoratedFunctionTool creation and basic properties."""

        def test_func(param: str) -> str:
            """Test function."""
            return f"Processed {param}"

        metadata = FunctionToolMetadata(test_func)
        tool_spec = metadata.extract_metadata()

        decorated_tool = DecoratedFunctionTool(
            tool_name="test_tool",
            tool_spec=tool_spec,
            tool_func=test_func,
            metadata=metadata
        )

        assert decorated_tool.tool_name == "test_tool"
        assert decorated_tool.tool_spec == tool_spec
        assert decorated_tool.tool_type == "function"
        assert decorated_tool.supports_hot_reload is True
        assert decorated_tool.is_dynamic is False

    def test_decorated_function_tool_call(self):
        """Test calling the decorated function tool."""

        def test_func(param: str, count: int = 1) -> str:
            """Test function with parameters."""
            return f"Processed {param} {count} times"

        metadata = FunctionToolMetadata(test_func)
        tool_spec = metadata.extract_metadata()

        decorated_tool = DecoratedFunctionTool(
            tool_name="test_tool",
            tool_spec=tool_spec,
            tool_func=test_func,
            metadata=metadata
        )

        # Test direct function call
        result = decorated_tool("hello", count=3)
        assert result == "Processed hello 3 times"

        # Test call with keyword arguments
        result = decorated_tool(param="world", count=2)
        assert result == "Processed world 2 times"

    def test_decorated_function_tool_descriptor(self):
        """Test descriptor protocol for method binding."""

        class TestClass:
            def __init__(self, value: str):
                self.value = value

            @tool  # Apply the decorator to get the descriptor behavior
            def instance_method(self, param: str) -> str:
                """Instance method."""
                return f"{self.value}: {param}"

        # Test accessing through class
        class_tool = TestClass.instance_method
        assert hasattr(class_tool, 'tool_name')

        # Test accessing through instance
        instance = TestClass("test")
        instance_tool = instance.instance_method
        assert hasattr(instance_tool, 'tool_name')

        # Test bound method call
        result = instance_tool("param")
        assert result == "test: param"

    def test_get_display_properties(self):
        """Test get_display_properties method."""

        def display_func(data: str) -> str:
            """Function for display testing."""
            return data

        metadata = FunctionToolMetadata(display_func)
        tool_spec = metadata.extract_metadata()

        decorated_tool = DecoratedFunctionTool(
            tool_name="display_tool",
            tool_spec=tool_spec,
            tool_func=display_func,
            metadata=metadata
        )

        properties = decorated_tool.get_display_properties()

        assert "Name" in properties
        assert "Type" in properties
        assert "Function" in properties
        assert properties["Name"] == "display_tool"
        assert properties["Type"] == "function"
        assert properties["Function"] == "display_func"

    def test_prepare_tool_kwargs(self):
        """prepare_tool_kwargs should validate and inject context."""

        @tool(context=True)
        def sample_tool(data: str, tool_context: ToolContext) -> str:
            return data

        tool_use: ToolUse = {
            "name": "sample_tool",
            "toolUseId": "tool-id",
            "input": {"data": "value"},
        }
        invocation_state = {"agent": "tester"}

        kwargs = sample_tool.prepare_tool_kwargs(tool_use, invocation_state)

        assert kwargs["data"] == "value"
        assert "tool_context" in kwargs
        assert kwargs["tool_context"].tool_use["toolUseId"] == "tool-id"

    def test_prepare_tool_kwargs_invalid_input(self):
        """prepare_tool_kwargs should error on non-object payloads."""

        @tool
        def sample_tool(data: str) -> str:
            return data

        tool_use: ToolUse = {"name": "sample_tool", "toolUseId": "bad", "input": "oops"}

        with pytest.raises(ValueError, match="expects object input"):
            sample_tool.prepare_tool_kwargs(tool_use, {})

    @pytest.mark.asyncio
    async def test_decorated_function_tool_acall_async(self):
        """Async decorated functions should be awaited via acall."""

        async def async_func(param: str) -> str:
            return f"Async {param}"

        metadata = FunctionToolMetadata(async_func)
        tool_spec = metadata.extract_metadata()

        decorated_tool = DecoratedFunctionTool(
            tool_name="async_tool",
            tool_spec=tool_spec,
            tool_func=async_func,
            metadata=metadata,
        )

        assert decorated_tool.supports_async is True
        assert decorated_tool.tool_spec["x_spark"]["supports_async"] is True
        result = await decorated_tool.acall("value")
        assert result == "Async value"

    @pytest.mark.asyncio
    async def test_decorated_function_tool_call_in_loop_requires_acall(self):
        """Calling async tools synchronously in running loop should raise."""

        async def async_func() -> str:
            return "async"

        metadata = FunctionToolMetadata(async_func)
        tool_spec = metadata.extract_metadata()
        decorated_tool = DecoratedFunctionTool(
            tool_name="loop_tool",
            tool_spec=tool_spec,
            tool_func=async_func,
            metadata=metadata,
        )

        with pytest.raises(RuntimeError, match="acall"):
            decorated_tool()

    def test_decorated_function_tool_long_running_metadata(self):
        """Long running flag should propagate to metadata."""

        def simple_func() -> str:
            return "value"

        metadata = FunctionToolMetadata(simple_func)
        tool_spec = metadata.extract_metadata()

        decorated_tool = DecoratedFunctionTool(
            tool_name="long_tool",
            tool_spec=tool_spec,
            tool_func=simple_func,
            metadata=metadata,
            long_running=True,
        )

        assert decorated_tool.is_long_running is True
        assert decorated_tool.tool_spec["x_spark"]["long_running"] is True


class TestToolDecorator:
    """Test cases for the @tool decorator."""

    def test_tool_decorator_without_parameters(self):
        """Test @tool decorator without parameters."""

        @tool
        def simple_tool(name: str) -> str:
            """Simple tool for testing.

            Args:
                name: Input name

            Returns:
                Greeting message
            """
            return f"Hello {name}"

        # Should return DecoratedFunctionTool
        assert hasattr(simple_tool, 'tool_name')
        assert simple_tool.tool_name == "simple_tool"
        assert simple_tool.tool_type == "function"

        # Should still be callable as original function
        result = simple_tool("World")
        assert result == "Hello World"

    def test_tool_decorator_with_custom_name(self):
        """Test @tool decorator with custom name."""

        @tool(name="custom_tool_name")
        def original_name(data: str) -> str:
            """Function with custom tool name."""
            return data

        assert original_name.tool_name == "custom_tool_name"

    def test_tool_decorator_with_custom_description(self):
        """Test @tool decorator with custom description."""

        @tool(description="This is a custom description")
        def func_with_desc(param: str) -> str:
            """Original docstring."""
            return param

        assert func_with_desc.tool_spec["description"] == "This is a custom description"

    def test_tool_decorator_with_context_true(self):
        """Test @tool decorator with context=True."""

        @tool(context=True)
        def context_tool(data: str, tool_context: ToolContext) -> str:
            """Tool with default context parameter."""
            tool_id = tool_context.tool_use["toolUseId"]
            return f"{data} (ID: {tool_id})"

        assert context_tool.tool_name == "context_tool"

    def test_tool_decorator_with_custom_context_param(self):
        """Test @tool decorator with custom context parameter name."""

        @tool(context="my_context")
        def custom_context_tool(data: str, my_context: ToolContext) -> str:
            """Tool with custom context parameter."""
            return data

        assert custom_context_tool.tool_name == "custom_context_tool"

    def test_tool_decorator_empty_context_name(self):
        """Test @tool decorator with empty context parameter name raises error."""

        with pytest.raises(ValueError, match="Context parameter name cannot be empty"):
            @tool(context="")
            def invalid_tool(data: str) -> str:
                return data

    def test_tool_decorator_non_string_tool_name(self):
        """Test @tool decorator with non-string tool name raises error."""

        with pytest.raises(ValueError, match="Tool name must be a string"):
            @tool(name=123)  # type: ignore
            def invalid_name_tool(data: str) -> str:
                return data

    def test_tool_decorator_method(self):
        """Test @tool decorator on class method."""

        class TestClass:
            @tool
            def method_tool(self, param: str) -> str:
                """Method tool."""
                return f"Method: {param}"

        instance = TestClass()
        result = instance.method_tool("test")
        assert result == "Method: test"

    def test_tool_decorator_no_docstring(self):
        """Test @tool decorator on function without docstring."""

        @tool
        def no_doc_tool(param: int) -> int:
            return param * 2

        # Should handle missing docstring gracefully
        assert no_doc_tool.tool_name == "no_doc_tool"
        assert no_doc_tool.tool_spec["description"] == "no_doc_tool"

    @pytest.mark.asyncio
    async def test_tool_decorator_async_function(self):
        """Async @tool functions should set metadata and support acall."""

        @tool
        async def async_tool(name: str) -> str:
            return f"hello {name}"

        assert async_tool.supports_async is True
        assert async_tool.tool_spec["x_spark"]["supports_async"] is True
        result = await async_tool.acall("spark")
        assert result == "hello spark"

    def test_tool_decorator_long_running_flag(self):
        """long_running hint should propagate to metadata."""

        @tool(long_running=True)
        def slow_tool() -> str:
            return "done"

        assert slow_tool.is_long_running is True
        assert slow_tool.tool_spec["x_spark"]["long_running"] is True

    def test_tool_decorator_async_execution_override(self):
        """async_execution flag should force metadata even for sync functions."""

        @tool(async_execution=True)
        def sync_tool() -> str:
            return "ok"

        assert sync_tool.supports_async is True
        assert sync_tool.tool_spec["x_spark"]["supports_async"] is True
