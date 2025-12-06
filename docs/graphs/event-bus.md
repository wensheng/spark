# Event Bus Reference

This reference covers the graph event system for observability, monitoring, and reactive programming in Spark workflows.

## Overview

The **GraphEventBus** provides a publish-subscribe system for graph and node lifecycle events. It enables:
- Monitoring graph execution in real-time
- Debugging workflow behavior
- Building reactive systems
- Collecting metrics and telemetry
- Implementing custom observability

## GraphEventBus Class

The event bus is automatically created for each graph and accessible via `graph.event_bus`.

### Constructor

```python
from spark.graphs.event_bus import GraphEventBus

event_bus = GraphEventBus(
    replay_buffer_size: int = 0  # Number of recent events to buffer for replay
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `replay_buffer_size` | `int` | `0` | Size of circular buffer for event replay (0 = disabled) |

### Basic Usage

```python
from spark.graphs import Graph

# Event bus is created automatically
graph = Graph(start=my_node)

# Access event bus
event_bus = graph.event_bus

# Subscribe to events
def on_node_finished(event):
    print(f"Node {event['node']} completed")

event_bus.subscribe('node_finished', on_node_finished)

# Run graph (events are published automatically)
result = await graph.run()
```

## Event Types

Spark publishes the following standard events during graph execution:

### graph_started

Published when graph execution begins.

**Event Data:**
```python
{
    'event_type': 'graph_started',
    'timestamp': datetime,
    'graph_id': str,
    'task': Task,
    'metadata': dict
}
```

### graph_finished

Published when graph execution completes successfully.

**Event Data:**
```python
{
    'event_type': 'graph_finished',
    'timestamp': datetime,
    'graph_id': str,
    'result': NodeMessage,
    'duration_ms': float,
    'metadata': dict
}
```

### node_started

Published when a node begins processing.

**Event Data:**
```python
{
    'event_type': 'node_started',
    'timestamp': datetime,
    'graph_id': str,
    'node': str,              # Node name/ID
    'node_type': str,         # Node class name
    'inputs': dict,           # Node inputs
    'metadata': dict
}
```

### node_finished

Published when a node completes successfully.

**Event Data:**
```python
{
    'event_type': 'node_finished',
    'timestamp': datetime,
    'graph_id': str,
    'node': str,
    'node_type': str,
    'outputs': dict,          # Node outputs
    'duration_ms': float,     # Node execution time
    'metadata': dict
}
```

### node_failed

Published when a node encounters an error.

**Event Data:**
```python
{
    'event_type': 'node_failed',
    'timestamp': datetime,
    'graph_id': str,
    'node': str,
    'node_type': str,
    'error': str,             # Error message
    'error_type': str,        # Exception class name
    'traceback': str,         # Full traceback
    'metadata': dict
}
```

## Subscribing to Events

### subscribe() Method

```python
event_bus.subscribe(
    event_type: str,
    handler: Callable[[dict], None]
) -> str
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Event type to subscribe to or `'*'` for all events |
| `handler` | `Callable` | Function to call when event occurs |

**Returns:** Subscription ID (string)

### Basic Subscription

```python
def handler(event):
    print(f"Event: {event['event_type']}")
    print(f"Timestamp: {event['timestamp']}")

# Subscribe to specific event type
sub_id = event_bus.subscribe('node_finished', handler)
```

### Subscribe to All Events

```python
def catch_all_handler(event):
    event_type = event.get('event_type', 'unknown')
    print(f"Received event: {event_type}")

# Subscribe to all event types
event_bus.subscribe('*', catch_all_handler)
```

### Multiple Handlers

```python
def log_handler(event):
    logger.info(f"Event: {event['event_type']}")

def metric_handler(event):
    metrics.increment(f"events.{event['event_type']}")

# Multiple handlers for same event
event_bus.subscribe('node_finished', log_handler)
event_bus.subscribe('node_finished', metric_handler)
```

### Unsubscribing

```python
# Subscribe and get ID
sub_id = event_bus.subscribe('node_started', handler)

# Unsubscribe later
event_bus.unsubscribe(sub_id)
```

## Publishing Custom Events

### publish() Method

```python
event_bus.publish(
    event_type: str,
    event_data: dict
) -> None
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | `str` | Custom event type name |
| `event_data` | `dict` | Event data dictionary |

### Example: Custom Application Events

```python
from spark.nodes import Node
from datetime import datetime

class ProcessingNode(Node):
    async def process(self, context):
        # Publish custom event
        context.graph.event_bus.publish(
            'data_processed',
            {
                'event_type': 'data_processed',
                'timestamp': datetime.now(),
                'record_count': 100,
                'processing_time_ms': 523.5,
                'metadata': {'batch_id': '12345'}
            }
        )

        return {'success': True}

