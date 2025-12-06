---
title: Telemetry
nav_order: 9
---
# Telemetry System Overview

## Introduction

Spark's telemetry system provides comprehensive observability for graph and node execution. It automatically captures execution traces, spans, events, and metrics, enabling performance analysis, debugging, monitoring, and autonomous improvement through the RSI (Recursive Self-Improvement) system.

## Purpose and Benefits

### Why Telemetry?

**Performance Analysis**: Identify bottlenecks and slow operations in your workflows.

**Debugging**: Understand execution flow and pinpoint failures with detailed traces.

**Monitoring**: Track system health, error rates, and resource usage in production.

**Cost Tracking**: Monitor LLM API costs and optimize spending.

**RSI Foundation**: Telemetry data powers Spark's autonomous self-improvement capabilities.

**Distributed Tracing**: Track execution across RPC boundaries and microservices.

### Key Benefits

- **Automatic instrumentation**: Zero-code observability for all graphs and nodes
- **Low overhead**: Configurable sampling and buffering for production use
- **Multiple backends**: Memory, SQLite, PostgreSQL, and OTLP for different use cases
- **Rich data model**: Comprehensive trace, span, event, and metric capture
- **Query API**: Flexible querying for analysis and monitoring
- **Standards-based**: Compatible with OpenTelemetry ecosystem

## Telemetry Data Model

Spark's telemetry system captures four types of data:

### Traces

A **trace** represents a complete workflow execution from start to finish.

```python
Trace(
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    name="production_workflow",
    start_time=datetime(2025, 1, 15, 10, 0, 0),
    end_time=datetime(2025, 1, 15, 10, 0, 5),
    duration=5.123,
    status="completed",
    attributes={
        "graph_id": "production_workflow",
        "graph_version": "1.0.0",
        "environment": "production"
    }
)
```

**Key properties**:
- `trace_id`: Unique identifier for the entire workflow execution
- `name`: Human-readable trace name
- `duration`: Total execution time in seconds
- `status`: Execution status (`completed`, `failed`, `cancelled`)
- `attributes`: Custom metadata as key-value pairs

### Spans

A **span** represents an individual operation within a trace (e.g., node execution, subgraph run).

```python
Span(
    span_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    parent_span_id="6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    name="TransformNode",
    kind="INTERNAL",
    start_time=datetime(2025, 1, 15, 10, 0, 1),
    end_time=datetime(2025, 1, 15, 10, 0, 2),
    duration=1.234,
    status="completed",
    attributes={
        "node_id": "transform_1",
        "node_type": "TransformNode",
        "input_size": 1024
    }
)
```

**Key properties**:
- `span_id`: Unique identifier for this operation
- `parent_span_id`: Links to parent span for hierarchy
- `kind`: Span type (`INTERNAL`, `CLIENT`, `SERVER`)
- `duration`: Operation execution time in seconds
- `status`: Operation status with optional error info

### Events

An **event** represents a discrete lifecycle moment (graph started, node finished, etc.).

```python
Event(
    event_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    span_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    type="node_finished",
    name="TransformNode Completed",
    timestamp=datetime(2025, 1, 15, 10, 0, 2),
    attributes={
        "node_id": "transform_1",
        "outputs": {"success": True}
    }
)
```

**Key properties**:
- `event_id`: Unique identifier for the event
- `type`: Event type category (for filtering)
- `name`: Human-readable event name
- `timestamp`: When the event occurred
- `attributes`: Event-specific metadata

### Metrics

A **metric** represents numerical measurements (execution counts, durations, custom values).

```python
Metric(
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

**Key properties**:
- `name`: Metric name (e.g., `execution_count`, `api_cost`)
- `value`: Numerical value
- `unit`: Measurement unit (`count`, `seconds`, `dollars`, etc.)
- `aggregation_type`: How values combine (`gauge`, `counter`, `histogram`)

## TelemetryManager

The `TelemetryManager` is a singleton that coordinates all telemetry collection and export.

```python
from spark.telemetry import TelemetryManager

# Get singleton instance
manager = TelemetryManager.get_instance()

# Start a trace
trace = manager.start_trace("my_operation", attributes={"user": "alice"})

# Create a span within the trace
async with manager.start_span("step1", trace.trace_id) as span:
    span.set_attribute("complexity", "high")
    # ... do work ...

# Record an event
manager.record_event(
    trace_id=trace.trace_id,
    event_type="milestone",
    name="checkpoint_reached",
    attributes={"checkpoint": "data_loaded"}
)

# Record a metric
manager.record_metric(
    name="cache_hits",
    value=42,
    unit="count",
    trace_id=trace.trace_id
)

# End the trace
manager.end_trace(trace.trace_id, status="completed")

