"""Unit tests for tool decorator and context injection."""

import json
import pytest
from typing import Any
from unittest.mock import MagicMock

from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.tools.decorator import (
    tool,
    ToolContext,
    DecoratedFunctionTool,
    FunctionToolMetadata,
)
from spark.tools.types import ToolSpec
from spark.models.echo import EchoModel


class TestToolDecorator:
    """Test the @tool decorator basic functionality."""

    def test_simple_tool_without_params(self):
        """Test decorating a simple function without parameters."""

        @tool
        def simple_tool() -> str:
            """A simple tool."""
            return "success"

        assert isinstance(simple_tool, DecoratedFunctionTool)
        assert simple_tool.tool_name == "simple_tool"
        assert simple_tool.tool_spec["name"] == "simple_tool"
        assert simple_tool.tool_spec["description"] == "A simple tool."
        # Test direct call
        assert simple_tool() == "success"

    def test_tool_with_params(self):
        """Test decorating a function with parameters."""

        @tool
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together.

            Args:
                a: First number
                b: Second number

            Returns:
                Sum of the numbers
            """
            return a + b

        assert isinstance(add_numbers, DecoratedFunctionTool)
        assert add_numbers.tool_name == "add_numbers"

        # Test direct call
        result = add_numbers(5, 3)
        assert result == 8

        # Check schema has properties
        schema = add_numbers.tool_spec["parameters"]["json"]
        assert "properties" in schema
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]

    def test_tool_with_optional_params(self):
        """Test tool with optional parameters."""

        @tool
        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone.

            Args:
                name: Person to greet
                greeting: Greeting to use (default: Hello)

            Returns:
                Greeting message
            """
            return f"{greeting}, {name}!"

        # Test with both params
        assert greet("Alice", "Hi") == "Hi, Alice!"
        # Test with default
        assert greet("Bob") == "Hello, Bob!"

        # Check schema
        schema = greet.tool_spec["parameters"]["json"]
        assert "name" in schema["properties"]
        assert "greeting" in schema["properties"]
        # name should be required, greeting optional
        assert "name" in schema.get("required", [])

    def test_tool_with_custom_name_and_description(self):
        """Test tool decorator with custom name and description."""

        @tool(name="custom_name", description="Custom description")
        def my_tool() -> str:
            """Original description."""
            return "result"

        assert my_tool.tool_name == "custom_name"
        assert my_tool.tool_spec["name"] == "custom_name"
        assert my_tool.tool_spec["description"] == "Custom description"

    def test_tool_properties(self):
        """Test DecoratedFunctionTool properties."""

        @tool
        def test_tool() -> str:
            """Test tool."""
            return "test"

        assert test_tool.tool_type == "function"
        assert test_tool.supports_hot_reload is True
        assert isinstance(test_tool.tool_spec, dict)
        assert "name" in test_tool.tool_spec
        assert "description" in test_tool.tool_spec


