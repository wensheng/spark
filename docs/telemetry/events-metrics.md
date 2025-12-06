---
title: Events and Metrics Reference
parent: Telemetry
nav_order: 3
---
# Events and Metrics Reference

## Overview

Events and metrics complement traces and spans by capturing discrete lifecycle moments and numerical measurements. **Events** record things that happen during execution, while **metrics** track quantifiable measurements over time.

This document provides comprehensive reference for working with events and metrics in Spark's telemetry system.

## Events

### Event Model

```python
from spark.telemetry.types import Event

event = Event(
    event_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    span_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    type="node_finished",
    name="TransformNode Completed",
    timestamp=datetime(2025, 1, 15, 10, 0, 2),
    attributes={
        "node_id": "transform_1",
        "node_type": "TransformNode",
        "outputs": {"success": True, "rows": 1000},
        "execution_count": 42
    }
)
```

### Event Fields

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | str (UUID) | Unique identifier for the event |
| `trace_id` | str (UUID) | Parent trace ID (optional) |
| `span_id` | str (UUID) | Parent span ID (optional) |
| `type` | str | Event type category for filtering |
| `name` | str | Human-readable event name |
| `timestamp` | datetime | When the event occurred |
| `attributes` | dict | Event-specific metadata |

### Event Types

Spark uses event types to categorize lifecycle moments:

**Graph Events**:
- `graph_started` - Graph execution begins
- `graph_finished` - Graph execution completes successfully
- `graph_failed` - Graph execution fails
- `graph_cancelled` - Graph execution is cancelled

**Node Events**:
- `node_started` - Node execution begins
- `node_finished` - Node execution completes successfully
- `node_failed` - Node execution fails
- `node_retry` - Node retry attempt

**RPC Events**:
- `rpc_request_received` - RPC request received
- `rpc_request_completed` - RPC request completed
- `rpc_notification_sent` - Server notification sent
- `rpc_connection_opened` - WebSocket connection opened
- `rpc_connection_closed` - WebSocket connection closed

**Agent Events**:
- `agent_started` - Agent processing begins
- `agent_step` - Agent reasoning step
- `agent_tool_call` - Tool execution
- `agent_finished` - Agent processing completes
- `llm_api_call` - LLM API invocation

**Custom Events**:
- `checkpoint` - Custom checkpoint reached
- `milestone` - Business milestone
- `alert` - Alert condition detected
- User-defined types

### Automatic Event Recording

Spark automatically records events for standard lifecycle moments:

```python
from spark.graphs import Graph
from spark.nodes import Node
from spark.telemetry import TelemetryConfig

class MyNode(Node):
    async def process(self, context):
        # node_started event recorded automatically
        result = await self.do_work()
        # node_finished event recorded automatically
        return {"result": result}

# Configure telemetry
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    enable_events=True
)

# Create and run graph
graph = Graph(start=MyNode(), telemetry_config=config)
await graph.run()

# Events recorded automatically:
# - graph_started
# - node_started (MyNode)
# - node_finished (MyNode)
# - graph_finished
```

### Manual Event Recording

Record custom events for application-specific moments:

```python
from spark.telemetry import TelemetryManager
from spark.nodes import Node

class DataProcessingNode(Node):
    async def process(self, context):
        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        # Load data
        data = await self.load_data()

        # Record checkpoint event
        manager.record_event(
            trace_id=trace_id,
            event_type="checkpoint",
            name="Data Loaded",
            attributes={
                "rows": len(data),
                "source": "database",
                "load_time": 1.23
            }
        )

        # Validate data
        errors = self.validate(data)

        if errors:
            # Record alert event
            manager.record_event(
                trace_id=trace_id,
                event_type="alert",
                name="Validation Errors Detected",
                attributes={
                    "error_count": len(errors),
                    "severity": "warning",
                    "errors": errors[:10]  # First 10 errors
                }
            )

        # Transform data
        result = self.transform(data)

        # Record milestone event
        manager.record_event(
            trace_id=trace_id,
            event_type="milestone",
            name="Data Processing Complete",
            attributes={
                "input_rows": len(data),
                "output_rows": len(result),
                "transformation": "normalize"
            }
        )

        return {"result": result}
```

### Event Recording API

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()

# Basic event
manager.record_event(
    trace_id=trace_id,
    event_type="custom",
    name="Something Happened"
)

