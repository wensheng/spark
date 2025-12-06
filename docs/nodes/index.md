---
title: Node
nav_order: 4
---

# Node Fundamentals

**Document Type**: Reference Documentation
**Audience**: Developers building custom nodes in Spark ADK
**Related**: [Node System Architecture](/docs/architecture/node-system.md), [Execution Context](/docs/nodes/execution-context.md), [Capabilities](/docs/nodes/capabilities.md)

---

## Overview

Nodes are the fundamental building blocks of Spark workflows. Each node represents an independent processing unit in the Actor Model, capable of receiving inputs, performing computation, and producing outputs. Nodes can be connected via edges to form directed graphs that define complete workflows.

**Key Characteristics**:
- **Self-contained**: Each node is an independent actor with its own state and lifecycle
- **Asynchronous**: All node execution is async internally, supporting both sync and async process methods
- **Configurable**: Declarative configuration via `NodeConfig` for capabilities and behavior
- **Composable**: Nodes connect via edges with conditional routing for complex workflows
- **Observable**: Lifecycle hooks and state management for monitoring and debugging

---

## Node Class Hierarchy

```
BaseNode (abstract)
  ├─ Node (concrete, with capabilities)
  └─ Specialized nodes
       ├─ AgentNode (LLM agents)
       ├─ HumanNode (human-in-the-loop)
       ├─ RpcNode (JSON-RPC servers)
       └─ RemoteRpcProxyNode (RPC clients)
```

### BaseNode

Abstract base class defining the core node interface. Located in `spark/nodes/base.py`.

**Core Responsibilities**:
- Edge management (connections to other nodes)
- State management via `NodeState`
- Lifecycle hooks (`pre_process_hooks`, `post_process_hooks`)
- Abstract `process()` method

### Node

Concrete implementation extending `BaseNode` with capabilities support. Located in `spark/nodes/nodes.py`.

**Additional Features**:
- Configuration via `NodeConfig`
- Declarative capabilities (retry, timeout, rate limiting, etc.)
- Continuous execution via `go()` method for long-running mode
- Policy application (rate limiting, circuit breaking, idempotency)

---

## Creating Custom Nodes

### Basic Node Pattern

All custom nodes inherit from `Node` and implement a `process()` method:

```python
from spark.nodes import Node
from spark.nodes.types import ExecutionContext

class GreetingNode(Node):
    """Simple node that greets users."""

    async def process(self, context: ExecutionContext) -> dict:
        """
        Process the context and return outputs.

        Args:
            context: Execution context containing inputs and state

        Returns:
            Dictionary that becomes the node's outputs
        """
        name = context.inputs.content.get('name', 'World')
        greeting = f"Hello, {name}!"

        return {
            'greeting': greeting,
            'processed': True
        }
```

**Key Points**:
- Inherit from `Node` class
- Implement `process()` method (can be sync or async)
- Accept `context` parameter of type `ExecutionContext`
- Return `dict` or `None` (returned dict becomes node outputs)
- Access inputs via `context.inputs.content`

### Running a Single Node

```python
from spark.utils import arun
from spark.nodes.types import NodeMessage

# Create node instance
node = GreetingNode()

# Prepare inputs
inputs = NodeMessage(content={'name': 'Alice'})

# Run the node
result = arun(node.run(inputs))

print(result.content)  # {'greeting': 'Hello, Alice!', 'processed': True}
```

---

## Process Method Patterns

### Async Process (Recommended)

```python
class AsyncProcessNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Can use await for async operations
        data = await fetch_data_async()
        result = await process_data_async(data)
        return {'result': result}
```

### Sync Process (Auto-wrapped)

```python
class SyncProcessNode(Node):
    def process(self, context: ExecutionContext) -> dict:
        # Sync code automatically wrapped to async
        data = fetch_data_sync()
        result = process_data_sync(data)
        return {'result': result}
```

The framework automatically wraps synchronous `process()` methods using `wrap_sync_method()` to make them async-compatible.

### No-Arg Process (Convenience Pattern)

For simple nodes that don't need the context:

```python
class SimpleNode(Node):
    def process(self) -> dict:
        # Framework detects no context argument
        # and calls without passing it
        return {'timestamp': time.time()}
```

**Note**: This pattern is detected via introspection during class definition. The framework sets `_process_no_arg = True` if the process method has fewer than 2 parameters (excluding `self`).

### Returning None

```python
class SideEffectNode(Node):
    async def process(self, context: ExecutionContext) -> None:
        # Perform side effects without producing outputs
        await send_notification(context.inputs.content)
        # No return or return None
```

