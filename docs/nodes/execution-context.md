---
title: Execution Context
parent: Node
nav_order: 2
---
# Execution Context

---

## Overview

The `ExecutionContext` is a comprehensive container passed to every node's `process()` method, providing access to inputs, state, metadata, and graph-level state. It serves as the primary interface between the framework and node logic, enabling nodes to receive data, track execution, and communicate with the broader graph.

**Location**: `spark/nodes/types.py`

**Key Responsibilities**:
- Deliver inputs from previous nodes
- Provide access to node-local state
- Track execution metadata (timing, attempts)
- Expose graph-level shared state
- Store outputs for next nodes
- Support context forking for branching

---

## ExecutionContext Structure

### Type Definition

```python
from dataclasses import dataclass, field
from typing import Any, Optional, Generic, TypeVar
from spark.nodes.types import NodeMessage, ExecutionMetadata, NodeState

TNodeState = TypeVar('TNodeState', bound=NodeState)

@dataclass(slots=True)
class ExecutionContext(Generic[TNodeState]):
    """Execution context for node.process() method."""

    inputs: NodeMessage = field(default_factory=NodeMessage)
    state: TNodeState = field(default_factory=default_node_state)
    metadata: ExecutionMetadata = field(default_factory=ExecutionMetadata)
    outputs: Any | None = None
    graph_state: Optional['GraphState'] = None
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `inputs` | `NodeMessage` | Inputs from previous node or initial task |
| `state` | `NodeState` | Node-local state (persists across executions) |
| `metadata` | `ExecutionMetadata` | Timing and attempt information |
| `outputs` | `Any \| None` | Outputs produced by process method |
| `graph_state` | `GraphState \| None` | Global state shared across all nodes |

---

## Accessing Inputs and Outputs

### Input Access

Nodes receive inputs via `context.inputs`:

```python
from spark.nodes import Node
from spark.nodes.types import ExecutionContext

class InputProcessorNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Access input content (dict from previous node)
        content = context.inputs.content

        # Extract specific fields
        user_id = content.get('user_id')
        query = content.get('query')

        # Access metadata
        request_id = context.inputs.metadata.get('request_id')

        # Access raw LLM output (if from agent/LLM node)
        raw_response = context.inputs.raw

        return {'processed': True, 'user_id': user_id}
```

### NodeMessage Structure

```python
class NodeMessage(BaseModel):
    """Payload to/from nodes."""

    id: str | None = None                    # Optional message ID
    type: Literal['json', 'text'] = 'text'   # Content type
    content: Any = None                       # Primary content (dict or other)
    raw: Any = None                          # Raw output before parsing
    metadata: dict = Field(default_factory=dict)  # Message metadata
    extras: dict = Field(default_factory=dict)    # Additional data
    state: dict[str, Any] | None = None      # Optional state snapshot
```

### Input Content Patterns

#### Dict Content (Most Common)

```python
class DictInputNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Previous node returned dict
        # context.inputs.content = {'key': 'value', 'count': 42}

        key = context.inputs.content['key']
        count = context.inputs.content['count']

        return {'result': f"{key}: {count}"}
```

#### List Content

```python
class ListInputNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Previous node returned list
        # context.inputs.content = ['item1', 'item2', 'item3']

        items = context.inputs.content
        for item in items:
            process_item(item)

        return {'processed_count': len(items)}
```

#### Primitive Content

```python
class PrimitiveInputNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Previous node returned simple value
        # context.inputs.content = "some text"

        text = context.inputs.content
        return {'length': len(text)}
```

### Output Generation

Return value becomes `context.outputs` and flows to next nodes:

```python
class OutputGeneratorNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Return dict becomes outputs
        return {
            'user_id': 123,
            'query': 'weather forecast',
            'timestamp': time.time(),
            'status': 'success'
        }

# Next node receives:
# context.inputs.content = {
#     'user_id': 123,
#     'query': 'weather forecast',
#     'timestamp': ...,
#     'status': 'success'
# }
```

### None Outputs

```python
class SideEffectNode(Node):
    async def process(self, context: ExecutionContext) -> None:
        # Perform side effects
        await send_notification(context.inputs.content)

        # No return or return None
        # context.outputs remains None
        # Next node receives empty inputs
