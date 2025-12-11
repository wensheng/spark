---
title: Agent Error Handling
parent: Agent
nav_order: 7
---
# Agent Error Handling
---

Spark agents provide comprehensive error handling with specific exception types, structured error propagation, and recovery patterns. The error handling system includes:

- Structured exception hierarchy
- Error propagation and logging
- Retry strategies
- Fallback patterns
- Graceful degradation
- Error state tracking

## Exception Types

### AgentError (Base Exception)

Base exception for all agent-related errors:

```python
from spark.agents import AgentError

class AgentError(Exception):
    """Base exception for agent errors."""
    pass
```

**Use**: Catch all agent-related exceptions

```python
from spark.agents import Agent, AgentError

agent = Agent()

try:
    result = await agent.run(user_message="Query")
except AgentError as e:
    print(f"Agent error occurred: {e}")
    # Handle any agent error
```

### ToolExecutionError

Raised when tool execution fails:

```python
from spark.agents import ToolExecutionError

class ToolExecutionError(AgentError):
    """Tool execution failed."""
    pass
```

**Causes**:
- Tool raises exception during execution
- Tool returns invalid format
- Tool timeout
- Tool parameter validation failure

**Example**:

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
    print(f"Tool execution error: {e}")
    # Tool failed, handle error
```

### ModelError

Raised when LLM model operations fail:

```python
from spark.agents import ModelError

class ModelError(AgentError):
    """Model API error."""
    pass
```

**Causes**:
- API rate limits
- API authentication failures
- Network errors
- Invalid model configuration
- Context length exceeded
- Model timeout

**Example**:

```python
from spark.agents import Agent, ModelError
from spark.models.openai import OpenAIModel

# Invalid API key
model = OpenAIModel(model_id="gpt-4o", api_key="invalid")
agent = Agent()

try:
    result = await agent.run(user_message="Hello")
except ModelError as e:
    print(f"Model error: {e}")
    # Handle API error
```

### ValidationError

Raised for configuration or input validation failures:

```python
from spark.agents import ValidationError

class ValidationError(AgentError):
    """Validation failed."""
    pass
```

**Causes**:
- Invalid agent configuration
- Invalid tool specifications
- Missing required parameters
- Type mismatches
- Constraint violations

**Example**:

```python
from spark.agents import AgentConfig, ValidationError

try:
    config = AgentConfig(
        model=None,  # Invalid - model required
        max_steps=-1  # Invalid - must be positive
    )
except ValidationError as e:
    print(f"Validation error: {e}")
    # Fix configuration
```

### ConfigurationError

Raised for agent configuration issues:

```python
from spark.agents import ConfigurationError

class ConfigurationError(AgentError):
    """Invalid agent configuration."""
    pass
```

**Causes**:
- Incompatible configuration options
- Missing required configuration
- Invalid configuration combinations
- Resource conflicts

**Example**:

```python
from spark.agents import AgentConfig, ConfigurationError, ReActStrategy

try:
    config = AgentConfig(
        model=model,
        output_mode="text",  # Invalid for ReAct
        reasoning_strategy=ReActStrategy()  # Requires JSON mode
    )
except ConfigurationError as e:
    print(f"Configuration error: {e}")
    # Use compatible configuration
```

### MemoryError

Raised for memory management failures:

```python
from spark.agents import MemoryError

class MemoryError(AgentError):
    """Memory operation failed."""
    pass
```

**Causes**:
- Memory policy failure
- History corruption
- Summarization failure
- Memory overflow

**Example**:

```python
from spark.agents import Agent, MemoryError

agent = Agent()

try:
    # Attempt to add invalid message
    agent.add_message_to_history({"invalid": "format"})
except MemoryError as e:
    print(f"Memory error: {e}")
    # Handle memory error
```

### Exception Hierarchy

```
Exception
└── AgentError (base)
    ├── ToolExecutionError
    ├── ModelError
    ├── ValidationError
    ├── ConfigurationError
    └── MemoryError
