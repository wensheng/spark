"""Tool registry.

This module provides the central registry for all tools available to the agent, including discovery, validation, and
invocation capabilities. Enhanced with spec-compatible serialization support.
"""

import logging
from typing import Any, Iterable, Optional, TypedDict

from spark.tools.types import BaseTool, ToolSpec
from spark.tools.tools import normalize_schema, normalize_tool_spec
from spark.utils.import_utils import import_from_ref, get_ref_for_callable, validate_reference

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all tools available to the agent.

    This class manages tool registration, validation, discovery, and invocation.
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self.registry: dict[str, BaseTool] = {}
        self.dynamic_tools: dict[str, BaseTool] = {}
        self.tool_config: Optional[dict[str, Any]] = None
        # Track tool references for spec serialization
        self.tool_refs: dict[str, str] = {}  # tool_name -> module:function

    def process_tools(self, tools: list[Any]) -> list[str]:
        """Process tools list that can contain tool names, paths, imported modules, or functions.

        Args:
            tools: List of BaseTool instance

        Returns:
            List of tool names that were processed.
        """
        tool_names = []

        def add_tool(tool: Any) -> None:
            if isinstance(tool, BaseTool):
                self.register_tool(tool)
                tool_names.append(tool.tool_name)
            # Case 6: Nested iterable (list, tuple, etc.) - add each sub-tool
            elif isinstance(tool, Iterable) and not isinstance(tool, (str, bytes, bytearray)):
                for t in tool:
                    add_tool(t)
            else:
                logger.warning("tool=<%s> | unrecognized tool specification", tool)

        for a_tool in tools:
            add_tool(a_tool)

        return tool_names

    def get_all_tools_config(self) -> dict[str, Any]:
        """Dynamically generate tool configuration by combining built-in and dynamic tools.

        Returns:
            Dictionary containing all tool configurations.
        """
        tool_config = {}
        logger.debug("getting tool configurations")

        # Add all registered tools
        for tool_name, tool in self.registry.items():
            # Make a deep copy to avoid modifying the original
            spec = tool.tool_spec.copy()
            try:
                # Normalize the schema before validation
                spec = normalize_tool_spec(spec)
                self.validate_tool_spec(spec)
                tool_config[tool_name] = spec
                logger.debug("tool_name=<%s> | loaded tool config", tool_name)
            except ValueError as e:
                logger.warning("tool_name=<%s> | spec validation failed | %s", tool_name, e)

        # Add any dynamic tools
        for tool_name, tool in self.dynamic_tools.items():
            if tool_name not in tool_config:
                # Make a deep copy to avoid modifying the original
                spec = tool.tool_spec.copy()
                try:
                    # Normalize the schema before validation
                    spec = normalize_tool_spec(spec)
                    self.validate_tool_spec(spec)
                    tool_config[tool_name] = spec
                    logger.debug("tool_name=<%s> | loaded dynamic tool config", tool_name)
                except ValueError as e:
                    logger.warning("tool_name=<%s> | dynamic tool spec validation failed | %s", tool_name, e)

        logger.debug("tool_count=<%s> | tools configured", len(tool_config))
        return tool_config

    # mypy has problems converting between DecoratedFunctionTool <-> BaseTool
    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool function with the given name.

        Args:
            tool: The tool to register.
        """
        logger.debug(
            "tool_name=<%s>, tool_type=<%s>, is_dynamic=<%s> | registering tool",
            tool.tool_name,
            tool.tool_type,
            tool.is_dynamic,
        )

        # Check duplicate tool name, throw on duplicate tool names except if hot_reloading is enabled
        if tool.tool_name in self.registry and not tool.supports_hot_reload:
            raise ValueError(
                f"Tool name '{tool.tool_name}' already exists. Cannot register tools with exact same name."
            )

        # Check for normalized name conflicts (- vs _)
        if self.registry.get(tool.tool_name) is None:
            normalized_name = tool.tool_name.replace("-", "_")

            matching_tools = [
                tool_name
                for (tool_name, tool) in self.registry.items()
                if tool_name.replace("-", "_") == normalized_name
            ]

            if matching_tools:
                raise ValueError(
                    f"Tool name '{tool.tool_name}' already exists as '{matching_tools[0]}'."
                    " Cannot add a duplicate tool which differs by a '-' or '_'"
                )

        # Register in main registry
        self.registry[tool.tool_name] = tool

        # Try to extract tool reference for spec serialization
        self._try_capture_tool_ref(tool)

        # Register in dynamic tools if applicable
        if tool.is_dynamic:
            self.dynamic_tools[tool.tool_name] = tool

            if not tool.supports_hot_reload:
                logger.debug("tool_name=<%s>, tool_type=<%s> | skipping hot reloading", tool.tool_name, tool.tool_type)
                return

            logger.debug(
                "tool_name=<%s>, tool_registry=<%s>, dynamic_tools=<%s> | tool registered",
                tool.tool_name,
                list(self.registry.keys()),
                list(self.dynamic_tools.keys()),
            )

    def get_all_tool_specs(self) -> list[ToolSpec]:
        """Get all the tool specs for all tools in this registry..

        Returns:
            A list of ToolSpecs.
        """
        all_tools = self.get_all_tools_config()
        tools: list[ToolSpec] = list(all_tools.values())
        return tools

    def get_tool(self, tool_name: str) -> BaseTool:
        """Retrieve a registered tool by name."""
        if tool_name in self.registry:
            return self.registry[tool_name]
        if tool_name in self.dynamic_tools:
            return self.dynamic_tools[tool_name]
        raise KeyError(f"Tool '{tool_name}' is not registered")

    def validate_tool_spec(self, tool_spec: ToolSpec) -> None:
        """Validate tool specification against required schema.

        Args:
            tool_spec: Tool specification to validate.

        Raises:
            ValueError: If the specification is invalid.
        """
        required_fields = ["name", "description"]
        missing_fields = [field for field in required_fields if field not in tool_spec]
        if missing_fields:
            raise ValueError(f"Missing required fields in tool spec: {', '.join(missing_fields)}")

        if "json" not in tool_spec["parameters"]:
            # Convert direct schema to proper format
            json_schema = normalize_schema(tool_spec["parameters"])
            tool_spec["parameters"] = {"json": json_schema}
            return

        # Validate json schema fields
        json_schema = tool_spec["parameters"]["json"]

        # Ensure schema has required fields
        if "type" not in json_schema:
            json_schema["type"] = "object"
        if "properties" not in json_schema:
            json_schema["properties"] = {}
        if "required" not in json_schema:
            json_schema["required"] = []

        # Validate property definitions
        for prop_name, prop_def in json_schema.get("properties", {}).items():
            if not isinstance(prop_def, dict):
                json_schema["properties"][prop_name] = {
                    "type": "string",
                    "description": f"Property {prop_name}",
                }
                continue

            # It is expected that type and description are already included in referenced $def.
            if "$ref" in prop_def:
                continue

            if "type" not in prop_def:
                prop_def["type"] = "string"
            if "description" not in prop_def:
                prop_def["description"] = f"Property {prop_name}"

    def _try_capture_tool_ref(self, tool: BaseTool) -> None:
        """Try to capture the module:function reference for a tool.

        This attempts to extract the reference from DecoratedFunctionTool instances
        to enable automatic serialization support.

        Args:
            tool: The tool to extract reference from
        """
        # Check if this is a DecoratedFunctionTool (has _tool_func attribute)
        if hasattr(tool, '_tool_func'):
            func = getattr(tool, '_tool_func')
            try:
                ref = get_ref_for_callable(func)
                self.tool_refs[tool.tool_name] = ref
                logger.debug("tool_name=<%s>, ref=<%s> | captured tool reference", tool.tool_name, ref)
            except Exception as e:
                logger.debug(
                    "tool_name=<%s> | could not capture tool reference: %s",
                    tool.tool_name,
                    e
                )

    def register_tool_by_ref(self, ref: str, tool_name: Optional[str] = None) -> None:
        """Register a tool by module:function string reference.

        This enables spec-compatible tool registration where tools are referenced
        by their module path instead of requiring instances.

        Args:
            ref: String reference in format "module.path:function_name"
            tool_name: Optional custom name for the tool (defaults to function name)

        Raises:
            ValueError: If the reference is invalid or cannot be imported

        Example:
            registry.register_tool_by_ref("myapp.tools:search_database")
            registry.register_tool_by_ref("myapp.tools:calculate", tool_name="calc")
        """
        # Validate the reference
        valid, error = validate_reference(ref)
        if not valid:
            raise ValueError(f"Invalid tool reference '{ref}': {error}")

        # Import the tool
        try:
            tool = import_from_ref(ref)
        except Exception as e:
            raise ValueError(f"Failed to import tool from '{ref}': {e}") from e

        # Check if it's a BaseTool instance
        if not isinstance(tool, BaseTool):
            raise ValueError(
                f"Tool at '{ref}' is not a BaseTool instance. "
                f"Use @tool decorator or subclass BaseTool."
            )

        # Determine the actual name to use
        actual_tool_name = tool_name or tool.tool_name

        # If custom name is provided and different from tool's name, register under custom name
        if tool_name and tool_name != tool.tool_name:
            # Register with custom name by directly adding to registry
            self.registry[tool_name] = tool
            logger.debug(
                "tool_name=<%s>, original_name=<%s>, tool_type=<%s> | registering tool with custom name",
                tool_name,
                tool.tool_name,
                tool.tool_type
            )
        else:
            # Register normally
            self.register_tool(tool)

        # Store the reference for serialization
        self.tool_refs[actual_tool_name] = ref

        logger.debug("tool_name=<%s>, ref=<%s> | registered tool by reference", actual_tool_name, ref)

    def get_tool_ref(self, tool_name: str) -> Optional[str]:
        """Get the module:function reference for a registered tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Module:function reference string, or None if not available

        Example:
            ref = registry.get_tool_ref("search_database")
            # Returns: "myapp.tools:search_database"
        """
        return self.tool_refs.get(tool_name)

    def to_spec_dict(self) -> dict[str, Any]:
        """Serialize the registry to a spec-compatible dictionary.

        This enables the tool registry to be serialized to JSON specifications
        for bidirectional conversion between Python and JSON.

        Returns:
            Dictionary containing tool specifications and references

        Example:
            spec = registry.to_spec_dict()
            # {
            #   "tools": [
            #     {"name": "search", "ref": "myapp.tools:search", "spec": {...}},
            #     ...
            #   ]
            # }
        """
        tools_list = []

        for tool_name, tool in self.registry.items():
            tool_dict: dict[str, Any] = {
                "name": tool_name,
                "spec": tool.tool_spec.copy()
            }

            # Add reference if available
            if tool_name in self.tool_refs:
                tool_dict["ref"] = self.tool_refs[tool_name]

            # Add metadata
            tool_dict["metadata"] = {
                "tool_type": tool.tool_type,
                "is_dynamic": tool.is_dynamic,
                "supports_async": tool.supports_async,
                "is_long_running": tool.is_long_running,
                "supports_hot_reload": tool.supports_hot_reload
            }

            tools_list.append(tool_dict)

        return {"tools": tools_list}

    @classmethod
    def from_spec_dict(cls, spec: dict[str, Any]) -> "ToolRegistry":
        """Deserialize a tool registry from a spec dictionary.

        This creates a new ToolRegistry and registers all tools from the spec.
        Tools with 'ref' field are loaded by reference, others must be
        provided as instances.

        Args:
            spec: Dictionary containing tool specifications

        Returns:
            New ToolRegistry instance with registered tools

        Raises:
            ValueError: If tool references cannot be imported

        Example:
            spec = {
                "tools": [
                    {"name": "search", "ref": "myapp.tools:search", ...},
                    ...
                ]
            }
            registry = ToolRegistry.from_spec_dict(spec)
        """
        registry = cls()

        for tool_dict in spec.get("tools", []):
            tool_name = tool_dict["name"]

            # If we have a reference, register by reference
            if "ref" in tool_dict:
                ref = tool_dict["ref"]
                try:
                    registry.register_tool_by_ref(ref, tool_name=tool_name)
                    logger.debug("tool_name=<%s>, ref=<%s> | loaded tool from spec", tool_name, ref)
                except Exception as e:
                    logger.warning(
                        "tool_name=<%s>, ref=<%s> | failed to load tool from spec: %s",
                        tool_name,
                        ref,
                        e
                    )
            else:
                logger.warning(
                    "tool_name=<%s> | no reference available, cannot load tool from spec",
                    tool_name
                )

        return registry

    class NewToolDict(TypedDict):
        """Dictionary type for adding or updating a tool in the configuration.

        Attributes:
            spec: The tool specification that defines the tool's interface and behavior.
        """

        spec: ToolSpec

    def _update_tool_config(self, tool_config: dict[str, Any], new_tool: NewToolDict) -> None:
        """Update tool configuration with a new tool.

        Args:
            tool_config: The current tool configuration dictionary.
            new_tool: The new tool to add/update.

        Raises:
            ValueError: If the new tool spec is invalid.
        """
        if not new_tool.get("spec"):
            raise ValueError("Invalid tool format - missing spec")

        # Validate tool spec before updating
        try:
            self.validate_tool_spec(new_tool["spec"])
        except ValueError as e:
            raise ValueError(f"Tool specification validation failed: {str(e)}") from e

        new_tool_name = new_tool["spec"]["name"]
        existing_tool_idx = None

        # Find if tool already exists
        for idx, tool_entry in enumerate(tool_config["tools"]):
            if tool_entry["toolSpec"]["name"] == new_tool_name:
                existing_tool_idx = idx
                break

        # Update existing tool or add new one
        new_tool_entry = {"toolSpec": new_tool["spec"]}
        if existing_tool_idx is not None:
            tool_config["tools"][existing_tool_idx] = new_tool_entry
            logger.debug("tool_name=<%s> | updated existing tool", new_tool_name)
        else:
            tool_config["tools"].append(new_tool_entry)
            logger.debug("tool_name=<%s> | added new tool", new_tool_name)
