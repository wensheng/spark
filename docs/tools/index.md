---
title: Tools 
nav_order: 7
---
# Tools
---

Spark's tools system provides a decorator-based approach to creating LLM-callable tools. The `@tool` decorator transforms ordinary Python functions into tools that can be:

- Called by LLM agents during reasoning and execution
- Automatically registered with tool registries
- Serialized into provider-specific schemas (OpenAI, Bedrock, Gemini)
- Validated for correctness and type safety

## The @tool Decorator

### Basic Usage

The simplest tool is a regular Python function decorated with `@tool`:

```python
from spark.tools.decorator import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The name of the city to get weather for

    Returns:
        A description of the current weather
    """
    # Implementation
    return f"Weather in {city}: Sunny, 72°F"
```

The decorator automatically extracts:
- **Function name** becomes tool name (`get_weather`)
- **Type hints** define parameter types and return type
- **Docstring** provides description and parameter documentation

### What the Decorator Does

When you apply `@tool`, the framework:

1. **Parses the function signature** to extract parameters and types
2. **Extracts metadata** from docstrings using `docstring_parser`
3. **Generates JSON schema** for parameter validation
4. **Creates a ToolDefinitionSpec** with all metadata
5. **Wraps the function** to handle async/sync execution
6. **Registers the tool** (if using a registry)

### Metadata Extraction

The decorator extracts rich metadata from your function:

```python
@tool
def search_database(
    query: str,
    limit: int = 10,
    include_archived: bool = False
) -> list[dict]:
    """Search the database for matching records.

    This tool searches across all indexed fields and returns
    matching records sorted by relevance.

    Args:
        query: The search query string
        limit: Maximum number of results to return (default: 10)
        include_archived: Whether to include archived records

    Returns:
        A list of matching records with metadata

    Raises:
        DatabaseError: If the database connection fails
    """
    # Implementation
    pass
```

**Extracted metadata**:
- **name**: `search_database`
- **description**: "Search the database for matching records. This tool searches..."
- **parameters**:
  - `query`: string, required, "The search query string"
  - `limit`: integer, optional (default: 10), "Maximum number of results..."
  - `include_archived`: boolean, optional (default: False), "Whether to include..."
- **return_type**: `list[dict]`
- **raises**: `DatabaseError`

## Function Signatures and Type Hints

### Required Type Hints

Type hints are required for all parameters and the return value:

```python
# CORRECT: Full type hints
@tool
def calculate(x: float, y: float) -> float:
    """Add two numbers."""
    return x + y

# INCORRECT: Missing type hints
@tool
def calculate(x, y):  # Will raise validation error
    """Add two numbers."""
    return x + y
```

### Supported Types

Spark tools support all standard Python types:

**Basic types**:
```python
@tool
def process(
    text: str,
    count: int,
    ratio: float,
    enabled: bool
) -> str:
    """Process with basic types."""
    pass
```

**Collection types**:
```python
from typing import List, Dict, Optional, Union

@tool
def batch_process(
    items: list[str],
    config: dict[str, int],
    optional_data: Optional[str] = None,
    mode: Union[str, int] = "auto"
) -> list[dict]:
    """Process with collection types."""
    pass
```

**Complex types**:
```python
from typing import Any, Literal
from pydantic import BaseModel

class SearchParams(BaseModel):
    query: str
    filters: dict[str, Any]

@tool
def search(
    params: SearchParams,
    output_format: Literal["json", "csv", "xml"] = "json"
) -> dict:
    """Search with complex types."""
    pass
```

### Type Validation

Types are validated at runtime using Pydantic. Invalid types raise `ValidationError`:

```python
@tool
def add(x: int, y: int) -> int:
    """Add two integers."""
    return x + y

# This will raise ValidationError
result = add("not", "numbers")  # Expected int, got str
```

## Docstring-Based Metadata

### Docstring Format

Spark supports standard Python docstring formats (Google, NumPy, Sphinx styles). The most commonly used is Google style:

```python
@tool
def transfer_funds(
    from_account: str,
    to_account: str,
    amount: float,
    memo: Optional[str] = None
) -> dict:
    """Transfer funds between accounts.

    This tool transfers money from one account to another with
    optional memo for record keeping. The transfer is atomic and
    will roll back if any error occurs.

    Args:
        from_account: The source account ID
        to_account: The destination account ID
        amount: Amount to transfer in USD
        memo: Optional memo for the transaction

    Returns:
        A dictionary containing:
        - transaction_id: Unique transaction identifier
        - status: Transaction status (success/failed)
        - timestamp: When the transaction occurred

    Raises:
        InsufficientFundsError: If source account has insufficient balance
        InvalidAccountError: If either account does not exist

    Examples:
        >>> transfer_funds("ACC001", "ACC002", 100.0, "Payment")
        {'transaction_id': 'TXN123', 'status': 'success', ...}
    """
    # Implementation
    pass
```

