---
title: Graph State
parent: Graph
nav_order: 2
---
# Graph State

---

**Graph state** is a thread-safe, transactional key-value store shared across all nodes in a graph. It provides a centralized location for data that needs to be accessed or modified by multiple nodes, such as counters, aggregated results, or workflow coordination flags.

Graph state is distinct from node-level state:
- **Graph state**: Shared across all nodes, persists across multiple `graph.run()` calls
- **Node state**: Local to each node, tracks per-node execution metadata

## GraphState Architecture

### Core Concepts

1. **Transactional**: Supports atomic read-modify-write operations
2. **Thread-Safe**: Automatic locking in concurrent execution modes
3. **Backend-Agnostic**: Supports multiple storage backends (memory, SQLite, JSON, custom)
4. **Schema-Based**: Optional schema validation for type safety
5. **Persistent**: Can persist across process restarts (backend-dependent)

### GraphState Class

Located in `spark/graphs/graph_state.py`, the `GraphState` class provides the core API:

```python
class GraphState:
    def __init__(
        self,
        backend: StateBackend,
        schema: Optional[StateSchema] = None,
        enable_locking: bool = False
    )
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | `StateBackend` | Required | Storage backend for state data |
| `schema` | `StateSchema` | `None` | Optional schema for validation |
| `enable_locking` | `bool` | `False` | Enable thread-safe locking |

## State Schema

Define data contracts for graph state to enforce type safety and structure.

### Defining a Schema

```python
from spark.graphs.graph_state import StateSchema
from typing import List

schema = StateSchema(
    fields={
        'counter': int,
        'results': List[str],
        'enabled': bool,
        'metadata': dict
    },
    required_fields=['counter'],  # Must be initialized
    default_values={'counter': 0, 'enabled': True}
)
```

### StateSchema Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `fields` | `dict[str, type]` | Field names and their expected types |
| `required_fields` | `list[str]` | Fields that must be present |
| `default_values` | `dict` | Default values for fields |

### Using Schema with Graph

```python
from spark.graphs import Graph
from spark.graphs.graph_state import StateSchema

schema = StateSchema(
    fields={'counter': int, 'items': list},
    required_fields=['counter'],
    default_values={'counter': 0, 'items': []}
)

graph = Graph(
    start=my_node,
    initial_state={'counter': 0, 'items': []},
    schema=schema  # Validates state operations
)
```

### Schema Validation

Schema validation occurs on:
- `set()`: Type checking for field values
- `update()`: Type checking for all updated fields
- Initialization: Required fields presence

```python
# Valid
await state.set('counter', 42)  # int matches schema

# Invalid - raises ValidationError
await state.set('counter', 'not an int')  # Type mismatch
await state.set('unknown_field', 123)  # Field not in schema
```

## Initialization and Configuration

### Graph Initialization with State

```python
from spark.graphs import Graph

# Empty state (backend defaults)
graph = Graph(start=node1)

# With initial values
graph = Graph(
    start=node1,
    initial_state={'counter': 0, 'results': [], 'status': 'ready'}
)

# Disable state (for minimal overhead)
graph = Graph(start=node1, enable_graph_state=False)
```

### Configuring State Backend

```python
from spark.graphs.graph_state import GraphState, InMemoryBackend

# Custom backend configuration
backend = InMemoryBackend()
state = GraphState(backend=backend, enable_locking=True)

graph = Graph(start=node1)
graph.graph_state = state  # Replace default state
```

## Reading and Writing State

### From Node Process Methods

Nodes access graph state via `context.graph_state`:

```python
from spark.nodes import Node

class MyNode(Node):
    async def process(self, context):
        # Check if state is enabled
        if context.graph_state is None:
            return {'error': 'State not enabled'}

        # Read value
        counter = await context.graph_state.get('counter', default=0)

        # Write value
        await context.graph_state.set('counter', counter + 1)

        # Read multiple values
        status = await context.graph_state.get('status')
        results = await context.graph_state.get('results', [])

        return {'counter': counter + 1}