# Subscribe to custom event
def on_data_processed(event):
    count = event.get('record_count', 0)
    print(f"Processed {count} records")

graph.event_bus.subscribe('data_processed', on_data_processed)
```

## Event Replay for Debugging

Event replay allows you to buffer recent events and replay them for debugging or analysis.

### Enabling Replay Buffer

```python
from spark.graphs import Graph
from spark.graphs.event_bus import GraphEventBus

# Create event bus with replay buffer
event_bus = GraphEventBus(replay_buffer_size=100)  # Buffer last 100 events

graph = Graph(start=my_node)
graph.event_bus = event_bus
```

### replay() Method

```python
events = event_bus.replay(
    topic: str = '*',           # Event type filter
    limit: Optional[int] = None # Maximum number of events
) -> List[dict]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `topic` | `str` | `'*'` | Event type to filter (`'*'` for all) |
| `limit` | `int` | `None` | Maximum events to return |

**Returns:** List of event dictionaries (oldest to newest)

### Replay Examples

```python
# Run graph
result = await graph.run()

# Replay all events
all_events = event_bus.replay(topic='*')
print(f"Total events: {len(all_events)}")

# Replay specific event type
node_finished_events = event_bus.replay(topic='node_finished')
for event in node_finished_events:
    print(f"Node {event['node']} took {event['duration_ms']:.2f}ms")

# Replay with limit
recent_events = event_bus.replay(topic='*', limit=10)
print(f"Last 10 events: {len(recent_events)}")
```

### Debugging Workflow

```python
# Enable replay
event_bus = GraphEventBus(replay_buffer_size=1000)
graph.event_bus = event_bus

# Run graph
try:
    result = await graph.run()
except Exception as e:
    print(f"Graph failed: {e}")

    # Analyze what happened
    events = event_bus.replay(topic='*')

    # Find all failed nodes
    failures = [e for e in events if e['event_type'] == 'node_failed']
    for failure in failures:
        print(f"Node {failure['node']} failed:")
        print(f"  Error: {failure['error']}")
        print(f"  Type: {failure['error_type']}")

    # Find slow nodes
    finished = [e for e in events if e['event_type'] == 'node_finished']
    slow_nodes = [e for e in finished if e['duration_ms'] > 1000]
    for slow in slow_nodes:
        print(f"Slow node: {slow['node']} took {slow['duration_ms']:.2f}ms")
```

## Event Patterns

### Observer Pattern

Monitor graph execution without modifying workflow:

```python
class GraphMonitor:
    def __init__(self):
        self.node_count = 0
        self.total_duration = 0.0
        self.errors = []

    def on_node_finished(self, event):
        self.node_count += 1
        self.total_duration += event.get('duration_ms', 0)

    def on_node_failed(self, event):
        self.errors.append({
            'node': event['node'],
            'error': event['error']
        })

    def report(self):
        avg_duration = self.total_duration / self.node_count if self.node_count > 0 else 0
        print(f"Nodes executed: {self.node_count}")
        print(f"Average duration: {avg_duration:.2f}ms")
        print(f"Errors: {len(self.errors)}")

# Use monitor
monitor = GraphMonitor()
event_bus.subscribe('node_finished', monitor.on_node_finished)
event_bus.subscribe('node_failed', monitor.on_node_failed)

result = await graph.run()
monitor.report()
```

### Reactor Pattern

React to events by triggering actions:

```python
class AlertingReactor:
    def __init__(self, alert_service):
        self.alert_service = alert_service

    def on_node_failed(self, event):
        # Send alert when node fails
        self.alert_service.send_alert(
            severity='error',
            message=f"Node {event['node']} failed: {event['error']}",
            metadata=event.get('metadata', {})
        )

    def on_slow_execution(self, event):
        # Alert on slow nodes
        duration = event.get('duration_ms', 0)
        if duration > 5000:  # > 5 seconds
            self.alert_service.send_alert(
                severity='warning',
                message=f"Node {event['node']} took {duration:.2f}ms"
            )

reactor = AlertingReactor(alert_service)
event_bus.subscribe('node_failed', reactor.on_node_failed)
event_bus.subscribe('node_finished', reactor.on_slow_execution)
```

### Metrics Collection

Collect metrics for monitoring and analysis:

```python
from collections import defaultdict

class MetricsCollector:
    def __init__(self):
        self.node_durations = defaultdict(list)
        self.node_executions = defaultdict(int)
        self.error_counts = defaultdict(int)

    def on_node_finished(self, event):
        node = event['node']
        duration = event.get('duration_ms', 0)
        self.node_durations[node].append(duration)
        self.node_executions[node] += 1

    def on_node_failed(self, event):
        node = event['node']
        self.error_counts[node] += 1

    def get_stats(self):
        stats = {}
        for node, durations in self.node_durations.items():
            stats[node] = {
                'executions': self.node_executions[node],
                'avg_duration_ms': sum(durations) / len(durations),
                'min_duration_ms': min(durations),
                'max_duration_ms': max(durations),
                'errors': self.error_counts[node]
            }
        return stats

# Use collector
collector = MetricsCollector()
event_bus.subscribe('node_finished', collector.on_node_finished)
event_bus.subscribe('node_failed', collector.on_node_failed)

result = await graph.run()

# Get statistics
stats = collector.get_stats()
for node, data in stats.items():
    print(f"{node}:")
    print(f"  Executions: {data['executions']}")
    print(f"  Avg Duration: {data['avg_duration_ms']:.2f}ms")
    print(f"  Errors: {data['errors']}")
```

## Async Event Handling

Handlers can be async functions for performing async operations:

```python
async def async_handler(event):
    # Async operations
    await save_to_database(event)
    await send_notification(event)

# Subscribe with async handler
event_bus.subscribe('node_finished', async_handler)
```

**Note:** Async handlers are awaited during event publication, which may add latency. For high-throughput scenarios, consider:
1. Using sync handlers that enqueue work
2. Using background tasks
3. Batching operations

### Example: Async Event Processing

```python
import asyncio

class AsyncEventProcessor:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.task = None

    async def handler(self, event):
        # Non-blocking: just enqueue
        await self.queue.put(event)

    async def processor(self):
        # Background task processes events
        while True:
            event = await self.queue.get()
            try:
                await self.process_event(event)
            except Exception as e:
                print(f"Error processing event: {e}")
            finally:
                self.queue.task_done()

    async def process_event(self, event):
        # Expensive async operation
        await save_to_database(event)

    async def start(self):
        self.task = asyncio.create_task(self.processor())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await self.task

# Use processor
processor = AsyncEventProcessor()
await processor.start()

event_bus.subscribe('*', processor.handler)

result = await graph.run()

await processor.stop()
```

## Event Filtering

### Filter by Node

```python
def node_filter(target_node):
    def handler(event):
        if event.get('node') == target_node:
            print(f"Event for {target_node}: {event['event_type']}")
    return handler

event_bus.subscribe('node_finished', node_filter('SpecificNode'))
```

### Filter by Duration

```python
def slow_node_handler(event):
    duration = event.get('duration_ms', 0)
    if duration > 1000:  # Slower than 1 second
        print(f"Slow node detected: {event['node']} ({duration:.2f}ms)")

event_bus.subscribe('node_finished', slow_node_handler)
```

### Filter by Metadata

```python
def priority_filter(event):
    metadata = event.get('metadata', {})
    if metadata.get('priority') == 'high':
        print(f"High priority event: {event['event_type']}")

event_bus.subscribe('*', priority_filter)
```

## Event Querying

After graph execution, query buffered events:

```python
# Run graph with replay enabled
event_bus = GraphEventBus(replay_buffer_size=500)
graph.event_bus = event_bus
result = await graph.run()

# Query patterns
events = event_bus.replay(topic='*')

# Find first node
first_event = next((e for e in events if e['event_type'] == 'node_started'), None)
if first_event:
    print(f"First node: {first_event['node']}")

# Find last node
finished_events = [e for e in events if e['event_type'] == 'node_finished']
if finished_events:
    last_event = finished_events[-1]
    print(f"Last node: {last_event['node']}")

# Calculate total execution time
graph_started = next((e for e in events if e['event_type'] == 'graph_started'), None)
graph_finished = next((e for e in events if e['event_type'] == 'graph_finished'), None)

if graph_started and graph_finished:
    duration = (graph_finished['timestamp'] - graph_started['timestamp']).total_seconds()
    print(f"Total execution: {duration:.2f}s")

# Find critical path (slowest nodes)
finished_sorted = sorted(finished_events, key=lambda e: e.get('duration_ms', 0), reverse=True)
print("Top 5 slowest nodes:")
for event in finished_sorted[:5]:
    print(f"  {event['node']}: {event['duration_ms']:.2f}ms")
```

## Integration with Telemetry

Event bus works alongside the telemetry system:

```python
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Enable both telemetry and event bus
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)

event_bus = GraphEventBus(replay_buffer_size=100)

graph = Graph(
    start=my_node,
    telemetry_config=telemetry_config
)
graph.event_bus = event_bus

# Subscribe to events for real-time monitoring
def monitor(event):
    print(f"Real-time: {event['event_type']}")

event_bus.subscribe('*', monitor)

# Run graph (events published, telemetry collected)
result = await graph.run()

# Query telemetry for historical analysis
# Query events for immediate debugging
```