```

## Error Propagation

### Automatic Error Logging

Agents automatically log errors:

```python
from spark.agents import Agent
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

agent = Agent()

try:
    result = await agent.run(user_message="Query")
except Exception as e:
    # Error automatically logged before raising
    # Log includes: timestamp, error type, message, context
    pass
```

### Error State Tracking

Agents track last error:

```python
from spark.agents import Agent

agent = Agent()

try:
    result = await agent.run(user_message="Failing query")
except Exception:
    pass

# Check error state
if agent._state.last_error:
    print(f"Last error: {agent._state.last_error}")
    print(f"Error type: {type(agent._state.last_error).__name__}")

# Clear error
agent._state.last_error = None
```

### Error Context

Errors include context information:

```python
from spark.agents import Agent, AgentError

agent = Agent()

try:
    result = await agent.run(user_message="Query")
except AgentError as e:
    # Error includes context
    print(f"Error: {e}")
    print(f"Error args: {e.args}")

    # Additional context from agent state
    print(f"Last result: {agent._state.last_result}")
    print(f"Tool traces: {len(agent._state.tool_traces)}")
```

## Retry Strategies

### Basic Retry

Simple retry with exponential backoff:

```python
from spark.agents import Agent, AgentError
import asyncio

async def run_with_retry(agent: Agent, message: str, max_retries: int = 3):
    """Run agent with retry logic."""
    for attempt in range(max_retries):
        try:
            result = await agent.run(user_message=message)
            return result

        except AgentError as e:
            if attempt == max_retries - 1:
                raise  # Final attempt, re-raise

            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Attempt {attempt + 1} failed: {e}")
            print(f"Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)

# Usage
agent = Agent()
result = await run_with_retry(agent, "Query")
```

### Conditional Retry

Retry based on error type:

```python
from spark.agents import Agent, ModelError, ToolExecutionError
import asyncio

async def run_with_conditional_retry(agent: Agent, message: str):
    """Retry only for retryable errors."""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            return await agent.run(user_message=message)

        except ModelError as e:
            # Model errors (rate limits, network) - retry
            if "rate limit" in str(e).lower():
                wait_time = 2 ** attempt
                print(f"Rate limited, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
            else:
                raise  # Other model errors - don't retry

        except ToolExecutionError as e:
            # Tool errors - don't retry (likely logic issue)
            raise

        except Exception as e:
            # Unknown errors - don't retry
            raise

    raise AgentError("Max retries exceeded")

# Usage
result = await run_with_conditional_retry(agent, "Query")
```

### Retry with Fallback

Retry with fallback strategy:

```python
from spark.agents import Agent, AgentError

async def run_with_fallback(
    agent: Agent,
    message: str,
    fallback_message: str = None
):
    """Run with retry and fallback."""
    # Try primary query
    for attempt in range(3):
        try:
            return await agent.run(user_message=message)
        except AgentError as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                print(f"Primary query failed: {e}")

    # Try fallback if available
    if fallback_message:
        print("Trying fallback query")
        try:
            return await agent.run(user_message=fallback_message)
        except AgentError as e:
            print(f"Fallback also failed: {e}")

    # Both failed
    raise AgentError("Primary and fallback queries failed")

# Usage
result = await run_with_fallback(
    agent,
    message="Complex query",
    fallback_message="Simpler alternative query"
)
```

## Fallback Patterns

### Model Fallback

Fall back to alternative model:

```python
from spark.agents import Agent, AgentConfig, ModelError
from spark.models.openai import OpenAIModel

async def run_with_model_fallback(message: str):
    """Try premium model, fallback to cheaper model."""
    # Try premium model first
    premium_model = OpenAIModel(model_id="gpt-4o")
    agent = Agent(config=AgentConfig(model=premium_model))

    try:
        return await agent.run(user_message=message)

    except ModelError as e:
        print(f"Premium model failed: {e}")

        # Fallback to cheaper model
        print("Falling back to gpt-4o-mini")
        fallback_model = OpenAIModel(model_id="gpt-4o-mini")
        agent = Agent(config=AgentConfig(model=fallback_model))

        return await agent.run(user_message=message)

# Usage
result = await run_with_model_fallback("Query")
```

### Strategy Fallback

Fall back to simpler reasoning strategy:

```python
from spark.agents import Agent, AgentConfig, ReActStrategy, NoOpStrategy

async def run_with_strategy_fallback(message: str):
    """Try ReAct, fallback to NoOp strategy."""
    # Try ReAct strategy
    config_react = AgentConfig(
        model=model,
        output_mode="json",
        reasoning_strategy=ReActStrategy(),
        tools=[search_tool]
    )
    agent = Agent(config=config_react)

    try:
        return await agent.run(user_message=message)

    except Exception as e:
        print(f"ReAct strategy failed: {e}")

        # Fallback to simple NoOp strategy
        print("Falling back to NoOp strategy")
        config_noop = AgentConfig(
            model=model,
            reasoning_strategy=NoOpStrategy()
        )
        agent = Agent(config=config_noop)

        return await agent.run(user_message=message)

# Usage
result = await run_with_strategy_fallback("Complex query")
```

### Tool Fallback

Fall back when tools unavailable:

```python
from spark.agents import Agent, AgentConfig, ToolExecutionError

async def run_with_tool_fallback(message: str):
    """Try with tools, fallback to no tools."""
    # Try with tools
    config_with_tools = AgentConfig(
        model=model,
        tools=[search_tool, calculate_tool]
    )
    agent = Agent(config=config_with_tools)

    try:
        return await agent.run(user_message=message)

    except ToolExecutionError as e:
        print(f"Tool execution failed: {e}")

        # Fallback to no tools
        print("Falling back to agent without tools")
        config_no_tools = AgentConfig(model=model)
        agent = Agent(config=config_no_tools)

        # Add context about tool unavailability
        enhanced_message = f"{message}\n\nNote: External tools unavailable, please use your knowledge."

        return await agent.run(user_message=enhanced_message)

# Usage
result = await run_with_tool_fallback("Search for Python tutorials")
```

## Graceful Degradation

### Partial Success Handling

Handle partial failures gracefully:

```python
from spark.agents import Agent, AgentConfig
from spark.tools.decorator import tool

@tool
def tool_a() -> str:
    """Tool A (may fail)."""
    return "A result"

@tool
def tool_b() -> str:
    """Tool B (may fail)."""
    raise RuntimeError("B failed")

@tool
def tool_c() -> str:
    """Tool C (may fail)."""
    return "C result"

async def run_with_partial_success(agent: Agent, message: str):
    """Handle partial tool failures."""
    try:
        result = await agent.run(user_message=message)
        return {"status": "success", "result": result}

    except Exception as e:
        # Check which tools succeeded
        tool_traces = agent._state.tool_traces
        successful = [t for t in tool_traces if 'observation' in t and 'error' not in str(t['observation']).lower()]
        failed = [t for t in tool_traces if 'error' in str(t.get('observation', '')).lower()]

        if successful:
            # Partial success
            return {
                "status": "partial_success",
                "successful_tools": len(successful),
                "failed_tools": len(failed),
                "partial_result": agent._state.last_result,
                "error": str(e)
            }
        else:
            # Complete failure
            return {
                "status": "failure",
                "error": str(e)
            }

# Usage
agent = Agent(config=AgentConfig(
    model=model,
    tools=[tool_a, tool_b, tool_c]
))

result = await run_with_partial_success(agent, "Use all tools")
print(f"Status: {result['status']}")
```

### Quality Degradation

Degrade quality rather than failing:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

async def run_with_quality_degradation(message: str):
    """Degrade response quality rather than fail."""
    # Quality levels (best to worst)
    models = [
        ("premium", OpenAIModel(model_id="gpt-4o")),
        ("standard", OpenAIModel(model_id="gpt-4o-mini")),
    ]

    last_error = None

    for quality_level, model in models:
        agent = Agent(config=AgentConfig(model=model))

        try:
            result = await agent.run(user_message=message)
            return {
                "result": result,
                "quality_level": quality_level,
                "degraded": quality_level != "premium"
            }

        except Exception as e:
            print(f"{quality_level} model failed: {e}")
            last_error = e
            continue

    # All quality levels failed
    raise AgentError(f"All quality levels failed: {last_error}")

# Usage
result = await run_with_quality_degradation("Complex query")
if result["degraded"]:
    print(f"Warning: Using degraded quality ({result['quality_level']})")
```

### Timeout Handling

Handle timeouts gracefully:

```python
from spark.agents import Agent
import asyncio

async def run_with_timeout(
    agent: Agent,
    message: str,
    timeout: float = 30.0
):
    """Run agent with timeout."""
    try:
        result = await asyncio.wait_for(
            agent.run(user_message=message),
            timeout=timeout
        )
        return {"status": "success", "result": result}

    except asyncio.TimeoutError:
        print(f"Agent timed out after {timeout}s")

        # Return partial result if available
        if agent._state.last_result:
            return {
                "status": "timeout",
                "partial_result": agent._state.last_result,
                "message": f"Operation timed out after {timeout}s"
            }
        else:
            return {
                "status": "timeout",
                "message": f"Operation timed out after {timeout}s with no partial result"
            }

# Usage
agent = Agent()
result = await run_with_timeout(agent, "Complex query", timeout=10.0)
print(f"Status: {result['status']}")
```

## Error Logging and Debugging

### Comprehensive Error Logging

Log errors with full context:

```python
from spark.agents import Agent, AgentError
import logging
import traceback

logger = logging.getLogger(__name__)

async def run_with_logging(agent: Agent, message: str):
    """Run agent with comprehensive error logging."""
    try:
        result = await agent.run(user_message=message)
        logger.info(f"Agent completed successfully")
        return result

    except AgentError as e:
        # Log error with context
        logger.error(
            f"Agent error: {type(e).__name__}: {e}\n"
            f"Message: {message}\n"
            f"Last result: {agent._state.last_result}\n"
            f"Tool traces: {len(agent._state.tool_traces)}\n"
            f"Traceback: {traceback.format_exc()}"
        )

        # Check agent state
        stats = agent.get_cost_stats()
        logger.error(
            f"Agent state at error:\n"
            f"  Total calls: {stats.total_calls}\n"
            f"  Total tokens: {stats.total_tokens}\n"
            f"  Total cost: ${stats.total_cost:.4f}"
        )

        raise

# Usage
logger.setLevel(logging.INFO)
agent = Agent()
result = await run_with_logging(agent, "Query")
```

### Debug Mode

Enable debug mode for verbose logging:

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
import logging

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create agent with verbose strategy
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True),  # Verbose reasoning
    tools=[search_tool]
)

