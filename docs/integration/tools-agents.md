---
title: Tools and Agents
parent: Integration
nav_order: 2
---
# Tools and Agents
---

This guide covers how to effectively integrate tools with agents, including tool registration, custom tool development, composition patterns, error handling, and performance optimization.

## Table of Contents

- [Overview](#overview)
- [Tool Registration with Agents](#tool-registration-with-agents)
- [Custom Tools for Specific Agents](#custom-tools-for-specific-agents)
- [Tool Composition and Chaining](#tool-composition-and-chaining)
- [Error Handling in Tools](#error-handling-in-tools)
- [Tool Performance Optimization](#tool-performance-optimization)
- [Testing Tools with Agents](#testing-tools-with-agents)

## Overview

Tools extend agent capabilities by providing access to external systems, APIs, databases, and computational resources. Spark's `@tool` decorator makes it easy to create LLM-callable tools with automatic schema generation.

**Key Concepts**:
- **Tool Registration**: Making tools available to agents
- **Tool Specifications**: JSON schemas for LLM understanding
- **Tool Execution**: Async/sync execution with context injection
- **Tool Context**: Access to execution metadata and agent state

## Tool Registration with Agents

### Basic Tool Registration

```python
from spark.tools.decorator import tool
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Define tools with @tool decorator
@tool
def search_documentation(query: str) -> str:
    """Search the documentation for relevant information.

    Args:
        query: The search query

    Returns:
        Relevant documentation snippets
    """
    # Implementation
    results = search_docs_db(query)
    return f"Found {len(results)} relevant documents: {results}"

@tool
def get_code_examples(topic: str) -> str:
    """Get code examples for a specific topic.

    Args:
        topic: The programming topic

    Returns:
        Code examples and explanations
    """
    examples = fetch_examples(topic)
    return f"Code examples for {topic}:\n{examples}"

# Register tools with agent
model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(
    model=model,
    tools=[search_documentation, get_code_examples],
    system_prompt="You are a helpful programming assistant."
)

agent = Agent(config=config)

# Agent can now use these tools
result = await agent.run("How do I create a custom node?")
```

### Async Tools

Tools can be async for I/O-bound operations:

```python
import asyncio
import httpx

@tool
async def fetch_api_data(endpoint: str) -> dict:
    """Fetch data from an API endpoint.

    Args:
        endpoint: The API endpoint URL

    Returns:
        JSON response from the API
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint)
        return response.json()

@tool
async def query_database(sql: str) -> list:
    """Execute SQL query against database.

    Args:
        sql: The SQL query to execute

    Returns:
        Query results as list of dictionaries
    """
    # Async database query
    async with get_db_connection() as conn:
        cursor = await conn.execute(sql)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

# Async tools work seamlessly with agents
config = AgentConfig(
    model=model,
    tools=[fetch_api_data, query_database]
)
agent = Agent(config=config)
```

### Tool with Context

Tools can access execution context for metadata and state:

```python
from spark.nodes.types import ExecutionContext

@tool
def log_action(action: str, context: ExecutionContext = None) -> str:
    """Log an action with context information.

    Args:
        action: The action to log
        context: Execution context (auto-injected)

    Returns:
        Confirmation message
    """
    # Access context metadata
    trace_id = context.metadata.get('trace_id') if context else 'unknown'
    node_name = context.metadata.get('node_name') if context else 'unknown'

    # Log with context
    log_entry = f"[{trace_id}][{node_name}] Action: {action}"
    print(log_entry)

    return f"Logged: {action}"
```

## Custom Tools for Specific Agents

Create specialized tools tailored to specific agent roles:

### Domain-Specific Tool Sets

```python
# Customer service tools
@tool
def lookup_customer(customer_id: str) -> dict:
    """Look up customer information by ID."""
    return get_customer_from_db(customer_id)

@tool
def get_order_history(customer_id: str) -> list:
    """Get customer's order history."""
    return get_orders_for_customer(customer_id)

@tool
def create_support_ticket(customer_id: str, issue: str) -> str:
    """Create a support ticket for the customer."""
    ticket_id = create_ticket(customer_id, issue)
    return f"Created ticket {ticket_id}"

# Customer service agent
customer_service_agent = Agent(config=AgentConfig(
    model=model,
    tools=[lookup_customer, get_order_history, create_support_ticket],
    system_prompt="You are a customer service representative. Help customers with their inquiries."
))

# Technical support tools
@tool
def diagnose_error(error_message: str) -> str:
    """Diagnose a technical error."""
    return run_diagnostics(error_message)

@tool
def check_system_status(system: str) -> dict:
    """Check the status of a system component."""
    return get_system_health(system)

@tool
def restart_service(service_name: str) -> str:
    """Restart a service (requires approval)."""
    return restart(service_name)

# Technical support agent
tech_support_agent = Agent(config=AgentConfig(
    model=model,
    tools=[diagnose_error, check_system_status, restart_service],
    system_prompt="You are a technical support engineer. Diagnose and resolve technical issues."
))
```

### Configurable Tools

Create tools that adapt to agent configuration:

```python
from functools import partial

def create_api_tool(api_key: str, base_url: str):
    """Factory for creating API-specific tools."""

    @tool
    async def call_api(endpoint: str, method: str = "GET") -> dict:
        """Call the configured API.

        Args:
            endpoint: API endpoint path
            method: HTTP method

        Returns:
            API response
        """
        url = f"{base_url}/{endpoint}"
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(url, headers=headers)

            return response.json()

    return call_api

# Create agent-specific API tools
stripe_tool = create_api_tool(api_key="sk_test_...", base_url="https://api.stripe.com/v1")
github_tool = create_api_tool(api_key="ghp_...", base_url="https://api.github.com")

# Different agents with different API access
payment_agent = Agent(config=AgentConfig(
    model=model,
    tools=[stripe_tool],
    system_prompt="You handle payment operations."
))

code_agent = Agent(config=AgentConfig(
    model=model,
    tools=[github_tool],
    system_prompt="You manage GitHub repositories."
))
```

## Tool Composition and Chaining

Build complex capabilities from simpler tools:

### Tool Chaining Pattern

```python
@tool
def search_products(query: str) -> list[dict]:
    """Search for products matching query."""
    return [
        {"id": "1", "name": "Widget", "price": 19.99},
        {"id": "2", "name": "Gadget", "price": 29.99}
    ]

@tool
def get_product_details(product_id: str) -> dict:
    """Get detailed information about a product."""
    return {
        "id": product_id,
        "name": "Widget",
        "price": 19.99,
        "stock": 42,
        "description": "A useful widget"
    }

@tool
def check_inventory(product_id: str) -> dict:
    """Check inventory for a product."""
    return {
        "product_id": product_id,
        "available": 42,
        "warehouse": "US-WEST",
        "next_shipment": "2024-12-15"
    }

# Agent can chain tools naturally
shopping_agent = Agent(config=AgentConfig(
    model=model,
    tools=[search_products, get_product_details, check_inventory],
    system_prompt="""You help customers find and purchase products.
    Use search_products first, then get_product_details for specifics,
    and check_inventory before confirming availability."""
))

# Agent will automatically chain: search -> details -> inventory
result = await shopping_agent.run("Do you have any widgets in stock?")
```

### Composite Tools

Create high-level tools that use multiple lower-level tools:

```python
@tool
async def full_product_search(query: str) -> list[dict]:
    """Comprehensive product search with inventory check.

    Args:
        query: Product search query

    Returns:
        Products with full details and inventory
    """
    # Search for products
    products = search_products(query)

    # Enrich with details and inventory
    enriched = []
    for product in products:
        details = get_product_details(product['id'])
        inventory = check_inventory(product['id'])

        enriched.append({
            **details,
            'inventory': inventory
        })

    return enriched

# Simpler agent interface with composite tool
efficient_agent = Agent(config=AgentConfig(
    model=model,
    tools=[full_product_search],  # One tool instead of three
    system_prompt="You help customers find products."
))
```

### Dynamic Tool Generation

Generate tools based on schemas or configurations:

```python
def create_crud_tools(entity_name: str, schema: dict):
    """Generate CRUD tools for an entity."""

    @tool
    async def create_entity(**fields) -> dict:
        f"""Create a new {entity_name}."""
        return await db.insert(entity_name, fields)

    @tool
    async def read_entity(id: str) -> dict:
        f"""Read {entity_name} by ID."""
        return await db.get(entity_name, id)

    @tool
    async def update_entity(id: str, **fields) -> dict:
        f"""Update {entity_name}."""
        return await db.update(entity_name, id, fields)

    @tool
    async def delete_entity(id: str) -> bool:
        f"""Delete {entity_name}."""
        return await db.delete(entity_name, id)

    return [create_entity, read_entity, update_entity, delete_entity]

# Generate tools for different entities
user_tools = create_crud_tools("user", {"name": str, "email": str})
product_tools = create_crud_tools("product", {"name": str, "price": float})

# Specialized agents
user_admin_agent = Agent(config=AgentConfig(
    model=model,
    tools=user_tools,
    system_prompt="You manage user accounts."
))

product_admin_agent = Agent(config=AgentConfig(
    model=model,
    tools=product_tools,
    system_prompt="You manage product catalog."
))
```

## Error Handling in Tools

Robust error handling ensures agent resilience:

### Basic Error Handling

```python
from spark.agents.types import ToolExecutionError

@tool
def risky_operation(input: str) -> str:
    """Perform operation that might fail.

    Args:
        input: Operation input

    Returns:
        Operation result

    Raises:
        ToolExecutionError: If operation fails
    """
    try:
        # Risky operation
        result = perform_operation(input)
        return result
    except ValueError as e:
        raise ToolExecutionError(f"Invalid input: {e}")
    except ConnectionError as e:
        raise ToolExecutionError(f"Connection failed: {e}")
    except Exception as e:
        raise ToolExecutionError(f"Operation failed: {e}")
```

### Retry with Exponential Backoff

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@tool
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def resilient_api_call(endpoint: str) -> dict:
    """API call with automatic retry.

    Args:
        endpoint: API endpoint

    Returns:
        API response
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(endpoint)
        response.raise_for_status()
        return response.json()
```

### Graceful Degradation

```python
@tool
async def fetch_with_fallback(source: str) -> dict:
    """Fetch data with fallback to cached version.

    Args:
        source: Data source identifier

    Returns:
        Data from source or cache
    """
    try:
        # Try primary source
        data = await fetch_from_primary(source)
        # Update cache
        await cache.set(source, data)
        return data
    except Exception as e:
        # Fallback to cache
        cached = await cache.get(source)
        if cached:
            return {"data": cached, "source": "cache", "warning": str(e)}
        else:
            raise ToolExecutionError(f"Failed to fetch and no cache available: {e}")
```

### Timeout Protection

```python
@tool
async def bounded_operation(query: str) -> str:
    """Operation with timeout protection.

    Args:
        query: Query to process

    Returns:
        Processing result
    """
    try:
        # 10 second timeout
        result = await asyncio.wait_for(
            long_running_operation(query),
            timeout=10.0
        )
        return result
    except asyncio.TimeoutError:
        raise ToolExecutionError("Operation timed out after 10 seconds")
```

## Tool Performance Optimization

Optimize tool execution for production agents:

### Caching Tool Results

```python
from functools import lru_cache
import hashlib
import json

# In-memory cache for expensive computations
@lru_cache(maxsize=1000)
def expensive_computation(input: str) -> str:
    """Cached expensive operation."""
    # Expensive computation
    return compute(input)

@tool
def cached_tool(query: str) -> str:
    """Tool with result caching.

    Args:
        query: Query to process

    Returns:
        Cached or computed result
    """
    return expensive_computation(query)

# Persistent cache for API calls
cache_store = {}

@tool
async def cached_api_call(url: str, ttl_seconds: int = 3600) -> dict:
    """API call with persistent caching.

    Args:
        url: API URL
        ttl_seconds: Cache time-to-live

    Returns:
        API response (cached or fresh)
    """
    cache_key = hashlib.md5(url.encode()).hexdigest()

    # Check cache
    if cache_key in cache_store:
        cached_at, data = cache_store[cache_key]
        if time.time() - cached_at < ttl_seconds:
            return data

    # Fetch fresh data
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()

    # Update cache
    cache_store[cache_key] = (time.time(), data)

    return data
```

### Parallel Tool Execution

Enable parallel execution in agent config:

```python
config = AgentConfig(
    model=model,
    tools=[tool1, tool2, tool3],
    parallel_tool_execution=True  # Execute independent tools in parallel
)

agent = Agent(config=config)

# When agent calls multiple tools, they run concurrently
result = await agent.run(
    "Check inventory for products A, B, and C"
)
# Tools execute in parallel instead of sequentially
```

### Connection Pooling

Reuse connections for database and API tools:

```python
from contextlib import asynccontextmanager

class ConnectionPool:
    """Shared connection pool for tools."""

    def __init__(self, connection_string: str, pool_size: int = 10):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.pool = None

    async def initialize(self):
        """Initialize connection pool."""
        self.pool = await create_pool(
            self.connection_string,
            min_size=1,
            max_size=self.pool_size
        )

    @asynccontextmanager
    async def get_connection(self):
        """Get connection from pool."""
        async with self.pool.acquire() as conn:
            yield conn

# Global pool
db_pool = ConnectionPool("postgresql://...")

@tool
async def query_with_pool(sql: str) -> list:
    """Query using connection pool.

    Args:
        sql: SQL query

    Returns:
        Query results
    """
    async with db_pool.get_connection() as conn:
        cursor = await conn.execute(sql)
        return await cursor.fetchall()
```

### Batching Operations

Batch multiple tool calls for efficiency:

```python
@tool
async def batch_lookup(ids: list[str]) -> list[dict]:
    """Look up multiple items in one call.

    Args:
        ids: List of IDs to look up

    Returns:
        List of items
    """
    # Single batch query instead of N individual queries
    query = "SELECT * FROM items WHERE id = ANY($1)"
    results = await db.fetch(query, ids)
    return [dict(row) for row in results]

# Agent can batch lookups
agent = Agent(config=AgentConfig(
    model=model,
    tools=[batch_lookup],
    system_prompt="When looking up multiple items, use batch_lookup with a list of IDs."
))
```

## Testing Tools with Agents

Comprehensive testing strategies for tools:

### Unit Testing Tools

```python
import pytest

@pytest.mark.asyncio
async def test_search_documentation():
    """Test search tool in isolation."""
    result = search_documentation("custom node")

    assert isinstance(result, str)
    assert "custom node" in result.lower()
    assert len(result) > 0

@pytest.mark.asyncio
async def test_async_tool():
    """Test async tool."""
    result = await fetch_api_data("https://api.example.com/data")

    assert isinstance(result, dict)
    assert "data" in result
```

### Integration Testing with Mock Agent

```python
from spark.models.echo import EchoModel

@pytest.mark.asyncio
async def test_tool_with_agent():
    """Test tool integration with agent."""

    @tool
    def test_tool(input: str) -> str:
        """Test tool."""
        return f"Processed: {input}"

    # Use EchoModel for deterministic testing
    config = AgentConfig(
        model=EchoModel(),
        tools=[test_tool]
    )

    agent = Agent(config=config)

    # Mock tool execution
    result = await agent.run("Use the test tool")

    # Verify tool was called
    assert agent.state.get('tool_traces')
```

### Testing Error Handling

```python
@pytest.mark.asyncio
async def test_tool_error_handling():
    """Test tool error handling."""

    @tool
    def failing_tool(input: str) -> str:
        """Tool that always fails."""
        raise ValueError("Intentional error")

    config = AgentConfig(
        model=EchoModel(),
        tools=[failing_tool]
    )

    agent = Agent(config=config)

    # Should handle error gracefully
    result = await agent.run("Use the failing tool")

    # Agent should report error
    assert "error" in result.output.lower()
```

### Mocking External Dependencies

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_api_tool_with_mock():
    """Test API tool with mocked HTTP client."""

    @tool
    async def fetch_data(url: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.json()

    # Mock HTTP client
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"data": "test"}
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

        result = await fetch_data("https://api.example.com")

        assert result == {"data": "test"}
```

## Best Practices

1. **Clear Documentation**: Write detailed docstrings for all tools
2. **Type Hints**: Use type hints for automatic schema generation
3. **Error Messages**: Provide helpful error messages for agents
4. **Idempotency**: Make tools idempotent when possible
5. **Validation**: Validate inputs before performing operations
6. **Logging**: Log tool execution for debugging
7. **Testing**: Test tools independently before agent integration
8. **Performance**: Cache results and use connection pooling
9. **Security**: Validate inputs and sanitize outputs
10. **Versioning**: Version tools for backward compatibility

## Related Documentation

- [Agents in Graphs](./agents-in-graphs.md) - Integrating agents into workflows
- [Tool System Reference](/docs/tools/fundamentals.md) - Tool decorator and registry
- [Agent System Reference](/docs/agents/fundamentals.md) - Agent configuration
- [Testing Strategies](/docs/best-practices/testing.md) - Testing approaches
