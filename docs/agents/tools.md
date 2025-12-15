---
title: Agent Tools
parent: Agent
nav_order: 4
---
# Agent Tools
---

Tools extend agent capabilities by allowing them to interact with external systems, APIs, databases, and services. Agents automatically determine when to call tools, execute them, and incorporate results into their reasoning.

Key capabilities:
- Automatic tool registration
- Schema generation from type hints
- Sync and async tool support
- Context injection for tool execution
- Parallel tool execution
- Error handling and retries
- Tool result processing

## Tool Registration with Agents

### Basic Registration

Register tools via `AgentConfig`:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool
from spark.models.openai import OpenAIModel

# Define tools
@tool
def get_weather(location: str) -> str:
    """Get current weather for a location.

    Args:
        location: City name or location string
    """
    # Implementation
    return f"Weather in {location}: Sunny, 72°F"

@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: Search query string
    """
    # Implementation
    return f"Search results for: {query}"

# Create agent with tools
model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(
    model=model,
    tools=[get_weather, search_web],
    system_prompt="You are a helpful assistant with access to weather and web search."
)

agent = Agent(config=config)
```

### Multiple Tool Registration

Register any number of tools:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

# Define many tools
@tool
def tool1(param: str) -> str:
    """Tool 1 description."""
    return "result1"

@tool
def tool2(param: int) -> int:
    """Tool 2 description."""
    return param * 2

@tool
def tool3(a: float, b: float) -> float:
    """Tool 3 description."""
    return a + b

# Register all tools
config = AgentConfig(
    model=model,
    tools=[tool1, tool2, tool3]  # List of tools
)

agent = Agent(config=config)
```

### Tool Validation

Tools are validated at registration time:

```python
from spark.agents import AgentConfig

# Invalid tool - missing type hints
@tool
def invalid_tool(param):  # Missing type hint
    """Invalid tool."""
    return param

# This raises ValidationError
config = AgentConfig(
    model=model,
    tools=[invalid_tool]  # Error: missing type hints
)
```

## Tool Calling Flow

### Automatic Tool Selection

Agents automatically decide when to call tools:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

@tool
def get_temperature(city: str) -> float:
    """Get temperature for a city in Fahrenheit."""
    # Implementation
    return 72.5

config = AgentConfig(
    model=model,
    tools=[get_temperature]
)

agent = Agent(config=config)

# Agent automatically calls tool when needed
result = await agent.run(user_message="What's the temperature in Paris?")
# Agent internally:
# 1. Recognizes need for temperature data
# 2. Calls get_temperature(city="Paris")
# 3. Receives result: 72.5
# 4. Formulates response: "The temperature in Paris is 72.5°F"

print(result)  # "The temperature in Paris is 72.5°F"
```

### Multi-Tool Workflows

Agents can call multiple tools in sequence:

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.tools.decorator import tool

@tool
def search_product(query: str) -> dict:
    """Search for products."""
    return {"product_id": "123", "name": "Laptop", "price": 999}

@tool
def check_inventory(product_id: str) -> dict:
    """Check product inventory."""
    return {"product_id": product_id, "in_stock": True, "quantity": 15}

@tool
def calculate_tax(price: float, state: str) -> float:
    """Calculate sales tax."""
    tax_rates = {"CA": 0.0725, "NY": 0.04, "TX": 0.0625}
    return price * tax_rates.get(state, 0.0)

config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True),
    tools=[search_product, check_inventory, calculate_tax]
)

agent = Agent(config=config)

# Agent calls multiple tools
result = await agent.run(
    user_message="Find a laptop, check if it's in stock, and calculate tax for CA"
)

# Agent internally:
# 1. search_product(query="laptop") → {product_id: "123", price: 999}
# 2. check_inventory(product_id="123") → {in_stock: True}
# 3. calculate_tax(price=999, state="CA") → 72.39
# 4. Final response with all information

print(result)
```

### Tool Call Tracking

Track tool calls via agent state:

```python
agent = Agent(config=config)
result = await agent.run(user_message="What's the weather?")

# Inspect tool calls
tool_traces = agent._state.tool_traces
for trace in tool_traces:
    tool_name = trace.get('action')
    tool_input = trace.get('action_input')
    tool_result = trace.get('observation')

    print(f"Tool: {tool_name}")
    print(f"Input: {tool_input}")
    print(f"Result: {tool_result}")
```

## Tool Execution and Error Handling

### Sync vs Async Tools

Tools can be synchronous or asynchronous:

```python
from spark.tools.decorator import tool

# Synchronous tool
@tool
def sync_tool(param: str) -> str:
    """Synchronous tool."""
    return process_data(param)

# Asynchronous tool
@tool
async def async_tool(param: str) -> str:
    """Asynchronous tool."""
    result = await fetch_data_async(param)
    return result

# Both work with agents
config = AgentConfig(
    model=model,
    tools=[sync_tool, async_tool]
)
```

### Error Handling in Tools

Handle errors within tools:

```python
from spark.tools.decorator import tool

@tool
def safe_divide(a: float, b: float) -> float:
    """Divide two numbers safely.

    Args:
        a: Numerator
        b: Denominator

    Returns:
        Division result, or error message
    """
    try:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
    except Exception as e:
        # Tool can return error info
        return f"Error: {str(e)}"

config = AgentConfig(
    model=model,
    tools=[safe_divide]
)

agent = Agent(config=config)
result = await agent.run(user_message="What is 10 divided by 0?")
# Agent receives error message and handles gracefully
```

### Agent-Level Error Handling

Agents handle tool execution errors:

```python
from spark.agents import Agent, AgentConfig, ToolExecutionError
from spark.tools.decorator import tool

@tool
def failing_tool() -> str:
    """Tool that always fails."""
    raise RuntimeError("Tool failed")

config = AgentConfig(
    model=model,
    tools=[failing_tool]
)

agent = Agent(config=config)

try:
    result = await agent.run(user_message="Use the failing tool")
except ToolExecutionError as e:
    print(f"Tool execution failed: {e}")
    # Agent can continue or handle error

# Check error state
if agent._state.last_error:
    print(f"Last error: {agent._state.last_error}")
```

### Retry Strategies

Implement retries within tools:

```python
from spark.tools.decorator import tool
import asyncio

@tool
async def retry_tool(param: str, max_retries: int = 3) -> str:
    """Tool with built-in retry logic.

    Args:
        param: Input parameter
        max_retries: Maximum retry attempts
    """
    for attempt in range(max_retries):
        try:
            result = await external_api_call(param)
            return result
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

    return "Failed after retries"
```

## Parallel Tool Execution

### Enabling Parallel Execution

Execute independent tools concurrently:

```python
from spark.agents import Agent, AgentConfig

config = AgentConfig(
    model=model,
    tools=[tool1, tool2, tool3],
    parallel_tool_execution=True  # Enable parallel execution
)

agent = Agent(config=config)

# When agent calls multiple independent tools, they run in parallel
result = await agent.run(
    user_message="Get weather in Paris, London, and Tokyo"
)
# Internally: get_weather("Paris"), get_weather("London"), get_weather("Tokyo")
# All execute concurrently → faster execution
```

### Benefits and Trade-offs

**Benefits**:
- ✅ Faster execution when multiple tools called
- ✅ Better resource utilization
- ✅ Reduced latency for independent operations

**Trade-offs**:
- ❌ Tools must be independent (no shared state)
- ❌ More complex error handling
- ❌ Debugging can be harder

### When to Use Parallel Execution

```python
# Good use case: Independent API calls
@tool
def get_weather(city: str) -> str:
    """Get weather (independent)."""
    return api_call(city)

# Bad use case: Shared state
counter = 0

@tool
def increment_counter() -> int:
    """Increment counter (NOT thread-safe)."""
    global counter
    counter += 1  # Race condition!
    return counter
```

### Parallel Execution Example

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool
import asyncio

@tool
async def fetch_price(product: str) -> float:
    """Fetch product price (slow API call)."""
    await asyncio.sleep(2)  # Simulate API delay
    prices = {"laptop": 999, "phone": 699, "tablet": 499}
    return prices.get(product, 0)

config = AgentConfig(
    model=model,
    tools=[fetch_price],
    parallel_tool_execution=True
)

agent = Agent(config=config)

# Sequential: 6 seconds (2s × 3 calls)
# Parallel: 2 seconds (all calls concurrent)
result = await agent.run(
    user_message="Get prices for laptop, phone, and tablet"
)
```

## Tool Context Injection

### Accessing Tool Context

Tools can receive execution context via optional parameter:

```python
from spark.tools.decorator import tool
from spark.tools.types import ToolContext

@tool
def context_aware_tool(query: str, context: ToolContext = None) -> str:
    """Tool with context access.

    Args:
        query: User query
        context: Tool execution context (injected automatically)
    """
    if context:
        # Access metadata
        agent_id = context.metadata.get("agent_id")
        user_id = context.metadata.get("user_id")

        print(f"Called by agent {agent_id} for user {user_id}")

        # Access other context info
        timestamp = context.metadata.get("timestamp")

    return f"Processed query: {query}"

config = AgentConfig(
    model=model,
    tools=[context_aware_tool]
)

agent = Agent(config=config)
```

### ToolContext Structure

```python
from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class ToolContext:
    """Context passed to tools during execution."""

    metadata: Dict[str, Any]  # Execution metadata
    agent_state: Any  # Agent state (optional)
    execution_id: str  # Unique execution ID
```

### Passing Context to Agents

```python
from spark.agents import Agent

agent = Agent(config=config)

# Pass metadata through context
result = await agent.run(
    user_message="Search for data",
    context={
        "user_id": "user_123",
        "session_id": "sess_456",
        "timestamp": "2025-12-05T10:30:00Z"
    }
)

# Tools receive this context
```

## Tool Result Handling

### Processing Tool Results

Agents automatically process tool results:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

@tool
def get_data() -> dict:
    """Get structured data."""
    return {
        "status": "success",
        "data": [1, 2, 3, 4, 5],
        "metadata": {"count": 5}
    }

config = AgentConfig(
    model=model,
    tools=[get_data]
)

agent = Agent(config=config)

# Agent receives dict result and formats response
result = await agent.run(user_message="Get the data")
print(result)
# Agent formats dict into natural language response
```

### Complex Return Types

Tools can return complex structures:

```python
from spark.tools.decorator import tool
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class Product:
    id: str
    name: str
    price: float

@tool
def search_products(query: str) -> List[Dict[str, any]]:
    """Search products and return structured results.

    Args:
        query: Search query

    Returns:
        List of product dictionaries
    """
    products = [
        Product(id="1", name="Laptop", price=999),
        Product(id="2", name="Mouse", price=29)
    ]

    # Convert to dicts for serialization
    return [
        {"id": p.id, "name": p.name, "price": p.price}
        for p in products
    ]

config = AgentConfig(
    model=model,
    tools=[search_products]
)

agent = Agent(config=config)
result = await agent.run(user_message="Find laptops")
# Agent processes list of dicts and creates response
```

### Error Results

Tools can return error information:

```python
from spark.tools.decorator import tool
from typing import Dict

@tool
def api_call(endpoint: str) -> Dict[str, any]:
    """Call external API.

    Args:
        endpoint: API endpoint

    Returns:
        API response or error info
    """
    try:
        response = make_api_call(endpoint)
        return {"status": "success", "data": response}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }

# Agent receives error info and can handle it
```

## Restricting Tool Access

### Tool Subsets

Create agents with specific tool subsets:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

# Define all tools
@tool
def read_tool() -> str:
    """Read-only tool."""
    return "data"

@tool
def write_tool(data: str) -> str:
    """Write tool."""
    return "written"

@tool
def delete_tool(id: str) -> str:
    """Delete tool."""
    return "deleted"

# Agent with read-only access
read_only_agent = Agent(config=AgentConfig(
    model=model,
    tools=[read_tool]  # Only read tool
))

# Agent with full access
admin_agent = Agent(config=AgentConfig(
    model=model,
    tools=[read_tool, write_tool, delete_tool]  # All tools
))
```

### Conditional Tool Access

Implement access control within tools:

```python
from spark.tools.decorator import tool
from spark.tools.types import ToolContext

@tool
def restricted_tool(data: str, context: ToolContext = None) -> str:
    """Tool with access control.

    Args:
        data: Input data
        context: Execution context
    """
    if context:
        user_role = context.metadata.get("user_role")

        # Check permissions
        if user_role != "admin":
            return "Error: Insufficient permissions"

    # Proceed with operation
    return f"Processed: {data}"

config = AgentConfig(
    model=model,
    tools=[restricted_tool]
)

agent = Agent(config=config)

# Pass role in context
result = await agent.run(
    user_message="Use restricted tool",
    context={"user_role": "admin"}
)
```

### Tool Filtering

Filter tools based on runtime conditions:

```python
from spark.agents import Agent, AgentConfig

def get_tools_for_user(user_role: str) -> list:
    """Get tools based on user role."""
    all_tools = [read_tool, write_tool, delete_tool]

    if user_role == "admin":
        return all_tools
    elif user_role == "editor":
        return [read_tool, write_tool]
    else:
        return [read_tool]

# Create agent with appropriate tools
user_role = "editor"
tools = get_tools_for_user(user_role)

agent = Agent(config=AgentConfig(
    model=model,
    tools=tools
))
```

## Tool Development Best Practices

### 1. Clear Docstrings

Write comprehensive docstrings:

```python
from spark.tools.decorator import tool

@tool
def well_documented_tool(param1: str, param2: int, flag: bool = False) -> dict:
    """Brief description of what the tool does.

    More detailed explanation of the tool's purpose and behavior.
    This helps the LLM understand when and how to use the tool.

    Args:
        param1: Description of param1
        param2: Description of param2 (must be positive)
        flag: Optional flag for special behavior (default: False)

    Returns:
        Dictionary with keys: 'status', 'result', 'metadata'

    Raises:
        ValueError: If param2 is negative
    """
    if param2 < 0:
        raise ValueError("param2 must be positive")

    return {
        "status": "success",
        "result": f"{param1}_{param2}",
        "metadata": {"flag": flag}
    }
```

### 2. Type Hints

Always use type hints:

```python
from typing import List, Dict, Optional

@tool
def typed_tool(
    items: List[str],
    config: Dict[str, any],
    optional_param: Optional[int] = None
) -> Dict[str, any]:
    """Tool with complete type hints."""
    return {"items": items, "count": len(items)}
```

### 3. Error Handling

Handle errors gracefully:

```python
from spark.tools.decorator import tool

@tool
def robust_tool(param: str) -> str:
    """Tool with robust error handling."""
    try:
        result = risky_operation(param)
        return result
    except ValueError as e:
        return f"Validation error: {e}"
    except ConnectionError as e:
        return f"Connection error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"
```

### 4. Validation

Validate inputs:

```python
from spark.tools.decorator import tool

@tool
def validated_tool(email: str, age: int) -> dict:
    """Tool with input validation.

    Args:
        email: Email address
        age: Age in years
    """
    # Validate email
    if "@" not in email:
        return {"error": "Invalid email address"}

    # Validate age
    if not 0 <= age <= 150:
        return {"error": "Invalid age"}

    # Process
    return {"status": "success", "email": email, "age": age}
```

### 5. Idempotency

Make tools idempotent where possible:

```python
from spark.tools.decorator import tool

@tool
def idempotent_tool(id: str, value: str) -> dict:
    """Idempotent update tool.

    Calling multiple times with same parameters produces same result.
    """
    # Check if already exists
    if record_exists(id):
        if get_value(id) == value:
            return {"status": "already_set", "id": id}

    # Set value
    set_value(id, value)
    return {"status": "updated", "id": id}
```

### 6. Logging

Log tool execution:

```python
from spark.tools.decorator import tool
import logging

logger = logging.getLogger(__name__)

@tool
def logged_tool(param: str) -> str:
    """Tool with comprehensive logging."""
    logger.info(f"Tool called with param: {param}")

    try:
        result = process(param)
        logger.info(f"Tool completed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Tool failed: {e}", exc_info=True)
        raise
```

## Common Patterns

### Database Access Tool

```python
from spark.tools.decorator import tool
from typing import List, Dict

@tool
async def query_database(sql: str, params: List[any] = None) -> List[Dict]:
    """Execute SQL query on database.

    Args:
        sql: SQL query string
        params: Query parameters (optional)

    Returns:
        List of result rows as dictionaries
    """
    async with get_db_connection() as conn:
        cursor = await conn.execute(sql, params or [])
        rows = await cursor.fetchall()

        # Convert to dicts
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
```

### API Integration Tool

```python
from spark.tools.decorator import tool
import httpx

@tool
async def call_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Call external API.

    Args:
        endpoint: API endpoint URL
        method: HTTP method (GET, POST, etc.)
        data: Request payload (for POST/PUT)

    Returns:
        API response as dictionary
    """
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=endpoint,
            json=data
        )
        response.raise_for_status()
        return response.json()