When `None` is returned, the node's outputs remain empty.

---

## Input/Output Flow Mechanics

### Input Flow

Nodes receive inputs through the `ExecutionContext`:

```python
class InputProcessingNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Access inputs from previous node
        content = context.inputs.content

        # Content is typically a dict with previous node's outputs
        user_id = content.get('user_id')
        query = content.get('query')

        # Access metadata if needed
        request_id = context.inputs.metadata.get('request_id')

        return {'result': f"Processing {query} for {user_id}"}
```

### Output Flow

Returned dictionaries become the node's outputs and flow to connected nodes:

```python
class ProducerNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        return {
            'user_id': 123,
            'query': 'weather forecast',
            'timestamp': time.time()
        }

# Next node receives these outputs as inputs
class ConsumerNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # context.inputs.content = {'user_id': 123, 'query': '...', ...}
        user_id = context.inputs.content['user_id']
        query = context.inputs.content['query']
        # ... process
```

### Output-to-Input Transformation

When node A connects to node B via an edge:
1. Node A's `process()` returns a dict
2. Dict becomes node A's `outputs.content`
3. Node B receives this as `context.inputs.content`

```python
# Node A returns
return {'result': 42, 'status': 'success'}

# Node B receives
context.inputs.content = {'result': 42, 'status': 'success'}
```

---

## Node Configuration

### NodeConfig Structure

The `NodeConfig` class (`spark/nodes/config.py`) provides declarative configuration:

```python
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy, TimeoutPolicy

config = NodeConfig(
    id="custom-node-1",
    description="Processes user queries",

    # Lifecycle and execution
    live=False,  # If True, runs continuously

    # Policies for resilience
    retry=RetryPolicy(max_attempts=3, backoff='exponential'),
    timeout=TimeoutPolicy(seconds=30.0),

    # State management
    keep_in_state=['user_id', 'session_id'],

    # Hooks
    pre_process_hooks=[validate_inputs],
    post_process_hooks=[log_outputs],
)

node = CustomNode(config=config)
```

### Configuration Fields Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | UUID hex | Unique node identifier |
| `type` | `str \| None` | Class name | Node type for serialization |
| `description` | `str \| None` | `""` | Human-readable description |
| `live` | `bool` | `False` | If True, runs continuously in LONG_RUNNING mode |
| `initial_state` | `NodeState` | Default state | Initial state values |
| `retry` | `RetryPolicy \| None` | `None` | Retry configuration |
| `timeout` | `TimeoutPolicy \| None` | `None` | Timeout configuration |
| `rate_limiter` | `RateLimiterPolicy \| None` | `None` | Rate limiting configuration |
| `circuit_breaker` | `CircuitBreakerPolicy \| None` | `None` | Circuit breaker configuration |
| `idempotency` | `IdempotencyPolicy \| None` | `None` | Idempotency configuration |
| `redact_keys` | `Set[str] \| None` | `None` | Keys to redact in logs |
| `event_sink` | `EventSink \| None` | `None` | Event recording sink |
| `validators` | `tuple[Callable, ...]` | `()` | Input validation functions |
| `human_policy` | `HumanInLoopPolicy \| None` | `None` | Human-in-the-loop policy |
| `pre_process_hooks` | `list[Callable]` | `[]` | Pre-processing hooks |
| `post_process_hooks` | `list[Callable]` | `[]` | Post-processing hooks |
| `keep_in_state` | `list[str]` | `[]` | Input keys to persist in state |

### Using Configuration

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy, TimeoutPolicy, Rate, RateLimiterPolicy

class ConfiguredNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            retry=RetryPolicy(max_attempts=5, backoff='exponential'),
            timeout=TimeoutPolicy(seconds=60.0),
            rate_limiter=RateLimiterPolicy(
                resource_key='api',
                rate=Rate(limit=10.0, burst=2)
            ),
            keep_in_state=['session_id', 'user_context']
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Configuration automatically applied
        # Retry, timeout, rate limiting handled transparently
        return {'status': 'processed'}
```

### Overriding Configuration with kwargs

```python
# Config-based defaults
config = NodeConfig(retry=RetryPolicy(max_attempts=3))

# Override via kwargs
node = MyNode(config=config, id='special-node', description='Custom description')
```

---

## Node State

### NodeState Structure

Each node maintains state via `NodeState` (`spark/nodes/types.py`):

```python
from typing import TypedDict
from collections import deque

class NodeState(TypedDict):
    context_snapshot: dict[str, Any] | None  # Last execution context
    processing: bool                          # Currently processing flag
    pending_inputs: deque[NodeMessage]        # Queued messages
    process_count: int                        # Execution counter
