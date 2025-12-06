---
title: Graph
nav_order: 5
---
# Graph Fundamentals

This reference covers the core concepts and APIs for creating and running graphs in Spark ADK.

## Overview

A **Graph** in Spark is a workflow composed of connected nodes. Graphs orchestrate node execution, manage data flow between nodes, and provide lifecycle management. The graph system supports both sequential execution for simple workflows and concurrent execution for long-running agents.

## Creating Graphs

### Basic Graph Creation

The simplest way to create a graph is to provide a start node:

```python
from spark.graphs import Graph
from spark.nodes import Node

class HelloNode(Node):
    async def process(self, context):
        print("Hello from graph!")
        return {'message': 'Done'}

# Create graph with start node
start_node = HelloNode()
graph = Graph(start=start_node)
```

### Graph Constructor Parameters

```python
Graph(
    start: BaseNode,                          # Starting node for graph execution
    initial_state: Optional[dict] = None,     # Initial graph state
    enable_graph_state: bool = True,          # Enable/disable graph state
    telemetry_config: Optional[TelemetryConfig] = None,  # Telemetry configuration
    event_bus: Optional[GraphEventBus] = None  # Custom event bus
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start` | `BaseNode` | Required | Entry point node for graph execution |
| `initial_state` | `dict` | `None` | Initial values for graph state |
| `enable_graph_state` | `bool` | `True` | Whether to enable shared graph state |
| `telemetry_config` | `TelemetryConfig` | `None` | Configuration for telemetry collection |
| `event_bus` | `GraphEventBus` | `None` | Custom event bus instance |

### Example with Configuration

```python
from spark.graphs import Graph
from spark.telemetry import TelemetryConfig

# Create graph with telemetry and initial state
graph = Graph(
    start=my_node,
    initial_state={'counter': 0, 'results': []},
    telemetry_config=TelemetryConfig.create_sqlite(
        db_path="telemetry.db",
        sampling_rate=1.0
    )
)
```

## Graph Discovery

Spark uses **automatic graph discovery** via breadth-first search (BFS) to find all reachable nodes from the start node. This happens automatically during graph preparation.

### How Discovery Works

1. Graph starts at the `start` node
2. BFS traversal follows all edges from each node
3. All reachable nodes are registered with the graph
4. Unreachable nodes are not included in execution

```python
from spark.nodes import Node

class NodeA(Node):
    async def process(self, context):
        return {'next': 'b'}

class NodeB(Node):
    async def process(self, context):
        return {'next': 'c'}

class NodeC(Node):
    async def process(self, context):
        return {'done': True}

# Connect nodes
node_a = NodeA()
node_b = NodeB()
node_c = NodeC()

node_a >> node_b >> node_c

# Graph automatically discovers all three nodes
graph = Graph(start=node_a)
# Discovered: node_a, node_b, node_c
```

### Unreachable Nodes

Nodes not connected to the start node are not discovered:

```python
node_a = NodeA()
node_b = NodeB()
orphan = NodeC()  # Not connected to node_a

node_a >> node_b

graph = Graph(start=node_a)
# Discovered: node_a, node_b
# Not discovered: orphan
```

## Node Connections and Edges

Nodes are connected via **edges**, which define the execution flow between nodes.

### Basic Connection Syntax

The `>>` operator creates an unconditional edge:

```python
node_a >> node_b  # Always go from node_a to node_b
```

### Chaining Connections

```python
node_a >> node_b >> node_c >> node_d
# Equivalent to:
# node_a >> node_b
# node_b >> node_c
# node_c >> node_d
```

### Conditional Edges

Use `on()` for simple conditions or `goto()` for complex conditions:

```python
# Simple condition: check output key
node_a.on(success=True) >> node_b
node_a.on(success=False) >> error_handler

# Complex condition with lambda
from spark.nodes.base import EdgeCondition

node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: n.outputs.content.get('score', 0) > 0.8)
)
```

See [Edge Conditions and Flow Control](edges.md) for complete edge documentation.

## Running Graphs

### Basic Execution

The `run()` method executes the graph:

```python
# Async execution
result = await graph.run()

# Access result
print(result.content)  # Final node's output
```

### Run Method Signature

