# Tool Registry Reference

This reference covers the `ToolRegistry` class for managing collections of tools in Spark ADK.

## Overview

The `ToolRegistry` provides a central repository for tool discovery, management, and validation. It serves as the bridge between tool definitions and agent/LLM execution, handling:

- Tool registration and deduplication
- Tool specification generation
- Tool lookup by name
- Tool validation and schema checking
- Provider-specific format conversion

## ToolRegistry Class

### Location

```python
from spark.tools.registry import ToolRegistry
```

### Basic Usage

```python
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import tool

# Create a registry
registry = ToolRegistry()

# Define tools
@tool
def search(query: str) -> list[dict]:
    """Search for information."""
    return [{"result": "example"}]

@tool
def calculate(expression: str) -> float:
    """Calculate a mathematical expression."""
    return eval(expression)

# Register tools
registry.process_tools([search, calculate])

# Get all tool specs
tool_specs = registry.get_all_tool_specs()

# Retrieve specific tool
search_tool = registry.get_tool("search")
```

## Core Methods

### process_tools()

Register one or more tools with the registry.

**Signature**:
```python
def process_tools(
    self,
    tools: list[Union[Callable, BaseTool]]
) -> None
```

**Parameters**:
- `tools`: List of tool functions (decorated with `@tool`) or `BaseTool` instances

**Behavior**:
- Extracts tool metadata from decorated functions
- Creates `BaseTool` instances if needed
- Stores tools in internal dictionary by name
- Skips duplicate registrations (same name)
- Validates tool specifications

**Examples**:

**Register multiple tools**:
```python
from spark.tools.decorator import tool
from spark.tools.registry import ToolRegistry

@tool
def tool1(x: int) -> int:
    """First tool."""
    return x * 2

@tool
def tool2(y: str) -> str:
    """Second tool."""
    return y.upper()

registry = ToolRegistry()
registry.process_tools([tool1, tool2])

print(f"Registered {len(registry._tools)} tools")
# Output: Registered 2 tools
```

**Register tools incrementally**:
```python
registry = ToolRegistry()

# First batch
registry.process_tools([tool1, tool2])

# Second batch (adds new, skips duplicates)
registry.process_tools([tool2, tool3])  # tool2 already registered, skipped
```

**Register BaseTool instances**:
```python
from spark.tools.types import BaseTool

class CustomTool(BaseTool):
    def __init__(self):
        self.tool_name = "custom_tool"
        self.tool_spec = {...}  # Tool specification

    async def __call__(self, **kwargs):
        # Tool implementation
        pass

custom = CustomTool()
registry.process_tools([custom])
```

### get_all_tool_specs()

Retrieve specifications for all registered tools.

**Signature**:
```python
def get_all_tool_specs(self) -> list[dict]
```

**Returns**:
- List of tool specification dictionaries

**Format**:
Each spec contains:
```python
{
    "name": "tool_name",
    "description": "Tool description from docstring",
    "input_schema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "integer", "description": "..."}
        },
        "required": ["param1"]
    }
}
```

**Example**:
```python
@tool
def add(x: int, y: int) -> int:
    """Add two numbers.

    Args:
        x: First number
        y: Second number
    """
    return x + y

registry = ToolRegistry()
registry.process_tools([add])

specs = registry.get_all_tool_specs()
print(specs)
# [
#     {
#         "name": "add",
#         "description": "Add two numbers.",
#         "input_schema": {
#             "type": "object",
#             "properties": {
#                 "x": {"type": "integer", "description": "First number"},
#                 "y": {"type": "integer", "description": "Second number"}
#             },
#             "required": ["x", "y"]
#         }
#     }
# ]
```

### get_tool()

Retrieve a specific tool by name.

**Signature**:
```python
def get_tool(self, name: str) -> Optional[BaseTool]
```

**Parameters**:
- `name`: The tool name to look up

**Returns**:
- `BaseTool` instance if found, `None` otherwise