class TestToolContext:
    """Test tool context injection functionality."""

    def test_tool_with_context_param(self):
        """Test tool decorated with context=True."""

        @tool(context=True)
        def context_tool(tool_context: ToolContext) -> str:
            """Tool that uses context.

            Returns:
                Context info
            """
            return f"Tool ID: {tool_context.tool_use.get('toolUseId')}"

        assert isinstance(context_tool, DecoratedFunctionTool)
        assert context_tool._metadata._context_param == "tool_context"

    def test_tool_with_custom_context_param_name(self):
        """Test tool with custom context parameter name."""

        @tool(context="ctx")
        def custom_context_tool(ctx: ToolContext) -> str:
            """Tool with custom context param.

            Returns:
                Context info
            """
            return f"Agent: {ctx.agent.config.name}"

        assert isinstance(custom_context_tool, DecoratedFunctionTool)
        assert custom_context_tool._metadata._context_param == "ctx"

    def test_context_parameter_excluded_from_schema(self):
        """Test that context parameter is excluded from input schema."""

        @tool(context=True)
        def tool_with_args(message: str, tool_context: ToolContext) -> str:
            """Tool with both regular and context params.

            Args:
                message: Message to process

            Returns:
                Result
            """
            return f"{message} - {tool_context.tool_use.get('name')}"

        schema = tool_with_args.tool_spec["parameters"]["json"]
        properties = schema.get("properties", {})

        # Regular param should be in schema
        assert "message" in properties
        # Context param should NOT be in schema
        assert "tool_context" not in properties

    def test_context_injection_with_agent(self):
        """Test that context is properly injected when executed via agent."""

        @tool(context=True)
        def get_agent_name(tool_context: ToolContext) -> str:
            """Get the agent's name.

            Returns:
                Agent name
            """
            # return tool_context.agent.config.name
            return tool_context.invocation_state.get("agent").config.name

        # Create agent with the tool
        agent = Agent(
            AgentConfig(
                model=EchoModel(),
                name="test_agent",
                tools=[get_agent_name],
            )
        )

        # Get the tool from registry
        tool_instance = agent.tool_registry.registry.get("get_agent_name")
        assert isinstance(tool_instance, DecoratedFunctionTool)

        # Simulate what the agent does during tool execution
        func_args = {}
        validated_input = tool_instance._metadata.validate_input(func_args)

        tool_use = {
            "toolUseId": "test-123",
            "name": "get_agent_name",
            "input": func_args,
        }

        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        # Execute with injected context
        result = tool_instance(**validated_input)
        assert result == "test_agent"

    def test_context_access_to_tool_use(self):
        """Test accessing tool use details from context."""

        @tool(context=True)
        def access_tool_use(tool_context: ToolContext) -> dict[str, Any]:
            """Access tool use information.

            Returns:
                Tool use details
            """
            return {
                "tool_use_id": tool_context.tool_use.get("toolUseId"),
                "tool_name": tool_context.tool_use.get("name"),
            }

        agent = Agent(
            AgentConfig(model=EchoModel(), name="test", tools=[access_tool_use])
        )

        tool_instance = agent.tool_registry.registry.get("access_tool_use")
        validated_input = tool_instance._metadata.validate_input({})

        tool_use = {
            "toolUseId": "abc-123",
            "name": "access_tool_use",
            "input": {},
        }

        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        result = tool_instance(**validated_input)
        assert result["tool_use_id"] == "abc-123"
        assert result["tool_name"] == "access_tool_use"

    def test_context_with_both_params(self):
        """Test tool with both regular and context parameters."""

        @tool(context=True)
        def mixed_params(message: str, count: int, tool_context: ToolContext) -> str:
            """Tool with mixed parameters.

            Args:
                message: Message to process
                count: Number of times to repeat

            Returns:
                Result with context
            """
            agent_name = tool_context.invocation_state.get("agent").config.name
            return f"{message} x{count} from {agent_name}"

        agent = Agent(
            AgentConfig(model=EchoModel(), name="mixer", tools=[mixed_params])
        )

        tool_instance = agent.tool_registry.registry.get("mixed_params")

        # Regular params
        func_args = {"message": "hello", "count": 3}
        validated_input = tool_instance._metadata.validate_input(func_args)

        # Inject context
        tool_use = {"toolUseId": "xyz", "name": "mixed_params", "input": func_args}
        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        result = tool_instance(**validated_input)
        assert result == "hello x3 from mixer"