```

### Accessing State

```python
class StatefulNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Access current state
        process_count = context.state['process_count']

        # State is automatically updated by framework
        # process_count increments on each execution

        # Read custom state values
        last_result = context.state.get('last_result')

        # Modify state (persists across executions if in keep_in_state)
        context.state['last_result'] = 42

        return {'count': process_count}
```

### State Persistence with keep_in_state

The `keep_in_state` config option persists input keys across executions:

```python
config = NodeConfig(
    keep_in_state=['user_id', 'session_id', 'preferences']
)

node = PersistentNode(config=config)

# First execution
inputs1 = NodeMessage(content={
    'user_id': 123,
    'session_id': 'abc',
    'query': 'hello'
})
await node.run(inputs1)

# Second execution - user_id and session_id available in state
inputs2 = NodeMessage(content={'query': 'goodbye'})
# In process(), context.state['user_id'] = 123 (persisted)
```

**Implementation**: The `process_keep_in_state` hook runs before `process()` and copies specified keys from inputs to state.

### State Snapshot

The framework captures state snapshots on errors for debugging:

```python
try:
    await node.run(inputs)
except NodeExecutionError as e:
    # Access state at time of error
    snapshot = e.context_snapshot
    print(f"Failed with state: {snapshot}")
```

---

## Lifecycle Hooks

Nodes support lifecycle hooks for cross-cutting concerns:

### Hook Types

1. **Pre-process hooks**: Run before `process()` method
2. **Post-process hooks**: Run after `process()` method
3. **Built-in hooks**: Framework-managed (e.g., `process_keep_in_state`)

### Defining Hooks

```python
from spark.nodes import Node
from spark.nodes.types import ExecutionContext

def log_input(context: ExecutionContext) -> None:
    """Log inputs before processing."""
    print(f"Processing inputs: {context.inputs.content}")

def validate_output(context: ExecutionContext) -> None:
    """Validate outputs after processing."""
    if context.outputs is None:
        raise ValueError("Node must produce outputs")
    if not isinstance(context.outputs, dict):
        raise TypeError("Outputs must be a dict")

def enrich_metadata(context: ExecutionContext) -> None:
    """Add metadata to outputs."""
    if context.outputs:
        context.outputs['_timestamp'] = time.time()
```

### Registering Hooks via Config

```python
config = NodeConfig(
    pre_process_hooks=[log_input, validate_inputs],
    post_process_hooks=[validate_output, enrich_metadata]
)

node = MyNode(config=config)
```

### Registering Hooks Programmatically

```python
node = MyNode()

# Add pre-process hooks
node.pre_process_hooks.append(log_input)
node.pre_process_hooks.append(validate_inputs)

# Add post-process hooks
node.post_process_hooks.append(validate_output)
node.post_process_hooks.append(enrich_metadata)
```

### Hook Execution Order

**Pre-process hooks** (executed in order):
1. `process_keep_in_state` (built-in, always first)
2. User-defined pre-process hooks (in registration order)

**Main process**:
3. `process()` method executes

**Post-process hooks** (executed in order):
4. User-defined post-process hooks (in registration order)

### Hook Examples

#### Validation Hook

```python
def validate_required_fields(context: ExecutionContext) -> None:
    """Ensure required fields are present in inputs."""
    content = context.inputs.content
    required = ['user_id', 'query']

    for field in required:
        if field not in content:
            raise ValueError(f"Missing required field: {field}")
```

#### Timing Hook

```python
import time

def add_timing(context: ExecutionContext) -> None:
    """Add timing information to metadata."""
    context.metadata.mark_started(context.metadata.attempt)

def record_duration(context: ExecutionContext) -> None:
    """Record execution duration."""
    context.metadata.mark_finished()
    duration = context.metadata.duration
    print(f"Execution took {duration:.3f}s")
```

#### Error Recovery Hook

```python
def log_error(context: ExecutionContext) -> None:
    """Log errors for debugging."""
    if hasattr(context, 'error'):
        print(f"Error in node: {context.error}")
        print(f"State snapshot: {context.snapshot()}")
```

---

## Testing Nodes

### Unit Testing Pattern

```python
import pytest
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.utils import arun