agent = Agent(config=config)

# Run with full debug output
result = await agent.run(user_message="Query")
# Logs every reasoning step, tool call, and decision
```

### Error Inspection

Inspect errors for debugging:

```python
from spark.agents import Agent, AgentError

agent = Agent()

try:
    result = await agent.run(user_message="Query")

except AgentError as e:
    print("=== Error Details ===")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")
    print(f"Error args: {e.args}")

    print("\n=== Agent State ===")
    print(f"Last result: {agent._state.last_result}")
    print(f"Last error: {agent._state.last_error}")
    print(f"Last output: {agent._state.last_output}")

    print("\n=== Tool Traces ===")
    for i, trace in enumerate(agent._state.tool_traces):
        print(f"Trace {i}: {trace}")

    print("\n=== Conversation History ===")
    history = agent.get_history()
    for msg in history[-3:]:  # Last 3 messages
        print(f"{msg['role']}: {msg['content'][0].get('text', 'N/A')[:100]}")

    print("\n=== Cost Stats ===")
    stats = agent.get_cost_stats()
    print(f"Total tokens: {stats.total_tokens}")
    print(f"Total cost: ${stats.total_cost:.4f}")
```

## Testing Error Handling

### Unit Tests

```python
import pytest
from spark.agents import Agent, AgentError, ToolExecutionError
from spark.tools.decorator import tool