class TestFunctionToolMetadata:
    """Test FunctionToolMetadata helper class."""

    def test_extract_metadata_from_simple_function(self):
        """Test extracting metadata from a simple function."""

        def simple_func(x: int) -> int:
            """Double a number.

            Args:
                x: Number to double

            Returns:
                Doubled number
            """
            return x * 2

        metadata = FunctionToolMetadata(simple_func)
        spec = metadata.extract_metadata()

        assert spec["name"] == "simple_func"
        assert "Double a number" in spec["description"]
        assert "parameters" in spec
        assert "json" in spec["parameters"]

    def test_validate_input_valid(self):
        """Test input validation with valid data."""

        def add(a: int, b: int) -> int:
            """Add two numbers.

            Args:
                a: First number
                b: Second number
            """
            return a + b

        metadata = FunctionToolMetadata(add)
        validated = metadata.validate_input({"a": 5, "b": 3})
        assert validated["a"] == 5
        assert validated["b"] == 3

    def test_validate_input_with_defaults(self):
        """Test validation with default parameters."""

        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone.

            Args:
                name: Person to greet
                greeting: Greeting message
            """
            return f"{greeting}, {name}"

        metadata = FunctionToolMetadata(greet)

        # Only required param
        validated = metadata.validate_input({"name": "Alice"})
        assert validated["name"] == "Alice"
        assert validated["greeting"] == "Hello"

        # Both params
        validated = metadata.validate_input({"name": "Bob", "greeting": "Hi"})
        assert validated["name"] == "Bob"
        assert validated["greeting"] == "Hi"

    def test_validate_input_invalid(self):
        """Test validation with invalid data."""

        def typed_func(x: int) -> int:
            """A typed function.

            Args:
                x: An integer
            """
            return x

        metadata = FunctionToolMetadata(typed_func)

        # Missing required param
        with pytest.raises(ValueError, match="Validation failed"):
            metadata.validate_input({})

    def test_special_parameter_detection(self):
        """Test detection of special parameters."""

        def func_with_special(self, x: int, agent: Any, tool_context: ToolContext):
            """Function with special params.

            Args:
                x: Regular param
            """
            pass

        metadata = FunctionToolMetadata(func_with_special, context_param="tool_context")

        assert metadata._is_special_parameter("self")
        assert metadata._is_special_parameter("cls")
        assert metadata._is_special_parameter("agent")
        assert metadata._is_special_parameter("tool_context")
        assert not metadata._is_special_parameter("x")


class TestToolIntegrationWithAgent:
    """Test tool integration with Agent class."""

    def test_agent_registers_tools(self):
        """Test that agent properly registers decorated tools."""

        @tool
        def tool1() -> str:
            """First tool."""
            return "one"

        @tool
        def tool2() -> str:
            """Second tool."""
            return "two"

        agent = Agent(AgentConfig(model=EchoModel(), tools=[tool1, tool2]))

        assert "tool1" in agent.tool_registry.registry
        assert "tool2" in agent.tool_registry.registry
        assert len(agent.tool_registry.registry) == 2

    def test_agent_tool_specs_generation(self):
        """Test that agent generates tool specs correctly."""

        @tool
        def my_tool(param: str) -> str:
            """My tool description.

            Args:
                param: A parameter
            """
            return param

        agent = Agent(AgentConfig(model=EchoModel(), tools=[my_tool]))

        specs = agent.tool_specs
        assert len(specs) == 1
        assert specs[0]["name"] == "my_tool"
        assert "description" in specs[0]

    def test_multiple_tools_with_context(self):
        """Test agent with multiple context-aware tools."""

        @tool(context=True)
        def tool_a(tool_context: ToolContext) -> str:
            """Tool A.

            Returns:
                Agent name with prefix
            """
            return f"A:{tool_context.invocation_state.get('agent').config.name}"

        @tool(context=True)
        def tool_b(tool_context: ToolContext) -> str:
            """Tool B.

            Returns:
                Agent name with prefix
            """
            return f"B:{tool_context.invocation_state.get('agent').config.name}"

        agent = Agent(
            AgentConfig(model=EchoModel(), name="multi", tools=[tool_a, tool_b])
        )

        # Manually execute both tools
        for tool_name in ["tool_a", "tool_b"]:
            tool_instance = agent.tool_registry.registry.get(tool_name)
            validated_input = tool_instance._metadata.validate_input({})

            tool_use = {"toolUseId": f"id-{tool_name}", "name": tool_name, "input": {}}
            invocation_state = {"agent": agent}
            tool_instance._metadata.inject_special_parameters(
                validated_input, tool_use, invocation_state
            )

            result = tool_instance(**validated_input)
            assert result == f"{tool_name[-1].upper()}:multi"

    def test_tool_execution_error_handling(self):
        """Test error handling in tool execution."""

        @tool
        def failing_tool(x: int) -> int:
            """A tool that fails.

            Args:
                x: Input number

            Returns:
                Never returns
            """
            raise ValueError("Something went wrong")

        agent = Agent(AgentConfig(model=EchoModel(), tools=[failing_tool]))

        tool_instance = agent.tool_registry.registry.get("failing_tool")
        validated_input = tool_instance._metadata.validate_input({"x": 5})

        with pytest.raises(ValueError, match="Something went wrong"):
            tool_instance(**validated_input)


class TestToolContextObject:
    """Test ToolContext dataclass."""

    def test_context_object_creation(self):
        """Test creating a ToolContext object."""
        mock_agent = MagicMock()
        mock_agent.config.name = "test_agent"

        tool_use = {"toolUseId": "123", "name": "test_tool", "input": {}}
        invocation_state = {"agent": mock_agent, "extra": "data"}

        context = ToolContext(
            tool_use=tool_use, invocation_state=invocation_state
        )

        assert context.tool_use == tool_use
        assert context.invocation_state == invocation_state
        assert context.invocation_state.get("agent") == mock_agent
        assert context.invocation_state["extra"] == "data"

    def test_context_access_in_tool(self):
        """Test accessing context fields in a tool function."""

        @tool(context=True)
        def examine_context(tool_context: ToolContext) -> dict[str, Any]:
            """Examine the context object.

            Returns:
                Context information
            """
            return {
                "has_agent": tool_context.invocation_state.get("agent") is not None,
                "has_tool_use": tool_context.tool_use is not None,
                "has_invocation_state": tool_context.invocation_state is not None,
                "agent_type": type(tool_context.invocation_state.get("agent")).__name__,
            }

        agent = Agent(AgentConfig(model=EchoModel(), tools=[examine_context]))

        tool_instance = agent.tool_registry.registry.get("examine_context")
        validated_input = tool_instance._metadata.validate_input({})

        tool_use = {"toolUseId": "test", "name": "examine_context", "input": {}}
        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        result = tool_instance(**validated_input)

        assert result["has_agent"] is True
        assert result["has_tool_use"] is True
        assert result["has_invocation_state"] is True
        assert result["agent_type"] == "Agent"


class TestComplexToolScenarios:
    """Test complex real-world tool scenarios."""

    def test_tool_with_complex_return_types(self):
        """Test tool returning complex data structures."""

        @tool(context=True)
        def get_statistics(tool_context: ToolContext) -> dict[str, Any]:
            """Get agent statistics.

            Returns:
                Statistics dictionary
            """
            agent = tool_context.invocation_state.get("agent")
            return {
                "name": agent.config.name,
                "model_type": type(agent.config.model).__name__,
                "tool_count": len(agent.tool_registry.registry),
                "tools": list(agent.tool_registry.registry.keys()),
                "has_memory": agent.memory_manager is not None,
            }

        agent = Agent(
            AgentConfig(model=EchoModel(), name="stats_agent", tools=[get_statistics])
        )

        tool_instance = agent.tool_registry.registry.get("get_statistics")
        validated_input = tool_instance._metadata.validate_input({})

        tool_use = {"toolUseId": "stats", "name": "get_statistics", "input": {}}
        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        result = tool_instance(**validated_input)

        assert result["name"] == "stats_agent"
        assert result["model_type"] == "EchoModel"
        assert result["tool_count"] == 1
        assert "get_statistics" in result["tools"]
        assert result["has_memory"] is True

    def test_tool_chaining_context(self):
        """Test using context from one tool in another."""
        call_log = []

        @tool(context=True)
        def first_tool(tool_context: ToolContext) -> str:
            """First tool in chain.

            Returns:
                Result
            """
            call_log.append(
                f"first:{tool_context.tool_use.get('toolUseId')}"
            )
            return "first_result"

        @tool(context=True)
        def second_tool(data: str, tool_context: ToolContext) -> str:
            """Second tool in chain.

            Args:
                data: Data from previous tool

            Returns:
                Result
            """
            call_log.append(
                f"second:{tool_context.tool_use.get('toolUseId')}:{data}"
            )
            return f"second_result:{data}"

        agent = Agent(
            AgentConfig(
                model=EchoModel(), name="chain", tools=[first_tool, second_tool]
            )
        )

        # Execute first tool
        tool1 = agent.tool_registry.registry.get("first_tool")
        input1 = tool1._metadata.validate_input({})
        use1 = {"toolUseId": "call-1", "name": "first_tool", "input": {}}
        tool1._metadata.inject_special_parameters(input1, use1, {"agent": agent})
        result1 = tool1(**input1)

        # Execute second tool with result from first
        tool2 = agent.tool_registry.registry.get("second_tool")
        input2 = tool2._metadata.validate_input({"data": result1})
        use2 = {"toolUseId": "call-2", "name": "second_tool", "input": {"data": result1}}
        tool2._metadata.inject_special_parameters(input2, use2, {"agent": agent})
        result2 = tool2(**input2)

        assert len(call_log) == 2
        assert call_log[0] == "first:call-1"
        assert call_log[1] == "second:call-2:first_result"
        assert result2 == "second_result:first_result"

    def test_tool_with_json_output(self):
        """Test tool that returns JSON data."""

        @tool(context=True)
        def json_tool(query: str, tool_context: ToolContext) -> str:
            """Tool that returns JSON.

            Args:
                query: Query string

            Returns:
                JSON string
            """
            result = {
                "query": query,
                "agent": tool_context.invocation_state.get("agent").config.name,
                "tool_id": tool_context.tool_use.get("toolUseId"),
                "status": "success",
            }
            return json.dumps(result, indent=2)

        agent = Agent(
            AgentConfig(model=EchoModel(), name="json_agent", tools=[json_tool])
        )

        tool_instance = agent.tool_registry.registry.get("json_tool")
        input_data = {"query": "test query"}
        validated_input = tool_instance._metadata.validate_input(input_data)

        tool_use = {"toolUseId": "json-123", "name": "json_tool", "input": input_data}
        invocation_state = {"agent": agent}
        tool_instance._metadata.inject_special_parameters(
            validated_input, tool_use, invocation_state
        )

        result = tool_instance(**validated_input)
        parsed = json.loads(result)

        assert parsed["query"] == "test query"
        assert parsed["agent"] == "json_agent"
        assert parsed["tool_id"] == "json-123"
        assert parsed["status"] == "success"