```

---

## Node State Access

### NodeState Structure

```python
class NodeState(TypedDict):
    """State of a node."""

    context_snapshot: dict[str, Any] | None  # Last context snapshot
    processing: bool                          # Currently processing flag
    pending_inputs: deque[NodeMessage]        # Queued messages
    process_count: int                        # Number of executions
    # ... any additional custom keys
```

### Reading State

```python
class StatefulNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Read standard state fields
        count = context.state['process_count']
        is_processing = context.state['processing']

        # Read custom state values
        last_result = context.state.get('last_result', None)
        user_context = context.state.get('user_context', {})

        return {'execution_count': count}
```

### Modifying State

```python
class StateModifierNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Modify state directly
        context.state['last_executed'] = time.time()
        context.state['custom_data'] = {'key': 'value'}

        # State modifications persist if key in keep_in_state
        return {'updated': True}
```

### State Persistence with keep_in_state

```python
from spark.nodes.config import NodeConfig

config = NodeConfig(
    keep_in_state=['user_id', 'session_id', 'preferences']
)

node = PersistentStateNode(config=config)

# First execution
inputs1 = NodeMessage(content={
    'user_id': 123,
    'session_id': 'abc',
    'query': 'hello'
})
await node.run(inputs1)

# In process():
# context.state['user_id'] = 123 (copied from inputs)
# context.state['session_id'] = 'abc' (copied from inputs)

# Second execution - state persists
inputs2 = NodeMessage(content={'query': 'goodbye'})
await node.run(inputs2)

# In process():
# context.state['user_id'] = 123 (persisted from previous run)
# context.state['session_id'] = 'abc' (persisted from previous run)
```

### State vs Graph State

| Aspect | Node State | Graph State |
|--------|------------|-------------|
| Scope | Single node | All nodes in graph |
| Access | `context.state` | `context.graph_state` |
| Persistence | Within node instance | Across graph execution |
| Isolation | Node-specific | Shared globally |
| Use case | Node-local counters, cache | Workflow coordination, aggregation |

---

## Metadata and Tracing

### ExecutionMetadata Structure

```python
@dataclass(slots=True)
class ExecutionMetadata:
    """Timing and attempt metadata."""

    attempt: int = 1                     # Current attempt number
    started_at: float | None = None      # Start timestamp (perf_counter)
    finished_at: float | None = None     # Finish timestamp (perf_counter)

    @property
    def duration(self) -> float | None:
        """Execution duration in seconds."""
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at
```

### Accessing Metadata

```python
class TimingAwareNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Current attempt (useful with retry capability)
        attempt = context.metadata.attempt

        # Start time (set by framework)
        started = context.metadata.started_at

        # Perform work
        result = await expensive_operation()

        # Duration not yet available (finished_at set after process returns)

        return {
            'result': result,
            'attempt': attempt
        }
```

### Timing Information

```python
class MetadataInspectorNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Metadata is updated by framework
        context.metadata.mark_started(attempt=1)

        # ... processing ...

        context.metadata.mark_finished()

        # Access duration
        duration = context.metadata.duration

        return {'duration_seconds': duration}
```

### Retry Attempts

```python
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy

class RetryAwareNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            retry=RetryPolicy(max_attempts=3)
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Attempt number increments on retry
        attempt = context.metadata.attempt

        if attempt == 1:
            print("First attempt")
        else:
            print(f"Retry attempt {attempt}")

        # Logic that may fail and trigger retry
        result = await unreliable_operation()

        return {'result': result, 'attempts': attempt}
```

---

## Graph State Access

### Overview

Graph state provides shared, transactional state across all nodes in a workflow.

**Key Features**:
- Thread-safe with automatic locking
- Transaction support for atomic updates
- Persists across `graph.run()` calls
- Optional (can be disabled)

### Checking Availability

```python
class GraphStateNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Check if graph state is enabled
        if context.graph_state is None:
            # Graph state not configured
            return {'status': 'no_graph_state'}

        # Use graph state
        counter = await context.graph_state.get('counter', 0)
        await context.graph_state.set('counter', counter + 1)

        return {'counter': counter + 1}
```

### Reading Values

```python
class ReaderNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Read with default value
        counter = await context.graph_state.get('counter', 0)
        results = await context.graph_state.get('results', [])

        return {
            'counter': counter,
            'result_count': len(results)
        }