```python
async def run(
    self,
    task: Optional[Task] = None,
    initial_inputs: Optional[dict] = None
) -> NodeMessage
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | `Task` | `None` | Task with inputs and budget constraints |
| `initial_inputs` | `dict` | `None` | Input data for the start node |

**Returns:** `NodeMessage` containing the final node's outputs.

### Using Initial Inputs

```python
# Pass inputs directly
result = await graph.run(initial_inputs={'query': 'Hello'})

# Or use Task
from spark.graphs.tasks import Task
from spark.nodes.types import NodeMessage

task = Task(inputs=NodeMessage(content={'query': 'Hello'}))
result = await graph.run(task)
```

### Complete Example

```python
from spark.graphs import Graph
from spark.nodes import Node
from spark.utils import arun

class InputNode(Node):
    async def process(self, context):
        user_input = context.inputs.content.get('query', '')
        return {'text': user_input.upper()}

class OutputNode(Node):
    async def process(self, context):
        text = context.inputs.content.get('text', '')
        return {'result': f"Processed: {text}"}

# Build graph
input_node = InputNode()
output_node = OutputNode()
input_node >> output_node

graph = Graph(start=input_node)

# Run graph
async def main():
    result = await graph.run(initial_inputs={'query': 'hello world'})
    print(result.content)  # {'result': 'Processed: HELLO WORLD'}

arun(main())
```

## Task Inputs and Budgets

The `Task` class provides structured input with execution constraints.

### Task Structure

```python
from spark.graphs.tasks import Task, TaskType, Budget
from spark.nodes.types import NodeMessage

task = Task(
    inputs=NodeMessage(content={'data': 'value'}),
    type=TaskType.STANDARD,  # or TaskType.LONG_RUNNING
    budget=Budget(max_seconds=60, max_tokens=10000)
)
```

### Task Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inputs` | `NodeMessage` | Required | Input data for the start node |
| `type` | `TaskType` | `STANDARD` | Execution mode (STANDARD or LONG_RUNNING) |
| `budget` | `Budget` | `None` | Resource constraints for execution |

### Budget Configuration

```python
from spark.graphs.tasks import Budget

budget = Budget(
    max_seconds=120,   # Maximum execution time in seconds
    max_tokens=50000   # Maximum LLM tokens to consume
)

task = Task(
    inputs=NodeMessage(content={}),
    budget=budget
)
```

**Budget Enforcement:**
- `max_seconds`: Graph execution stops after timeout (raises `TimeoutError`)
- `max_tokens`: Tracked by nodes; enforcement depends on node implementation

### TaskType Options

| Type | Description | Use Case |
|------|-------------|----------|
| `TaskType.STANDARD` | Sequential node execution | Standard workflows, ETL pipelines |
| `TaskType.LONG_RUNNING` | Concurrent node execution | Agents, daemons, continuous processing |

See [Execution Modes](execution-modes.md) for detailed mode documentation.

### Example with Budget

```python
from spark.graphs import Graph
from spark.graphs.tasks import Task, Budget
from spark.nodes.types import NodeMessage

task = Task(
    inputs=NodeMessage(content={'query': 'process this'}),
    budget=Budget(max_seconds=30, max_tokens=5000)
)

try:
    result = await graph.run(task)
    print("Success:", result.content)
except TimeoutError:
    print("Graph execution exceeded budget")
```

## Graph Results and Outputs

### NodeMessage Result

The `run()` method returns a `NodeMessage` containing the final node's outputs:

```python
result = await graph.run()

# Access content
output_data = result.content  # dict with node outputs

# Access metadata
print(result.metadata)  # Execution metadata
print(result.timestamp)  # When the message was created
```

### NodeMessage Structure

```python
class NodeMessage:
    content: dict              # Node output data
    metadata: dict             # Additional metadata
    timestamp: datetime        # Creation timestamp
    source_node: Optional[str] # Node that produced this message
```

### Extracting Specific Outputs

```python
result = await graph.run()

# Get specific field
status = result.content.get('status')
data = result.content.get('data', [])

# Check for success
if result.content.get('success', False):
    print("Graph completed successfully")
```

### Example: Multi-Step Processing

```python
class Step1(Node):
    async def process(self, context):
        return {'step1_result': 'data from step 1'}

class Step2(Node):
    async def process(self, context):
        prev_result = context.inputs.content.get('step1_result')
        return {'step2_result': f"processed {prev_result}"}

class Step3(Node):
    async def process(self, context):
        prev_result = context.inputs.content.get('step2_result')
        return {
            'final_result': prev_result.upper(),
            'success': True,
            'steps_completed': 3
        }

# Build and run
step1 = Step1()
step2 = Step2()
step3 = Step3()

step1 >> step2 >> step3

graph = Graph(start=step1)
result = await graph.run()

# Access final outputs
print(result.content['final_result'])
print(result.content['steps_completed'])  # 3
```