class TestGreetingNode:
    """Test suite for GreetingNode."""

    @pytest.fixture
    def node(self):
        """Create a fresh node instance for each test."""
        return GreetingNode()

    def test_process_with_name(self, node):
        """Test greeting with provided name."""
        inputs = NodeMessage(content={'name': 'Alice'})
        result = arun(node.run(inputs))

        assert result.content['greeting'] == 'Hello, Alice!'
        assert result.content['processed'] is True

    def test_process_default_name(self, node):
        """Test greeting with default name."""
        inputs = NodeMessage(content={})
        result = arun(node.run(inputs))

        assert result.content['greeting'] == 'Hello, World!'

    def test_state_updates(self, node):
        """Test that process count increments."""
        inputs = NodeMessage(content={'name': 'Bob'})

        # First execution
        arun(node.run(inputs))
        assert node.state['process_count'] == 1

        # Second execution
        arun(node.run(inputs))
        assert node.state['process_count'] == 2
```

### Testing with Context

```python
def test_process_method_directly():
    """Test process method in isolation."""
    node = GreetingNode()

    # Create execution context manually
    inputs = NodeMessage(content={'name': 'Charlie'})
    context = ExecutionContext(
        inputs=inputs,
        state=node.state
    )

    # Call process directly
    result = arun(node.process(context))

    assert result['greeting'] == 'Hello, Charlie!'
```

### Testing Hooks

```python
def test_pre_process_hook():
    """Test that pre-process hooks execute."""
    hook_called = []

    def tracking_hook(context):
        hook_called.append(True)

    config = NodeConfig(pre_process_hooks=[tracking_hook])
    node = GreetingNode(config=config)

    inputs = NodeMessage(content={'name': 'Dave'})
    arun(node.run(inputs))

    assert len(hook_called) == 1
```

### Testing with Capabilities

```python
def test_retry_capability():
    """Test node with retry capability."""
    from spark.nodes.policies import RetryPolicy

    attempts = []

    class FlakyNode(Node):
        async def process(self, context):
            attempts.append(1)
            if len(attempts) < 3:
                raise Exception("Temporary failure")
            return {'success': True}

    config = NodeConfig(
        retry=RetryPolicy(max_attempts=5, backoff='constant')
    )
    node = FlakyNode(config=config)

    inputs = NodeMessage(content={})
    result = arun(node.run(inputs))

    assert len(attempts) == 3
    assert result.content['success'] is True
```

### Mocking External Dependencies

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_api_calling_node():
    """Test node that calls external API."""

    class APINode(Node):
        async def process(self, context):
            response = await self.fetch_data()
            return {'data': response}

        async def fetch_data(self):
            # Would normally call external API
            pass

    node = APINode()

    # Mock the external call
    mock_response = {'result': 'test data'}
    node.fetch_data = AsyncMock(return_value=mock_response)

    inputs = NodeMessage(content={})
    result = await node.run(inputs)

    assert result.content['data'] == mock_response
    node.fetch_data.assert_called_once()
```

---

## Advanced Patterns

### Stateful Counter Node

```python
class CounterNode(Node):
    """Node that maintains a counter in state."""

    def __init__(self, **kwargs):
        config = NodeConfig(keep_in_state=['counter'])
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Get current counter from state
        counter = context.state.get('counter', 0)

        # Increment
        counter += 1

        # Store back in state (persists due to keep_in_state)
        context.state['counter'] = counter

        return {'count': counter}
```

### Conditional Output Node

```python
class ConditionalNode(Node):
    """Node that produces different outputs based on logic."""

    async def process(self, context: ExecutionContext) -> dict:
        value = context.inputs.content.get('value', 0)

        if value > 10:
            return {'status': 'high', 'proceed': True}
        elif value > 5:
            return {'status': 'medium', 'proceed': True}
        else:
            return {'status': 'low', 'proceed': False}
```

### Node with Custom Validation

```python
def validate_numeric_input(context: ExecutionContext) -> None:
    """Validate that input contains a numeric value."""
    content = context.inputs.content

    if 'value' not in content:
        raise ValueError("Missing 'value' field")

    if not isinstance(content['value'], (int, float)):
        raise TypeError("'value' must be numeric")

class ValidatedNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            pre_process_hooks=[validate_numeric_input]
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Input guaranteed to be valid
        value = context.inputs.content['value']
        return {'result': value * 2}
```

---

## Best Practices

### 1. Single Responsibility

Each node should do one thing well:

```python
# Good: Single responsibility
class FetchDataNode(Node):
    async def process(self, context):
        data = await fetch_from_api()
        return {'data': data}

class TransformDataNode(Node):
    async def process(self, context):
        data = context.inputs.content['data']
        transformed = transform(data)
        return {'transformed': transformed}

# Less ideal: Multiple responsibilities
class FetchAndTransformNode(Node):
    async def process(self, context):
        data = await fetch_from_api()
        transformed = transform(data)
        return {'transformed': transformed}
```