# Event with attributes
manager.record_event(
    trace_id=trace_id,
    event_type="checkpoint",
    name="Processing Milestone",
    attributes={
        "stage": "validation",
        "progress": 0.45,
        "items_processed": 450
    }
)

# Event with span association
manager.record_event(
    trace_id=trace_id,
    span_id=span_id,
    event_type="alert",
    name="High Memory Usage",
    attributes={
        "memory_mb": 8192,
        "threshold_mb": 6144
    }
)

# Event without trace (global event)
manager.record_event(
    event_type="system",
    name="Cache Cleared",
    attributes={"cache_size_mb": 512}
)
```

## Metrics

### Metric Model

```python
from spark.telemetry.types import Metric

metric = Metric(
    metric_id="8d9e7789-8536-51ef-a55c-f18fc2g01bf8",
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    name="node_execution_count",
    value=42.0,
    unit="count",
    aggregation_type="counter",
    timestamp=datetime(2025, 1, 15, 10, 0, 2),
    attributes={
        "node_id": "transform_1",
        "graph_id": "production_workflow"
    }
)
```

### Metric Fields

| Field | Type | Description |
|-------|------|-------------|
| `metric_id` | str (UUID) | Unique identifier for the metric |
| `trace_id` | str (UUID) | Parent trace ID (optional) |
| `name` | str | Metric name (e.g., `api_cost`, `execution_count`) |
| `value` | float | Numerical value |
| `unit` | str | Measurement unit (e.g., `count`, `seconds`, `dollars`) |
| `aggregation_type` | str | How values combine: `gauge`, `counter`, `histogram` |
| `timestamp` | datetime | When the metric was recorded |
| `attributes` | dict | Metric dimensions/labels |

### Aggregation Types

**Counter**: Cumulative value that only increases.
```python
# Total API calls
manager.record_metric(
    name="api_calls_total",
    value=1,
    unit="count",
    aggregation_type="counter"
)
```

**Gauge**: Point-in-time value that can increase or decrease.
```python
# Current queue depth
manager.record_metric(
    name="queue_depth",
    value=42,
    unit="items",
    aggregation_type="gauge"
)
```

**Histogram**: Distribution of values (for percentile analysis).
```python
# Response time distribution
manager.record_metric(
    name="response_time",
    value=0.523,
    unit="seconds",
    aggregation_type="histogram"
)
```

### Automatic Metric Recording

Spark automatically records metrics for standard operations:

**Node Metrics**:
- `node_execution_count` - Number of executions per node
- `node_duration` - Node execution duration
- `node_error_count` - Number of failures per node

**Graph Metrics**:
- `graph_execution_count` - Number of graph runs
- `graph_duration` - Total graph execution time

**Agent Metrics**:
- `llm_input_tokens` - LLM input token count
- `llm_output_tokens` - LLM output token count
- `llm_api_cost` - LLM API cost in dollars
- `tool_execution_count` - Tool invocation count

```python
from spark.graphs import Graph
from spark.telemetry import TelemetryConfig

# Configure telemetry
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    enable_metrics=True
)

# Run graph - metrics collected automatically
graph = Graph(start=my_node, telemetry_config=config)
await graph.run()

# Query metrics
manager = TelemetryManager.get_instance()
await manager.flush()

metrics = await manager.query_metrics(name="node_duration")
for metric in metrics:
    print(f"{metric.attributes['node_id']}: {metric.value:.3f}s")
```

### Manual Metric Recording

Record custom metrics for application-specific measurements:

```python
from spark.telemetry import TelemetryManager
from spark.nodes import Node

class CacheNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache_hits = 0
        self.cache_misses = 0

    async def process(self, context):
        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        key = context.inputs.content.get('key')

        if key in self.cache:
            self.cache_hits += 1
            result = self.cache[key]

            # Record cache hit
            manager.record_metric(
                name="cache_hits",
                value=1,
                unit="count",
                aggregation_type="counter",
                trace_id=trace_id,
                attributes={"node_id": self.node_id}
            )
        else:
            self.cache_misses += 1
            result = await self.fetch_data(key)
            self.cache[key] = result

            # Record cache miss
            manager.record_metric(
                name="cache_misses",
                value=1,
                unit="count",
                aggregation_type="counter",
                trace_id=trace_id,
                attributes={"node_id": self.node_id}
            )

        # Record cache hit rate
        total = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total if total > 0 else 0

        manager.record_metric(
            name="cache_hit_rate",
            value=hit_rate,
            unit="ratio",
            aggregation_type="gauge",
            trace_id=trace_id,
            attributes={"node_id": self.node_id}
        )

        return {"result": result}
