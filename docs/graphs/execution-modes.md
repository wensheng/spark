---
title: Execution Modes
parent: Graph
nav_order: 3
---
# Execution Modes

This reference covers the different execution modes available for Spark graphs and when to use each one.

## Overview

Spark supports two primary execution modes:

1. **Standard Sequential Execution**: Nodes execute one at a time in sequence (default)
2. **Long-Running Mode**: All nodes run concurrently as continuous workers

The execution mode determines how nodes are scheduled, how they communicate, and how resources are managed.

## Standard Sequential Execution

### Overview

In standard mode, the graph executes nodes sequentially following the edge conditions. Each node runs to completion before the next node starts.

### Characteristics

- **Sequential**: One node at a time
- **Synchronous Flow**: Clear execution path from start to end
- **Direct Data Passing**: Output of one node becomes input to next
- **Low Overhead**: Minimal scheduling and coordination cost
- **Deterministic**: Same inputs produce same execution path
- **Bounded Execution**: Finite execution time

### When to Use

Standard mode is ideal for:
- ETL pipelines and data processing workflows
- Request-response patterns
- Sequential business logic
- Workflows with clear start and end
- Batch processing
- Simple agent interactions

### Configuration

Standard mode is the default. No special configuration needed:

```python
from spark.graphs import Graph
from spark.graphs.tasks import Task

# Default: standard mode
graph = Graph(start=my_node)
result = await graph.run()

# Explicit task type
task = Task(inputs=NodeMessage(content={}))  # TaskType.STANDARD is default
result = await graph.run(task)
```

### Example: Data Processing Pipeline

```python
from spark.nodes import Node
from spark.graphs import Graph

class ExtractNode(Node):
    async def process(self, context):
        # Extract data from source
        data = extract_from_database()
        return {'data': data}

class TransformNode(Node):
    async def process(self, context):
        # Transform data
        data = context.inputs.content.get('data', [])
        transformed = [transform(item) for item in data]
        return {'data': transformed}

class LoadNode(Node):
    async def process(self, context):
        # Load data to destination
        data = context.inputs.content.get('data', [])
        load_to_warehouse(data)
        return {'loaded': len(data)}

# Build pipeline
extract = ExtractNode()
transform = TransformNode()
load = LoadNode()

extract >> transform >> load

graph = Graph(start=extract)

# Execute sequentially
result = await graph.run()
print(f"Loaded {result.content['loaded']} records")
```

### Execution Flow

```
Start Node
    |
    v
Process Node 1
    |
    v
Edge Evaluation
    |
    v
Process Node 2
    |
    v
Edge Evaluation
    |
    v
Process Node 3
    |
    v
End (Return Result)
```

### Performance Characteristics

| Metric | Value |
|--------|-------|
| Startup Overhead | Very Low (~1ms) |
| Per-Node Overhead | Minimal (~0.1ms) |
| Memory Usage | Low (single active node) |
| Concurrency | None (sequential) |
| Suitable For | < 1000 nodes typical |

## Long-Running Mode

### Overview

In long-running mode, all nodes start simultaneously and run as continuous workers. Nodes communicate via message passing through channels and mailboxes.

### Characteristics

- **Concurrent**: All nodes run simultaneously
- **Asynchronous Communication**: Message-based via channels
- **Continuous Processing**: Nodes process messages in loop
- **Higher Overhead**: Channel management and coordination
- **Event-Driven**: Nodes react to incoming messages
- **Unbounded Execution**: Runs until explicitly stopped or budget exhausted

### When to Use

Long-running mode is ideal for:
- Autonomous agents with continuous operation
- Reactive systems and event processing
- Multi-agent coordination
- Daemon-like workflows
- Real-time stream processing
- Systems requiring concurrent node execution

### Configuration

Use `TaskType.LONG_RUNNING` to enable long-running mode:

```python
from spark.graphs import Graph
from spark.graphs.tasks import Task, TaskType, Budget
from spark.nodes.types import NodeMessage

# Configure long-running task
task = Task(
    inputs=NodeMessage(content={'query': 'start'}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=60)  # Run for up to 60 seconds
)

graph = Graph(start=my_node)
result = await graph.run(task)
```

### Example: Autonomous Agent

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.graphs.tasks import Task, TaskType, Budget
from spark.nodes.types import NodeMessage

