---
title: Graph Checkpointing
parent: Graph
nav_order: 5
---
# Graph Checkpointing
---

**Graph checkpointing** captures the complete state of a graph at specific points during execution, allowing:
- Recovery from failures
- Long-running workflow resilience
- Debugging and inspection
- Testing with pre-configured states
- Workflow versioning and auditing

Checkpoints store graph state, node states, execution metadata, and configuration in a recoverable format.

## GraphCheckpoint Structure

A checkpoint contains a complete snapshot of graph execution state.

### Checkpoint Schema

```python
from spark.graphs.checkpoint import GraphCheckpoint
from datetime import datetime

checkpoint = GraphCheckpoint(
    checkpoint_id: str,           # Unique checkpoint identifier
    graph_id: str,                # Graph identifier
    timestamp: datetime,          # When checkpoint was created
    graph_state: dict,            # Complete graph state snapshot
    node_states: dict,            # Per-node state snapshots
    execution_metadata: dict,     # Execution context and metadata
    config: dict,                 # Graph configuration
    version: str                  # Checkpoint format version
)
```

### Checkpoint Contents

| Component | Description | Example |
|-----------|-------------|---------|
| `checkpoint_id` | Unique identifier | `"ckpt_20240101_123045_abc123"` |
| `graph_id` | Graph identifier | `"recommendation_pipeline"` |
| `timestamp` | Creation time | `datetime.now()` |
| `graph_state` | Shared graph state | `{'counter': 42, 'results': [...]}` |
| `node_states` | Individual node states | `{'node1': {...}, 'node2': {...}}` |
| `execution_metadata` | Runtime metadata | `{'iteration': 10, 'last_node': 'processor'}` |
| `config` | Graph configuration | `{'enable_state': True, 'mode': 'STANDARD'}` |
| `version` | Format version | `"1.0.0"` |

## Auto-Checkpoint Configuration

Configure automatic checkpointing during graph execution.

### CheckpointConfig

```python
from spark.graphs.checkpoint import CheckpointConfig, CheckpointBackend

config = CheckpointConfig(
    enabled: bool = True,                           # Enable checkpointing
    backend: CheckpointBackend = None,             # Storage backend
    trigger_on_iteration: Optional[int] = None,    # Checkpoint every N iterations
    trigger_on_seconds: Optional[float] = None,    # Checkpoint every N seconds
    trigger_on_node: Optional[List[str]] = None,   # Checkpoint after specific nodes
    max_checkpoints: int = 10,                     # Maximum checkpoints to retain
    auto_cleanup: bool = True                      # Auto-delete old checkpoints
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable/disable checkpointing |
| `backend` | `CheckpointBackend` | `None` | Storage backend (memory, file, database) |
| `trigger_on_iteration` | `int` | `None` | Checkpoint every N iterations (loops) |
| `trigger_on_seconds` | `float` | `None` | Checkpoint every N seconds |
| `trigger_on_node` | `List[str]` | `None` | Checkpoint after specific nodes execute |
| `max_checkpoints` | `int` | `10` | Maximum checkpoints to retain |
| `auto_cleanup` | `bool` | `True` | Automatically delete oldest checkpoints |

### Example: Configure Auto-Checkpointing

```python
from spark.graphs import Graph
from spark.graphs.checkpoint import CheckpointConfig, FileCheckpointBackend

# Configure checkpointing
checkpoint_config = CheckpointConfig(
    enabled=True,
    backend=FileCheckpointBackend(directory='/var/checkpoints'),
    trigger_on_iteration=10,  # Every 10 iterations
    trigger_on_seconds=60.0,  # Every 60 seconds
    max_checkpoints=5         # Keep last 5 checkpoints
)

graph = Graph(
    start=my_node,
    checkpoint_config=checkpoint_config
)

# Run graph (checkpoints created automatically)
result = await graph.run()
```

## State Backends

Checkpoints can be stored in different backends based on persistence and performance needs.

### InMemoryCheckpointBackend

Store checkpoints in memory (volatile, fast).

```python
from spark.graphs.checkpoint import InMemoryCheckpointBackend

backend = InMemoryCheckpointBackend()
```

**Characteristics:**
- Fastest performance
- No persistence across process restarts
- Suitable for testing and development
- Low storage overhead

**Use when:**
- Testing checkpoint functionality
- Development and debugging
- Short-lived workflows
- No persistence required

### FileCheckpointBackend

Store checkpoints as files on disk (persistent).

```python
from spark.graphs.checkpoint import FileCheckpointBackend

