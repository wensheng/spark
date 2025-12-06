---
title: Tool Classes API Reference
parent: API
nav_order: 3
---
# Tool Classes API Reference

This document provides the complete API reference for Spark's tool system, including the @tool decorator, BaseTool interface, ToolRegistry, and type definitions.

## Table of Contents

- [@tool Decorator](#tool-decorator)
- [ToolContext](#toolcontext)
- [BaseTool](#basetool)
- [DecoratedFunctionTool](#decoratedfunctiontool)
- [ToolRegistry](#toolregistry)
- [Type Definitions](#type-definitions)
  - [ToolSpec](#toolspec)
  - [ToolUse](#tooluse)
  - [ToolChoice](#toolchoice)
  - [ToolResult](#toolresult)

---

## @tool Decorator

**Module**: `spark.tools.decorator`

Decorator that transforms a Python function into a Spark tool with automatic metadata extraction and validation.

### Signature

```python
def tool(
    func: Optional[Callable[P, R]] = None,
    description: Optional[str] = None,
    parameters: Optional[dict] = None,
    name: Optional[str] = None,
    context: bool | str = False,
    long_running: bool = False,
    async_execution: bool | None = None
) -> Union[DecoratedFunctionTool[P, R], Callable[[Callable[P, R]], DecoratedFunctionTool[P, R]]]
```

**Parameters:**
- **func** (Callable, optional): The function to decorate. When used as `@tool` (no parentheses).
- **name** (str, optional): Custom name to override the function's name.
- **description** (str, optional): Custom description to override the function's docstring.
- **parameters** (dict, optional): Custom JSON schema to override automatically generated schema.
- **context** (bool | str): When True, injects ToolContext into parameter named `tool_context`. If string, uses that parameter name.
- **long_running** (bool): Hint that the tool may take a long time to complete.
- **async_execution** (bool, optional): Override automatic detection of coroutine functions.

**Returns:** DecoratedFunctionTool that wraps the original function.

### Usage Patterns

#### Simple Decorator

```python
from spark.tools.decorator import tool

@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: The search query

    Returns:
        Search results as a string
    """
    # Implementation here
    return results
```

#### With Parameters

```python
@tool(name="custom_search", description="Custom web search tool")
def my_search(query: str, max_results: int = 10) -> str:
    """Search with custom settings."""
    return search(query, max_results)
```

#### With Context Injection

```python
from spark.tools.decorator import tool, ToolContext

@tool(context=True)
def contextual_tool(query: str, tool_context: ToolContext) -> str:
    """Tool that accesses execution context."""
    agent = tool_context.invocation_state.get('agent')
    tool_id = tool_context.tool_use['toolUseId']

    return f"Processed {query} with tool ID {tool_id}"
```

#### Custom Context Parameter Name

```python
@tool(context="ctx")
def my_tool(query: str, ctx: ToolContext) -> str:
    """Tool with custom context parameter name."""
    return process(query, ctx)
```

#### Async Tool

```python
@tool
async def async_search(query: str) -> str:
    """Async web search."""
    result = await async_search_api(query)
    return result
```

### Metadata Extraction

The @tool decorator automatically extracts:

1. **Function name**: Used as tool name (unless overridden)
2. **Docstring**: Parsed for description and parameter docs
3. **Type hints**: Used for parameter types and validation
4. **Default values**: Preserved in generated schema
5. **Return type**: Documented in tool spec

### Example with Full Documentation

```python
from typing import Optional

@tool
def calculate(
    operation: str,
    a: float,
    b: float,
    precision: Optional[int] = 2
) -> float:
    """Perform a mathematical calculation.

    This tool supports basic arithmetic operations including addition,
    subtraction, multiplication, and division.

    Args:
        operation: The operation to perform (add, subtract, multiply, divide)
        a: First operand
        b: Second operand
        precision: Number of decimal places for result (default: 2)

    Returns:
        The result of the calculation rounded to specified precision

    Raises:
        ValueError: If operation is not supported
        ZeroDivisionError: If dividing by zero
    """
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        result = a / b
    else:
        raise ValueError(f"Unsupported operation: {operation}")

    return round(result, precision)
```

---

## ToolContext

**Module**: `spark.tools.decorator`

Context object containing framework-provided data for decorated tools.

```python
@dataclass
class ToolContext:
    tool_use: ToolUse
    invocation_state: dict[str, Any]
```

**Attributes:**
- **tool_use** (ToolUse): The complete ToolUse object containing tool invocation details:
  - `toolUseId`: Unique identifier for this invocation
  - `name`: Tool name
  - `input`: Input parameters passed to the tool
- **invocation_state** (dict): Caller-provided kwargs passed to the agent, including:
  - `agent`: The Agent instance executing this tool (if available)
  - Other custom state from the invocation

**Example:**
```python
@tool(context=True)
def smart_tool(query: str, tool_context: ToolContext) -> str:
    # Access tool use metadata
    tool_id = tool_context.tool_use['toolUseId']
    tool_name = tool_context.tool_use['name']

    # Access agent if available
    agent = tool_context.invocation_state.get('agent')
    if agent:
        history = agent.get_history()
        # Use history to inform tool behavior

    return f"Processed {query} (ID: {tool_id})"
```

---

## BaseTool

**Module**: `spark.tools.types`

Abstract base class for all Spark tools. Defines the interface that all tool implementations must follow.

### Abstract Properties

#### tool_name

```python
@property
@abstractmethod
def tool_name(self) -> str
```

The unique name of the tool used for identification and invocation.

#### tool_spec

```python
@property
@abstractmethod
def tool_spec(self) -> ToolSpec
```

Tool specification that describes its functionality and parameters.

#### tool_type

```python
@property
@abstractmethod
def tool_type(self) -> str
```

The type of the tool implementation (e.g., 'function', 'python', 'lambda').

### Properties

#### supports_hot_reload

```python
@property
def supports_hot_reload(self) -> bool
```

Whether the tool supports automatic reloading when modified.

**Returns:** False by default.

#### is_dynamic

```python
@property
def is_dynamic(self) -> bool
```

Whether the tool was dynamically loaded during runtime.

**Returns:** True if loaded dynamically, False otherwise.

#### supports_async

```python
@property
def supports_async(self) -> bool
```

Whether the tool provides an async execution path.

**Returns:** True if tool supports async, False otherwise.

#### is_long_running

```python
@property
def is_long_running(self) -> bool
```

Whether the tool is expected to run for an extended period.

**Returns:** True if long-running, False otherwise.

### Methods

#### mark_dynamic

```python
def mark_dynamic(self) -> None
```

Mark this tool as dynamically loaded.

#### mark_supports_async

```python
def mark_supports_async(self) -> None
```

Mark this tool as supporting async execution.

#### mark_long_running

```python
def mark_long_running(self) -> None
```

Mark this tool as potentially long running.

#### __call__ (abstract)

```python
@abstractmethod
def __call__(self, *args: Any, **kwargs: Any) -> Any
```

Call the tool with the given arguments.

#### acall

```python
async def acall(self, *args: Any, **kwargs: Any) -> Any
```

Async entry point for tools. Defaults to calling the synchronous implementation.

#### get_display_properties

```python
def get_display_properties(self) -> dict[str, str]
```

Get properties to display in UI representations of this tool.

**Returns:** Dictionary of property names and their string values.

### Example Custom Tool

```python
from spark.tools.types import BaseTool, ToolSpec

class CustomTool(BaseTool):
    """Custom tool implementation."""

    @property
    def tool_name(self) -> str:
        return "custom_tool"

    @property
    def tool_spec(self) -> ToolSpec:
        return {
            "name": "custom_tool",
            "description": "A custom tool implementation",
            "parameters": {
                "json": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "Input parameter"
                        }
                    },
                    "required": ["input"]
                }
            }
        }

    @property
    def tool_type(self) -> str:
        return "custom"

    def __call__(self, input: str) -> str:
        return f"Processed: {input}"
```

---

## DecoratedFunctionTool

**Module**: `spark.tools.decorator`

A BaseTool that wraps a function decorated with @tool. This class adapts Python functions to the BaseTool interface while maintaining the function's original behavior.

### Properties

All properties from BaseTool, plus:

#### tool_func

The original wrapped function (internal use).

### Methods

#### __call__

```python
def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R
```

Call the original function with provided arguments. Handles both sync and async functions.

#### acall

```python
async def acall(self, *args: P.args, **kwargs: P.kwargs) -> Any
```

Async entry point that honors the wrapped function type.

#### prepare_tool_kwargs

```python
def prepare_tool_kwargs(
    self,
    tool_use: ToolUse,
    invocation_state: Optional[dict[str, Any]] = None
) -> dict[str, Any]
```

Validate and augment tool_use input for execution. Used internally by the framework.

**Parameters:**
- `tool_use`: The tool use request
- `invocation_state`: Optional invocation state

**Returns:** Validated and augmented kwargs for the tool function.

---

## ToolRegistry

**Module**: `spark.tools.registry`

Central registry for all tools available to an agent. Manages tool registration, validation, discovery, and invocation.

### Constructor

```python
def __init__(self) -> None
```

### Attributes

- **registry** (dict[str, BaseTool]): Main tool registry
- **dynamic_tools** (dict[str, BaseTool]): Dynamically loaded tools
- **tool_refs** (dict[str, str]): Tool name to module:function reference mapping

### Methods

#### process_tools

```python
def process_tools(self, tools: list[Any]) -> list[str]
```

Process tools list that can contain tool names, paths, imported modules, or functions.

**Parameters:**
- `tools`: List of BaseTool instances

**Returns:** List of tool names that were processed.

**Example:**
```python
from spark.tools.registry import ToolRegistry

registry = ToolRegistry()
tool_names = registry.process_tools([search_tool, calculator_tool])
print(f"Registered tools: {tool_names}")
```

#### register_tool

```python
def register_tool(self, tool: BaseTool) -> None
```

Register a tool with the registry.

**Parameters:**
- `tool`: The tool to register

**Raises:**
- `ValueError`: If tool name already exists or conflicts with normalized name

**Example:**
```python
@tool
def my_tool(input: str) -> str:
    return f"Processed: {input}"

registry = ToolRegistry()
registry.register_tool(my_tool)
```

#### register_tool_by_ref

```python
def register_tool_by_ref(
    self,
    ref: str,
    tool_name: Optional[str] = None
) -> None
```

Register a tool by module:function string reference (spec-compatible).

**Parameters:**
- `ref`: String reference in format "module.path:function_name"
- `tool_name`: Optional custom name for the tool

**Raises:**
- `ValueError`: If reference is invalid or cannot be imported

**Example:**
```python
registry.register_tool_by_ref("myapp.tools:search_database")
registry.register_tool_by_ref("myapp.tools:calculate", tool_name="calc")
```

#### get_tool

```python
def get_tool(self, tool_name: str) -> BaseTool
```

Retrieve a registered tool by name.

**Parameters:**
- `tool_name`: Name of the tool

**Returns:** BaseTool instance

**Raises:**
- `KeyError`: If tool is not registered

#### get_all_tool_specs

```python
def get_all_tool_specs(self) -> list[ToolSpec]
```

Get all tool specifications for all tools in this registry.

**Returns:** List of ToolSpec dictionaries.

#### get_all_tools_config

```python
def get_all_tools_config(self) -> dict[str, Any]
```

Dynamically generate tool configuration by combining built-in and dynamic tools.

**Returns:** Dictionary containing all tool configurations.

#### validate_tool_spec

```python
def validate_tool_spec(self, tool_spec: ToolSpec) -> None
```

Validate tool specification against required schema.

**Parameters:**
- `tool_spec`: Tool specification to validate

**Raises:**
- `ValueError`: If the specification is invalid

#### get_tool_ref

```python
def get_tool_ref(self, tool_name: str) -> Optional[str]
```

Get the module:function reference for a registered tool.

**Parameters:**
- `tool_name`: Name of the tool

**Returns:** Module:function reference string, or None if not available.

#### to_spec_dict

```python
def to_spec_dict(self) -> dict[str, Any]
```

Serialize the registry to a spec-compatible dictionary.

**Returns:** Dictionary containing tool specifications and references.

**Example:**
```python
spec = registry.to_spec_dict()
# {
#   "tools": [
#     {"name": "search", "ref": "myapp.tools:search", "spec": {...}},
#     ...
#   ]
# }
```

#### from_spec_dict (classmethod)

```python
@classmethod
def from_spec_dict(cls, spec: dict[str, Any]) -> ToolRegistry
```

Deserialize a tool registry from a spec dictionary.

**Parameters:**
- `spec`: Dictionary containing tool specifications

**Returns:** New ToolRegistry instance with registered tools.

**Raises:**
- `ValueError`: If tool references cannot be imported

---

## Type Definitions

### ToolSpec

**Module**: `spark.tools.types`

Specification for a tool that can be used by an agent.

```python
class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: dict[str, Any]
    response_schema: NotRequired[dict]
    x_spark: NotRequired[ToolRuntimeMetadata]
```

**Fields:**
- **name** (str): The unique name of the tool
- **description** (str): Human-readable description of what the tool does
- **parameters** (dict): JSON Schema defining expected input parameters
  - Must contain a `json` key with the schema object
  - Schema should have `type`, `properties`, and `required` fields
- **response_schema** (dict, optional): JSON Schema for expected output format (Bedrock only)
- **x_spark** (ToolRuntimeMetadata, optional): Spark-specific runtime hints

**Example:**
```python
tool_spec: ToolSpec = {
    "name": "search_database",
    "description": "Search the customer database",
    "parameters": {
        "json": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results"
                }
            },
            "required": ["query"]
        }
    }
}
```

### ToolUse

**Module**: `spark.tools.types`

A request from the model to use a specific tool with provided input.

```python
class ToolUse(TypedDict):
    input: Any
    name: NotRequired[str]
    toolUseId: str
```

**Fields:**
- **input** (Any): The input parameters for the tool (JSON-serializable)
- **name** (str, optional): The name of the tool to invoke
- **toolUseId** (str): Unique identifier for this specific tool use request

**Example:**
```python
tool_use: ToolUse = {
    "toolUseId": "call_abc123",
    "name": "search_database",
    "input": {
        "query": "customer orders",
        "limit": 10
    }
}
```

### ToolChoice

**Module**: `spark.tools.types`

Configuration for how the model should choose tools.

```python
ToolChoice = Union[
    dict[Literal["auto"], ToolChoiceAuto],
    dict[Literal["any"], ToolChoiceAny],
    dict[Literal["tool"], ToolChoiceTool],
]
```

**Variants:**

#### Auto

```python
{"auto": {}}
```

The model decides whether to use tools based on context.

#### Any

```python
{"any": {}}
```

The model must use at least one tool (any available tool).

#### Specific Tool

```python
{"tool": {"name": "search_database"}}
```

The model must use the specified tool.

**Example:**
```python
# Let model decide
tool_choice = {"auto": {}}

# Require tool usage
tool_choice = {"any": {}}

# Force specific tool
tool_choice = {"tool": {"name": "calculator"}}
```

### ToolResult

**Module**: `spark.tools.types`

Result of a tool execution.

```python
class ToolResult(TypedDict):
    content: list
    status: Literal["success", "error", "in_progress"]
    toolUseId: str
    metadata: NotRequired[dict[str, Any]]
    started_at: NotRequired[str]
    completed_at: NotRequired[str]
    progress: NotRequired[float]
```

**Fields:**
- **content** (list): List of result content returned by the tool
- **status** (str): Status of the tool execution
  - `"success"`: Tool completed successfully
  - `"error"`: Tool execution failed
  - `"in_progress"`: Tool is still running (long-running tools)
- **toolUseId** (str): The unique identifier of the tool use request
- **metadata** (dict, optional): Implementation-specific metadata (latency, identifiers, etc.)
- **started_at** (str, optional): ISO timestamp when execution started
- **completed_at** (str, optional): ISO timestamp when execution completed
- **progress** (float, optional): Progress indicator between 0 and 1 for long-running tools

**Example:**
```python
tool_result: ToolResult = {
    "toolUseId": "call_abc123",
    "status": "success",
    "content": [{"text": "Found 5 matching records"}],
    "metadata": {
        "latency_ms": 245,
        "records_found": 5
    },
    "completed_at": "2025-01-15T10:30:00Z"
}
```

### ToolRuntimeMetadata

**Module**: `spark.tools.types`

Spark-specific runtime hints for a tool.

```python
class ToolRuntimeMetadata(TypedDict, total=False):
    supports_async: bool
    long_running: bool
```

**Fields:**
- **supports_async** (bool): Whether the tool provides async execution
- **long_running** (bool): Whether the tool may take extended time to complete

---

## Helper Functions

### update_tool_runtime_metadata

**Module**: `spark.tools.types`

```python
def update_tool_runtime_metadata(
    tool_spec: ToolSpec,
    *,
    supports_async: bool | None = None,
    long_running: bool | None = None
) -> None
```

Attach Spark runtime metadata flags to a tool specification.

**Parameters:**
- `tool_spec`: The tool specification to update (modified in place)
- `supports_async`: Whether tool supports async execution
- `long_running`: Whether tool is long-running

**Example:**
```python
from spark.tools.types import ToolSpec, update_tool_runtime_metadata

tool_spec: ToolSpec = {
    "name": "data_processor",
    "description": "Process large datasets",
    "parameters": {...}
}

update_tool_runtime_metadata(
    tool_spec,
    supports_async=True,
    long_running=True
)
```

---

## Complete Example

Here's a complete example showing tool creation, registration, and usage:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool, ToolContext
from spark.tools.registry import ToolRegistry
from typing import Optional

# Define tools with @tool decorator
@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the customer database.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        Search results as formatted string
    """
    # Implementation
    results = perform_search(query, limit)
    return f"Found {len(results)} results: {results}"

@tool(context=True)
def contextual_search(query: str, tool_context: ToolContext) -> str:
    """Search with access to agent context.

    Args:
        query: Search query string
        tool_context: Execution context (injected automatically)
    """
    agent = tool_context.invocation_state.get('agent')
    # Use agent history to improve search
    history = agent.get_history() if agent else []
    return enhanced_search(query, history)

@tool
async def async_api_call(endpoint: str) -> dict:
    """Make an async API call.

    Args:
        endpoint: API endpoint to call

    Returns:
        API response as dictionary
    """
    response = await make_api_call(endpoint)
    return response

# Create registry and register tools
registry = ToolRegistry()
registry.process_tools([search_database, contextual_search, async_api_call])

# Use tools with agent
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o-mini"),
    tools=[search_database, contextual_search, async_api_call],
    tool_choice='auto',
    parallel_tool_execution=True
)

agent = Agent(config=config)

# Agent can now use all registered tools
result = await agent.process(context)
```

---

## See Also

- [Agent Classes](agents.md) - Agent configuration and tool usage
- [Model Classes](models.md) - LLM model providers
- [Examples](/examples/) - Complete tool examples
