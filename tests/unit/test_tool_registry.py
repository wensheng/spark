"""Tests for enhanced tool registry with spec compatibility."""

import pytest
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import tool
from spark.tools.types import BaseTool, ToolSpec


# Test tools defined at module level (can be imported by reference)
@tool
def example_tool(query: str, limit: int = 10) -> str:
    """Search for information.

    Args:
        query: The search query
        limit: Maximum number of results

    Returns:
        Search results
    """
    return f"Found {limit} results for: {query}"


@tool
def another_tool(value: int) -> int:
    """Double a value.

    Args:
        value: The value to double

    Returns:
        The doubled value
    """
    return value * 2


class TestToolRegistry:
    """Test enhanced ToolRegistry functionality."""

    def test_registry_initialization(self):
        """Test registry initializes with empty state."""
        registry = ToolRegistry()
        assert len(registry.registry) == 0
        assert len(registry.dynamic_tools) == 0
        assert len(registry.tool_refs) == 0

    def test_register_tool_instance(self):
        """Test registering a tool instance."""
        registry = ToolRegistry()
        tool_instance = example_tool

        registry.register_tool(tool_instance)

        assert "example_tool" in registry.registry
        assert registry.get_tool("example_tool") == tool_instance

    def test_register_tool_captures_reference(self):
        """Test that registering a DecoratedFunctionTool captures its reference."""
        registry = ToolRegistry()
        tool_instance = example_tool

        registry.register_tool(tool_instance)

        # Should have captured the reference
        ref = registry.get_tool_ref("example_tool")
        assert ref is not None
        assert "test_tool_registry:example_tool" in ref

    def test_register_tool_by_ref(self):
        """Test registering a tool by module:function reference."""
        registry = ToolRegistry()

        # Register by reference
        registry.register_tool_by_ref("tests.unit.test_tool_registry:example_tool")

        # Should be registered
        assert "example_tool" in registry.registry

        # Should have stored the reference
        ref = registry.get_tool_ref("example_tool")
        assert ref == "tests.unit.test_tool_registry:example_tool"

    def test_register_tool_by_ref_with_custom_name(self):
        """Test registering a tool by reference with custom name."""
        registry = ToolRegistry()

        registry.register_tool_by_ref(
            "tests.unit.test_tool_registry:example_tool",
            tool_name="custom_search"
        )

        # Should be registered with custom name
        assert "custom_search" in registry.registry

        # Reference should use custom name
        ref = registry.get_tool_ref("custom_search")
        assert ref == "tests.unit.test_tool_registry:example_tool"

    def test_register_tool_by_ref_invalid(self):
        """Test that invalid references raise ValueError."""
        registry = ToolRegistry()

        with pytest.raises(ValueError, match="Invalid tool reference"):
            registry.register_tool_by_ref("invalid_module:nonexistent_tool")

    def test_to_spec_dict(self):
        """Test serializing registry to spec dictionary."""
        registry = ToolRegistry()

        # Register a couple tools
        registry.register_tool(example_tool)
        registry.register_tool(another_tool)

        # Serialize
        spec = registry.to_spec_dict()

        # Check structure
        assert "tools" in spec
        assert len(spec["tools"]) == 2

        # Check first tool
        tool_dict = spec["tools"][0]
        assert "name" in tool_dict
        assert "spec" in tool_dict
        assert "ref" in tool_dict
        assert "metadata" in tool_dict

        # Check metadata
        metadata = tool_dict["metadata"]
        assert "tool_type" in metadata
        assert "is_dynamic" in metadata
        assert "supports_async" in metadata
        assert "is_long_running" in metadata
        assert "supports_hot_reload" in metadata

    def test_from_spec_dict(self):
        """Test deserializing registry from spec dictionary."""
        # Create and populate a registry
        registry1 = ToolRegistry()
        registry1.register_tool(example_tool)
        registry1.register_tool(another_tool)

        # Serialize
        spec = registry1.to_spec_dict()

        # Deserialize into new registry
        registry2 = ToolRegistry.from_spec_dict(spec)

        # Check that tools were loaded
        assert "example_tool" in registry2.registry
        assert "another_tool" in registry2.registry

        # Check that references were preserved
        assert registry2.get_tool_ref("example_tool") is not None
        assert registry2.get_tool_ref("another_tool") is not None

    def test_round_trip_serialization(self):
        """Test that registry can be serialized and deserialized correctly."""
        # Create original registry
        registry1 = ToolRegistry()
        registry1.register_tool(example_tool)

        # Serialize
        spec = registry1.to_spec_dict()

        # Deserialize
        registry2 = ToolRegistry.from_spec_dict(spec)

        # Serialize again
        spec2 = registry2.to_spec_dict()

        # Should be identical (or at least equivalent)
        assert len(spec["tools"]) == len(spec2["tools"])
        assert spec["tools"][0]["name"] == spec2["tools"][0]["name"]
        assert spec["tools"][0]["ref"] == spec2["tools"][0]["ref"]

    def test_process_tools_with_list(self):
        """Test processing a list of tool instances."""
        registry = ToolRegistry()

        tools = [example_tool, another_tool]
        tool_names = registry.process_tools(tools)

        assert len(tool_names) == 2
        assert "example_tool" in tool_names
        assert "another_tool" in tool_names
        assert len(registry.registry) == 2

    def test_get_all_tool_specs(self):
        """Test getting all tool specifications."""
        registry = ToolRegistry()
        registry.register_tool(example_tool)
        registry.register_tool(another_tool)

        specs = registry.get_all_tool_specs()

        assert len(specs) == 2
        for spec in specs:
            assert "name" in spec
            assert "description" in spec
            assert "parameters" in spec

    def test_tool_ref_persistence(self):
        """Test that tool references persist across operations."""
        registry = ToolRegistry()

        # Register tool
        registry.register_tool(example_tool)

        # Get reference
        ref1 = registry.get_tool_ref("example_tool")
        assert ref1 is not None

        # Get it again
        ref2 = registry.get_tool_ref("example_tool")
        assert ref2 == ref1

        # Check it's in the spec
        spec = registry.to_spec_dict()
        tool_dict = spec["tools"][0]
        assert tool_dict["ref"] == ref1


class TestToolRegistryIntegration:
    """Test tool registry integration with actual workflows."""

    def test_registry_with_agent_config(self):
        """Test that tool registry works with AgentConfig patterns."""
        from spark.agents.config import AgentConfig
        from spark.models.echo import EchoModel

        registry = ToolRegistry()
        registry.register_tool(example_tool)
        registry.register_tool(another_tool)

        # Get tools as list
        tools_list = [
            registry.get_tool("example_tool"),
            registry.get_tool("another_tool")
        ]

        # This should work with AgentConfig
        config = AgentConfig(
            model=EchoModel(),
            tools=tools_list
        )

        assert len(config.tools) == 2

    def test_spec_export_and_reload(self):
        """Test exporting spec and reloading in new registry."""
        # Create registry with tools
        registry1 = ToolRegistry()
        registry1.register_tool(example_tool)

        # Export to spec
        spec = registry1.to_spec_dict()

        # Simulate saving/loading (e.g., to/from JSON)
        import json
        spec_json = json.dumps(spec)
        spec_loaded = json.loads(spec_json)

        # Create new registry from spec
        registry2 = ToolRegistry.from_spec_dict(spec_loaded)

        # Should have same tools
        assert "example_tool" in registry2.registry

        # Tool should be callable
        tool = registry2.get_tool("example_tool")
        result = tool(query="test", limit=5)
        assert "test" in result
        assert "5" in result