```

### Writing Values

```python
class WriterNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Single value
        await context.graph_state.set('status', 'processing')

        # Multiple values
        await context.graph_state.update({
            'current_node': self.id,
            'timestamp': time.time()
        })

        return {'updated': True}
```

### Atomic Transactions

For read-modify-write operations, use transactions:

```python
class AtomicCounterNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Atomic increment
        async with context.graph_state.transaction() as state:
            counter = state.get('counter', 0)
            state['counter'] = counter + 1

        return {'new_count': counter + 1}
```

### Accumulation Pattern

```python
class AccumulatorNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        result = context.inputs.content['result']

        # Append to shared collection
        async with context.graph_state.transaction() as state:
            results = state.get('results', [])
            results.append(result)
            state['results'] = results

        return {'accumulated': len(results)}
```

### Coordination Pattern

```python
class CoordinatorNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Check shared flag
        stop_requested = await context.graph_state.get('stop', False)

        if stop_requested:
            return {'status': 'stopped', 'continue': False}

        # Perform work
        result = await do_work()

        # Update progress
        async with context.graph_state.transaction() as state:
            completed = state.get('completed', 0)
            state['completed'] = completed + 1

        return {'status': 'continue', 'continue': True}
```

---

## Error Handling Context

### Context Snapshot on Error

When errors occur, the framework captures context state:

```python
from spark.nodes.exceptions import NodeExecutionError

try:
    await node.run(inputs)
except NodeExecutionError as e:
    # Access context snapshot at time of error
    snapshot = e.context_snapshot

    print(f"Failed with state: {snapshot}")
    print(f"Process count: {snapshot.get('process_count')}")
    print(f"Custom data: {snapshot.get('custom_data')}")
```

### Snapshot Method

```python
class SnapshotNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Create snapshot manually
        snapshot = context.snapshot()

        # Snapshot is a deep copy of state
        # Safe to store or inspect without affecting state

        return {'snapshot': snapshot}
```

### Error Recovery

```python
class ErrorRecoveryNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        try:
            result = await risky_operation()
            return {'result': result}
        except Exception as e:
            # Access context for error reporting
            error_report = {
                'error': str(e),
                'attempt': context.metadata.attempt,
                'state_snapshot': context.snapshot()
            }

            # Log or store error report
            await log_error(error_report)

            # Can return error in outputs or re-raise
            return {'error': error_report}
```

---

## Context in Different Execution Modes

### Sequential Mode

In standard sequential execution:

```python
# Context flows linearly
# node1 -> node2 -> node3

class SequentialNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Receives inputs from previous node
        prev_result = context.inputs.content

        # No special considerations
        # Context is fresh for each execution

        return {'done': True}
```

### Long-Running Mode

In `LONG_RUNNING` mode, nodes operate continuously:

```python
from spark.graphs import Task, TaskType

class LongRunningNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(live=True)
        super().__init__(config=config, **kwargs)

    async def go(self):
        """Continuous execution loop."""
        while not self._stop_flag:
            # Receive message from mailbox
            message = await self.mailbox.receive()

            if message.is_shutdown:
                break

            # Create context from message
            inputs = NodeMessage(content=message.payload)
            context = self._prepare_context(inputs)

            # Process
            await self._process(context)

# Run in long-running mode
task = Task(
    inputs=NodeMessage(content={'start': True}),
    type=TaskType.LONG_RUNNING
)
await graph.run(task)
```

### Context Preparation

The framework prepares contexts via `_prepare_context()`:

```python
def _prepare_context(self, inputs: NodeMessage) -> ExecutionContext:
    """Prepare execution context from inputs."""
    context = ExecutionContext(
        inputs=inputs,
        state=self._state
    )

    # Attach graph state if available
    graph_state = getattr(self, '_graph_state', None)
    if graph_state is not None:
        context.graph_state = graph_state

    return context
```

---

## Context Forking

For branching workflows, contexts can be forked:

```python
def fork(self) -> ExecutionContext:
    """Produce a copy suitable for branch execution."""
    return ExecutionContext(
        inputs=_safe_copy(self.inputs),
        state=_safe_copy(self.state),
        metadata=replace(self.metadata),
        outputs=_safe_copy(self.outputs),
        graph_state=self.graph_state  # Shared, not copied
    )