class SensorNode(Node):
    async def process(self, context):
        # Continuously read sensor data
        while True:
            data = read_sensor()
            return {'sensor_data': data}

class AnalyzerNode(Node):
    async def process(self, context):
        # Analyze incoming sensor data
        sensor_data = context.inputs.content.get('sensor_data')
        if sensor_data is None:
            return {'continue': True}

        anomaly = detect_anomaly(sensor_data)
        return {'anomaly': anomaly, 'data': sensor_data}

class ActuatorNode(Node):
    async def process(self, context):
        # React to anomalies
        anomaly = context.inputs.content.get('anomaly', False)
        if anomaly:
            trigger_alert(context.inputs.content.get('data'))
        return {'continue': True}

# Build agent
sensor = SensorNode()
analyzer = AnalyzerNode()
actuator = ActuatorNode()

sensor >> analyzer
analyzer.on(anomaly=True) >> actuator
actuator >> sensor  # Loop back

# Run in long-running mode
task = Task(
    inputs=NodeMessage(content={}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=300)  # Run for 5 minutes
)

graph = Graph(start=sensor)
result = await graph.run(task)
```

### Channels and Mailboxes

In long-running mode, nodes communicate via channels:

- **Mailbox**: Each node has a mailbox (asyncio.Queue) for receiving messages
- **Channels**: Connect node mailboxes for message passing
- **ChannelMessage**: Envelope containing payload and metadata

```python
from spark.nodes.channels import ChannelMessage

# Nodes receive messages via mailbox
class WorkerNode(Node):
    async def process(self, context):
        # Process message from mailbox
        data = context.inputs.content
        result = process_data(data)

        # Return output (sent to downstream mailboxes)
        return {'result': result}
```

### Execution Flow

```
All Nodes Start Concurrently
        |
        v
    +--------+--------+--------+
    |        |        |        |
    v        v        v        v
  Node 1   Node 2   Node 3   Node 4
   (loop)   (loop)   (loop)   (loop)
    |        |        |        |
    v        v        v        v
 Mailbox  Mailbox  Mailbox  Mailbox
    ^        ^        ^        ^
    |        |        |        |
    +-- Message Passing ------+
```

### Graceful Shutdown

Long-running graphs support graceful shutdown:

```python
from spark.nodes.channels import ChannelMessage

# Shutdown signal via ChannelMessage
shutdown_msg = ChannelMessage(
    payload={},
    shutdown=True  # Signal shutdown
)

# Nodes check for shutdown
class WorkerNode(Node):
    async def process(self, context):
        # Check if shutdown requested
        if context.inputs.metadata.get('shutdown', False):
            # Cleanup and exit
            return {'shutdown': True}

        # Normal processing
        return {'continue': True}
```

### Budget Enforcement

Budgets control long-running execution:

```python
from spark.graphs.tasks import Budget

# Time budget
budget = Budget(max_seconds=120)  # Run for max 2 minutes

# Token budget (for LLM-heavy workflows)
budget = Budget(max_tokens=100000)  # Max 100k tokens

# Combined budgets
budget = Budget(max_seconds=300, max_tokens=50000)

task = Task(
    type=TaskType.LONG_RUNNING,
    budget=budget
)
```

**Budget Behavior:**
- `max_seconds`: Graph stops when time limit reached
- `max_tokens`: Tracked by nodes; enforcement is node-dependent
- Shutdown is graceful (nodes finish current iteration)

### Performance Characteristics

| Metric | Value |
|--------|-------|
| Startup Overhead | Higher (~10-50ms) |
| Per-Message Overhead | Low (~0.5ms) |
| Memory Usage | Higher (all nodes active) |
| Concurrency | Full (all nodes concurrent) |
| Suitable For | Continuous operation |

## TaskType Configuration

### TaskType Enum

```python
from spark.graphs.tasks import TaskType

# Standard sequential execution
TaskType.STANDARD

# Long-running concurrent execution
TaskType.LONG_RUNNING
```

### Task Class

```python
from spark.graphs.tasks import Task, TaskType, Budget
from spark.nodes.types import NodeMessage