# Flush buffered data
await manager.flush()
```

### Manager Responsibilities

1. **Collection**: Gather telemetry data from graphs and nodes
2. **Buffering**: Queue data for efficient batch export
3. **Export**: Send data to configured backend(s)
4. **Querying**: Provide API for retrieving telemetry data
5. **Lifecycle**: Manage initialization and cleanup

## TelemetryConfig

Configure telemetry behavior with `TelemetryConfig`:

```python
from spark.telemetry import TelemetryConfig

# Create configuration for SQLite backend
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,          # Sample 100% of traces
    buffer_size=100,             # Buffer 100 items before export
    export_interval=5.0,         # Export every 5 seconds
    enable_metrics=True,         # Collect metrics
    enable_events=True,          # Collect events
    enable_traces=True,          # Collect traces/spans
    metadata={                   # Custom metadata
        "environment": "production",
        "version": "1.0.0"
    }
)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `backend` | str | "memory" | Backend type (`memory`, `sqlite`, `postgresql`, `otlp`) |
| `sampling_rate` | float | 1.0 | Fraction of traces to collect (0.0-1.0) |
| `buffer_size` | int | 100 | Items to buffer before export |
| `export_interval` | float | 5.0 | Seconds between exports |
| `enable_traces` | bool | True | Collect traces and spans |
| `enable_events` | bool | True | Collect events |
| `enable_metrics` | bool | True | Collect metrics |
| `metadata` | dict | {} | Global metadata for all telemetry |

### Backend-Specific Configs

```python
# Memory backend (development/testing)
config = TelemetryConfig.create_memory(
    sampling_rate=1.0
)

# SQLite backend (local persistence)
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)

# PostgreSQL backend (production)
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@localhost/telemetry",
    sampling_rate=0.1  # Sample 10% in production
)

# OTLP backend (observability platforms)
config = TelemetryConfig.create_otlp(
    endpoint="http://localhost:4317",
    sampling_rate=0.1
)
```

See [Backends Reference](backends.md) for detailed backend configuration.

## Automatic Instrumentation

Spark automatically instruments graphs and nodes when telemetry is enabled:

```python
from spark.graphs import Graph
from spark.nodes import Node
from spark.telemetry import TelemetryConfig

# Define a simple node
class ProcessNode(Node):
    async def process(self, context):
        # Your logic here
        return {"success": True}

# Create telemetry config
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)

# Create graph with telemetry
graph = Graph(
    start=ProcessNode(),
    telemetry_config=telemetry_config
)

# Run graph - telemetry collected automatically!
result = await graph.run()
```

### What Gets Instrumented

**Graph Execution**:
- Trace created for entire graph run
- Graph start/finish events
- Top-level span for graph execution

**Node Execution**:
- Span created for each node execution
- Node start/finish/failed events
- Node execution metrics (duration, count)
- Node outputs captured in attributes

**RPC Calls**:
- CLIENT spans for outgoing RPC calls
- SERVER spans for incoming RPC requests
- Request/response payloads in attributes

**Agent Operations**:
- LLM API calls (model, tokens, cost)
- Tool executions
- Reasoning steps

## Manual Instrumentation

Add custom telemetry to your code:

### Custom Spans

```python
from spark.telemetry import TelemetryManager

class MyNode(Node):
    async def process(self, context):
        manager = TelemetryManager.get_instance()

        # Get trace ID from context
        trace_id = context.metadata.get('trace_id')

        # Create custom span
        async with manager.start_span(
            "database_query",
            trace_id,
            attributes={"query_type": "select"}
        ) as span:
            result = await self.query_database()
            span.set_attribute("rows_returned", len(result))

        return {"data": result}
```

### Custom Events

```python
manager = TelemetryManager.get_instance()

manager.record_event(
    trace_id=trace_id,
    event_type="checkpoint",
    name="Data Validation Complete",
    attributes={
        "records_validated": 1000,
        "errors_found": 5
    }
)
```

### Custom Metrics

```python
manager = TelemetryManager.get_instance()

# Counter metric
manager.record_metric(
    name="api_calls_total",
    value=1,
    unit="count",
    aggregation_type="counter",
    trace_id=trace_id
)

# Gauge metric
manager.record_metric(
    name="queue_depth",
    value=42,
    unit="items",
    aggregation_type="gauge",
    trace_id=trace_id
)

# Histogram metric
manager.record_metric(
    name="response_time",
    value=0.523,
    unit="seconds",
    aggregation_type="histogram",
    trace_id=trace_id
)
```

## Performance Considerations

### Sampling

Reduce overhead by sampling traces in production:

```python
# Sample 10% of traces
config = TelemetryConfig.create_postgresql(
    connection_string="...",
    sampling_rate=0.1  # Only 10% of traces collected
)
```

**When to sample**:
- High-volume production systems
- Cost-sensitive environments
- When full trace capture is unnecessary