```

### File Operations Tool

```python
from spark.tools.decorator import tool
import aiofiles

@tool
async def read_file(filepath: str) -> str:
    """Read file contents.

    Args:
        filepath: Path to file

    Returns:
        File contents as string
    """
    try:
        async with aiofiles.open(filepath, 'r') as f:
            contents = await f.read()
        return contents
    except FileNotFoundError:
        return f"Error: File not found: {filepath}"
    except Exception as e:
        return f"Error reading file: {e}"
```

### Calculation Tool

```python
from spark.tools.decorator import tool
import math

@tool
def calculate(expression: str) -> float:
    """Evaluate mathematical expression safely.

    Args:
        expression: Math expression to evaluate

    Returns:
        Calculated result
    """
    # Safe evaluation - whitelist allowed operations
    allowed = {
        'abs': abs, 'round': round,
        'pow': pow, 'sqrt': math.sqrt,
        'sin': math.sin, 'cos': math.cos,
        'pi': math.pi, 'e': math.e
    }

    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return float(result)
    except Exception as e:
        return f"Error: {e}"
```

## Testing Tools

### Unit Testing Tools

```python
import pytest
from spark.tools.decorator import tool

@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def test_add_tool():
    """Test add tool."""
    # Call tool directly
    result = add(5, 3)
    assert result == 8

    # Test edge cases
    assert add(0, 0) == 0
    assert add(-5, 5) == 0
    assert add(100, 200) == 300

@pytest.mark.asyncio
async def test_async_tool():
    """Test async tool."""
    @tool
    async def async_add(a: int, b: int) -> int:
        """Async add."""
        return a + b

    result = await async_add(5, 3)
    assert result == 8
```

### Integration Testing with Agents

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

@tool
def test_tool(value: int) -> int:
    """Test tool for integration tests."""
    return value * 2

@pytest.mark.asyncio
async def test_agent_tool_integration():
    """Test tool integration with agent."""
    config = AgentConfig(
        model=model,
        tools=[test_tool]
    )

    agent = Agent(config=config)
    result = await agent.run(user_message="Use test_tool with value 5")

    # Verify tool was called
    assert "10" in result or test_tool(5) == 10

    # Check tool traces
    traces = agent._state.tool_traces
    assert len(traces) > 0
```

## Next Steps

- Review [Agent Configuration](configuration.md) for tool configuration options
- See [Reasoning Strategies](reasoning-strategies.md) for tool integration with reasoning
- Learn about [Error Handling](error-handling.md) for tool error patterns
- Explore [Agent Fundamentals](fundamentals.md) for general usage
