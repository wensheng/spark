# Agent Fundamentals Reference

This reference covers the core concepts and fundamental operations for working with Spark agents.

## Overview

Spark agents are production-ready LLM-powered components that orchestrate conversations, tool execution, and reasoning. Agents provide a high-level interface for building autonomous AI systems with support for:

- Multi-turn conversations with memory management
- Tool calling with automatic execution
- Multiple reasoning strategies (ReAct, Chain-of-Thought, Plan-and-Solve)
- Cost tracking and performance monitoring
- State persistence and checkpointing
- Parallel tool execution
- Comprehensive error handling

Agents are built on top of Spark's model abstraction layer, supporting OpenAI, AWS Bedrock, Google Gemini, and other LLM providers.

## Creating Agents

### Basic Agent Creation

The simplest way to create an agent is to instantiate the `Agent` class with default configuration:

```python
from spark.agents import Agent

# Create agent with defaults
agent = Agent()

# Run agent
result = await agent.run(user_message="What is the capital of France?")
print(result)  # "The capital of France is Paris."
```

### Agent with Configuration

For production use, create agents with explicit configuration using `AgentConfig`:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Configure model
model = OpenAIModel(
    model_id="gpt-4o",
    temperature=0.7,
    max_tokens=2000
)

# Create agent configuration
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant specializing in geography.",
    max_steps=5,
    output_mode="text"
)

# Create agent
agent = Agent(config=config)
```

### Agent with Tools

Agents can be configured with tools for enhanced capabilities:

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

# Configure agent with tools
model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    tools=[get_weather, search_web],
    system_prompt="You are a helpful assistant with access to weather and web search."
)

agent = Agent(config=config)
```

## Running Agents

### Basic Execution

The `run()` method is the primary interface for executing agents:

```python
# Simple text query
result = await agent.run(user_message="What's the weather in Paris?")
print(result)

# With additional context
result = await agent.run(
    user_message="Summarize the article",
    context={"article_text": "..."}
)
```

### Async Execution

All agent operations are asynchronous. Use Python's `asyncio` to run agents:

```python
import asyncio
from spark.agents import Agent

async def main():
    agent = Agent()
    result = await agent.run(user_message="Hello!")
    print(result)

# Run from async context
await main()

# Run from sync context
asyncio.run(main())
```

### Using arun() Utility

Spark provides an `arun()` utility for running async code from synchronous contexts:

```python
from spark.agents import Agent
from spark.utils import arun

agent = Agent()

# Run synchronously
result = arun(agent.run(user_message="Hello!"))
print(result)
```

## Multi-Turn Conversations

Agents maintain conversation history automatically across multiple interactions:

```python
from spark.agents import Agent

agent = Agent()

# First turn
response1 = await agent.run(user_message="My name is Alice.")
print(response1)  # "Nice to meet you, Alice!"

# Second turn - agent remembers context
response2 = await agent.run(user_message="What's my name?")
print(response2)  # "Your name is Alice."

# Third turn
response3 = await agent.run(user_message="Tell me a fact about France.")
print(response3)  # Agent provides information
```

### Manual Message Addition

You can manually add messages to the conversation history:

```python
from spark.agents import Agent

agent = Agent()

# Add context messages
agent.add_message_to_history({
    "role": "user",
    "content": [{"text": "I'm working on a Python project."}]
})

agent.add_message_to_history({
    "role": "assistant",
    "content": [{"text": "Great! I'd be happy to help with your Python project."}]
})

# Continue conversation with context
result = await agent.run(user_message="Can you review this code?")
```

### Accessing Conversation History

Retrieve the full conversation history:

```python
# Get all messages
history = agent.get_history()
for msg in history:
    role = msg["role"]
    content = msg["content"][0]["text"]
    print(f"{role}: {content}")
```

## Message History Management

### History Structure

Agent messages follow Spark's unified message format:

```python
message = {
    "role": "user",  # or "assistant"
    "content": [
        {"text": "Hello, how are you?"}
    ]
}

# Messages with tool use
message_with_tool = {
    "role": "assistant",
    "content": [
        {"text": "Let me check the weather for you."},
        {
            "toolUse": {
                "toolUseId": "tool_123",
                "name": "get_weather",
                "input": {"location": "Paris"}
            }
        }
    ]
}

# Tool result messages
tool_result_message = {
    "role": "user",
    "content": [
        {
            "toolResult": {
                "toolUseId": "tool_123",
                "content": [{"text": "Sunny, 72°F"}]
            }
        }
    ]
}
```

### Clearing History

Clear conversation history to start fresh:

```python
# Clear all history
agent.clear_history()

# Start new conversation
result = await agent.run(user_message="Hello!")  # No previous context
```

### Memory Policies

Configure how agents manage conversation history:

```python
from spark.agents import AgentConfig, MemoryPolicy

# Full memory - keep everything
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL
)

# Rolling window - keep last N tokens
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={"window_size": 4000}  # tokens
)

# Summarization - auto-summarize old context
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SUMMARIZATION,
    memory_config={"max_tokens": 4000}
)

agent = Agent(config=config)
```

See [Memory Management Reference](memory.md) for detailed memory policy documentation.

## Agent State and Persistence

### Agent State

Agents maintain internal state including:

- Conversation history
- Tool call traces
- Last execution result
- Last error (if any)
- Last output
- Cost tracking data

### Inspecting State

Access agent state programmatically:

```python
from spark.agents import Agent

agent = Agent()
result = await agent.run(user_message="Hello")

# Get conversation history
history = agent.get_history()
print(f"Messages in history: {len(history)}")

# Get cost statistics
stats = agent.get_cost_stats()
print(f"Total cost: ${stats.total_cost:.4f}")
print(f"Total tokens: {stats.total_tokens:,}")

# Access internal state
print(f"Last result: {agent._state.last_result}")
print(f"Tool traces: {agent._state.tool_traces}")
```

### State Persistence with Checkpoints

Save and restore complete agent state using checkpointing:

```python
from spark.agents import Agent

# Create and use agent
agent = Agent()
await agent.run(user_message="My name is Alice.")
await agent.run(user_message="I like Python.")

# Save checkpoint to file
agent.save_checkpoint("agent_state.json")

# Later: restore agent from checkpoint
restored_agent = Agent.load_checkpoint("agent_state.json", config=agent.config)

# Agent remembers conversation
result = await restored_agent.run(user_message="What's my name?")
print(result)  # "Your name is Alice."
```

See [Checkpointing Reference](checkpointing.md) for complete checkpoint documentation.

## Testing Agents

### Unit Testing Patterns

Test agents in isolation with mocked models and tools:

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

@pytest.mark.asyncio
async def test_agent_basic_response():
    """Test agent responds to simple query."""
    agent = Agent()
    result = await agent.run(user_message="Say hello")

    assert result is not None
    assert len(result) > 0

@pytest.mark.asyncio
async def test_agent_with_history():
    """Test agent maintains conversation history."""
    agent = Agent()

    # First message
    await agent.run(user_message="My name is Bob.")

    # Second message
    result = await agent.run(user_message="What's my name?")

    assert "Bob" in result or "bob" in result.lower()

@pytest.mark.asyncio
async def test_agent_tool_calling():
    """Test agent calls tools correctly."""
    from spark.tools.decorator import tool

    # Define test tool
    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    # Configure agent with tool
    model = OpenAIModel(model_id="gpt-4o")
    config = AgentConfig(
        model=model,
        tools=[add],
        max_steps=3
    )
    agent = Agent(config=config)

    # Run agent
    result = await agent.run(user_message="What is 5 + 7?")

    assert "12" in result