**When NOT to sample**:
- Development and testing
- Critical workflows requiring full observability
- RSI system operation (requires comprehensive data)

### Buffering

Control export frequency to balance freshness and overhead:

```python
config = TelemetryConfig(
    backend="postgresql",
    buffer_size=1000,        # Large buffer
    export_interval=60.0,    # Export every minute
    # ... other config
)
```

**Tuning guidelines**:
- **Low latency**: Small buffer (10-50), short interval (1-5s)
- **High throughput**: Large buffer (500-1000), longer interval (30-60s)
- **Balanced**: Default values (buffer_size=100, export_interval=5.0)

### Disabling Telemetry Types

Disable specific telemetry types to reduce overhead:

```python
config = TelemetryConfig(
    backend="sqlite",
    enable_traces=True,      # Keep traces/spans
    enable_events=False,     # Disable events
    enable_metrics=False,    # Disable metrics
)
```

### Backend Performance

Different backends have different performance characteristics:

| Backend | Write Speed | Query Speed | Best For |
|---------|-------------|-------------|----------|
| Memory | Fastest | Fastest | Testing, development |
| SQLite | Fast | Fast | Local, single-machine |
| PostgreSQL | Good | Good | Production, multi-machine |
| OTLP | Good | N/A | External platforms |

See [Backends Reference](backends.md) for detailed performance comparison.

### Overhead Estimates

Typical overhead with default settings:

- **Memory backend**: < 1% overhead
- **SQLite backend**: 1-3% overhead
- **PostgreSQL backend**: 2-5% overhead
- **OTLP backend**: 3-8% overhead

Overhead increases with:
- Higher sampling rates
- Smaller buffer sizes
- Shorter export intervals
- More custom instrumentation

## Integration with RSI

Telemetry is the foundation for Spark's Recursive Self-Improvement system:

```python
from spark.telemetry import TelemetryConfig
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig
from spark.models.openai import OpenAIModel

# 1. Enable telemetry on production graph
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0  # RSI needs comprehensive data
)

production_graph = Graph(
    start=my_node,
    telemetry_config=telemetry_config
)

# 2. Run production graph to collect data
for i in range(100):
    await production_graph.run()

# 3. RSI analyzes telemetry for improvements
model = OpenAIModel(model_id="gpt-4o")
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="production_workflow",
    analysis_window_hours=24
)

rsi_graph = RSIMetaGraph(config=rsi_config)
result = await rsi_graph.run_single_cycle()
```

RSI uses telemetry for:
- **Performance analysis**: Identify bottlenecks and slow nodes
- **Error detection**: Find high-failure operations
- **Cost tracking**: Optimize expensive operations
- **Pattern recognition**: Learn from execution history
- **Validation**: Measure improvement impact

See [RSI Documentation](../rsi/overview.md) for more details.

## Next Steps

- **[Backends Reference](backends.md)**: Detailed backend configuration and selection
- **[Traces and Spans](traces-spans.md)**: Deep dive into trace/span model
- **[Events and Metrics](events-metrics.md)**: Event and metric reference
- **[Querying Telemetry](querying.md)**: Query API and examples
- **[Telemetry Patterns](patterns.md)**: Common patterns and best practices

## Quick Reference

### Complete Example

```python
from spark.telemetry import TelemetryConfig, TelemetryManager
from spark.graphs import Graph
from spark.nodes import Node

# Configure telemetry
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    enable_metrics=True,
    enable_events=True
)

# Create graph with telemetry
class MyNode(Node):
    async def process(self, context):
        return {"result": "success"}

graph = Graph(start=MyNode(), telemetry_config=config)

# Run graph (automatic instrumentation)
result = await graph.run()

# Query telemetry
manager = TelemetryManager.get_instance()
await manager.flush()

traces = await manager.query_traces(limit=10)
for trace in traces:
    print(f"Trace: {trace.name}, Duration: {trace.duration:.3f}s")

    spans = await manager.query_spans(trace_id=trace.trace_id)
    for span in spans:
        print(f"  Span: {span.name}, Duration: {span.duration:.3f}s")
```

### API Quick Reference

```python
# TelemetryManager
manager = TelemetryManager.get_instance()
trace = manager.start_trace(name, attributes={})
manager.end_trace(trace_id, status="completed")
async with manager.start_span(name, trace_id) as span: ...
manager.record_event(trace_id, event_type, name, attributes={})
manager.record_metric(name, value, unit, trace_id=None)
await manager.flush()

# Querying
traces = await manager.query_traces(limit=10, status="completed")
spans = await manager.query_spans(trace_id=trace_id, kind="INTERNAL")
events = await manager.query_events(event_type="node_failed")
metrics = await manager.query_metrics(name="api_cost")
```
