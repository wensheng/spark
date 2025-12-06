# Core Classes

This document provides comprehensive API reference for Spark's core classes. These classes form the foundation of the framework and are essential for building agentic workflows.

## Table of Contents

- [BaseNode](#basenode)
- [Node](#node)
- [BaseGraph](#basegraph)
- [Graph](#graph)
- [Task](#task)
- [ExecutionContext](#executioncontext)
- [NodeState](#nodestate)
- [GraphState](#graphstate)

---

## BaseNode

**Module**: `spark.nodes.base`

**Inheritance**: `ABC` (Abstract Base Class)

### Overview

`BaseNode` is the abstract base class for all nodes in the Spark framework. A node represents an actor in the Actor Model—a single unit of computation that can process inputs, maintain state, and connect to other nodes via edges.

### Class Signature

```python
class BaseNode(ABC):
    """
    The base class for all nodes in the Spark framework.
    A node represents an actor in the Spark graph.
    It is a single unit of computation.
    """
```

### Constructor

```python
def __init__(self, **kwargs) -> None
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | `str` | `uuid4().hex` | Unique identifier for the node |
| `description` | `str` | `''` | Human-readable description |
| `mailbox` | `BaseChannel` | `InMemoryChannel()` | Channel for receiving messages in long-running mode |
| `policy_engine` | `PolicyEngine \| None` | `None` | Optional policy engine for governance |

### Key Properties

#### `state: NodeState`
Returns the current state of the node, including execution context snapshot, processing flag, pending inputs queue, and process count.

```python
@property
def state(self) -> NodeState
```

#### `outputs: NodeMessage`
The outputs produced by the node after processing, used as inputs for successor nodes.

#### `edges: list[Edge]`
List of edges connecting this node to successor nodes.

#### `event_bus: GraphEventBus | None`
Reference to the graph-level event bus for pub/sub communication.

#### `mailbox: BaseChannel`
Channel for receiving messages when running in long-running mode.

### Abstract Methods

#### `process()`
The core processing logic that must be implemented by all subclasses.

```python
@abstractmethod
async def process(self, context: ExecutionContext) -> Any
```

**Parameters**:
- `context`: ExecutionContext containing inputs, state, metadata, and graph state

**Returns**: Any value (typically a dict or None). If a dict is returned, it becomes the node's outputs.

**Example**:
```python
class MyNode(BaseNode):
    async def process(self, context):
        data = context.inputs.content
        result = transform(data)
        return {'result': result, 'status': 'success'}
```

### Key Methods

#### `do()`
Execute the node's complete processing lifecycle including hooks.

```python
async def do(self, inputs: NodeMessage | dict | list | None = None) -> NodeMessage
```

**Parameters**:
- `inputs`: Input data for the node (converted to NodeMessage internally)

**Returns**: NodeMessage containing the processed outputs

**Lifecycle**:
1. Prepare execution context
2. Run pre-process hooks
3. Execute `process()` method
4. Collect human input if policy configured
5. Run post-process hooks
6. Record context snapshot

#### `goto()`
Create an edge to another node with optional condition.

```python
def goto(
    self,
    next_node: BaseNode,
    condition: EdgeCondition | str | None = None
) -> Edge
```

**Parameters**:
- `next_node`: Target node to connect to
- `condition`: Optional edge condition (EdgeCondition instance or expression string)

**Returns**: Edge connecting this node to the target

**Example**:
```python
# Unconditional edge
node1.goto(node2)

# Conditional edge with expression
node1.goto(node2, "$.outputs.score > 0.5")

# Conditional edge with EdgeCondition
node1.goto(node2, EdgeCondition(expr="$.outputs.ready == true"))
```

**Note**: Lambda/callable conditions are NOT supported for spec compatibility.

#### `on()`
Create a conditional edge without specifying the target node yet (fluent API).

```python
def on(
    self,
    condition: EdgeCondition | str | None = None,
    expr: str | None = None,
    priority: int = 0,
    **equals: Any
) -> Edge
```

**Parameters**:
- `condition`: EdgeCondition instance or expression string
- `expr`: Expression string (alternative to condition parameter)
- `priority`: Edge priority (higher values evaluated first)
- `**equals`: Key-value pairs for equality-based conditions

**Returns**: Edge with condition set but no target node

**Example**:
```python
# Expression-based condition
node1.on(expr="$.outputs.action == 'search'") >> search_node

# Equality shorthand
node1.on(action='search') >> search_node

# Priority
node1.on(priority=10, action='critical') >> critical_handler
```

#### `on_timer()`
Create a delayed edge that fires after a specified duration.

```python
def on_timer(
    self,
    seconds: float,
    *,
    condition: EdgeCondition | str | None = None,
    expr: str | None = None,
    priority: int = 0,
    **equals: Any
) -> Edge
```

**Parameters**:
- `seconds`: Delay in seconds before edge activation
- `condition`: Optional additional condition
- `expr`: Optional expression string
- `priority`: Edge priority
- `**equals`: Optional equality conditions

**Returns**: Edge with delay configured

**Example**:
```python
# Delay 5 seconds then activate
node1.on_timer(5.0) >> delayed_node

# Conditional delayed activation
node1.on_timer(3.0, expr="$.outputs.retry == true") >> retry_node
```

#### `on_event()`
Create an event-driven edge that activates when an event is published.

```python
def on_event(
    self,
    topic: str,
    *,
    event_filter: EdgeCondition | str | None = None,
    expr: str | None = None,
    priority: int = 0,
    **equals: Any
) -> Edge
```

**Parameters**:
- `topic`: Event topic to subscribe to
- `event_filter`: Optional filter condition for events
- `expr`: Optional filter expression
- `priority`: Edge priority
- `**equals`: Optional equality filters

**Returns**: Event-driven edge

**Example**:
```python
# Subscribe to all events on topic
node1.on_event("data.updated") >> handler_node

# Filtered event subscription
node1.on_event("user.action", action="login") >> login_handler
```

#### `get_next_nodes()`
Get list of successor nodes based on active edge conditions.

```python
def get_next_nodes(self) -> list[BaseNode]
```

**Returns**: List of nodes that should execute next based on current outputs

#### `receive_from_parent()`
Receive input from a parent node and queue it for processing.

```python
async def receive_from_parent(self, parent: BaseNode) -> bool
```

**Parameters**:
- `parent`: The parent node sending outputs

**Returns**: True if input was received and node should be scheduled

#### `enqueue_input()`
Add a payload to the node's pending input queue.

```python
def enqueue_input(
    self,
    payload: NodeMessage | dict | list | None
) -> None
```

**Parameters**:
- `payload`: Input data to queue (converted to NodeMessage)

#### `pop_ready_input()`
Retrieve the next queued input for processing.

```python
def pop_ready_input(self) -> Any | None
```

**Returns**: Next pending input or None if queue is empty

#### `attach_event_bus()`
Attach a graph-level event bus for pub/sub communication.

```python
def attach_event_bus(self, event_bus: GraphEventBus) -> None
```

#### `publish_event()`
Publish an event to the event bus.

```python
async def publish_event(
    self,
    topic: str,
    payload: Any,
    *,
    metadata: dict[str, Any] | None = None
) -> None
```

**Parameters**:
- `topic`: Event topic
- `payload`: Event payload
- `metadata`: Optional event metadata

#### `subscribe_event()`
Subscribe to events on a topic.

```python
async def subscribe_event(self, topic: str) -> AsyncIterator
```

**Parameters**:
- `topic`: Topic to subscribe to

**Returns**: Async iterator yielding events

### Lifecycle Hooks

#### `pre_process_hooks: list[Callable]`
List of functions called before `process()` executes. Each hook receives the ExecutionContext.

#### `post_process_hooks: list[Callable]`
List of functions called after `process()` completes. Each hook receives the ExecutionContext.

**Example**:
```python
def logging_hook(context):
    print(f"Processing: {context.inputs.content}")

node.pre_process_hooks.append(logging_hook)
```

### Operator Overloading

#### `>>` (Right Shift)
Chain nodes together using the `>>` operator.

```python
def __rshift__(self, right: BaseNode | Chain) -> Chain
```

**Example**:
```python
node1 >> node2 >> node3  # Creates a chain
```

### Related Classes

- [Node](#node) - Concrete implementation with capabilities
- [Edge](#edge) - Represents connections between nodes
- [EdgeCondition](#edgecondition) - Defines conditional routing logic
- [ExecutionContext](#executioncontext) - Context passed to process() methods

### Notes

- BaseNode uses the Actor Model pattern for concurrency
- All processing is async internally (sync `process()` methods are automatically wrapped)
- Node state persists across executions if configured via `keep_in_state`
- Nodes can be reused across multiple graph executions
- The `_process_no_arg` flag allows `process()` methods with no parameters (convenience feature)

---

## Node

**Module**: `spark.nodes.nodes`

**Inheritance**: `BaseNode`

### Overview

`Node` is the concrete implementation of BaseNode that adds configuration support, capability integration, and continuous execution via the `go()` method. This is the primary class for creating custom processing nodes.

### Class Signature

```python
class Node(BaseNode):
    """
    A Node is an actor in the Actor Model.
    The differences between Node and BaseNode are:
      1. Node can have a config object.
      2. Node has capabilities (retry, timeout, rate limiting, etc.).
      3. Node has a go method that runs continuously.
    """
```

### Constructor

```python
def __init__(
    self,
    config: NodeConfig | None = None,
    **kwargs
) -> None
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `NodeConfig \| None` | `NodeConfig()` | Configuration object with capabilities and settings |
| `**kwargs` | `Any` | - | Override individual config attributes |

**Config Attributes** (can be set via config or kwargs):
- `retry`: RetryPolicy for automatic retry on failure
- `timeout`: TimeoutPolicy for execution time limits
- `rate_limiter`: RateLimiterPolicy for throttling
- `circuit_breaker`: CircuitBreakerPolicy for failure prevention
- `idempotency`: IdempotencyPolicy for deduplication
- `keep_in_state`: List of keys to persist across executions
- `validators`: List of input validation functions
- `max_workers`: Maximum concurrent workers for batch processing
- `live`: Boolean flag for continuous execution mode

### Key Methods

#### `process()` (Abstract)
Must be implemented by subclasses. Contains the node's core processing logic.

```python
async def process(self, context: ExecutionContext) -> Any
```

**Parameters**:
- `context`: ExecutionContext with inputs, state, metadata, graph_state

**Returns**: Dict or None. Dict keys become available in `node.outputs.content`

**Example**:
```python
class TransformNode(Node):
    async def process(self, context):
        input_data = context.inputs.content

        # Access node state
        counter = context.state.get('counter', 0)

        # Access graph state
        if context.graph_state:
            total = await context.graph_state.get('total', 0)

        # Process
        result = transform(input_data)

        # Return outputs
        return {
            'result': result,
            'counter': counter + 1,
            'success': True
        }
```

#### `go()`
Run the node continuously, processing messages from the mailbox until stopped.

```python
async def go(self) -> None
```

**Behavior**:
- Continuously receives messages from `self.mailbox`
- Processes each message through the full lifecycle
- Forwards outputs to successor nodes
- Honors the `_stop_flag` for graceful shutdown
- Used for LONG_RUNNING and RESUMABLE task types

**Example**:
```python
# In a long-running graph
class StreamProcessor(Node):
    async def process(self, context):
        message = context.inputs.content
        processed = await process_stream_message(message)
        return {'processed': processed}

# Graph will run node.go() continuously
graph = Graph(start=stream_node)
task = Task(type=TaskType.LONG_RUNNING)
await graph.run(task)
```

#### `work()`
Internal wrapper that applies capabilities (retry, timeout, etc.) to the process method. This is managed by the framework and typically not called directly.

#### `stop()`
Signal the node to stop processing after completing the current message.

```python
def stop(self) -> None
```

**Note**: Only applicable for nodes running in `go()` mode.

#### `run()`
Run the node based on its configuration.

```python
async def run(self, arg: Any = None) -> Any
```

**Parameters**:
- `arg`: Input data

**Returns**:
- If `self.live` is True: None (runs continuously via `go()`)
- If `self.live` is False: NodeMessage from `do()`

### Configuration

#### NodeConfig Properties

Nodes can be configured with various capabilities and settings:

**Retry Configuration**:
```python
from spark.nodes.policies import RetryPolicy

config = NodeConfig(
    retry=RetryPolicy(
        max_attempts=3,
        backoff_factor=2.0,
        max_delay=60.0
    )
)
node = MyNode(config=config)
```

**Timeout Configuration**:
```python
from spark.nodes.policies import TimeoutPolicy

config = NodeConfig(
    timeout=TimeoutPolicy(timeout_seconds=30.0)
)
node = MyNode(config=config)
```

**Rate Limiting**:
```python
from spark.nodes.policies import RateLimiterPolicy

config = NodeConfig(
    rate_limiter=RateLimiterPolicy(
        max_calls=10,
        period_seconds=60.0
    )
)
node = MyNode(config=config)
```

**Circuit Breaker**:
```python
from spark.nodes.policies import CircuitBreakerPolicy

config = NodeConfig(
    circuit_breaker=CircuitBreakerPolicy(
        failure_threshold=5,
        timeout_seconds=60.0
    )
)
node = MyNode(config=config)
```

**Idempotency**:
```python
from spark.nodes.policies import IdempotencyPolicy

config = NodeConfig(
    idempotency=IdempotencyPolicy(
        key_fn=lambda ctx: ctx.inputs.content.get('request_id')
    )
)
node = MyNode(config=config)
```

**State Persistence**:
```python
config = NodeConfig(
    keep_in_state=['counter', 'last_result', 'user_id']
)
node = MyNode(config=config)
```

### Capability Integration

Capabilities are automatically applied during node initialization in this order:
1. Idempotency (checked first to avoid unnecessary work)
2. Rate Limiting (throttle before execution)
3. Circuit Breaker (prevent cascading failures)
4. Timeout (enforce execution time limits)
5. Retry (outermost wrapper for failure recovery)

This ordering ensures optimal behavior and prevents redundant operations.

### Event Emission

Nodes emit structured lifecycle events for observability:

- `stage_done`: Emitted after successful stage completion
- `node_error`: Emitted on errors with decision context
- Custom events via telemetry integration

**Example**:
```python
# Events are automatically emitted during execution
# Access via graph event bus or telemetry manager
```

### Related Classes

- [BaseNode](#basenode) - Abstract parent class
- [NodeConfig](./config.md#nodeconfig) - Configuration options
- [ExecutionContext](#executioncontext) - Process method parameter
- [NodeState](#nodestate) - State container

### Notes

- All nodes are async by default; sync `process()` methods are automatically wrapped
- Capabilities are composable and applied as wrappers
- The `go()` method enables true long-running, reactive nodes
- Node instances can be reused across multiple graph runs
- Thread safety is handled automatically in concurrent mode

---

## BaseGraph

**Module**: `spark.graphs.base`

**Inheritance**: `ABC` (Abstract Base Class)

### Overview

`BaseGraph` is the abstract base class for all graphs in Spark. A graph defines the complete blueprint of an agentic workflow by connecting nodes through edges. Graphs manage node discovery, lifecycle, and execution orchestration.

### Class Signature

```python
class BaseGraph(ABC):
    """
    Abstract Base class for all graphs.
    A graph must have a start node to be runnable.
    How nodes are connected is defined outside of the graph.
    """
```

### Constructor

```python
def __init__(self, *edges: Edge, **kwargs) -> None
```

**Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `*edges` | `Edge` | Variable number of edges to initialize the graph |
| `start` | `BaseNode` | Starting node for execution (via kwargs) |
| `end` | `BaseNode` | Optional explicit end node (via kwargs) |
| `id` | `str` | Unique identifier (default: auto-generated) |

**Auto-Discovery**: If `start` is provided but no edges, the graph automatically traverses from the start node using BFS to discover all reachable nodes and their edges.

### Key Properties

#### `start: BaseNode | None`
The starting node where graph execution begins.

#### `end_node: BaseNode | None`
The terminal node of the graph. Can be explicitly set or automatically inferred as the node with no outgoing edges.

#### `nodes: set[BaseNode]`
Set of all nodes in the graph.

#### `edges: list[Edge]`
List of all edges connecting nodes in the graph.

### Key Methods

#### `add()`
Add edges to the graph and update node set.

```python
def add(self, *edges: Edge) -> None
```

**Parameters**:
- `*edges`: One or more Edge instances

**Example**:
```python
graph = BaseGraph()
graph.add(edge1, edge2, edge3)
```

#### `add_node()`
Add a single node to the graph and attach graph services (event bus, state).

```python
def add_node(self, node: BaseNode) -> None
```

**Parameters**:
- `node`: Node to add to the graph

#### `get_nodes_from_edges()`
Extract all nodes referenced in a list of edges.

```python
def get_nodes_from_edges(self, edges: list[Edge]) -> set[BaseNode]
```

**Parameters**:
- `edges`: List of edges to extract nodes from

**Returns**: Set of nodes (both from_node and to_node)

### Abstract Methods

#### `run()`
Execute the graph. Must be implemented by subclasses.

```python
@abstractmethod
async def run(self, arg: Any = None) -> Any
```

**Parameters**:
- `arg`: Input argument (Task, NodeMessage, dict, or raw value)

**Returns**: Graph execution result

### Auto-Discovery

If a graph is created with only a start node and no explicit edges, it automatically discovers the graph structure:

```python
# Define nodes with edges
node1 = MyNode()
node2 = MyNode()
node3 = MyNode()

node1 >> node2
node2 >> node3

# Auto-discovery finds all nodes and edges
graph = Graph(start=node1)  # No edges needed!
```

**Discovery Algorithm**:
1. Start from `start` node
2. Use breadth-first search (BFS)
3. Follow all edges from each discovered node
4. Continue until no new nodes found
5. Collect all edges encountered

### End Node Inference

The end node is automatically inferred as:
- The single node with no outgoing edges (sink node)
- `None` if multiple or zero sink nodes exist

Can be explicitly overridden:
```python
graph = Graph(start=node1, end=node_final)
```

### Related Classes

- [Graph](#graph) - Concrete implementation
- [BaseNode](#basenode) - Node base class
- [Edge](#edge) - Connections between nodes

### Notes

- Graphs must have a `start` node to be runnable
- Node connections are defined via edges, not within the graph itself
- The graph is responsible for execution orchestration, not business logic
- Auto-discovery enables declarative graph construction

---

## Graph

**Module**: `spark.graphs.graph`

**Inheritance**: `BaseGraph`

### Overview

`Graph` is the concrete implementation of BaseGraph that provides complete workflow execution with two modes: standard sequential flow and long-running concurrent mode. It includes telemetry integration, state management, lifecycle hooks, policy enforcement, and advanced features like checkpointing and resumable execution.

### Class Signature

```python
class Graph(BaseGraph):
    """
    A graph-based workflow executor.
    Supports both sequential and long-running execution modes.
    """
```

### Constructor

```python
def __init__(self, *edges: Edge, **kwargs) -> None
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `*edges` | `Edge` | - | Edges defining the graph structure |
| `start` | `BaseNode` | `None` | Starting node for execution |
| `end` | `BaseNode` | `None` | Optional explicit end node |
| `id` | `str` | Auto-generated | Unique graph identifier |
| `event_bus` | `GraphEventBus` | New instance | Event bus for pub/sub |
| `initial_state` | `dict` | `None` | Initial graph state |
| `enable_graph_state` | `bool` | `True` | Enable/disable graph state |
| `state_backend` | `StateBackend` | In-memory | State storage backend |
| `state_schema` | `BaseModel` | `None` | Pydantic model for state validation |
| `telemetry_config` | `TelemetryConfig` | `None` | Telemetry configuration |
| `policy_engine` | `PolicyEngine` | `None` | Policy engine for governance |
| `policy_set` | `PolicySet` | `None` | Alternative policy configuration |
| `policy_rules` | `list[PolicyRule]` | `None` | List of policy rules |
| `lifecycle_hooks` | `dict` | `None` | Lifecycle event handlers |
| `workspace` | `Workspace` | `None` | Workspace for file I/O |
| `artifact_manager` | `ArtifactManager` | `None` | Artifact lifecycle manager |
| `checkpoint_config` | `GraphCheckpointConfig` | `None` | Auto-checkpoint configuration |
| `auto_shutdown` | `bool` | `True` | Auto-shutdown for long-running tasks |
| `idle_timeout` | `float` | `2.0` | Idle timeout in seconds |

### Execution Modes

#### Standard Mode (Sequential)
```python
graph = Graph(start=node1)
task = Task(inputs=NodeMessage(content={'query': 'Hello'}))
result = await graph.run(task)
```

**Behavior**:
- Executes nodes sequentially
- Evaluates edge conditions after each node
- Follows active edges to next nodes
- Supports concurrent successors
- Returns final output from end node

#### Long-Running Mode (Concurrent)
```python
graph = Graph(start=node1)
task = Task(
    type=TaskType.LONG_RUNNING,
    inputs=NodeMessage(content={'query': 'Hello'})
)
result = await graph.run(task)
```

**Behavior**:
- All nodes run concurrently as continuous workers
- Nodes communicate via channels (mailboxes)
- Each node processes messages from its mailbox in a loop
- Auto-shutdown when all nodes idle (configurable)
- Graph state uses thread-safe locking

### Key Methods

#### `run()`
Execute the graph with the specified task configuration.

```python
async def run(self, arg: Any = None) -> Any
```

**Parameters**:
- `arg`: Task, NodeMessage, dict, or raw value

**Returns**:
- Standard mode: NodeMessage from final node
- Long-running mode: NodeMessage from end node after shutdown

**Lifecycle**:
1. Prepare task from input
2. Emit BEFORE_RUN lifecycle event
3. Initialize state and services
4. Configure telemetry trace (if enabled)
5. Execute graph (sequential or concurrent)
6. Emit AFTER_RUN lifecycle event
7. Finalize workspace and artifacts

**Timeout Handling**:
```python
task = Task(
    inputs=message,
    budget=Budget(max_seconds=30)
)
try:
    result = await graph.run(task)
except TimeoutError:
    print("Graph execution exceeded timeout")
```

#### `run_tasks()`
Execute multiple tasks with dependency management and campaign budgets.

```python
async def run_tasks(
    self,
    scheduler: TaskScheduler,
    *,
    continue_on_error: bool = False,
    on_task_completed: Callable | None = None,
    on_task_failed: Callable | None = None,
    usage_provider: Callable | None = None
) -> TaskBatchResult
```

**Parameters**:
- `scheduler`: TaskScheduler with tasks and dependencies
- `continue_on_error`: Continue execution if tasks fail
- `on_task_completed`: Callback after successful task
- `on_task_failed`: Callback after task failure
- `usage_provider`: Function to extract usage metrics

**Returns**: TaskBatchResult with completed and failed task mappings

**Example**:
```python
from spark.graphs.tasks import TaskScheduler, Task

scheduler = TaskScheduler()
scheduler.add_task(Task(task_id='task1', inputs=data1))
scheduler.add_task(Task(
    task_id='task2',
    inputs=data2,
    depends_on=['task1']  # Runs after task1
))

result = await graph.run_tasks(scheduler)
print(f"Completed: {len(result.completed)}")
print(f"Failed: {len(result.failed)}")
```

#### `stop_all_nodes()`
Stop all running nodes gracefully (long-running mode only).

```python
def stop_all_nodes(self) -> None
```

**Behavior**:
- Sets stop flag on all nodes
- Sends shutdown sentinel to mailboxes
- Nodes finish current message then exit
- Non-blocking (synchronous method)

### State Management

#### `get_state()`
Get value from graph state.

```python
async def get_state(self, key: str, default: Any = None) -> Any
```

#### `set_state()`
Set value in graph state.

```python
async def set_state(self, key: str, value: Any) -> None
```

#### `update_state()`
Batch update multiple state keys.

```python
async def update_state(self, updates: dict[str, Any]) -> None
```

#### `reset_state()`
Reset graph state (useful between runs).

```python
def reset_state(
    self,
    new_state: dict[str, Any] | None = None,
    *,
    preserve_backend: bool = True
) -> None
```

**Parameters**:
- `new_state`: Optional new state dict (None clears state)
- `preserve_backend`: Reuse existing backend (default: True)

#### `get_state_snapshot()`
Get a snapshot of current state.

```python
def get_state_snapshot(self) -> dict[str, Any]
```

**Returns**: Shallow copy of state dictionary

**Example**:
```python
# Initialize with state
graph = Graph(
    start=node1,
    initial_state={'counter': 0, 'results': []}
)

# Access in nodes
class MyNode(Node):
    async def process(self, context):
        counter = await context.graph_state.get('counter', 0)
        await context.graph_state.set('counter', counter + 1)
        return {'done': True}

# Access from graph
result = await graph.run()
counter = await graph.get_state('counter')
print(f"Total iterations: {counter}")
```

### Checkpointing

#### `configure_checkpoints()`
Configure automatic checkpointing behavior.

```python
def configure_checkpoints(
    self,
    config: GraphCheckpointConfig | dict | None
) -> None
```

**Example**:
```python
from spark.graphs.checkpoint import GraphCheckpointConfig

config = GraphCheckpointConfig(
    enabled=True,
    interval_iterations=5,  # Checkpoint every 5 iterations
    retain_last=10  # Keep last 10 checkpoints
)
graph.configure_checkpoints(config)
```

#### `checkpoint_state()`
Create a manual checkpoint.

```python
async def checkpoint_state(
    self,
    *,
    iteration: int | None = None,
    metadata: dict[str, Any] | None = None
) -> GraphCheckpoint
```

**Returns**: GraphCheckpoint object with state snapshot

#### `restore_state()`
Restore state from a checkpoint.

```python
async def restore_state(
    self,
    snapshot: GraphCheckpoint | dict
) -> None
```

#### `resume_from()`
Resume execution from a checkpoint.

```python
async def resume_from(
    self,
    checkpoint: GraphCheckpoint | dict,
    *,
    overrides: dict[str, Any] | None = None,
    task: Task | None = None
) -> Any
```

**Parameters**:
- `checkpoint`: Checkpoint to resume from
- `overrides`: State overrides to apply
- `task`: Optional task configuration

**Example**:
```python
# Save checkpoint
checkpoint = await graph.checkpoint_state(iteration=10)

# Later: resume from checkpoint
result = await graph.resume_from(
    checkpoint,
    overrides={'retries': 0}
)
```

### Lifecycle Hooks

#### `register_hook()`
Register a lifecycle event handler.

```python
def register_hook(
    self,
    event: GraphLifecycleEvent | str,
    hook: HookFn
) -> None
```

**Events**:
- `BEFORE_RUN`: Before graph execution starts
- `AFTER_RUN`: After graph execution completes
- `BEFORE_ITERATION`: Before each iteration in sequential mode
- `AFTER_ITERATION`: After each iteration
- `ITERATION_COMPLETE`: Synonym for AFTER_ITERATION

**Example**:
```python
async def log_iteration(context):
    print(f"Iteration {context.iteration_index}")
    print(f"Last output: {context.last_output}")

graph.register_hook('BEFORE_ITERATION', log_iteration)
```

### Event Bus

The graph's event bus enables pub/sub communication between nodes:

```python
# Publish from node
await node.publish_event('data.ready', {'id': 123})

# Subscribe in another node
async for event in node.subscribe_event('data.ready'):
    process(event.payload)

# Event-driven edges
node1.on_event('data.updated') >> handler_node
```

### Telemetry Integration

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_sqlite(
    db_path='telemetry.db',
    sampling_rate=1.0
)

graph = Graph(
    start=my_node,
    telemetry_config=config
)

result = await graph.run()

# Query telemetry
from spark.telemetry import TelemetryManager
manager = TelemetryManager.get_instance()
traces = await manager.query_traces(limit=10)
```

### Policy Enforcement

```python
from spark.governance import PolicyEngine, PolicyRule, PolicyEffect

rule = PolicyRule(
    name='high_cost_approval',
    effect=PolicyEffect.REQUIRE_APPROVAL,
    conditions={'estimated_cost': {'gt': 100}}
)

engine = PolicyEngine()
engine.add_rule(rule)

graph = Graph(
    start=node,
    policy_engine=engine
)

try:
    result = await graph.run(task)
except ApprovalPendingError as e:
    print(f"Approval required: {e.approval}")
```

### Workspace Integration

```python
from spark.graphs.workspace import Workspace

workspace = Workspace(root='/tmp/spark-workspace')

graph = Graph(
    start=node,
    workspace=workspace
)

# Access in nodes
class FileProcessor(Node):
    async def process(self, context):
        workspace = context.metadata.get('workspace')
        input_path = workspace.get_path('input.txt')
        # Process file...
```

### Related Classes

- [BaseGraph](#basegraph) - Abstract parent
- [Task](#task) - Execution configuration
- [GraphState](#graphstate) - State management
- [TelemetryConfig](./telemetry.md#telemetryconfig) - Observability
- [PolicyEngine](./governance.md#policyengine) - Governance

### Notes

- Graphs can be reused across multiple runs
- State persists across runs unless explicitly reset
- Long-running mode requires all nodes to implement `go()` properly
- Auto-shutdown prevents hanging long-running tasks
- Telemetry traces entire graph execution when enabled
- Checkpointing enables fault-tolerant long-running workflows

---

## Task

**Module**: `spark.graphs.tasks`

**Inheritance**: `BaseModel` (Pydantic)

### Overview

`Task` is the execution wrapper that configures how a graph runs. It specifies the task type (one-off, long-running, streaming, resumable), input data, execution budget, dependencies, and campaign information for grouped task management.

### Class Signature

```python
class Task(BaseModel):
    """
    A task is a unit of work that can be executed by a graph.
    """
    model_config = ConfigDict(extra='allow')
```

### Constructor

```python
Task(
    task_id: str | None = None,
    type: TaskType = TaskType.ONE_OFF,
    inputs: NodeMessage = NodeMessage(),
    budget: Budget = Budget(),
    depends_on: list[str] = [],
    priority: int = 0,
    campaign: CampaignInfo | None = None,
    metadata: dict[str, Any] = {},
    resume_from: str | None = None
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task_id` | `str \| None` | `None` | Unique identifier (required for dependencies) |
| `type` | `TaskType` | `ONE_OFF` | Task execution type |
| `inputs` | `NodeMessage` | Empty | Input data for the graph |
| `budget` | `Budget` | Empty | Execution budget constraints |
| `depends_on` | `list[str]` | `[]` | Task IDs that must complete first |
| `priority` | `int` | `0` | Priority for scheduling (higher = earlier) |
| `campaign` | `CampaignInfo \| None` | `None` | Campaign metadata for grouped budgets |
| `metadata` | `dict` | `{}` | Arbitrary metadata for custom logic |
| `resume_from` | `str \| None` | `None` | Checkpoint ID to resume from |

### TaskType Enum

```python
class TaskType(StrEnum):
    ONE_OFF = "oneoff"          # Standard sequential execution
    LONG_RUNNING = "longrunning"  # Concurrent continuous execution
    STREAMING = "streaming"      # Stream processing (future)
    RESUMABLE = "resumable"      # Can resume from checkpoint
```

### Budget Class

```python
class Budget(BaseModel):
    max_tokens: int = 0      # Max tokens (0 = unlimited)
    max_seconds: int = 0     # Max execution time (0 = unlimited)
    max_cost: float = 0      # Max cost (0 = unlimited)
```

**Example**:
```python
budget = Budget(
    max_tokens=10000,
    max_seconds=60,
    max_cost=1.0
)
```

### Key Methods

#### `is_ready()`
Check if task dependencies are satisfied.

```python
def is_ready(self, completed_ids: set[str] | None = None) -> bool
```

**Parameters**:
- `completed_ids`: Set of completed task IDs

**Returns**: True if all dependencies in `depends_on` are in `completed_ids`

**Example**:
```python
task = Task(
    task_id='task2',
    depends_on=['task1']
)

# Check if ready
if task.is_ready({'task1'}):
    await graph.run(task)
```

### Usage Patterns

#### Basic Task
```python
from spark.graphs.tasks import Task
from spark.nodes.types import NodeMessage

task = Task(
    inputs=NodeMessage(content={'query': 'Hello'}),
    budget=Budget(max_seconds=30)
)

result = await graph.run(task)
```

#### Long-Running Task
```python
task = Task(
    type=TaskType.LONG_RUNNING,
    inputs=NodeMessage(content={'stream': 'data'}),
    budget=Budget(max_seconds=3600)  # 1 hour
)

# Graph runs nodes concurrently until idle or timeout
result = await graph.run(task)
```

#### Task with Dependencies
```python
task1 = Task(task_id='fetch', inputs=fetch_params)
task2 = Task(
    task_id='process',
    inputs=process_params,
    depends_on=['fetch']  # Wait for task1
)
task3 = Task(
    task_id='save',
    inputs=save_params,
    depends_on=['process']  # Wait for task2
)

scheduler = TaskScheduler([task1, task2, task3])
result = await graph.run_tasks(scheduler)
```

#### Priority Scheduling
```python
high_priority = Task(
    task_id='urgent',
    priority=100,
    inputs=urgent_data
)

low_priority = Task(
    task_id='background',
    priority=1,
    inputs=background_data
)

# high_priority runs first when both are ready
```

#### Campaign Budgets
```python
from spark.graphs.tasks import CampaignInfo

campaign = CampaignInfo(
    campaign_id='user_123_session',
    name='User Analysis',
    budget=Budget(
        max_tokens=50000,
        max_cost=5.0
    )
)

task1 = Task(task_id='t1', campaign=campaign, inputs=data1)
task2 = Task(task_id='t2', campaign=campaign, inputs=data2)
task3 = Task(task_id='t3', campaign=campaign, inputs=data3)

# All tasks share campaign budget
# Execution stops when campaign budget exceeded
scheduler = TaskScheduler([task1, task2, task3])
result = await graph.run_tasks(scheduler)
```

#### Resumable Task
```python
# First run
task = Task(
    task_id='long_job',
    type=TaskType.RESUMABLE,
    inputs=job_data
)

checkpoint = await graph.checkpoint_state(iteration=50)

# Resume from checkpoint
resume_task = Task(
    task_id='long_job',
    type=TaskType.RESUMABLE,
    inputs=job_data,
    resume_from=checkpoint.checkpoint_id
)

result = await graph.resume_from(checkpoint, task=resume_task)
```

### Related Classes

- [Graph](#graph) - Executes tasks
- [NodeMessage](#nodemessage) - Input data format
- [TaskScheduler](#taskscheduler) - Dependency management
- [CampaignInfo](#campaigninfo) - Campaign metadata

### Notes

- `task_id` is required when using dependencies
- Budget enforcement requires telemetry or usage tracking
- Campaign budgets are shared across all tasks in the campaign
- Tasks with higher priority execute first when multiple are ready
- Resumable tasks require checkpoint configuration

---

## ExecutionContext

**Module**: `spark.nodes.types`

**Inheritance**: `dataclass`, `Generic[TNodeState]`

### Overview

`ExecutionContext` is the context object passed to node `process()` methods. It provides access to inputs, node state, execution metadata, outputs, and shared graph state. The context encapsulates all information needed for a node to execute.

### Class Signature

```python
@dataclass(slots=True)
class ExecutionContext(Generic[TNodeState]):
    """
    Execution context for the node.process method.

    This context is passed to the node.process method.
    It contains the inputs, state, and metadata for the node.
    """
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `inputs` | `NodeMessage` | Input data from previous node or graph |
| `state` | `NodeState` | Node-local state (persists across executions) |
| `metadata` | `ExecutionMetadata` | Timing and attempt information |
| `outputs` | `Any \| None` | Output data (set by framework) |
| `graph_state` | `GraphState \| None` | Shared state across all nodes |

### NodeMessage Class

```python
class NodeMessage(BaseModel):
    """Payload to/from nodes/agents"""

    id: str | None = None
    type: Literal['json', 'text'] = 'text'
    content: Any = None
    raw: Any = None              # Raw LLM output before parsing
    metadata: dict = {}          # Metadata about the message
    extras: dict = {}            # Additional metadata
    state: dict[str, Any] | None = None
```

**Common Usage**:
```python
# Access input content
data = context.inputs.content

# Access metadata
request_id = context.inputs.metadata.get('request_id')

# Input is typically a dict
if isinstance(context.inputs.content, dict):
    query = context.inputs.content['query']
    options = context.inputs.content.get('options', {})
```

### ExecutionMetadata Class

```python
@dataclass(slots=True)
class ExecutionMetadata:
    """Timing and attempt metadata captured for each run."""

    attempt: int = 1
    started_at: float | None = None
    finished_at: float | None = None
```

**Properties**:
- `duration: float | None` - Computed duration of execution

**Methods**:
- `mark_started(attempt: int)` - Mark execution start
- `mark_finished()` - Mark execution end
- `as_dict() -> dict` - Convert to dictionary

### Key Methods

#### `snapshot()`
Create a deep copy of the current state for diagnostics.

```python
def snapshot(self) -> dict[str, Any]
```

**Returns**: Deep copy of the state dictionary

**Usage**: Automatically called by framework to preserve state history.

#### `fork()`
Create a copy of the context suitable for branch execution.

```python
def fork(self) -> ExecutionContext[TNodeState]
```

**Returns**: New ExecutionContext with copied inputs, state, metadata

**Usage**: Used internally for parallel node execution or branching workflows.

### Accessing Context Components

#### Inputs
```python
class MyNode(Node):
    async def process(self, context):
        # Access content
        content = context.inputs.content

        # Typically a dict
        if isinstance(content, dict):
            user_id = content.get('user_id')
            query = content['query']

        # Access metadata
        trace_id = context.inputs.metadata.get('trace_id')

        return {'result': 'processed'}
```

#### Node State
```python
class StatefulNode(Node):
    async def process(self, context):
        # Get from state
        counter = context.state.get('counter', 0)
        history = context.state.get('history', [])

        # Update state
        context.state['counter'] = counter + 1
        context.state['history'].append(context.inputs.content)

        # State persists across executions if in keep_in_state
        return {'count': counter + 1}
```

#### Graph State
```python
class SharedStateNode(Node):
    async def process(self, context):
        # Check if graph state available
        if context.graph_state is None:
            return {'error': 'No graph state'}

        # Get value
        total = await context.graph_state.get('total', 0)

        # Set value
        await context.graph_state.set('total', total + 1)

        # Batch update
        await context.graph_state.update({
            'total': total + 1,
            'last_update': time.time()
        })

        # Atomic transaction
        async with context.graph_state.transaction() as state:
            state['x'] = state.get('x', 0) + 1
            state['y'] = state.get('y', 0) + 1

        return {'updated': True}
```

#### Metadata
```python
class MetadataNode(Node):
    async def process(self, context):
        # Access execution metadata
        attempt = context.metadata.attempt
        started_at = context.metadata.started_at

        # Check if retry
        if attempt > 1:
            print(f"Retry attempt {attempt}")

        return {'attempt': attempt}
```

### Complete Example

```python
class ProcessingNode(Node):
    async def process(self, context):
        # 1. Extract inputs
        input_data = context.inputs.content
        request_id = context.inputs.metadata.get('request_id', 'unknown')

        # 2. Access node state
        processed_count = context.state.get('processed_count', 0)

        # 3. Access graph state (shared)
        if context.graph_state:
            global_count = await context.graph_state.get('global_count', 0)
            await context.graph_state.set('global_count', global_count + 1)

        # 4. Check execution metadata
        if context.metadata.attempt > 1:
            print(f"Retry attempt {context.metadata.attempt}")

        # 5. Process
        result = transform(input_data)

        # 6. Update node state
        context.state['processed_count'] = processed_count + 1
        context.state['last_request_id'] = request_id

        # 7. Return outputs
        return {
            'result': result,
            'request_id': request_id,
            'count': processed_count + 1
        }
```

### Related Classes

- [Node](#node) - Receives ExecutionContext in process()
- [NodeMessage](#nodemessage) - Input/output format
- [NodeState](#nodestate) - Node-local state structure
- [GraphState](#graphstate) - Shared state management

### Notes

- ExecutionContext is created fresh for each node execution
- State changes persist across executions if keys in `keep_in_state`
- Graph state is only available if graph has `enable_graph_state=True`
- Metadata is managed by the framework (timing, retries)
- Context is generic over NodeState type for type safety

---

## NodeState

**Module**: `spark.nodes.types`

**Inheritance**: `TypedDict`

### Overview

`NodeState` is the state container that persists information across node executions. Each node maintains its own isolated state that tracks execution history, processing status, queued inputs, and custom data.

### Class Signature

```python
class NodeState(TypedDict, extra_items=Any):
    """State of the node."""

    context_snapshot: dict[str, Any] | None
    processing: bool
    pending_inputs: deque[NodeMessage]
    process_count: int
    # ... additional custom keys allowed
```

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `context_snapshot` | `dict \| None` | Snapshot of last execution context |
| `processing` | `bool` | Whether node is currently processing |
| `pending_inputs` | `deque[NodeMessage]` | Queue of inputs waiting to be processed |
| `process_count` | `int` | Number of times node has executed |

### Factory Function

```python
def default_node_state(**kwargs) -> NodeState
```

Creates a new NodeState with default values plus any custom fields.

**Example**:
```python
state = default_node_state(
    counter=0,
    user_id='abc123'
)
```

### State Persistence

Nodes can persist specific keys across executions using `keep_in_state`:

```python
class PersistentNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            keep_in_state=['counter', 'history', 'user_id']
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context):
        # Retrieve persisted value
        counter = context.state.get('counter', 0)
        history = context.state.get('history', [])

        # Update
        context.state['counter'] = counter + 1
        context.state['history'].append(context.inputs.content)

        # These persist across process() calls
        return {'count': counter + 1}
```

### Accessing State

#### From ExecutionContext
```python
class MyNode(Node):
    async def process(self, context):
        # Access state dict
        state = context.state

        # Get value with default
        counter = state.get('counter', 0)

        # Set value
        state['counter'] = counter + 1

        # Custom keys
        state['last_timestamp'] = time.time()
        state['user_data'] = {'id': 123, 'name': 'Alice'}

        return {'success': True}
```

#### From Node Instance
```python
class MyNode(Node):
    async def process(self, context):
        # Access via self.state (same as context.state)
        counter = self.state.get('counter', 0)

        # Check processing status
        if self.state['processing']:
            print("Already processing")

        # Check queue
        pending = len(self.state['pending_inputs'])
        print(f"{pending} inputs queued")

        return {'done': True}
```

### State Lifecycle

1. **Initialization**: State created with default values when node instantiated
2. **Pre-Process**: `keep_in_state` hook restores persisted values before `process()`
3. **Process**: Node reads/writes state in `process()` method
4. **Post-Process**: Framework records context snapshot
5. **Persistence**: Keys in `keep_in_state` are available in next execution

### Common Patterns

#### Counter Pattern
```python
class CounterNode(Node):
    def __init__(self, **kwargs):
        super().__init__(
            config=NodeConfig(keep_in_state=['counter']),
            **kwargs
        )

    async def process(self, context):
        count = context.state.get('counter', 0)
        context.state['counter'] = count + 1
        return {'count': count + 1}
```

#### History Pattern
```python
class HistoryNode(Node):
    def __init__(self, **kwargs):
        super().__init__(
            config=NodeConfig(keep_in_state=['history']),
            **kwargs
        )

    async def process(self, context):
        history = context.state.get('history', [])
        history.append(context.inputs.content)
        context.state['history'] = history[-100:]  # Keep last 100
        return {'history_size': len(history)}
```

#### Session Pattern
```python
class SessionNode(Node):
    def __init__(self, **kwargs):
        super().__init__(
            config=NodeConfig(keep_in_state=['session']),
            **kwargs
        )

    async def process(self, context):
        session = context.state.get('session', {})

        # Lazy initialize
        if not session:
            session = {
                'id': uuid4().hex,
                'created_at': time.time(),
                'requests': 0
            }

        session['requests'] += 1
        session['last_request'] = time.time()
        context.state['session'] = session

        return {'session_id': session['id']}
```

### Built-in State Fields

#### context_snapshot
Snapshot of the last execution context for debugging:
```python
# Access snapshot
snapshot = self.state['context_snapshot']
if snapshot:
    last_inputs = snapshot.get('inputs')
    last_outputs = snapshot.get('outputs')
```

#### processing
Flag indicating if node is currently executing:
```python
# Check if processing
if self.state['processing']:
    print("Node is busy")
```

#### pending_inputs
Queue of inputs waiting to be processed:
```python
# Check queue size
queue_size = len(self.state['pending_inputs'])

# Peek at next input
if self.state['pending_inputs']:
    next_input = self.state['pending_inputs'][0]
```

#### process_count
Total number of executions:
```python
# Access execution count
count = self.state['process_count']
print(f"Node executed {count} times")
```

### Thread Safety

- In sequential mode: No locking, state access is safe
- In LONG_RUNNING mode: Node state is accessed from single node's go() loop, safe by design
- For cross-node communication: Use GraphState instead

### Related Classes

- [ExecutionContext](#executioncontext) - Provides access to state
- [Node](#node) - Maintains NodeState instance
- [GraphState](#graphstate) - For shared state across nodes

### Notes

- NodeState is node-local, not shared between nodes
- State persists across `run()` calls within same graph instance
- State is reset when node is recreated
- Keys not in `keep_in_state` are ephemeral
- State is automatically passed to `process()` via ExecutionContext

---

## GraphState

**Module**: `spark.graphs.graph_state`

**Inheritance**: Plain class (wraps StateBackend)

### Overview

`GraphState` provides thread-safe shared state management across all nodes in a graph. It supports multiple backends (in-memory, SQLite, PostgreSQL, etc.), concurrent access control, atomic transactions, and optional schema validation. Graph state enables coordination between nodes through shared data.

### Class Signature

```python
class GraphState:
    """Thread-safe graph state with backend abstraction.

    Provides safe concurrent access to mission state regardless of where it is stored.
    Default backend is in-memory; durable backends can be supplied for checkpoints.
    """
```

### Constructor

```python
def __init__(
    self,
    initial_state: dict[str, Any] | None = None,
    backend: StateBackend | None = None,
    schema_model: Type[BaseModel] | BaseModel | None = None
) -> None
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_state` | `dict \| None` | `None` | Initial state dictionary |
| `backend` | `StateBackend \| None` | In-memory | Storage backend |
| `schema_model` | `BaseModel \| None` | `None` | Pydantic model for validation |

### State Backends

#### In-Memory (Default)
```python
from spark.graphs.graph_state import GraphState

state = GraphState(initial_state={'counter': 0})
```

#### SQLite Backend
```python
from spark.graphs.state_backend import SQLiteStateBackend

backend = SQLiteStateBackend('state.db')
state = GraphState(backend=backend)
```

#### PostgreSQL Backend
```python
from spark.graphs.state_backend import PostgresStateBackend

backend = PostgresStateBackend(
    host='localhost',
    database='spark',
    user='user',
    password='pass'
)
state = GraphState(backend=backend)
```

#### Custom Backend
```python
from spark.graphs.state_backend import StateBackend

class RedisBackend(StateBackend):
    # Implement required methods
    pass

state = GraphState(backend=RedisBackend())
```

### Concurrency Modes

#### Sequential Mode
For standard graph execution (no concurrent node access):
```python
state = GraphState()
# No locking overhead
```

#### Concurrent Mode
For LONG_RUNNING tasks with concurrent node execution:
```python
state = GraphState()
state.enable_concurrent_mode()  # Automatic locking

# ... concurrent execution ...

state.disable_concurrent_mode()
```

**Note**: Graph automatically configures mode based on TaskType.

### Key Methods

#### `get()`
Retrieve value from state.

```python
async def get(self, key: str, default: Any = None) -> Any
```

**Example**:
```python
counter = await state.get('counter', 0)
config = await state.get('config', {})
```

#### `set()`
Set value in state with validation.

```python
async def set(self, key: str, value: Any) -> None
```

**Example**:
```python
await state.set('counter', 42)
await state.set('results', [1, 2, 3])
```

#### `update()`
Batch update multiple keys atomically.

```python
async def update(self, updates: dict[str, Any]) -> None
```

**Example**:
```python
await state.update({
    'counter': 10,
    'timestamp': time.time(),
    'status': 'completed'
})
```

#### `delete()`
Remove key from state.

```python
async def delete(self, key: str) -> None
```

**Example**:
```python
await state.delete('temporary_data')
```

#### `has()`
Check if key exists.

```python
async def has(self, key: str) -> bool
```

**Example**:
```python
if await state.has('initialized'):
    # Already initialized
    pass
```

#### `keys()`
Get all state keys.

```python
async def keys(self) -> list[str]
```

**Example**:
```python
all_keys = await state.keys()
print(f"State contains: {all_keys}")
```

### Transactions

#### `transaction()`
Atomic multi-operation transaction context manager.

```python
@asynccontextmanager
async def transaction(self) -> dict[str, Any]
```

**Example**:
```python
# Atomic read-modify-write
async with state.transaction() as data:
    data['x'] = data.get('x', 0) + 1
    data['y'] = data.get('y', 0) + 1
    # Changes committed atomically
```

**Use Cases**:
- Prevent race conditions
- Ensure consistency across multiple updates
- Atomic increment operations

### Locking

#### `lock()`
Acquire named lock for custom synchronization.

```python
@asynccontextmanager
async def lock(self, name: str = 'global')
```

**Example**:
```python
async with state.lock('resource_pool'):
    # Critical section
    resources = await state.get('resources', [])
    resource = resources.pop()
    await state.set('resources', resources)
    # Use resource...
```

#### `get_lock_stats()`
Get lock wait statistics.

```python
def get_lock_stats(self) -> dict[str, Any]
```

**Returns**: Statistics including wait times, acquisitions, etc.

### State Snapshots

#### `get_snapshot()`
Get shallow copy of current state (non-blocking).

```python
def get_snapshot(self) -> dict[str, Any]
```

**Example**:
```python
snapshot = state.get_snapshot()
print(f"Current state: {snapshot}")
```

#### `get_raw()`
Direct access to internal state (use with caution).

```python
def get_raw(self) -> dict[str, Any]
```

### State Management

#### `clear()`
Clear all state.

```python
def clear(self) -> None
```

#### `reset()`
Replace entire state atomically.

```python
async def reset(self, new_state: dict[str, Any] | None = None) -> None
```

**Example**:
```python
# Reset to new state
await state.reset({'counter': 0, 'status': 'initialized'})

# Clear completely
await state.reset()
```

#### `initialize()`
Initialize backend (called automatically by Graph).

```python
async def initialize(self) -> None
```

### Schema Validation

Define a schema for type safety and validation:

```python
from pydantic import BaseModel

class MyStateSchema(BaseModel):
    counter: int = 0
    results: list[str] = []
    config: dict[str, Any] = {}

# Create state with schema
state = GraphState(
    initial_state={'counter': 0},
    schema_model=MyStateSchema
)

# Valid update
await state.set('counter', 10)

# Invalid update raises ValidationError
await state.set('counter', 'invalid')  # Error!
```

### Backend Information

#### `describe_backend()`
Get backend metadata.

```python
def describe_backend(self) -> dict[str, Any]
```

#### `describe_schema()`
Get schema metadata if configured.

```python
def describe_schema(self) -> dict[str, Any] | None
```

### Mailbox Persistence

For long-running tasks, GraphState can persist node mailboxes:

#### `persist_mailbox_messages()`
```python
async def persist_mailbox_messages(
    self,
    mailbox_id: str,
    entries: list[Any]
) -> None
```

#### `load_mailbox_messages()`
```python
async def load_mailbox_messages(
    self,
    mailbox_id: str
) -> list[Any]
```

#### `mailbox_snapshot()`
```python
async def mailbox_snapshot(self) -> dict[str, list[Any]]
```

#### `restore_mailboxes()`
```python
async def restore_mailboxes(
    self,
    payload: dict[str, list[Any]] | None
) -> None
```

### Blob Storage

Some backends support streaming blob storage:

#### `supports_blobs()`
```python
def supports_blobs(self) -> bool
```

#### `open_blob_writer()`
```python
@asynccontextmanager
async def open_blob_writer(
    self,
    *,
    blob_id: str | None = None,
    metadata: dict[str, Any] | None = None
)
```

#### `open_blob_reader()`
```python
@asynccontextmanager
async def open_blob_reader(self, blob_id: str)
```

#### `delete_blob()`
```python
async def delete_blob(self, blob_id: str) -> None
```

#### `list_blobs()`
```python
async def list_blobs(self) -> list[str]
```

### Usage Patterns

#### Counter Pattern
```python
# Atomic increment
async with state.transaction() as data:
    data['counter'] = data.get('counter', 0) + 1
```

#### Aggregation Pattern
```python
# Collect results from multiple nodes
async with state.transaction() as data:
    results = data.get('results', [])
    results.append(new_result)
    data['results'] = results
```

#### Configuration Pattern
```python
# Initialize once
if not await state.has('initialized'):
    await state.update({
        'initialized': True,
        'config': load_config(),
        'start_time': time.time()
    })
```

#### Flag Pattern
```python
# Coordinate nodes
await state.set('ready_to_proceed', True)

# In another node
if await state.get('ready_to_proceed', False):
    proceed()
```

### Complete Example

```python
# Initialize graph with state
graph = Graph(
    start=node1,
    initial_state={
        'counter': 0,
        'results': [],
        'config': {'threshold': 10}
    }
)

# Node accessing state
class AggregatorNode(Node):
    async def process(self, context):
        # Atomic counter increment
        async with context.graph_state.transaction() as state:
            state['counter'] = state.get('counter', 0) + 1

            # Append result
            results = state.get('results', [])
            results.append(context.inputs.content)
            state['results'] = results

        # Read config
        threshold = await context.graph_state.get('config', {})
        threshold = threshold.get('threshold', 10)

        return {'done': True}

# After execution
result = await graph.run()
counter = await graph.get_state('counter')
results = await graph.get_state('results')
print(f"Processed {counter} items")
print(f"Results: {results}")
```

### Related Classes

- [Graph](#graph) - Creates and manages GraphState
- [ExecutionContext](#executioncontext) - Provides access via context.graph_state
- [StateBackend](./backends.md#statebackend) - Backend implementations

### Notes

- Thread safety depends on mode (sequential vs concurrent)
- State persists across multiple `graph.run()` calls
- Use `reset_state()` on Graph to clear between runs
- Schema validation is optional but recommended for production
- Transactions prevent race conditions in concurrent mode
- Graph automatically configures state mode based on task type
- State is automatically injected into all nodes during graph preparation

---

## Additional Classes Reference

For complete API coverage, refer to these related documents:

- **Edge & EdgeCondition**: [Edges and Conditions](./edges.md)
- **Capabilities**: [Capabilities System](./capabilities.md)
- **Agent Classes**: [Agent System](./agents.md)
- **Tools**: [Tools System](./tools.md)
- **Telemetry**: [Telemetry System](./telemetry.md)
- **State Backends**: [State Backends](./backends.md)
- **Policy & Governance**: [Governance System](./governance.md)

---

## Version Information

**Document Version**: 1.0
**Spark Version**: 0.1.0 (all classes as of January 2025)
**Last Updated**: 2025-12-05

For the most up-to-date API information, refer to the source code in `/Users/wwang1/github/spark/spark/`.