```

### Testing with Mock Models

Mock model responses for deterministic tests:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from spark.agents import Agent, AgentConfig

@pytest.mark.asyncio
async def test_agent_with_mock_model():
    """Test agent with mocked model response."""
    # Create mock model
    mock_model = MagicMock()
    mock_model.get_text = AsyncMock(return_value="Mocked response")

    # Configure agent
    config = AgentConfig(model=mock_model)
    agent = Agent(config=config)

    # Run agent
    result = await agent.run(user_message="Test")

    # Verify
    assert result == "Mocked response"
    mock_model.get_text.assert_called_once()
```

### Integration Testing

Test agents with real models using response caching:

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

@pytest.mark.asyncio
async def test_agent_integration():
    """Integration test with real model (cached)."""
    # Enable caching for fast, deterministic tests
    model = OpenAIModel(
        model_id="gpt-4o",
        enable_cache=True,
        cache_ttl_seconds=3600
    )

    config = AgentConfig(
        model=model,
        system_prompt="You are a test assistant."
    )

    agent = Agent(config=config)

    # First run hits API and caches
    result1 = await agent.run(user_message="What is 2+2?")
    assert "4" in result1

    # Second run uses cache (instant)
    result2 = await agent.run(user_message="What is 2+2?")
    assert result2 == result1  # Deterministic from cache
```

### Testing Error Handling

Test agent error scenarios:

```python
import pytest
from spark.agents import Agent, AgentConfig, ToolExecutionError
from spark.tools.decorator import tool

@pytest.mark.asyncio
async def test_agent_tool_error_handling():
    """Test agent handles tool errors gracefully."""

    @tool
    def failing_tool() -> str:
        """Tool that always fails."""
        raise ValueError("Intentional error")

    config = AgentConfig(
        model=model,
        tools=[failing_tool]
    )
    agent = Agent(config=config)

    # Agent should handle tool error gracefully
    result = await agent.run(user_message="Call the failing tool")

    # Verify error was logged
    assert agent._state.last_error is not None
```

## Configuration Reference

For complete agent configuration options, see:

- [Configuration Reference](configuration.md) - Complete AgentConfig field reference
- [Memory Management](memory.md) - Memory policies and management
- [Reasoning Strategies](reasoning-strategies.md) - Strategy selection and configuration
- [Tools](tools.md) - Tool registration and execution
- [Cost Tracking](cost-tracking.md) - Token usage and cost monitoring
- [Checkpointing](checkpointing.md) - State persistence
- [Error Handling](error-handling.md) - Exception types and patterns

## Best Practices

### 1. Always Use Configuration

Create agents with explicit configuration for maintainability:

```python
# Good
config = AgentConfig(
    model=model,
    system_prompt="...",
    max_steps=5
)
agent = Agent(config=config)

# Avoid - unclear defaults
agent = Agent()
```

### 2. Enable Response Caching

Use response caching for development and testing:

```python
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)
```

### 3. Set Appropriate max_steps

Limit agent steps to prevent runaway costs:

```python
config = AgentConfig(
    model=model,
    max_steps=10,  # Reasonable limit
    tools=[...]
)
```

### 4. Use Structured Output

For programmatic use, enable JSON output mode:

```python
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy()
)
```

### 5. Monitor Costs

Track costs in production:

```python
agent = Agent(config=config)
result = await agent.run(user_message="...")

stats = agent.get_cost_stats()
if stats.total_cost > threshold:
    logger.warning(f"High cost: ${stats.total_cost:.2f}")
```

### 6. Handle Errors Gracefully

Wrap agent calls in try-except blocks:

```python
from spark.agents import AgentError, ModelError

try:
    result = await agent.run(user_message="...")
except ModelError as e:
    logger.error(f"Model error: {e}")
    # Fallback logic
except AgentError as e:
    logger.error(f"Agent error: {e}")
    # Error handling
```

## Next Steps

- Learn about [Agent Configuration](configuration.md) for complete configuration options
- Explore [Reasoning Strategies](reasoning-strategies.md) for advanced reasoning patterns
- See [Tools Reference](tools.md) for tool integration
- Review [Memory Management](memory.md) for conversation history strategies