backend = FileCheckpointBackend(
    directory: str,                    # Checkpoint directory
    format: str = 'json',              # File format: 'json' or 'pickle'
    compression: bool = False,         # Compress checkpoints
    pretty_print: bool = False         # Pretty-print JSON
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `directory` | `str` | Required | Directory for checkpoint files |
| `format` | `str` | `'json'` | Serialization format |
| `compression` | `bool` | `False` | Enable gzip compression |
| `pretty_print` | `bool` | `False` | Format JSON for readability |

**Example:**

```python
backend = FileCheckpointBackend(
    directory='/var/lib/spark/checkpoints',
    format='json',
    compression=True,
    pretty_print=True
)

config = CheckpointConfig(enabled=True, backend=backend)
```

**Characteristics:**
- Persistent across restarts
- Human-readable (JSON format)
- Good performance
- Easy inspection and debugging

**Use when:**
- Production workflows requiring recovery
- Need to inspect checkpoints manually
- Single-machine deployments
- Persistent storage available

### DatabaseCheckpointBackend

Store checkpoints in a database (persistent, queryable).

```python
from spark.graphs.checkpoint import DatabaseCheckpointBackend

backend = DatabaseCheckpointBackend(
    connection_string: str,            # Database connection
    table_name: str = 'checkpoints'   # Table name
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection_string` | `str` | Required | Database connection string |
| `table_name` | `str` | `'checkpoints'` | Table for checkpoints |

**Example:**

```python
# SQLite
backend = DatabaseCheckpointBackend(
    connection_string='sqlite:///checkpoints.db'
)

# PostgreSQL
backend = DatabaseCheckpointBackend(
    connection_string='postgresql://user:pass@localhost/spark'
)

config = CheckpointConfig(enabled=True, backend=backend)
```

**Characteristics:**
- Persistent and queryable
- Supports concurrent access
- Suitable for distributed systems
- Advanced querying capabilities

**Use when:**
- Multiple graph instances
- Need to query checkpoints
- Distributed deployments
- Centralized checkpoint storage

## Checkpoint Triggers

Configure when checkpoints are created during execution.

### Iteration-Based Triggers

Checkpoint every N iterations in looping workflows:

```python
config = CheckpointConfig(
    enabled=True,
    trigger_on_iteration=5  # Checkpoint every 5 iterations
)

# Example: Loop that checkpoints periodically
class LoopNode(Node):
    async def process(self, context):
        iteration = await context.graph_state.get('iteration', 0)
        iteration += 1
        await context.graph_state.set('iteration', iteration)

        done = iteration >= 50
        return {'done': done, 'iteration': iteration}

loop = LoopNode()
exit_node = ExitNode()

loop.on(done=False) >> loop
loop.on(done=True) >> exit_node

graph = Graph(start=loop, checkpoint_config=config)
# Checkpoints created at iterations 5, 10, 15, 20, etc.
```

### Time-Based Triggers

Checkpoint every N seconds:

```python
config = CheckpointConfig(
    enabled=True,
    trigger_on_seconds=30.0  # Checkpoint every 30 seconds
)

# Useful for long-running graphs
from spark.graphs.tasks import Task, TaskType, Budget

task = Task(
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=300)
)

graph = Graph(start=my_node, checkpoint_config=config)
result = await graph.run(task)
# Checkpoints created at 30s, 60s, 90s, etc.
```

### Node-Based Triggers

Checkpoint after specific nodes complete:

```python
config = CheckpointConfig(
    enabled=True,
    trigger_on_node=['DataProcessor', 'ModelTrainer', 'ResultValidator']
)

graph = Graph(start=my_node, checkpoint_config=config)
# Checkpoint created after each specified node finishes
```

### Combined Triggers

Use multiple trigger types together:

```python
config = CheckpointConfig(
    enabled=True,
    trigger_on_iteration=10,   # Every 10 iterations
    trigger_on_seconds=60.0,   # Every 60 seconds
    trigger_on_node=['CriticalNode']  # After critical nodes
)

# Checkpoint created when ANY trigger condition is met
```

## Retention Policies

Control how many checkpoints are kept and when old ones are deleted.

### Max Checkpoints

```python
config = CheckpointConfig(
    enabled=True,
    max_checkpoints=5  # Keep only last 5 checkpoints
)

# Oldest checkpoints automatically deleted when limit exceeded
```

### Auto-Cleanup

```python
config = CheckpointConfig(
    enabled=True,
    max_checkpoints=10,
    auto_cleanup=True  # Automatically delete old checkpoints
)
```

### Manual Cleanup

```python
from spark.graphs.checkpoint import CheckpointManager

manager = CheckpointManager(backend=backend)

# List all checkpoints
checkpoints = await manager.list_checkpoints(graph_id='my_graph')

# Delete specific checkpoint
await manager.delete_checkpoint(checkpoint_id='ckpt_123')

# Delete all checkpoints for a graph
await manager.delete_all_checkpoints(graph_id='my_graph')

# Cleanup checkpoints older than date
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=7)
await manager.cleanup_before(cutoff)
```

## Recovery from Checkpoints

Restore graph execution from a saved checkpoint.

### Manual Checkpoint Creation

```python
from spark.graphs.checkpoint import GraphCheckpoint

# Create checkpoint manually
checkpoint = graph.create_checkpoint(
    checkpoint_id='manual_ckpt_001',
    metadata={'reason': 'before_risky_operation'}
)

# Save checkpoint
await checkpoint.save(backend)
```

### Restore from Checkpoint

```python
from spark.graphs.checkpoint import CheckpointManager

# Load checkpoint
manager = CheckpointManager(backend=backend)
checkpoint = await manager.load_checkpoint(checkpoint_id='ckpt_123')

# Create graph from checkpoint
graph = Graph.from_checkpoint(checkpoint)

# Continue execution from checkpoint state
result = await graph.run()
```

### Complete Recovery Example

```python
from spark.graphs import Graph
from spark.graphs.checkpoint import (
    CheckpointConfig,
    FileCheckpointBackend,
    CheckpointManager
)

# Setup checkpointing
backend = FileCheckpointBackend(directory='/var/checkpoints')
config = CheckpointConfig(
    enabled=True,
    backend=backend,
    trigger_on_iteration=10
)

graph = Graph(start=my_node, checkpoint_config=config)

try:
    # Run graph
    result = await graph.run()
except Exception as e:
    print(f"Graph failed: {e}")

    # Recover from latest checkpoint
    manager = CheckpointManager(backend=backend)
    checkpoints = await manager.list_checkpoints(graph_id=graph.graph_id)

    if checkpoints:
        # Load latest checkpoint
        latest = checkpoints[-1]
        print(f"Recovering from checkpoint: {latest.checkpoint_id}")

        checkpoint = await manager.load_checkpoint(latest.checkpoint_id)
        graph = Graph.from_checkpoint(checkpoint)

        # Retry from checkpoint
        result = await graph.run()
        print("Recovery successful")
```

## Custom Checkpoint Handlers

Implement custom logic for checkpoint creation and restoration.

### CheckpointHandler Interface

```python
from spark.graphs.checkpoint import CheckpointHandler

class CustomCheckpointHandler(CheckpointHandler):
    async def on_checkpoint_created(self, checkpoint: GraphCheckpoint):
        """Called when checkpoint is created."""
        # Custom logic: upload to cloud, send notification, etc.
        print(f"Checkpoint created: {checkpoint.checkpoint_id}")
        await upload_to_s3(checkpoint)

    async def on_checkpoint_restored(self, checkpoint: GraphCheckpoint):
        """Called when checkpoint is restored."""
        # Custom logic: log recovery, validate state, etc.
        print(f"Restored from checkpoint: {checkpoint.checkpoint_id}")
        await log_recovery(checkpoint)

    async def on_checkpoint_deleted(self, checkpoint_id: str):
        """Called when checkpoint is deleted."""
        print(f"Checkpoint deleted: {checkpoint_id}")

# Use custom handler
handler = CustomCheckpointHandler()
config = CheckpointConfig(
    enabled=True,
    backend=backend,
    handler=handler
)
```

### Example: Notification Handler

```python
class NotificationHandler(CheckpointHandler):
    def __init__(self, notification_service):
        self.notification_service = notification_service

    async def on_checkpoint_created(self, checkpoint):
        # Notify on checkpoint creation
        await self.notification_service.send(
            message=f"Checkpoint {checkpoint.checkpoint_id} created",
            channel='#operations'
        )

    async def on_checkpoint_restored(self, checkpoint):
        # Alert on recovery
        await self.notification_service.send(
            message=f"Graph recovered from {checkpoint.checkpoint_id}",
            channel='#alerts',
            severity='warning'
        )
```

## Serialization and Deserialization

Checkpoints must be serializable to storage backends.

### Serializable Types

Automatically serialized:
- Primitive types: int, float, str, bool, None
- Collections: list, dict, tuple, set
- datetime objects
- Pydantic models
- Node state objects

### Custom Serialization

For custom types, implement serialization methods:

```python
from spark.graphs.checkpoint import CheckpointSerializer

class CustomSerializer(CheckpointSerializer):
    def serialize(self, obj):
        """Convert object to JSON-serializable format."""
        if isinstance(obj, MyCustomType):
            return {
                '_type': 'MyCustomType',
                'data': obj.to_dict()
            }
        return obj

    def deserialize(self, data):
        """Reconstruct object from serialized data."""
        if isinstance(data, dict) and data.get('_type') == 'MyCustomType':
            return MyCustomType.from_dict(data['data'])
        return data

# Use custom serializer
backend = FileCheckpointBackend(
    directory='/var/checkpoints',
    serializer=CustomSerializer()
)
```

### Example: Complex State Serialization

```python
from dataclasses import dataclass
from typing import List

@dataclass
class ModelState:
    weights: List[float]
    iteration: int
    accuracy: float

    def to_dict(self):
        return {
            'weights': self.weights,
            'iteration': self.iteration,
            'accuracy': self.accuracy
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

class ModelCheckpointSerializer(CheckpointSerializer):
    def serialize(self, obj):
        if isinstance(obj, ModelState):
            return {
                '_type': 'ModelState',
                'data': obj.to_dict()
            }
        return obj

    def deserialize(self, data):
        if isinstance(data, dict) and data.get('_type') == 'ModelState':
            return ModelState.from_dict(data['data'])
        return data
```

## Testing with Checkpoints

Use checkpoints to test graphs with pre-configured states.

### Create Test Checkpoint

```python
import pytest
from spark.graphs.checkpoint import GraphCheckpoint
from datetime import datetime

@pytest.fixture
def test_checkpoint():
    """Create checkpoint for testing."""
    return GraphCheckpoint(
        checkpoint_id='test_ckpt',
        graph_id='test_graph',
        timestamp=datetime.now(),
        graph_state={'counter': 42, 'results': ['a', 'b', 'c']},
        node_states={
            'node1': {'processed': True},
            'node2': {'processed': False}
        },
        execution_metadata={'iteration': 10},
        config={'enable_state': True},
        version='1.0.0'
    )

@pytest.mark.asyncio
async def test_graph_from_checkpoint(test_checkpoint):
    """Test graph restoration from checkpoint."""
    # Create graph from checkpoint
    graph = Graph.from_checkpoint(test_checkpoint)

    # Verify state
    counter = await graph.get_state('counter')
    assert counter == 42

    # Continue execution
    result = await graph.run()
    assert result.content['success'] == True
```

### Test Recovery Scenarios

```python
@pytest.mark.asyncio
async def test_recovery_after_failure():
    """Test recovery from checkpoint after failure."""
    # Setup
    backend = InMemoryCheckpointBackend()
    config = CheckpointConfig(
        enabled=True,
        backend=backend,
        trigger_on_iteration=5
    )

    graph = Graph(start=FailingNode(), checkpoint_config=config)

    # Run until failure (checkpoint should be created)
    with pytest.raises(Exception):
        await graph.run()

    # Verify checkpoint was created
    manager = CheckpointManager(backend=backend)
    checkpoints = await manager.list_checkpoints(graph_id=graph.graph_id)
    assert len(checkpoints) > 0

    # Recover from checkpoint
    checkpoint = await manager.load_checkpoint(checkpoints[-1].checkpoint_id)
    recovered_graph = Graph.from_checkpoint(checkpoint)

    # Fix the issue and retry
    recovered_graph.start = WorkingNode()
    result = await recovered_graph.run()
    assert result.content['success'] == True
```

## Performance Considerations

### Checkpoint Creation Cost

| Backend | Time to Checkpoint | Storage Size |
|---------|-------------------|--------------|
| InMemory | ~1ms | In-memory (variable) |
| File (JSON) | ~10ms | ~10KB typical |
| File (Pickle) | ~5ms | ~5KB typical |
| Database | ~20ms | Depends on DB |

### Optimization Tips

1. **Choose appropriate trigger frequency**
   ```python
   # Too frequent: high overhead
   config = CheckpointConfig(trigger_on_iteration=1)  # Every iteration!

   # Better: reasonable frequency
   config = CheckpointConfig(trigger_on_iteration=10)
   ```

2. **Minimize state size**
   ```python
   # Bad: storing large data in state
   await context.graph_state.set('large_data', huge_list)

   # Good: store references or summaries
   await context.graph_state.set('data_ref', file_path)
   ```

3. **Use compression**
   ```python
   backend = FileCheckpointBackend(
       directory='/var/checkpoints',
       compression=True  # Enable compression
   )
   ```

4. **Cleanup old checkpoints**
   ```python
   config = CheckpointConfig(
       max_checkpoints=5,  # Keep only recent
       auto_cleanup=True
   )
   ```

## Best Practices

1. **Enable Checkpointing for Long-Running Graphs**: Protect against failures
2. **Set Reasonable Retention**: Balance storage vs. recovery options
3. **Use Persistent Backends in Production**: File or database backends
4. **Test Recovery**: Verify checkpoint restoration works
5. **Document Checkpoint Strategy**: Explain trigger choices
6. **Monitor Checkpoint Size**: Alert on unexpectedly large checkpoints
7. **Secure Checkpoints**: Protect sensitive data in checkpoints
8. **Version Checkpoints**: Use versioning for breaking changes

## Common Pitfalls

### 1. Not Enabling Persistent Backend

```python
# Bad: Using memory backend in production
config = CheckpointConfig(
    enabled=True,
    backend=InMemoryCheckpointBackend()  # Lost on crash!
)

# Good: Use persistent backend
config = CheckpointConfig(
    enabled=True,
    backend=FileCheckpointBackend(directory='/var/checkpoints')
)
```

### 2. Checkpoint Triggers Too Frequent

```python
# Bad: Checkpoint every iteration
config = CheckpointConfig(trigger_on_iteration=1)  # Too much overhead!

# Good: Reasonable frequency
config = CheckpointConfig(trigger_on_iteration=10)
```

### 3. Not Testing Recovery

```python
# Bad: Enable checkpointing but never test recovery
config = CheckpointConfig(enabled=True, backend=backend)
graph = Graph(start=my_node, checkpoint_config=config)
# Hope it works in production!

# Good: Test recovery in development
async def test_recovery():
    # Create checkpoint
    await graph.run()

    # Simulate failure and recovery
    manager = CheckpointManager(backend=backend)
    checkpoints = await manager.list_checkpoints(graph_id=graph.graph_id)
    checkpoint = await manager.load_checkpoint(checkpoints[-1].checkpoint_id)

    # Verify recovery works
    recovered = Graph.from_checkpoint(checkpoint)
    result = await recovered.run()
    assert result.content['success']
```

### 4. Large State in Checkpoints

```python
# Bad: Storing huge data in graph state
await context.graph_state.set('all_records', million_row_dataframe)
# Checkpoint will be huge and slow!

# Good: Store references
await context.graph_state.set('data_path', '/path/to/data.parquet')
```

## Troubleshooting

### Checkpoint Creation Fails

```python
# Problem: Serialization error
# Solution: Ensure all state is serializable

# Check graph state types
snapshot = graph.get_state_snapshot()
for key, value in snapshot.items():
    try:
        json.dumps(value)
    except TypeError:
        print(f"Cannot serialize {key}: {type(value)}")
```

### Recovery Fails

```python
# Problem: Incompatible checkpoint format
# Solution: Check checkpoint version

checkpoint = await manager.load_checkpoint(checkpoint_id)
if checkpoint.version != CURRENT_VERSION:
    print(f"Incompatible checkpoint version: {checkpoint.version}")
    # Implement migration logic
```

### Checkpoint Storage Full

```python
# Problem: Too many checkpoints consuming storage
# Solution: Reduce retention or increase cleanup frequency

config = CheckpointConfig(
    max_checkpoints=3,  # Reduce from 10
    auto_cleanup=True
)

# Manual cleanup
manager = CheckpointManager(backend=backend)
await manager.cleanup_before(datetime.now() - timedelta(hours=24))
```

## Next Steps

- **[Graph State](graph-state.md)**: Understand what state is checkpointed
- **[Execution Modes](execution-modes.md)**: Checkpointing in different modes
- **[Event Bus](event-bus.md)**: Monitor checkpoint events
- **[Workspace and Artifacts](workspace-artifacts.md)**: Checkpoint artifacts