### 2. Explicit Input Requirements

Document what inputs your node expects:

```python
class DataProcessorNode(Node):
    """
    Process user data.

    Required Inputs:
        user_id (int): User identifier
        data_type (str): Type of data to process

    Optional Inputs:
        format (str): Output format, defaults to 'json'

    Outputs:
        processed_data (dict): Processed results
        metadata (dict): Processing metadata
    """

    async def process(self, context: ExecutionContext) -> dict:
        # Implementation
        pass
```

### 3. Use Type Hints

```python
from typing import Any

class TypedNode(Node):
    async def process(self, context: ExecutionContext) -> dict[str, Any]:
        user_id: int = context.inputs.content['user_id']
        query: str = context.inputs.content['query']

        result: dict[str, Any] = await self.query_database(user_id, query)
        return {'result': result}
```

### 4. Error Handling

```python
class RobustNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        try:
            data = await self.fetch_data()
            return {'data': data, 'error': None}
        except APIError as e:
            # Return error in outputs rather than raising
            return {'data': None, 'error': str(e)}
```

### 5. Use Capabilities for Resilience

```python
# Instead of manual retry logic in process()
config = NodeConfig(
    retry=RetryPolicy(max_attempts=3, backoff='exponential'),
    timeout=TimeoutPolicy(seconds=30.0)
)
node = MyNode(config=config)
```

### 6. Avoid Side Effects When Possible

```python
# Good: Pure transformation
class PureNode(Node):
    async def process(self, context):
        data = context.inputs.content['data']
        result = transform(data)  # No side effects
        return {'result': result}

# Use with caution: Side effects
class SideEffectNode(Node):
    async def process(self, context):
        await send_email()  # Side effect
        await update_database()  # Side effect
        return {'sent': True}
```

---

## Common Pitfalls

### 1. Modifying Inputs

```python
# Wrong: Modifying inputs
class BadNode(Node):
    async def process(self, context):
        data = context.inputs.content['data']
        data.append('modified')  # Mutates input!
        return {'data': data}

# Correct: Copy before modifying
class GoodNode(Node):
    async def process(self, context):
        data = context.inputs.content['data'].copy()
        data.append('modified')
        return {'data': data}
```

### 2. Forgetting to Return Outputs

```python
# Wrong: No return statement
class IncompleteNode(Node):
    async def process(self, context):
        result = compute_something()
        # Forgot to return!

# Correct: Always return dict or None
class CompleteNode(Node):
    async def process(self, context):
        result = compute_something()
        return {'result': result}
```

### 3. Blocking Operations

```python
# Wrong: Blocking operation in async method
class BlockingNode(Node):
    async def process(self, context):
        time.sleep(5)  # Blocks event loop!
        return {'done': True}

# Correct: Use async sleep
class NonBlockingNode(Node):
    async def process(self, context):
        await asyncio.sleep(5)
        return {'done': True}
```

### 4. State Mutation Without keep_in_state

```python
# Wrong: Expecting state to persist without configuration
class StatefulNode(Node):
    async def process(self, context):
        context.state['counter'] = context.state.get('counter', 0) + 1
        # counter won't persist across runs!

# Correct: Configure keep_in_state
class PersistentNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(keep_in_state=['counter'])
        super().__init__(config=config, **kwargs)

    async def process(self, context):
        context.state['counter'] = context.state.get('counter', 0) + 1
        return {'count': context.state['counter']}
```

---

## Related Documentation

- [Node System Architecture](/docs/architecture/node-system.md) - Design principles and architecture
- [Execution Context](/docs/nodes/execution-context.md) - Context object reference
- [Capabilities System](/docs/nodes/capabilities.md) - Retry, timeout, rate limiting, etc.
- [Special Node Types](/docs/nodes/special-nodes.md) - AgentNode, HumanNode, RpcNode, etc.
- [Channels & Messaging](/docs/nodes/channels.md) - Inter-node communication
- [Graph Fundamentals](/docs/graphs/fundamentals.md) - Connecting nodes into workflows

---

## Summary

This reference covered:
- Node class hierarchy (BaseNode vs Node)
- Creating custom nodes with the process method
- Process method patterns (async, sync, no-arg)
- Input/output flow mechanics
- Node configuration via NodeConfig
- Node state management and persistence
- Lifecycle hooks (pre-process, post-process)
- Testing strategies and patterns
- Best practices and common pitfalls

Nodes are the foundation of Spark workflows. Master these fundamentals to build robust, composable, and testable processing units.