## Graph Lifecycle and Cleanup

### Graph Lifecycle Phases

1. **Initialization**: Graph object created, start node assigned
2. **Preparation**: Auto-discovery runs, nodes are registered
3. **Execution**: Nodes execute according to edges
4. **Completion**: Final node finishes, result returned
5. **Cleanup**: Resources released (optional)

### Manual Preparation

Graphs are automatically prepared on first `run()`. You can manually trigger preparation:

```python
graph = Graph(start=my_node)

# Manual preparation (optional)
await graph.prepare()

# Now run
result = await graph.run()
```

### Resetting Graph State

Reset graph state between runs:

```python
# Run graph
result1 = await graph.run()

# Reset state to initial values
graph.reset_state({'counter': 0})

# Run again with fresh state
result2 = await graph.run()
```

### Accessing Graph State After Execution

```python
# Run graph
result = await graph.run()

# Access graph state
counter = await graph.get_state('counter')
snapshot = graph.get_state_snapshot()

print(f"Counter: {counter}")
print(f"Full state: {snapshot}")
```

### Resource Cleanup

For long-running graphs, ensure proper cleanup:

```python
from spark.graphs.tasks import TaskType, Task

task = Task(type=TaskType.LONG_RUNNING)

try:
    result = await graph.run(task)
finally:
    # Cleanup is automatic, but you can perform additional cleanup
    # Close external connections, flush logs, etc.
    pass
```

### Event Bus Cleanup

If using custom event handlers, unsubscribe when done:

```python
def handler(event):
    print(f"Event: {event}")

# Subscribe
graph.event_bus.subscribe('node_finished', handler)

# Run graph
result = await graph.run()

# Unsubscribe (if needed)
# Note: Event bus cleanup is automatic on graph destruction
```

## Multiple Executions

Graphs can be executed multiple times:

```python
graph = Graph(start=my_node)

# First execution
result1 = await graph.run(initial_inputs={'run': 1})

# Second execution (state persists unless reset)
result2 = await graph.run(initial_inputs={'run': 2})

# Reset between runs if needed
graph.reset_state({})
result3 = await graph.run(initial_inputs={'run': 3})
```

## Error Handling

Handle errors during graph execution:

```python
from spark.graphs.graph import GraphExecutionError

try:
    result = await graph.run()
except TimeoutError:
    print("Graph execution timed out")
except GraphExecutionError as e:
    print(f"Graph execution failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Considerations

### Graph Size
- Auto-discovery has O(V + E) complexity (vertices + edges)
- Large graphs (1000+ nodes) may have preparation overhead
- Consider splitting large workflows into subgraphs

### State Access
- Graph state access has minimal overhead in sequential mode
- Concurrent mode uses locks (small overhead)
- Use transactions for atomic multi-operation updates

### Telemetry
- Telemetry adds minimal overhead (~1-5% typical)
- Use sampling (`sampling_rate < 1.0`) for high-throughput graphs
- Disable telemetry in benchmarks if needed

### Execution Mode Selection
- Use `STANDARD` for sequential workflows (lowest overhead)
- Use `LONG_RUNNING` for concurrent agents (higher overhead)
- See [Execution Modes](execution-modes.md) for detailed guidance

## Best Practices

1. **Single Responsibility**: Keep graphs focused on one workflow
2. **Clear Start Node**: Choose a clear entry point for the graph
3. **State Management**: Use graph state for shared data, node state for local data
4. **Error Boundaries**: Handle errors at appropriate levels
5. **Resource Budgets**: Set reasonable budgets for time and token limits
6. **Telemetry**: Enable telemetry for production graphs
7. **Testing**: Test graphs with various inputs and edge cases

## Next Steps

- **[Edge Conditions](edges.md)**: Learn about conditional flow control
- **[Graph State](graph-state.md)**: Deep dive into shared state management
- **[Execution Modes](execution-modes.md)**: Understand sequential vs. concurrent execution
- **[Event Bus](event-bus.md)**: Work with graph events and observability
- **[Subgraphs](subgraphs.md)**: Compose complex workflows from smaller graphs