**Example**:
```python
@tool
def search(query: str) -> list[dict]:
    """Search for information."""
    return []

registry = ToolRegistry()
registry.process_tools([search])

# Retrieve by name
search_tool = registry.get_tool("search")
if search_tool:
    result = await search_tool(query="example")

# Non-existent tool
missing = registry.get_tool("nonexistent")  # Returns None
```

### validate_tool_spec()

Validate a tool specification for correctness.

**Signature**:
```python
def validate_tool_spec(self, spec: dict) -> tuple[bool, Optional[str]]
```

**Parameters**:
- `spec`: Tool specification dictionary to validate

**Returns**:
- Tuple of `(is_valid, error_message)`
  - `is_valid`: `True` if spec is valid, `False` otherwise
  - `error_message`: Description of validation error, or `None` if valid

**Validation Checks**:
- Required fields present (`name`, `description`, `input_schema`)
- Schema structure is valid JSON Schema
- Parameter types are supported
- Required parameters exist in properties

**Example**:
```python
registry = ToolRegistry()

# Valid spec
valid_spec = {
    "name": "test_tool",
    "description": "A test tool",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string"}
        },
        "required": ["param"]
    }
}

is_valid, error = registry.validate_tool_spec(valid_spec)
print(f"Valid: {is_valid}")  # True

# Invalid spec (missing required field)
invalid_spec = {
    "name": "bad_tool",
    # Missing description
    "input_schema": {...}
}

is_valid, error = registry.validate_tool_spec(invalid_spec)
print(f"Valid: {is_valid}, Error: {error}")
# Valid: False, Error: Missing required field 'description'
```

## Registry Management

### Clearing Tools

Remove all tools from registry:

```python
registry = ToolRegistry()
registry.process_tools([tool1, tool2, tool3])

# Clear all tools
registry._tools.clear()

print(len(registry.get_all_tool_specs()))  # 0
```

### Checking Registration

Check if a tool is registered:

```python
registry = ToolRegistry()
registry.process_tools([search])

# Check if tool exists
if registry.get_tool("search"):
    print("Search tool is registered")

# Check by name
if "search" in registry._tools:
    print("Search tool exists")
```

### Tool Count

Get the number of registered tools:

```python
registry = ToolRegistry()
registry.process_tools([tool1, tool2, tool3])

tool_count = len(registry._tools)
print(f"Registry contains {tool_count} tools")
```

### Listing Tool Names

Get names of all registered tools:

```python
registry = ToolRegistry()
registry.process_tools([search, calculate, format_text])

tool_names = list(registry._tools.keys())
print(f"Available tools: {', '.join(tool_names)}")
# Available tools: search, calculate, format_text
```

## Global vs. Local Registries

### Global Registry Pattern

Use a single global registry for application-wide tools:

```python
# tools/registry.py
from spark.tools.registry import ToolRegistry

# Global registry instance
GLOBAL_REGISTRY = ToolRegistry()

def register_tool(func):
    """Decorator to auto-register tools globally."""
    from spark.tools.decorator import tool
    decorated = tool(func)
    GLOBAL_REGISTRY.process_tools([decorated])
    return decorated

# tools/search_tools.py
from .registry import register_tool

@register_tool
def web_search(query: str) -> list[dict]:
    """Search the web."""
    return []

@register_tool
def db_search(query: str) -> list[dict]:
    """Search the database."""
    return []

# main.py
from tools.registry import GLOBAL_REGISTRY
from spark.agents import Agent

# Use global registry
agent = Agent(tools=GLOBAL_REGISTRY.get_all_tool_specs())
```

**Advantages**:
- Single source of truth
- Easy to share tools across agents
- Automatic registration at import time

**Disadvantages**:
- Global state can make testing harder
- Less flexibility per-agent

### Local Registry Pattern

Create separate registries for different contexts:

```python
from spark.tools.registry import ToolRegistry

# Create context-specific registries
admin_registry = ToolRegistry()
admin_registry.process_tools([delete_user, modify_settings, view_logs])

user_registry = ToolRegistry()
user_registry.process_tools([search, view_profile, send_message])

# Use appropriate registry per agent
admin_agent = Agent(tools=admin_registry.get_all_tool_specs())
user_agent = Agent(tools=user_registry.get_all_tool_specs())
```

**Advantages**:
- Explicit tool access control
- Easier testing with isolated registries
- Different tool sets per context

**Disadvantages**:
- More boilerplate
- Must manage multiple registries

### Hybrid Pattern

Combine global and local registries:

```python
from spark.tools.registry import ToolRegistry

# Global registry for common tools
global_registry = ToolRegistry()
global_registry.process_tools([search, calculate, format_text])

# Create specialized registry extending global
def create_specialized_registry(additional_tools: list):
    """Create registry with global + specialized tools."""
    registry = ToolRegistry()

    # Add global tools
    for tool_name, tool in global_registry._tools.items():
        registry._tools[tool_name] = tool

    # Add specialized tools
    registry.process_tools(additional_tools)

    return registry

# Use for specialized agents
admin_registry = create_specialized_registry([delete_user, modify_settings])
```

## Advanced Usage

### Conditional Tool Registration

Register tools based on configuration or environment:

```python
from spark.tools.registry import ToolRegistry
import os

def create_registry(config: dict) -> ToolRegistry:
    """Create registry with tools based on config."""
    registry = ToolRegistry()

    # Always available tools
    base_tools = [search, calculate]
    registry.process_tools(base_tools)

    # Optional tools based on config
    if config.get("enable_web_search"):
        registry.process_tools([web_search])

    if config.get("enable_database"):
        registry.process_tools([db_query])

    if os.getenv("ENABLE_ADMIN_TOOLS"):
        registry.process_tools([delete_user, modify_settings])

    return registry

# Create registry with specific features
registry = create_registry({
    "enable_web_search": True,
    "enable_database": False
})
```

### Tool Versioning

Manage multiple versions of tools:

```python
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import tool

@tool
def search_v1(query: str) -> list[dict]:
    """Search (v1) - basic search."""
    return basic_search(query)

@tool
def search_v2(query: str) -> list[dict]:
    """Search (v2) - enhanced search with ranking."""
    return enhanced_search(query)

# Create version-specific registries
registry_v1 = ToolRegistry()
registry_v1.process_tools([search_v1])

registry_v2 = ToolRegistry()
registry_v2.process_tools([search_v2])

# Use appropriate version
agent = Agent(tools=registry_v2.get_all_tool_specs())
```

### Tool Groups

Organize tools into logical groups:

```python
from spark.tools.registry import ToolRegistry
from typing import Dict

class ToolGroups:
    """Organize tools into logical groups."""

    def __init__(self):
        self.groups: Dict[str, ToolRegistry] = {}

    def add_group(self, name: str, tools: list):
        """Add a tool group."""
        registry = ToolRegistry()
        registry.process_tools(tools)
        self.groups[name] = registry

    def get_group(self, name: str) -> ToolRegistry:
        """Get a tool group registry."""
        return self.groups.get(name, ToolRegistry())

    def get_combined(self, group_names: list[str]) -> ToolRegistry:
        """Combine multiple groups into one registry."""
        combined = ToolRegistry()
        for name in group_names:
            if registry := self.groups.get(name):
                for tool_name, tool in registry._tools.items():
                    combined._tools[tool_name] = tool
        return combined

# Usage
groups = ToolGroups()
groups.add_group("search", [web_search, db_search, file_search])
groups.add_group("data", [fetch_data, transform_data, save_data])
groups.add_group("admin", [delete_user, modify_settings])

# Create agent with specific tool groups
search_tools = groups.get_group("search")
agent1 = Agent(tools=search_tools.get_all_tool_specs())

# Create agent with combined groups
combined = groups.get_combined(["search", "data"])
agent2 = Agent(tools=combined.get_all_tool_specs())
```

### Dynamic Tool Loading