```

### get() Method

```python
async def get(self, key: str, default: Any = None) -> Any
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `key` | `str` | Required | State key to retrieve |
| `default` | `Any` | `None` | Default value if key doesn't exist |

**Returns:** Value associated with key, or default if not found.

**Example:**

```python
# With default
counter = await context.graph_state.get('counter', 0)

# Without default (returns None if missing)
status = await context.graph_state.get('status')

# Handle missing keys
value = await context.graph_state.get('optional_key')
if value is None:
    # Key doesn't exist
    pass
```

### set() Method

```python
async def set(self, key: str, value: Any) -> None
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | State key to set |
| `value` | `Any` | Value to store (must be JSON-serializable for persistent backends) |

**Example:**

```python
# Set simple value
await context.graph_state.set('counter', 42)

# Set complex value
await context.graph_state.set('results', [
    {'id': 1, 'value': 'a'},
    {'id': 2, 'value': 'b'}
])

# Set nested dict
await context.graph_state.set('config', {
    'enabled': True,
    'settings': {'timeout': 30, 'retries': 3}
})
```

### update() Method

```python
async def update(self, updates: dict) -> None
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `updates` | `dict` | Dictionary of key-value pairs to update |

**Example:**

```python
# Update multiple keys at once
await context.graph_state.update({
    'counter': 10,
    'status': 'processing',
    'timestamp': datetime.now().isoformat()
})
```

### Complete Example

```python
from spark.nodes import Node
from spark.graphs import Graph

class CounterNode(Node):
    async def process(self, context):
        # Read current counter
        counter = await context.graph_state.get('counter', 0)

        # Increment
        counter += 1

        # Write back
        await context.graph_state.set('counter', counter)

        # Check if done
        done = counter >= 10
        return {'done': done, 'counter': counter}

class ResultNode(Node):
    async def process(self, context):
        final_count = await context.graph_state.get('counter', 0)
        return {'result': f"Counted to {final_count}"}

# Build graph
counter = CounterNode()
result = ResultNode()

counter.on(done=False) >> counter  # Loop
counter.on(done=True) >> result    # Exit

graph = Graph(start=counter, initial_state={'counter': 0})
output = await graph.run()
print(output.content)  # {'result': 'Counted to 10'}
```

## Transactions for Atomic Updates

Use transactions for atomic read-modify-write operations to prevent race conditions.

### Transaction Context Manager

```python
async with context.graph_state.transaction() as state:
    # All operations within this block are atomic
    current = state.get('counter', 0)
    state['counter'] = current + 1
    state['last_updated'] = datetime.now().isoformat()
    # Changes committed when context exits
```

### Why Use Transactions

**Without transaction (race condition possible):**

```python
# Node A
count = await state.get('counter', 0)
# <-- Node B might read same value here
await state.set('counter', count + 1)

# Node B (concurrent)
count = await state.get('counter', 0)  # Reads same value as A
await state.set('counter', count + 1)  # Overwrites A's increment!
```

**With transaction (atomic):**

```python
# Node A
async with state.transaction() as s:
    count = s.get('counter', 0)
    s['counter'] = count + 1
# Node B waits until A's transaction completes

# Node B
async with state.transaction() as s:
    count = s.get('counter', 0)  # Reads updated value
    s['counter'] = count + 1
```

### Transaction Example

```python
from spark.nodes import Node

class AccountTransferNode(Node):
    async def process(self, context):
        from_account = context.inputs.content.get('from')
        to_account = context.inputs.content.get('to')
        amount = context.inputs.content.get('amount')

        # Atomic transfer
        async with context.graph_state.transaction() as state:
            # Read balances
            from_balance = state.get(f'balance_{from_account}', 0)
            to_balance = state.get(f'balance_{to_account}', 0)

            # Check sufficient funds
            if from_balance < amount:
                return {'success': False, 'error': 'Insufficient funds'}

            # Update both balances atomically
            state[f'balance_{from_account}'] = from_balance - amount
            state[f'balance_{to_account}'] = to_balance + amount

        return {'success': True, 'amount': amount}
```

### Transaction API

Inside a transaction, the state object supports:

```python
async with context.graph_state.transaction() as state:
    # Dict-like access
    value = state.get('key', default)
    state['key'] = value

    # Check existence
    if 'key' in state:
        pass

    # Delete key
    del state['key']

    # Iterate keys
    for key in state:
        print(key, state[key])
```

## Thread Safety in Concurrent Mode

Graph state automatically enables locking when running in concurrent mode (`TaskType.LONG_RUNNING`).

### Automatic Locking

```python
from spark.graphs.tasks import Task, TaskType

# Sequential mode: no locking overhead
task = Task(type=TaskType.STANDARD)
result = await graph.run(task)

# Concurrent mode: automatic locking enabled
task = Task(type=TaskType.LONG_RUNNING)
result = await graph.run(task)  # State operations are thread-safe
```

### Locking Behavior

- **Sequential mode**: No locks, zero overhead
- **Concurrent mode**: Automatic `asyncio.Lock` per operation
- **Transactions**: Always locked, regardless of mode

### Manual Locking Control

```python
from spark.graphs.graph_state import GraphState, InMemoryBackend

# Force locking on
state = GraphState(backend=InMemoryBackend(), enable_locking=True)

# Force locking off (use with caution in concurrent mode)
state = GraphState(backend=InMemoryBackend(), enable_locking=False)
```

## State Persistence Across Runs

Graph state persists across multiple `graph.run()` calls unless explicitly reset.

### Persistent State Example

```python
from spark.graphs import Graph
from spark.nodes import Node

class IncrementNode(Node):
    async def process(self, context):
        count = await context.graph_state.get('count', 0)
        await context.graph_state.set('count', count + 1)
        return {'count': count + 1}

graph = Graph(start=IncrementNode(), initial_state={'count': 0})

# First run
result1 = await graph.run()
print(result1.content['count'])  # 1

# Second run (state persists)
result2 = await graph.run()
print(result2.content['count'])  # 2

# Third run
result3 = await graph.run()
print(result3.content['count'])  # 3
```

### Resetting State

```python
# Reset to initial values
graph.reset_state({'count': 0})

result = await graph.run()
print(result.content['count'])  # 1 (reset)

# Reset to empty
graph.reset_state({})
```

### Checking State After Execution

```python
# Run graph
result = await graph.run()

# Access graph state from graph level
counter = await graph.get_state('counter')
print(f"Final counter: {counter}")

# Get full state snapshot
snapshot = graph.get_state_snapshot()
print(f"Full state: {snapshot}")
```

## State Backends

Spark supports multiple storage backends for graph state.

### InMemoryBackend (Default)

Volatile, fast storage in memory. Lost when process exits.

```python
from spark.graphs.graph_state import InMemoryBackend

backend = InMemoryBackend()
# No configuration needed
```

**Characteristics:**
- Fastest performance
- No persistence across process restarts
- Suitable for development, testing, short-lived workflows

**Use when:**
- State doesn't need to persist
- Maximum performance required
- Simple workflows without crash recovery needs

### SQLiteBackend

Persistent local storage using SQLite database.

```python
from spark.graphs.graph_state import SQLiteBackend

backend = SQLiteBackend(
    db_path='/path/to/state.db',
    table_name='graph_state',  # Optional, default: 'graph_state'
    auto_commit=True           # Optional, default: True
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | Required | Path to SQLite database file |
| `table_name` | `str` | `'graph_state'` | Table name for state storage |
| `auto_commit` | `bool` | `True` | Auto-commit after each write |

**Characteristics:**
- Persistent across process restarts
- Good performance for moderate state sizes
- Suitable for production use
- Transactional support

**Use when:**
- State must survive process restarts
- Single-machine deployments
- Moderate state size (< 1GB typical)

**Example:**

```python
from spark.graphs import Graph
from spark.graphs.graph_state import GraphState, SQLiteBackend

# Create backend
backend = SQLiteBackend(db_path='/var/lib/spark/workflow_state.db')

# Create state with backend
state = GraphState(backend=backend, enable_locking=True)

