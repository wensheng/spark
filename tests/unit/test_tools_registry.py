"""Unit tests for spark.tools.registry module."""

import pytest
from typing import Any
from unittest.mock import Mock, patch

from spark.tools.registry import ToolRegistry
from spark.tools.types import BaseTool, ToolSpec


class MockTool(BaseTool):
    """Mock tool implementation for testing."""

    def __init__(self, name: str, tool_type: str = "test", supports_hot_reload: bool = False, is_dynamic: bool = False):
        super().__init__()
        self._tool_name = name
        self._tool_type = tool_type
        self._supports_hot_reload = supports_hot_reload
        self._is_dynamic = is_dynamic
        self.mark_dynamic() if is_dynamic else None

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def tool_spec(self) -> ToolSpec:
        return {
            "name": self._tool_name,
            "description": f"Mock tool {self._tool_name}",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

    @property
    def tool_type(self) -> str:
        return self._tool_type

    @property
    def supports_hot_reload(self) -> bool:
        return self._supports_hot_reload

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return f"Mock tool {self._tool_name} called"


class TestToolRegistry:
    """Test cases for ToolRegistry class."""

    def test_registry_initialization(self):
        """Test ToolRegistry initialization."""
        registry = ToolRegistry()

        assert registry.registry == {}
        assert registry.dynamic_tools == {}
        assert registry.tool_config is None

    def test_process_tools_empty_list(self):
        """Test processing empty tools list."""
        registry = ToolRegistry()
        result = registry.process_tools([])

        assert result == []
        assert registry.registry == {}

    def test_process_tools_single_tool(self):
        """Test processing a single tool."""
        registry = ToolRegistry()
        mock_tool = MockTool("test_tool")

        result = registry.process_tools([mock_tool])

        assert result == ["test_tool"]
        assert "test_tool" in registry.registry
        assert registry.registry["test_tool"] == mock_tool

    def test_process_tools_multiple_tools(self):
        """Test processing multiple tools."""
        registry = ToolRegistry()
        tools = [
            MockTool("tool1"),
            MockTool("tool2"),
            MockTool("tool3")
        ]

        result = registry.process_tools(tools)

        assert len(result) == 3
        assert "tool1" in result
        assert "tool2" in result
        assert "tool3" in result
        assert len(registry.registry) == 3

    def test_process_tools_with_iterable(self):
        """Test processing tools with nested iterable."""
        registry = ToolRegistry()
        tools = [
            MockTool("tool1"),
            [MockTool("tool2"), MockTool("tool3")],
            MockTool("tool4")
        ]

        result = registry.process_tools(tools)

        assert len(result) == 4
        assert all(tool_name in result for tool_name in ["tool1", "tool2", "tool3", "tool4"])
        assert len(registry.registry) == 4

    def test_process_tools_with_unrecognized_spec(self):
        """Test processing tools with unrecognized specifications."""
        registry = ToolRegistry()

        with patch('spark.tools.registry.logger') as mock_logger:
            result = registry.process_tools(["not_a_tool", 123, MockTool("valid_tool")])

            # Should have warned about unrecognized tools
            assert mock_logger.warning.called

            # Should still process valid tools
            assert result == ["valid_tool"]
            assert "valid_tool" in registry.registry

    def test_register_tool_basic(self):
        """Test basic tool registration."""
        registry = ToolRegistry()
        mock_tool = MockTool("new_tool")

        registry.register_tool(mock_tool)

        assert "new_tool" in registry.registry
        assert registry.registry["new_tool"] == mock_tool

    def test_register_duplicate_tool_name(self):
        """Test registering tool with duplicate name raises error."""
        registry = ToolRegistry()
        tool1 = MockTool("duplicate_name")
        tool2 = MockTool("duplicate_name")

        registry.register_tool(tool1)

        with pytest.raises(ValueError, match="Tool name 'duplicate_name' already exists"):
            registry.register_tool(tool2)

    def test_register_duplicate_tool_name_with_hot_reload(self):
        """Test registering duplicate tool with hot reload enabled."""
        registry = ToolRegistry()
        tool1 = MockTool("hot_reload_tool", supports_hot_reload=True)
        tool2 = MockTool("hot_reload_tool", supports_hot_reload=True)

        registry.register_tool(tool1)
        # Should not raise error for hot reload tools
        registry.register_tool(tool2)

        assert registry.registry["hot_reload_tool"] == tool2  # Should overwrite

    def test_register_tool_with_normalized_name_conflict(self):
        """Test registering tool with conflicting normalized name."""
        registry = ToolRegistry()
        tool1 = MockTool("tool_name")
        tool2 = MockTool("tool-name")  # Different by dash vs underscore

        registry.register_tool(tool1)

        with pytest.raises(ValueError, match="Tool name 'tool-name' already exists as 'tool_name'"):
            registry.register_tool(tool2)

    def test_register_dynamic_tool(self):
        """Test registering a dynamic tool."""
        registry = ToolRegistry()
        dynamic_tool = MockTool("dynamic_tool", is_dynamic=True)

        registry.register_tool(dynamic_tool)

        assert "dynamic_tool" in registry.registry
        assert "dynamic_tool" in registry.dynamic_tools
        assert registry.registry["dynamic_tool"] == dynamic_tool
        assert registry.dynamic_tools["dynamic_tool"] == dynamic_tool

    def test_get_all_tools_config_empty(self):
        """Test getting all tools config from empty registry."""
        registry = ToolRegistry()
        config = registry.get_all_tools_config()

        assert config == {}

    def test_get_all_tools_config_with_tools(self):
        """Test getting all tools config with registered tools."""
        registry = ToolRegistry()
        tool1 = MockTool("config_tool1")
        tool2 = MockTool("config_tool2")

        registry.register_tool(tool1)
        registry.register_tool(tool2)

        config = registry.get_all_tools_config()

        assert len(config) == 2
        assert "config_tool1" in config
        assert "config_tool2" in config
        assert config["config_tool1"]["name"] == "config_tool1"
        assert config["config_tool2"]["name"] == "config_tool2"

    def test_get_all_tools_config_with_invalid_spec(self):
        """Test getting config with invalid tool spec."""
        registry = ToolRegistry()

        # Create a tool with invalid spec
        class InvalidSpecTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "invalid_tool"

            @property
            def tool_spec(self) -> ToolSpec:
                # Missing required fields
                return {
                    "name": "invalid_tool"
                    # Missing description
                }

            @property
            def tool_type(self) -> str:
                return "invalid"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return None

        invalid_tool = InvalidSpecTool()
        registry.register_tool(invalid_tool)

        with patch('spark.tools.registry.logger') as mock_logger:
            config = registry.get_all_tools_config()

            # Should have logged warning about validation failure
            assert mock_logger.warning.called
            # Should not include invalid tool in config
            assert "invalid_tool" not in config

    def test_get_all_tool_specs(self):
        """Test getting all tool specs."""
        registry = ToolRegistry()
        tool1 = MockTool("spec_tool1")
        tool2 = MockTool("spec_tool2")

        registry.register_tool(tool1)
        registry.register_tool(tool2)

        specs = registry.get_all_tool_specs()

        assert len(specs) == 2
        spec_names = [spec["name"] for spec in specs]
        assert "spec_tool1" in spec_names
        assert "spec_tool2" in spec_names

    def test_get_tool(self):
        """Test retrieving a tool by name."""
        registry = ToolRegistry()

        class SampleTool(BaseTool):
            @property
            def tool_name(self) -> str:
                return "sample"

            @property
            def tool_spec(self) -> ToolSpec:
                return {
                    "name": "sample",
                    "description": "Sample",
                    "parameters": {"json": {"type": "object", "properties": {}, "required": []}},
                }

            @property
            def tool_type(self) -> str:
                return "test"

            def __call__(self, *args: Any, **kwargs: Any) -> Any:
                return None

        sample_tool = SampleTool()
        registry.register_tool(sample_tool)

        retrieved = registry.get_tool("sample")
        assert retrieved is sample_tool

        with pytest.raises(KeyError):
            registry.get_tool("unknown")

    def test_validate_tool_spec_valid(self):
        """Test validating a valid tool spec."""
        registry = ToolRegistry()
        valid_spec: ToolSpec = {
            "name": "valid_tool",
            "description": "A valid tool specification",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "param1": {
                            "type": "string",
                            "description": "First parameter"
                        }
                    },
                    "required": ["param1"]
                }
            }
        }

        # Should not raise any exceptions
        registry.validate_tool_spec(valid_spec)

    def test_validate_tool_spec_missing_required_fields(self):
        """Test validating tool spec with missing required fields."""
        registry = ToolRegistry()

        # Missing name and description
        invalid_spec: ToolSpec = {
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

        with pytest.raises(ValueError, match="Missing required fields in tool spec: name, description"):
            registry.validate_tool_spec(invalid_spec)

    def test_validate_tool_spec_missing_json_schema(self):
        """Test validating tool spec with missing json schema."""
        registry = ToolRegistry()
        spec_without_json: ToolSpec = {
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

        # Should convert to proper format
        registry.validate_tool_spec(spec_without_json)
        assert "json" in spec_without_json["parameters"]

    def test_validate_tool_spec_adds_missing_schema_fields(self):
        """Test that validation adds missing JSON schema fields."""
        registry = ToolRegistry()
        minimal_spec: ToolSpec = {
            "name": "minimal_tool",
            "description": "Minimal tool spec",
            "parameters": {
                "json": {
                    # Missing type, properties, required
                }
            }
        }

        registry.validate_tool_spec(minimal_spec)

        json_schema = minimal_spec["parameters"]["json"]
        assert json_schema["type"] == "object"
        assert json_schema["properties"] == {}
        assert json_schema["required"] == []

    def test_validate_tool_spec_property_defaults(self):
        """Test that validation adds default values to properties."""
        registry = ToolRegistry()
        spec_with_properties: ToolSpec = {
            "name": "prop_tool",
            "description": "Tool with properties",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "prop1": {
                            "type": "string"
                            # Missing description
                        },
                        "prop2": {
                            # Missing type and description
                        }
                    },
                    "required": []
                }
            }
        }

        registry.validate_tool_spec(spec_with_properties)

        properties = spec_with_properties["parameters"]["json"]["properties"]
        assert properties["prop1"]["description"] == "Property prop1"
        assert properties["prop2"]["type"] == "string"
        assert properties["prop2"]["description"] == "Property prop2"

    def test_validate_tool_spec_with_ref_properties(self):
        """Test validation with $ref properties (should skip processing)."""
        registry = ToolRegistry()
        spec_with_ref: ToolSpec = {
            "name": "ref_tool",
            "description": "Tool with $ref properties",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "ref_prop": {
                            "$ref": "#/definitions/SomeType"
                        }
                    },
                    "required": []
                }
            }
        }

        # Should not raise errors for $ref properties
        registry.validate_tool_spec(spec_with_ref)

    def test_validate_tool_spec_non_dict_properties(self):
        """Test validation with non-dict property definitions."""
        registry = ToolRegistry()
        spec_with_invalid_prop: ToolSpec = {
            "name": "invalid_prop_tool",
            "description": "Tool with invalid property",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "invalid_prop": "not_a_dict"
                    },
                    "required": []
                }
            }
        }

        registry.validate_tool_spec(spec_with_invalid_prop)

        properties = spec_with_invalid_prop["parameters"]["json"]["properties"]
        assert properties["invalid_prop"]["type"] == "string"
        assert properties["invalid_prop"]["description"] == "Property invalid_prop"

    def test_update_tool_config_new_tool(self):
        """Test updating tool config with new tool."""
        registry = ToolRegistry()
        existing_config = {"tools": []}

        new_tool = {
            "spec": {
                "name": "new_tool",
                "description": "A new tool",
                "parameters": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        }

        registry._update_tool_config(existing_config, new_tool)

        assert len(existing_config["tools"]) == 1
        assert existing_config["tools"][0]["toolSpec"]["name"] == "new_tool"

    def test_update_tool_config_existing_tool(self):
        """Test updating tool config with existing tool."""
        registry = ToolRegistry()
        existing_config = {
            "tools": [
                {"toolSpec": {"name": "existing_tool", "description": "Old description"}}
            ]
        }

        updated_tool = {
            "spec": {
                "name": "existing_tool",
                "description": "Updated description",
                "parameters": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        }

        registry._update_tool_config(existing_config, updated_tool)

        assert len(existing_config["tools"]) == 1
        assert existing_config["tools"][0]["toolSpec"]["description"] == "Updated description"

    def test_update_tool_config_invalid_format(self):
        """Test updating tool config with invalid format."""
        registry = ToolRegistry()
        existing_config = {"tools": []}

        invalid_tool = {"not_spec": "invalid_format"}

        with pytest.raises(ValueError, match="Invalid tool format - missing spec"):
            registry._update_tool_config(existing_config, invalid_tool)

    def test_update_tool_config_invalid_spec(self):
        """Test updating tool config with invalid spec."""
        registry = ToolRegistry()
        existing_config = {"tools": []}

        invalid_spec_tool = {
            "spec": {
                "name": "invalid_tool"
                # Missing required description
            }
        }

        with pytest.raises(ValueError, match="Tool specification validation failed"):
            registry._update_tool_config(existing_config, invalid_spec_tool)