task = Task(
    inputs: NodeMessage,                      # Input data
    type: TaskType = TaskType.STANDARD,       # Execution mode
    budget: Optional[Budget] = None           # Resource limits
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inputs` | `NodeMessage` | Required | Input data for start node |
| `type` | `TaskType` | `STANDARD` | Execution mode |
| `budget` | `Budget` | `None` | Resource constraints |

### Specifying Task Type

```python
# Standard mode (explicit)
task = Task(
    inputs=NodeMessage(content={'data': 'value'}),
    type=TaskType.STANDARD
)
result = await graph.run(task)

# Long-running mode
task = Task(
    inputs=NodeMessage(content={'query': 'start'}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=60)
)
result = await graph.run(task)
```

## Budget Constraints

### Budget Class

```python
from spark.graphs.tasks import Budget

budget = Budget(
    max_seconds: Optional[float] = None,   # Maximum execution time
    max_tokens: Optional[int] = None       # Maximum LLM tokens
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_seconds` | `float` | `None` | Maximum execution time in seconds |
| `max_tokens` | `int` | `None` | Maximum total LLM tokens to consume |

### Time Budget

```python
# Standard mode with timeout
budget = Budget(max_seconds=30)
task = Task(inputs=NodeMessage(content={}), budget=budget)

try:
    result = await graph.run(task)
except TimeoutError:
    print("Execution exceeded time budget")
```

### Token Budget

```python
# Long-running agent with token limit
budget = Budget(max_tokens=50000)
task = Task(
    inputs=NodeMessage(content={'query': 'analyze data'}),
    type=TaskType.LONG_RUNNING,
    budget=budget
)

result = await graph.run(task)

# Check token usage (node-dependent tracking)
tokens_used = result.metadata.get('tokens_used', 0)
print(f"Used {tokens_used} tokens")
```

### Combined Budgets

```python
# Both time and token limits
budget = Budget(max_seconds=120, max_tokens=25000)

task = Task(
    inputs=NodeMessage(content={}),
    type=TaskType.LONG_RUNNING,
    budget=budget
)

result = await graph.run(task)
```

## Mode Selection Guidelines

### Decision Matrix

| Requirement | Standard | Long-Running |
|-------------|----------|--------------|
| Sequential workflow | Yes | No |
| Request-response | Yes | No |
| Clear start/end | Yes | Maybe |
| Concurrent nodes | No | Yes |
| Continuous operation | No | Yes |
| Event-driven | No | Yes |
| Multiple agents | No | Yes |
| Stream processing | No | Yes |
| Low latency | Yes | Maybe |
| Low overhead | Yes | No |

### Use Standard Mode When

1. Workflow has clear sequential steps
2. Each step depends on previous step's output
3. Execution time is bounded
4. Low latency is critical
5. Workflow completes and returns result
6. No need for concurrent node execution
7. Simple data processing pipeline

### Use Long-Running Mode When

1. Nodes need to run continuously
2. Nodes react to events/messages
3. Multiple agents coordinate
4. System is reactive or event-driven
5. No clear end point (runs until stopped)
6. Concurrent node execution required
7. Stream processing or real-time systems

### Example Scenarios

**Standard Mode:**
- User uploads file → validate → transform → store → return URL
- API request → fetch data → process → format → return response
- Batch job → read records → transform each → write results
- Form submission → validate → save to DB → send email → show confirmation

**Long-Running Mode:**
- Monitoring system continuously checks metrics → alerts on anomalies
- Chat agent continuously listens → processes messages → responds
- Multi-agent system where agents coordinate and communicate
- Real-time data pipeline processing stream of events

## Performance Comparison

### Latency

| Scenario | Standard | Long-Running |
|----------|----------|--------------|
| Simple 3-node flow | ~1ms | ~10ms |
| 10-node pipeline | ~5ms | ~50ms |
| Complex branching | ~10ms | ~100ms |

### Throughput

| Metric | Standard | Long-Running |
|--------|----------|--------------|
| Single execution | Fast | Slower startup |
| Repeated executions | Very fast | High throughput |
| Concurrent operations | Limited | Excellent |

### Resource Usage

| Resource | Standard | Long-Running |
|----------|----------|--------------|
| Memory | Low (single active node) | Higher (all nodes active) |
| CPU | Efficient (sequential) | Higher (concurrent) |
| Context switches | Minimal | Many |

## Advanced Patterns

### Hybrid Mode

Combine both modes using subgraphs:

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.graphs.tasks import Task, TaskType

class SubgraphNode(Node):
    def __init__(self):
        super().__init__()
        # Inner graph runs in standard mode
        self.inner_graph = Graph(start=ProcessingNode())

    async def process(self, context):
        # Run inner graph sequentially
        result = await self.inner_graph.run(
            initial_inputs=context.inputs.content
        )
        return result.content

# Outer graph runs in long-running mode
outer_graph = Graph(start=SubgraphNode())

task = Task(
    inputs=NodeMessage(content={}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=60)
)

result = await outer_graph.run(task)
```

### Conditional Mode Switching

```python
class AdaptiveNode(Node):
    async def process(self, context):
        workload = context.inputs.content.get('workload_size', 0)

        # Small workload: return simple result
        if workload < 100:
            return {'result': 'processed small workload'}

        # Large workload: suggest long-running mode
        return {
            'result': 'requires long-running mode',
            'recommend_mode': 'long_running'
        }
```

## Best Practices

### Standard Mode

1. **Keep Pipelines Focused**: Limit to reasonable node count (< 100 typical)
2. **Clear Flow**: Ensure linear or simple branching flow
3. **Fast Nodes**: Each node should complete quickly (< 1s typical)
4. **Stateless Preferred**: Minimize shared state dependencies
5. **Error Handling**: Handle errors at appropriate granularity

### Long-Running Mode

1. **Set Budgets**: Always set `max_seconds` to prevent runaway execution
2. **Graceful Shutdown**: Handle shutdown signals properly
3. **Message Size**: Keep messages small for efficiency
4. **Backpressure**: Consider mailbox queue sizes
5. **Resource Limits**: Monitor memory and connection usage

### General

1. **Start Standard**: Default to standard mode unless you need concurrency
2. **Profile First**: Measure before optimizing mode selection
3. **Test Both Modes**: Test critical workflows in both modes
4. **Document Choice**: Document why you chose a specific mode
5. **Monitor Production**: Track performance metrics in production

## Troubleshooting

### Standard Mode Issues

**Problem: Graph execution seems slow**
```python
# Check: Are nodes doing expensive operations?
# Solution: Optimize node processing or parallelize with subgraphs

# Check: Many nodes in sequence?
# Solution: Consider breaking into smaller graphs or batching
```

**Problem: Need concurrent processing**
```python
# Wrong: Using standard mode for concurrent needs
task = Task(type=TaskType.STANDARD)

# Right: Switch to long-running mode
task = Task(type=TaskType.LONG_RUNNING, budget=Budget(max_seconds=60))
```

### Long-Running Mode Issues

**Problem: High memory usage**
```python
# Check: All nodes stay in memory
# Solution: Reduce node count or optimize node memory usage

# Check: Large messages in mailboxes
# Solution: Keep messages small, process and discard
```

**Problem: Doesn't stop**
```python
# Wrong: No budget set
task = Task(type=TaskType.LONG_RUNNING)  # Runs forever!

# Right: Set time budget
task = Task(
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=120)
)
```

**Problem: Nodes not processing**
```python
# Check: Are messages being sent?
# Solution: Verify edge conditions and message flow

# Check: Deadlock in message passing?
# Solution: Review node dependencies and cycles
```

## Migration Guide

### From Standard to Long-Running

```python
# Before: Standard mode
class MyNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data')
        return {'result': process_data(data)}

graph = Graph(start=MyNode())
result = await graph.run()

# After: Long-running mode
class MyNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data')
        return {'result': process_data(data)}

task = Task(
    inputs=NodeMessage(content={'data': 'value'}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=60)
)

graph = Graph(start=MyNode())
result = await graph.run(task)
```

### From Long-Running to Standard

```python
# Before: Long-running (continuous)
task = Task(
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=300)
)
result = await graph.run(task)

# After: Standard (one-shot)
result = await graph.run(initial_inputs={'data': 'value'})
```

## Next Steps

- **[Graph State](graph-state.md)**: Learn about state in different execution modes
- **[Event Bus](event-bus.md)**: Monitor execution in both modes
- **[Fundamentals](fundamentals.md)**: Review basic graph concepts
- **[Checkpointing](checkpointing.md)**: Checkpoint long-running graphs