@tool
def failing_tool() -> str:
    """Tool that fails."""
    raise RuntimeError("Tool failed")

@pytest.mark.asyncio
async def test_tool_execution_error():
    """Test tool execution error handling."""
    from spark.agents import AgentConfig

    config = AgentConfig(
        model=model,
        tools=[failing_tool]
    )

    agent = Agent(config=config)

    with pytest.raises(ToolExecutionError):
        await agent.run(user_message="Use the failing tool")

    # Verify error state
    assert agent._state.last_error is not None

@pytest.mark.asyncio
async def test_error_recovery():
    """Test error recovery."""
    agent = Agent()

    # Cause error
    try:
        await agent.run(user_message="Query that fails")
    except AgentError:
        pass

    # Verify agent can recover
    result = await agent.run(user_message="Simple query")
    assert result is not None
```

### Integration Tests

```python
import pytest
from spark.agents import Agent, AgentConfig, ModelError
from spark.models.openai import OpenAIModel

@pytest.mark.asyncio
async def test_model_error_handling():
    """Test model error handling."""
    # Invalid API key
    model = OpenAIModel(model_id="gpt-4o", api_key="invalid")
    agent = Agent(config=AgentConfig(model=model))

    with pytest.raises(ModelError):
        await agent.run(user_message="Test")