```

### Metric Recording API

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()

# Counter metric
manager.record_metric(
    name="requests_total",
    value=1,
    unit="count",
    aggregation_type="counter",
    trace_id=trace_id,
    attributes={
        "endpoint": "/api/process",
        "method": "POST"
    }
)

# Gauge metric
manager.record_metric(
    name="memory_usage_mb",
    value=4096,
    unit="megabytes",
    aggregation_type="gauge",
    attributes={
        "host": "worker-01"
    }
)

# Histogram metric
manager.record_metric(
    name="query_duration",
    value=0.234,
    unit="seconds",
    aggregation_type="histogram",
    trace_id=trace_id,
    attributes={
        "query_type": "SELECT",
        "table": "users"
    }
)

# Metric without trace (global metric)
manager.record_metric(
    name="system_cpu_percent",
    value=45.2,
    unit="percent",
    aggregation_type="gauge"
)
```

## Common Metric Patterns

### Rate Metrics

Track operations per time period:

```python
import time

class RateLimitedNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.request_count = 0
        self.window_start = time.time()

    async def process(self, context):
        manager = TelemetryManager.get_instance()
        self.request_count += 1

        # Check if window expired (1 minute)
        now = time.time()
        if now - self.window_start >= 60:
            # Record requests per minute
            manager.record_metric(
                name="requests_per_minute",
                value=self.request_count,
                unit="count",
                aggregation_type="gauge",
                attributes={"node_id": self.node_id}
            )

            # Reset window
            self.request_count = 0
            self.window_start = now

        # Process request
        result = await self.do_work()
        return {"result": result}
```

### Percentile Metrics

Track value distributions:

```python
class LatencyTracker(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.latencies = []

    async def process(self, context):
        manager = TelemetryManager.get_instance()

        start = time.time()
        result = await self.do_work()
        latency = time.time() - start

        # Record individual latency (histogram)
        manager.record_metric(
            name="operation_latency",
            value=latency,
            unit="seconds",
            aggregation_type="histogram",
            attributes={"node_id": self.node_id}
        )

        # Calculate and record percentiles periodically
        self.latencies.append(latency)
        if len(self.latencies) >= 100:
            sorted_latencies = sorted(self.latencies)

            manager.record_metric(
                name="operation_latency_p50",
                value=sorted_latencies[50],
                unit="seconds",
                aggregation_type="gauge",
                attributes={"node_id": self.node_id}
            )

            manager.record_metric(
                name="operation_latency_p95",
                value=sorted_latencies[95],
                unit="seconds",
                aggregation_type="gauge",
                attributes={"node_id": self.node_id}
            )

            manager.record_metric(
                name="operation_latency_p99",
                value=sorted_latencies[99],
                unit="seconds",
                aggregation_type="gauge",
                attributes={"node_id": self.node_id}
            )

            # Reset after reporting
            self.latencies = []

        return {"result": result}
```

### Cost Metrics

Track operational costs:

```python
from spark.agents import Agent

class CostTrackingNode(Node):
    async def process(self, context):
        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        # Use agent with cost tracking
        agent = Agent(config=agent_config)
        result = await agent.run(prompt)

        # Get cost statistics
        stats = agent.get_cost_stats()

        # Record cost metrics
        manager.record_metric(
            name="llm_api_cost",
            value=stats.total_cost,
            unit="dollars",
            aggregation_type="counter",
            trace_id=trace_id,
            attributes={
                "model": agent_config.model.model_id,
                "node_id": self.node_id
            }
        )

        manager.record_metric(
            name="llm_input_tokens",
            value=stats.total_input_tokens,
            unit="count",
            aggregation_type="counter",
            trace_id=trace_id
        )

        manager.record_metric(
            name="llm_output_tokens",
            value=stats.total_output_tokens,
            unit="count",
            aggregation_type="counter",
            trace_id=trace_id
        )

        return {"result": result}
```

### Resource Metrics

Track system resource usage:

```python
import psutil

class ResourceMonitorNode(Node):
    async def process(self, context):
        manager = TelemetryManager.get_instance()

        # Record CPU usage
        manager.record_metric(
            name="cpu_percent",
            value=psutil.cpu_percent(),
            unit="percent",
            aggregation_type="gauge",
            attributes={"host": "worker-01"}
        )

        # Record memory usage
        memory = psutil.virtual_memory()
        manager.record_metric(
            name="memory_used_mb",
            value=memory.used / 1024 / 1024,
            unit="megabytes",
            aggregation_type="gauge",
            attributes={"host": "worker-01"}
        )

        manager.record_metric(
            name="memory_percent",
            value=memory.percent,
            unit="percent",
            aggregation_type="gauge",
            attributes={"host": "worker-01"}
        )

        # Perform actual work
        result = await self.do_work()
        return {"result": result}
```

## Querying Events

### Query All Events

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()
await manager.flush()

# Get all events
events = await manager.query_events(limit=100)

for event in events:
    print(f"{event.timestamp}: {event.name} ({event.type})")
```

### Filter by Event Type

```python
# Get node failure events
failures = await manager.query_events(event_type="node_failed")

for event in failures:
    print(f"Node failed: {event.attributes['node_id']}")
    print(f"  Error: {event.attributes.get('error')}")
    print(f"  Trace: {event.trace_id}")
```

### Filter by Time Range

```python
from datetime import datetime, timedelta

# Get events from last hour
start_time = datetime.now() - timedelta(hours=1)
recent_events = await manager.query_events(
    start_time=start_time,
    limit=1000
)
```

### Filter by Trace

```python
# Get all events for a specific trace
trace_events = await manager.query_events(trace_id=trace_id)

# Sort by timestamp
trace_events_sorted = sorted(trace_events, key=lambda e: e.timestamp)

for event in trace_events_sorted:
    print(f"{event.timestamp}: {event.name}")
```

### Custom Event Analysis

```python
# Find checkpoint events
checkpoints = await manager.query_events(event_type="checkpoint")

# Group by trace
from collections import defaultdict
checkpoints_by_trace = defaultdict(list)
for event in checkpoints:
    checkpoints_by_trace[event.trace_id].append(event)

# Find traces with incomplete checkpoints
expected_checkpoints = {"data_loaded", "data_validated", "data_saved"}

for trace_id, events in checkpoints_by_trace.items():
    checkpoint_names = {e.attributes.get("stage") for e in events}
    missing = expected_checkpoints - checkpoint_names

    if missing:
        print(f"Trace {trace_id} missing checkpoints: {missing}")
```

## Querying Metrics

### Query All Metrics

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()
await manager.flush()

# Get all metrics
metrics = await manager.query_metrics(limit=100)

for metric in metrics:
    print(f"{metric.name}: {metric.value} {metric.unit}")
```

### Filter by Metric Name

```python
# Get cache hit metrics
cache_hits = await manager.query_metrics(name="cache_hits")

total_hits = sum(m.value for m in cache_hits)
print(f"Total cache hits: {total_hits}")
```

### Aggregate Metrics

```python
# Get all latency metrics
latencies = await manager.query_metrics(name="operation_latency")

if latencies:
    values = [m.value for m in latencies]
    avg_latency = sum(values) / len(values)
    min_latency = min(values)
    max_latency = max(values)

    print(f"Latency statistics:")
    print(f"  Count: {len(values)}")
    print(f"  Min: {min_latency:.3f}s")
    print(f"  Max: {max_latency:.3f}s")
    print(f"  Avg: {avg_latency:.3f}s")
```

### Time Series Analysis

```python
# Get metrics over time
from datetime import datetime, timedelta

start_time = datetime.now() - timedelta(hours=1)
cpu_metrics = await manager.query_metrics(
    name="cpu_percent",
    start_time=start_time
)

# Group by 5-minute buckets
bucket_size = timedelta(minutes=5)
buckets = {}

for metric in cpu_metrics:
    bucket = metric.timestamp.replace(
        minute=(metric.timestamp.minute // 5) * 5,
        second=0,
        microsecond=0
    )
    buckets.setdefault(bucket, []).append(metric.value)

# Calculate average per bucket
for bucket, values in sorted(buckets.items()):
    avg = sum(values) / len(values)
    print(f"{bucket}: {avg:.1f}%")
```