```

**Use Case**: Parallel execution paths need independent contexts:

```python
class BranchingNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Fork context for parallel processing
        context_a = context.fork()
        context_b = context.fork()

        # Process branches independently
        result_a = await process_branch_a(context_a)
        result_b = await process_branch_b(context_b)

        # Merge results
        return {
            'branch_a': result_a,
            'branch_b': result_b
        }
```

**Note**: Graph state is shared (not copied) to maintain coordination across branches.

---

## Best Practices

### 1. Always Check graph_state Availability

```python
# Good: Defensive check
if context.graph_state is not None:
    await context.graph_state.set('key', value)

# Risky: Assumes graph_state exists
await context.graph_state.set('key', value)  # May raise AttributeError
```

### 2. Use Transactions for Read-Modify-Write

```python
# Wrong: Non-atomic
counter = await context.graph_state.get('counter', 0)
await context.graph_state.set('counter', counter + 1)

# Correct: Atomic transaction
async with context.graph_state.transaction() as state:
    state['counter'] = state.get('counter', 0) + 1
```

### 3. Document Expected Inputs

```python
class DocumentedNode(Node):
    """
    Process user data.

    Expected Inputs (context.inputs.content):
        user_id (int): User identifier
        query (str): Search query
        filters (dict, optional): Query filters

    Outputs:
        results (list): Search results
        total (int): Total result count
    """
    async def process(self, context: ExecutionContext) -> dict:
        # Implementation
        pass
```

### 4. Validate Inputs

```python
class ValidatingNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        content = context.inputs.content

        # Validate required fields
        if 'user_id' not in content:
            raise ValueError("Missing required field: user_id")

        if not isinstance(content['user_id'], int):
            raise TypeError("user_id must be int")

        # Process validated inputs
        return {'validated': True}
```

### 5. Use Metadata for Debugging

```python
class DebuggableNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Log execution metadata
        print(f"Attempt {context.metadata.attempt}")
        print(f"Started at {context.metadata.started_at}")

        result = await operation()

        # Include metadata in outputs for tracing
        return {
            'result': result,
            'metadata': {
                'attempt': context.metadata.attempt,
                'node_id': self.id
            }
        }
```

---

## Advanced Patterns

### Context-Aware State Management

```python
class ContextAwareNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Combine node state and graph state
        local_count = context.state.get('local_count', 0)
        global_count = await context.graph_state.get('global_count', 0) \
            if context.graph_state else 0

        # Update both
        context.state['local_count'] = local_count + 1

        if context.graph_state:
            async with context.graph_state.transaction() as state:
                state['global_count'] = global_count + 1

        return {
            'local': local_count + 1,
            'global': global_count + 1
        }
```

### Dynamic Configuration from Context

```python
class DynamicNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Read configuration from inputs
        config = context.inputs.content.get('config', {})

        timeout = config.get('timeout', 30)
        max_results = config.get('max_results', 10)

        # Use dynamic configuration
        results = await self.query(
            timeout=timeout,
            limit=max_results
        )

        return {'results': results}
```

### Context Enrichment Pattern

```python
class EnricherNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Start with inputs
        data = context.inputs.content.copy()

        # Enrich with state
        data['execution_count'] = context.state['process_count']

        # Enrich with graph state
        if context.graph_state:
            data['workflow_id'] = await context.graph_state.get('workflow_id')

        # Enrich with metadata
        data['attempt'] = context.metadata.attempt

        return {'enriched_data': data}
```

---

## Related Documentation

- [Node Fundamentals](/docs/nodes/fundamentals.md) - Basic node concepts
- [Node State](/docs/nodes/fundamentals.md#node-state) - NodeState reference
- [Graph State](/docs/graphs/graph-state.md) - Global shared state
- [Execution Modes](/docs/graphs/execution-modes.md) - Sequential vs long-running

---

## Summary

`ExecutionContext` provides comprehensive access to:
- **Inputs**: Data from previous nodes via `context.inputs`
- **State**: Node-local state via `context.state`
- **Metadata**: Timing and attempts via `context.metadata`
- **Outputs**: Results to pass to next nodes
- **Graph State**: Shared workflow state via `context.graph_state`

The context is the primary interface between framework and node logic, enabling data flow, state management, and coordination across workflows.