### Best Practices for Docstrings

1. **Write clear descriptions**: LLMs read these to understand tool purpose
2. **Document all parameters**: Explain what each parameter means
3. **Describe return values**: Help LLMs understand what they'll receive
4. **Note side effects**: Document any state changes or external effects
5. **Provide examples**: Help LLMs understand usage patterns

**Good docstring**:
```python
@tool
def send_email(recipient: str, subject: str, body: str) -> bool:
    """Send an email to a recipient.

    Sends an email using the configured SMTP server. The email
    is sent asynchronously and this function returns immediately
    after queuing the message.

    Args:
        recipient: Email address of the recipient (must be valid format)
        subject: Email subject line (max 200 characters)
        body: Email body content (supports plain text only)

    Returns:
        True if email was queued successfully, False otherwise
    """
    pass
```

**Poor docstring**:
```python
@tool
def send_email(recipient: str, subject: str, body: str) -> bool:
    """Sends email."""  # Too brief, no parameter documentation
    pass
```

## Sync vs. Async Tools

### Synchronous Tools

Most tools are synchronous functions:

```python
@tool
def calculate_tax(amount: float, tax_rate: float) -> float:
    """Calculate tax on an amount."""
    return amount * tax_rate
```

**When to use sync tools**:
- Pure computation with no I/O
- Calling synchronous libraries
- Simple transformations
- Quick operations (< 1ms)

### Asynchronous Tools

Use async tools for I/O-bound operations:

```python
import httpx

@tool
async def fetch_url(url: str) -> str:
    """Fetch content from a URL.

    Args:
        url: The URL to fetch

    Returns:
        The response body as a string
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
```

**When to use async tools**:
- Network requests (HTTP, database, RPC)
- File I/O operations
- Long-running computations
- Operations that benefit from concurrency

### Mixed Sync/Async Execution

The framework handles both automatically:

```python
from spark.agents import Agent

# Register both sync and async tools
@tool
def sync_tool(x: int) -> int:
    """A synchronous tool."""
    return x * 2

@tool
async def async_tool(url: str) -> str:
    """An asynchronous tool."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text

# Agent handles both transparently
agent = Agent(tools=[sync_tool, async_tool])
result = await agent.run("Fetch https://example.com and double the number 42")
```

## Tool Context Parameter

### What is Tool Context?

Tool context provides access to execution metadata and runtime information. It's an optional parameter you can add to any tool:

```python
from spark.tools.types import ToolContext

@tool
def debug_info(message: str, context: ToolContext = None) -> str:
    """Log a debug message with context information.

    Args:
        message: The message to log
        context: Tool execution context (injected automatically)

    Returns:
        Formatted log message with context
    """
    if context:
        return f"[{context.tool_name}] {message} (call_id: {context.call_id})"
    return f"[unknown] {message}"
```

### Context Contents

The `ToolContext` object contains:

```python
class ToolContext:
    tool_name: str          # Name of the tool being executed
    call_id: str            # Unique identifier for this tool call
    metadata: dict          # Additional metadata from the agent
    timestamp: datetime     # When the tool was invoked
    agent_id: Optional[str] # ID of the calling agent (if available)
```

### Using Context

**Access execution metadata**:
```python
@tool
def audit_action(action: str, context: ToolContext = None) -> dict:
    """Perform an audited action."""
    if context:
        log_audit_event(
            tool=context.tool_name,
            call_id=context.call_id,
            timestamp=context.timestamp,
            action=action
        )

    # Perform action
    result = perform_action(action)

    return {
        "success": True,
        "call_id": context.call_id if context else None
    }
```

**Context-aware behavior**:
```python
@tool
def get_data(query: str, context: ToolContext = None) -> dict:
    """Fetch data with context-aware caching."""
    cache_key = f"{context.agent_id}:{query}" if context else query

    # Check cache
    if cached := cache.get(cache_key):
        return cached

    # Fetch and cache
    data = fetch_data(query)
    cache.set(cache_key, data)
    return data
```

### Important Notes

1. **Context parameter must be named `context`**
2. **Context must have default value `None`**
3. **Context is injected automatically** by the agent/registry
4. **Context is optional** - tools work without it

## Tool Execution Lifecycle

### Execution Flow

Understanding the tool execution lifecycle helps with debugging and optimization:

```
1. Tool Call Initiated
   ├─> LLM generates tool call in response
   └─> Tool call extracted from response

2. Tool Lookup
   ├─> Registry finds tool by name
   └─> Tool spec retrieved

3. Parameter Validation
   ├─> Input parameters parsed
   ├─> Type checking performed
   └─> Pydantic validation applied

4. Context Injection
   ├─> ToolContext created (if needed)
   └─> Context injected into call

5. Tool Execution
   ├─> Function invoked with parameters
   ├─> Async/sync handled automatically
   └─> Exception handling applied

6. Result Processing
   ├─> Return value validated
   ├─> Result serialized
   └─> Tool result block created

7. Result Return
   ├─> Result added to conversation
   └─> Control returns to agent
```