### Multi-Dimensional Analysis

```python
# Analyze cache performance by node
cache_hits = await manager.query_metrics(name="cache_hits")
cache_misses = await manager.query_metrics(name="cache_misses")

# Group by node
node_stats = {}

for metric in cache_hits:
    node_id = metric.attributes.get("node_id")
    node_stats.setdefault(node_id, {"hits": 0, "misses": 0})
    node_stats[node_id]["hits"] += metric.value

for metric in cache_misses:
    node_id = metric.attributes.get("node_id")
    node_stats.setdefault(node_id, {"hits": 0, "misses": 0})
    node_stats[node_id]["misses"] += metric.value

# Calculate hit rates
for node_id, stats in node_stats.items():
    total = stats["hits"] + stats["misses"]
    hit_rate = stats["hits"] / total if total > 0 else 0
    print(f"{node_id}: {hit_rate:.1%} hit rate ({stats['hits']} hits, {stats['misses']} misses)")
```

## Best Practices

### Event Guidelines

**Use events for discrete moments**:
```python
# Good: specific, meaningful events
manager.record_event(
    event_type="checkpoint",
    name="Data Validation Complete",
    attributes={"rows_validated": 1000}
)

# Bad: too frequent
for item in items:
    manager.record_event(event_type="item_processed", name=f"Item {item}")
```

**Include relevant context**:
```python
# Good: rich context
manager.record_event(
    event_type="alert",
    name="High Error Rate Detected",
    attributes={
        "error_rate": 0.15,
        "threshold": 0.10,
        "time_window": "5m",
        "affected_service": "api"
    }
)

# Bad: missing context
manager.record_event(event_type="alert", name="High Error Rate")
```

**Use consistent event types**:
```python
# Define event types as constants
CHECKPOINT = "checkpoint"
ALERT = "alert"
MILESTONE = "milestone"

manager.record_event(event_type=CHECKPOINT, name="Stage 1 Complete")
```

### Metric Guidelines

**Choose appropriate aggregation types**:
```python
# Counter: cumulative values
manager.record_metric(name="requests_total", value=1, aggregation_type="counter")

# Gauge: point-in-time values
manager.record_metric(name="queue_depth", value=42, aggregation_type="gauge")

# Histogram: distributions
manager.record_metric(name="response_time", value=0.5, aggregation_type="histogram")
```

**Use consistent naming**:
```python
# Good: consistent naming convention
"requests_total"
"requests_per_second"
"request_duration_seconds"

# Bad: inconsistent
"total_requests"
"rps"
"req_time_ms"
```

**Include units in names or metadata**:
```python
# Option 1: Include in name
manager.record_metric(name="memory_used_mb", value=4096, unit="megabytes")

# Option 2: Use standard units
manager.record_metric(name="memory_used", value=4096, unit="megabytes")
```

**Use attributes for dimensions**:
```python
# Good: dimensions in attributes
manager.record_metric(
    name="http_requests_total",
    value=1,
    aggregation_type="counter",
    attributes={
        "method": "POST",
        "endpoint": "/api/process",
        "status": 200
    }
)

# Bad: dimensions in metric name
manager.record_metric(name="http_requests_post_api_process_200", value=1)
```

### Performance Considerations

**Batch event recording**:
```python
# Collect events in memory, flush periodically
events_buffer = []

for item in items:
    events_buffer.append({
        "type": "item_processed",
        "attributes": {"item_id": item.id}
    })

# Flush in batch
for event_data in events_buffer:
    manager.record_event(**event_data)
```

**Sample high-frequency metrics**:
```python
import random

# Sample 10% of requests
if random.random() < 0.1:
    manager.record_metric(name="request_latency", value=latency)
```

**Disable when not needed**:
```python
# Disable events in production if not needed
config = TelemetryConfig.create_postgresql(
    connection_string="...",
    enable_events=False,  # Reduce overhead
    enable_metrics=True
)
```

## Next Steps

- **[Querying Telemetry](querying.md)**: Advanced query patterns for events and metrics
- **[Telemetry Patterns](patterns.md)**: Common analysis patterns and recipes
- **[Traces and Spans](traces-spans.md)**: Learn about traces and spans
- **[Backends Reference](backends.md)**: Backend-specific features for events and metrics