**When to use each:**
- **Event Bus**: Real-time monitoring, reactive systems, immediate debugging
- **Telemetry**: Historical analysis, performance profiling, persistent storage

## Performance Considerations

### Handler Performance

- Keep handlers fast (< 1ms typical)
- Avoid blocking operations in sync handlers
- Use async handlers for I/O operations
- Consider batching for high event volume

### Memory Usage

| Replay Buffer Size | Memory Usage (Approx) |
|-------------------|----------------------|
| 0 (disabled) | Minimal (~1KB) |
| 100 events | ~100KB |
| 1000 events | ~1MB |
| 10000 events | ~10MB |

### Event Volume

Typical event counts per graph execution:

| Graph Type | Events per Run |
|------------|----------------|
| Simple pipeline (5 nodes) | ~12 events |
| Complex workflow (20 nodes) | ~50 events |
| Long-running (continuous) | 1000+ events |

### Optimization Tips

```python
# Bad: Expensive handler
def slow_handler(event):
    expensive_operation()  # Blocks event publication
    save_to_database_sync()  # More blocking

# Good: Fast handler with async work
async def fast_handler(event):
    await queue.put(event)  # Non-blocking enqueue

# Good: Batched processing
class BatchProcessor:
    def __init__(self):
        self.batch = []

    def handler(self, event):
        self.batch.append(event)
        if len(self.batch) >= 10:
            process_batch(self.batch)
            self.batch = []
```

## Best Practices

1. **Keep Handlers Fast**: Minimize work in event handlers
2. **Use Replay for Debugging**: Enable replay buffer in development
3. **Subscribe Early**: Subscribe before running graph
4. **Unsubscribe When Done**: Clean up subscriptions to prevent leaks
5. **Filter Events**: Only subscribe to events you need
6. **Separate Concerns**: Use events for observation, not control flow
7. **Test Event Handlers**: Unit test handlers independently
8. **Document Custom Events**: Document custom event schemas

## Common Pitfalls

### 1. Forgetting to Subscribe Before Run

```python
# Bad: Subscribe after run (misses events)
result = await graph.run()
event_bus.subscribe('node_finished', handler)  # Too late!

# Good: Subscribe before run
event_bus.subscribe('node_finished', handler)
result = await graph.run()
```

### 2. Blocking in Handlers

```python
# Bad: Blocking operation in handler
def handler(event):
    time.sleep(1)  # Blocks event publication!
    send_email_sync()  # More blocking

# Good: Async operations
async def handler(event):
    await asyncio.sleep(1)
    await send_email_async()
```

### 3. Not Handling Exceptions

```python
# Bad: Unhandled exception crashes handler
def handler(event):
    result = process(event['data'])  # May raise KeyError

# Good: Handle exceptions
def handler(event):
    try:
        data = event.get('data')
        if data:
            result = process(data)
    except Exception as e:
        logger.error(f"Handler error: {e}")
```

### 4. Memory Leaks from Large Replay Buffers

```python
# Bad: Huge replay buffer
event_bus = GraphEventBus(replay_buffer_size=100000)  # 100k events!

# Good: Reasonable buffer size
event_bus = GraphEventBus(replay_buffer_size=100)  # Last 100 events
```

## Testing with Events

### Unit Testing Event Handlers

```python
import pytest
from datetime import datetime

def test_handler():
    results = []

    def handler(event):
        results.append(event['event_type'])

    # Create mock event
    event = {
        'event_type': 'node_finished',
        'timestamp': datetime.now(),
        'node': 'TestNode',
        'outputs': {'result': 'done'}
    }

    # Test handler
    handler(event)

    assert len(results) == 1
    assert results[0] == 'node_finished'
```

### Integration Testing with Event Bus

```python
import pytest
from spark.graphs import Graph
from spark.graphs.event_bus import GraphEventBus

@pytest.mark.asyncio
async def test_graph_events():
    received_events = []

    def collector(event):
        received_events.append(event['event_type'])

    # Create graph with event bus
    event_bus = GraphEventBus()
    graph = Graph(start=TestNode())
    graph.event_bus = event_bus

    # Subscribe
    event_bus.subscribe('*', collector)

    # Run graph
    result = await graph.run()

    # Verify events
    assert 'graph_started' in received_events
    assert 'node_started' in received_events
    assert 'node_finished' in received_events
    assert 'graph_finished' in received_events
```

## Next Steps

- **[Telemetry](../telemetry/overview.md)**: Learn about the telemetry system
- **[Graph State](graph-state.md)**: Monitor state changes via events
- **[Execution Modes](execution-modes.md)**: Events in different execution modes
- **[Fundamentals](fundamentals.md)**: Review graph basics