### Lifecycle Hooks

You can add lifecycle hooks for logging, monitoring, or custom behavior:

```python
from spark.tools.decorator import tool
from functools import wraps
import time

def with_timing(func):
    """Decorator to add timing to tool execution."""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start
            print(f"Tool {func.__name__} took {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            print(f"Tool {func.__name__} failed after {duration:.3f}s: {e}")
            raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            print(f"Tool {func.__name__} took {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            print(f"Tool {func.__name__} failed after {duration:.3f}s: {e}")
            raise

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

@tool
@with_timing
async def slow_operation(data: str) -> str:
    """A slow operation with timing."""
    await asyncio.sleep(2)
    return f"Processed: {data}"
```

## Testing Tools

### Unit Testing Patterns

Test tools like regular Python functions:

```python
import pytest
from spark.tools.decorator import tool

@tool
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y

# Test the tool function directly
def test_add_basic():
    result = add(2, 3)
    assert result == 5

def test_add_negative():
    result = add(-1, 1)
    assert result == 0

def test_add_type_validation():
    with pytest.raises(ValidationError):
        add("not", "numbers")
```

### Testing with Context

Test context-aware tools by providing mock context:

```python
from spark.tools.types import ToolContext
from datetime import datetime

@tool
def log_message(msg: str, context: ToolContext = None) -> dict:
    """Log a message with context."""
    return {
        "message": msg,
        "tool": context.tool_name if context else "unknown",
        "timestamp": context.timestamp if context else None
    }

def test_log_with_context():
    mock_context = ToolContext(
        tool_name="log_message",
        call_id="test-123",
        metadata={},
        timestamp=datetime.now()
    )

    result = log_message("test", context=mock_context)

    assert result["message"] == "test"
    assert result["tool"] == "log_message"
    assert result["timestamp"] is not None

def test_log_without_context():
    result = log_message("test")

    assert result["message"] == "test"
    assert result["tool"] == "unknown"
    assert result["timestamp"] is None
```

### Testing Async Tools

Use pytest-asyncio for async tool tests:

```python
import pytest
import httpx

@tool
async def fetch_data(url: str) -> dict:
    """Fetch JSON data from URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

@pytest.mark.asyncio
async def test_fetch_data_success(httpx_mock):
    # Mock HTTP response
    httpx_mock.add_response(
        url="https://api.example.com/data",
        json={"result": "success"}
    )

    result = await fetch_data("https://api.example.com/data")

    assert result["result"] == "success"

@pytest.mark.asyncio
async def test_fetch_data_error(httpx_mock):
    # Mock HTTP error
    httpx_mock.add_response(
        url="https://api.example.com/data",
        status_code=500
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_data("https://api.example.com/data")
```

### Integration Testing with Agents

Test tools in the context of agents:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

@tool
def get_user_info(user_id: str) -> dict:
    """Get information about a user."""
    return {"id": user_id, "name": "Test User"}

@pytest.mark.asyncio
async def test_agent_uses_tool():
    model = OpenAIModel(model_id="gpt-4o-mini")
    config = AgentConfig(
        model=model,
        tools=[get_user_info],
        system_prompt="Use tools to answer questions."
    )
    agent = Agent(config=config)

    result = await agent.run("Get info for user user123")

    # Verify tool was called
    assert any(
        "user123" in str(trace)
        for trace in agent.state.tool_traces
    )
```

### Test Organization

Organize tool tests in a structured way:

```
tests/
├── unit/
│   └── tools/
│       ├── test_basic_tools.py
│       ├── test_async_tools.py
│       └── test_context_tools.py
├── integration/
│   └── tools/
│       ├── test_agent_integration.py
│       └── test_tool_registry.py
└── fixtures/
    └── tool_fixtures.py
```

### Best Practices

1. **Test tool logic independently** from agent integration
2. **Mock external dependencies** (HTTP, databases, etc.)
3. **Test error conditions** and edge cases
4. **Verify type validation** works correctly
5. **Test with and without context** for context-aware tools
6. **Use fixtures** for common test data and configurations
7. **Test async tools** with proper async test utilities

## Summary

The tool fundamentals provide:

- **Simple decorator-based API** for creating tools
- **Automatic metadata extraction** from function signatures and docstrings
- **Type safety** through Python type hints and Pydantic validation
- **Flexible execution** supporting both sync and async functions
- **Context awareness** for tools that need execution metadata
- **Clear execution lifecycle** for understanding tool behavior
- **Comprehensive testing patterns** for reliable tools

Next steps:
- See [Tool Registry Reference](registry.md) for managing collections of tools
- See [Tool Development Reference](development.md) for advanced tool patterns
- See [Tool Depot Reference](depot.md) for pre-built tools
- See [Agent Documentation](/docs/agents/) for using tools with agents