Load tools dynamically from modules:

```python
import importlib
from spark.tools.registry import ToolRegistry

def load_tools_from_module(module_path: str) -> ToolRegistry:
    """Load all tools from a Python module."""
    registry = ToolRegistry()

    # Import module
    module = importlib.import_module(module_path)

    # Find all tool functions (decorated with @tool)
    tools = []
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and hasattr(obj, 'tool_spec'):
            tools.append(obj)

    registry.process_tools(tools)
    return registry

# Load tools from specific modules
search_registry = load_tools_from_module("myapp.tools.search")
data_registry = load_tools_from_module("myapp.tools.data")
```

## Error Handling

### Registration Errors

Handle errors during tool registration:

```python
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import tool

registry = ToolRegistry()

try:
    # This tool has invalid type hints
    @tool
    def bad_tool(x):  # Missing type hint
        """A bad tool."""
        return x

    registry.process_tools([bad_tool])
except ValidationError as e:
    print(f"Tool registration failed: {e}")
```

### Tool Lookup Errors

Handle missing tools gracefully:

```python
registry = ToolRegistry()
registry.process_tools([search])

# Safe tool lookup
tool = registry.get_tool("nonexistent")
if tool is None:
    print("Tool not found, using fallback")
    tool = registry.get_tool("search")

# Or with exception
def get_tool_or_error(registry: ToolRegistry, name: str):
    tool = registry.get_tool(name)
    if tool is None:
        raise ValueError(f"Tool '{name}' not found in registry")
    return tool

try:
    tool = get_tool_or_error(registry, "missing")
except ValueError as e:
    print(e)
```

## Testing Registries

### Unit Testing

Test registry operations:

```python
import pytest
from spark.tools.registry import ToolRegistry
from spark.tools.decorator import tool

@tool
def test_tool(x: int) -> int:
    """A test tool."""
    return x

def test_process_tools():
    registry = ToolRegistry()
    registry.process_tools([test_tool])

    assert "test_tool" in registry._tools
    assert len(registry.get_all_tool_specs()) == 1

def test_get_tool():
    registry = ToolRegistry()
    registry.process_tools([test_tool])

    tool = registry.get_tool("test_tool")
    assert tool is not None
    assert tool.tool_name == "test_tool"

def test_get_nonexistent_tool():
    registry = ToolRegistry()
    tool = registry.get_tool("missing")
    assert tool is None

def test_duplicate_registration():
    registry = ToolRegistry()
    registry.process_tools([test_tool])
    registry.process_tools([test_tool])  # Should not error

    # Still only one tool
    assert len(registry.get_all_tool_specs()) == 1
```

### Integration Testing

Test registry with agents:

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.tools.registry import ToolRegistry

@tool
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y

@pytest.mark.asyncio
async def test_agent_with_registry():
    # Create registry
    registry = ToolRegistry()
    registry.process_tools([multiply])

    # Create agent with tools from registry
    config = AgentConfig(
        model=mock_model,
        tools=registry.get_all_tool_specs()
    )
    agent = Agent(config=config)

    # Test agent uses tool
    result = await agent.run("What is 5 times 6?")
    assert "30" in result
```

## Summary

The `ToolRegistry` provides:

- **Centralized tool management** with simple registration API
- **Tool specification generation** for LLM consumption
- **Tool lookup and validation** for runtime execution
- **Flexible patterns** for global, local, and hybrid registries
- **Dynamic tool loading** for modular applications
- **Error handling** for robust tool management

**Key methods**:
- `process_tools()`: Register tools
- `get_all_tool_specs()`: Get all tool specifications
- `get_tool()`: Retrieve tool by name
- `validate_tool_spec()`: Validate tool specifications

Next steps:
- See [Tool Fundamentals](fundamentals.md) for creating tools
- See [Tool Development](development.md) for advanced patterns
- See [Tool Specifications](specifications.md) for spec details
- See [Agent Documentation](/docs/agents/) for using registries with agents