# Use with graph
graph = Graph(start=my_node)
graph.graph_state = state

# State persists across runs
result1 = await graph.run()
# ... process restarts ...
result2 = await graph.run()  # State restored
```

### JSONBackend

File-based persistence using JSON files.

```python
from spark.graphs.graph_state import JSONBackend

backend = JSONBackend(
    file_path='/path/to/state.json',
    pretty_print=True,  # Optional, default: False
    auto_save=True      # Optional, default: True
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | Required | Path to JSON file |
| `pretty_print` | `bool` | `False` | Format JSON with indentation |
| `auto_save` | `bool` | `True` | Save after each write |

**Characteristics:**
- Human-readable file format
- Easy to inspect and debug
- Slower than SQLite for large state
- Good for configuration-style state

**Use when:**
- State needs to be human-readable
- Debugging and development
- Small to medium state sizes
- Easy inspection required

**Example:**

```python
from spark.graphs.graph_state import JSONBackend

backend = JSONBackend(
    file_path='/tmp/workflow_state.json',
    pretty_print=True
)

state = GraphState(backend=backend)
graph = Graph(start=my_node)
graph.graph_state = state
```

### Custom Backend Implementation

Implement custom backends for specialized storage needs (Redis, PostgreSQL, etc.).

```python
from spark.graphs.graph_state import StateBackend

class RedisBackend(StateBackend):
    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url)

    async def get(self, key: str) -> Any:
        value = self.client.get(key)
        return json.loads(value) if value else None

    async def set(self, key: str, value: Any) -> None:
        self.client.set(key, json.dumps(value))

    async def update(self, updates: dict) -> None:
        pipeline = self.client.pipeline()
        for key, value in updates.items():
            pipeline.set(key, json.dumps(value))
        pipeline.execute()

    async def delete(self, key: str) -> None:
        self.client.delete(key)

    async def clear(self) -> None:
        # Clear all keys (implement carefully)
        pass

    async def snapshot(self) -> dict:
        # Return all state as dict
        pass

# Use custom backend
backend = RedisBackend('redis://localhost:6379/0')
state = GraphState(backend=backend, enable_locking=True)
```

### Backend Comparison

| Backend | Persistence | Performance | Use Case |
|---------|-------------|-------------|----------|
| InMemoryBackend | No | Fastest | Development, testing, ephemeral workflows |
| SQLiteBackend | Yes | Fast | Production, single-machine, moderate state |
| JSONBackend | Yes | Moderate | Debugging, human-readable, small state |
| Custom | Depends | Varies | Specialized needs (Redis, PostgreSQL, etc.) |

## State in Subgraphs

Subgraphs have isolated state by default but can share parent state if configured.

### Isolated State (Default)

```python
from spark.nodes import Node
from spark.graphs import Graph

class SubgraphNode(Node):
    def __init__(self):
        super().__init__()
        # Create subgraph with its own state
        self.subgraph = Graph(
            start=InnerNode(),
            initial_state={'sub_counter': 0}
        )

    async def process(self, context):
        # Subgraph state is isolated
        result = await self.subgraph.run()
        return result.content
```

### Shared State

```python
class SubgraphNode(Node):
    def __init__(self, parent_graph):
        super().__init__()
        # Create subgraph sharing parent state
        self.subgraph = Graph(start=InnerNode())
        self.subgraph.graph_state = parent_graph.graph_state

    async def process(self, context):
        # Subgraph can access parent state
        result = await self.subgraph.run()
        return result.content

# Build
parent_graph = Graph(start=SubgraphNode(parent_graph), initial_state={'shared': 0})
```

## Performance Considerations

### Read vs. Write Performance

- **get()**: Very fast (O(1) for in-memory)
- **set()**: Fast (O(1) for in-memory)
- **transaction()**: Adds locking overhead but ensures atomicity

### Backend Performance

| Operation | InMemory | SQLite | JSON |
|-----------|----------|--------|------|
| Read | ~0.1μs | ~50μs | ~100μs |
| Write | ~0.1μs | ~100μs | ~1ms |
| Transaction | ~1μs | ~200μs | ~2ms |

### Optimization Tips

1. **Batch Updates**: Use `update()` instead of multiple `set()` calls
2. **Minimize State Size**: Store only necessary data
3. **Use Transactions Sparingly**: Only when atomicity is required
4. **Choose Right Backend**: Match backend to persistence needs
5. **Disable State**: If not needed, disable for zero overhead

### Example: Optimized State Usage

```python
# Bad: Multiple individual writes
await state.set('key1', value1)
await state.set('key2', value2)
await state.set('key3', value3)

# Good: Single batch update
await state.update({
    'key1': value1,
    'key2': value2,
    'key3': value3
})

# Bad: Unnecessary transaction
async with state.transaction() as s:
    s['key'] = value  # Single write doesn't need transaction

# Good: Transaction only when needed
async with state.transaction() as s:
    current = s.get('counter', 0)
    s['counter'] = current + 1  # Read-modify-write needs transaction
```

## Common Patterns

### Counter Pattern

```python
class CounterNode(Node):
    async def process(self, context):
        async with context.graph_state.transaction() as state:
            count = state.get('counter', 0)
            state['counter'] = count + 1
        return {'count': count + 1}
```

### Accumulator Pattern

```python
class AccumulatorNode(Node):
    async def process(self, context):
        item = context.inputs.content.get('item')

        async with context.graph_state.transaction() as state:
            results = state.get('results', [])
            results.append(item)
            state['results'] = results

        return {'total': len(results)}
```

### Flag Coordination

```python
class ProducerNode(Node):
    async def process(self, context):
        # Do work
        await context.graph_state.set('data_ready', True)
        return {'produced': True}

class ConsumerNode(Node):
    async def process(self, context):
        # Wait for flag
        ready = await context.graph_state.get('data_ready', False)
        if not ready:
            return {'continue': False}

        # Process data
        return {'continue': True}
```

### Aggregation Pattern

```python
class AggregatorNode(Node):
    async def process(self, context):
        metrics = context.inputs.content.get('metrics', {})

        async with context.graph_state.transaction() as state:
            totals = state.get('totals', {})
            for key, value in metrics.items():
                totals[key] = totals.get(key, 0) + value
            state['totals'] = totals

        return {'updated': True}
```

## Best Practices

1. **Use Transactions for Read-Modify-Write**: Prevent race conditions
2. **Initialize State**: Provide defaults via `initial_state` or `get(key, default)`
3. **Check State Availability**: Verify `context.graph_state is not None`
4. **Choose Appropriate Backend**: Match persistence needs
5. **Keep State Minimal**: Store only necessary shared data
6. **Document State Schema**: Clearly document expected state structure
7. **Test Concurrency**: Test graphs with concurrent execution
8. **Handle Missing Keys**: Always provide defaults in `get()`

## Troubleshooting

### State Not Available

```python
# Problem: state is None
counter = await context.graph_state.get('counter')  # AttributeError!

# Solution: check availability
if context.graph_state is not None:
    counter = await context.graph_state.get('counter', 0)
else:
    # Handle case where state is disabled
    counter = 0
```

### Race Conditions

```python
# Problem: concurrent updates lost
count = await state.get('counter', 0)
await asyncio.sleep(0.1)  # Another node might update here
await state.set('counter', count + 1)  # Overwrites other update!

# Solution: use transaction
async with state.transaction() as s:
    count = s.get('counter', 0)
    s['counter'] = count + 1
```

### State Not Persisting

```python
# Problem: using InMemoryBackend expecting persistence
backend = InMemoryBackend()
state = GraphState(backend=backend)
# State lost on process restart!

# Solution: use persistent backend
backend = SQLiteBackend(db_path='state.db')
state = GraphState(backend=backend)
```

## Next Steps

- **[Execution Modes](execution-modes.md)**: Understand state in different execution modes
- **[Checkpointing](checkpointing.md)**: Learn about graph checkpointing and recovery
- **[Subgraphs](subgraphs.md)**: Work with state in nested graphs
- **[Event Bus](event-bus.md)**: Monitor state changes via events