@pytest.mark.asyncio
async def test_retry_logic():
    """Test retry logic."""
    agent = Agent()
    max_retries = 3
    attempts = 0

    async def run_with_tracking():
        nonlocal attempts
        for attempt in range(max_retries):
            attempts += 1
            try:
                return await agent.run(user_message="Query")
            except AgentError:
                if attempt < max_retries - 1:
                    continue
                raise

    try:
        result = await run_with_tracking()
    except AgentError:
        pass

    # Verify retries occurred
    assert attempts == max_retries
```

## Best Practices

### 1. Always Catch Specific Exceptions

```python
# Good - specific exception handling
try:
    result = await agent.run(user_message="Query")
except ToolExecutionError as e:
    # Handle tool errors
    pass
except ModelError as e:
    # Handle model errors
    pass
except AgentError as e:
    # Handle other agent errors
    pass

# Avoid - catching generic Exception
try:
    result = await agent.run(user_message="Query")
except Exception as e:
    # Too broad
    pass
```

### 2. Log Before Re-raising

```python
import logging

logger = logging.getLogger(__name__)

try:
    result = await agent.run(user_message="Query")
except AgentError as e:
    logger.error(f"Agent error: {e}", exc_info=True)
    raise  # Re-raise after logging
```

### 3. Provide Context in Errors

```python
try:
    result = await agent.run(user_message="Query")
except AgentError as e:
    # Add context
    raise AgentError(f"Failed to process query: {message}") from e
```

### 4. Clean Up Resources

```python
agent = Agent()

try:
    result = await agent.run(user_message="Query")
finally:
    # Clean up if needed
    agent.clear_history()
    agent.reset_cost_tracking()
```

### 5. Test Error Paths

Always test error handling:

```python
@pytest.mark.asyncio
async def test_error_handling():
    """Test all error paths."""
    # Test tool error
    # Test model error
    # Test validation error
    # Test recovery
    pass
```

## Next Steps

- Review [Agent Fundamentals](fundamentals.md) for general agent usage
- See [Configuration Reference](configuration.md) for validation rules
- Learn about [Checkpointing](checkpointing.md) for error recovery
- Explore [Tools Reference](tools.md) for tool error handling
