---
title: Traces and Spans
parent: Telemetry
nav_order: 2
---
# Traces and Spans
---

Traces and spans form the hierarchical structure for tracking workflow execution in Spark. A **trace** represents a complete workflow execution from start to finish, while **spans** represent individual operations within that trace.

This document provides comprehensive reference for working with traces and spans in Spark's telemetry system.

## Trace Structure

### Trace Model

```python
from spark.telemetry.types import Trace

trace = Trace(
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    name="production_workflow",
    start_time=datetime(2025, 1, 15, 10, 0, 0),
    end_time=datetime(2025, 1, 15, 10, 0, 5),
    duration=5.123,
    status="completed",
    attributes={
        "graph_id": "production_workflow",
        "graph_version": "1.0.0",
        "environment": "production",
        "user_id": "alice",
        "request_id": "req_abc123"
    }
)
```

### Trace Fields

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | str (UUID) | Unique identifier for the trace |
| `name` | str | Human-readable trace name |
| `start_time` | datetime | When the trace started |
| `end_time` | datetime | When the trace ended (None if ongoing) |
| `duration` | float | Total execution time in seconds (None if ongoing) |
| `status` | str | Trace status: `started`, `completed`, `failed`, `cancelled` |
| `attributes` | dict | Custom metadata as key-value pairs |

### Trace Lifecycle

```
┌─────────┐     ┌──────────┐     ┌───────────┐
│ Started │ ──> │ Running  │ ──> │ Completed │
└─────────┘     └──────────┘     └───────────┘
                      │
                      │ (on error)
                      ↓
                ┌──────────┐
                │  Failed  │
                └──────────┘
```

**Status Values**:

- `started`: Trace has begun, execution ongoing
- `completed`: Trace finished successfully
- `failed`: Trace terminated with error
- `cancelled`: Trace was explicitly cancelled

## Span Structure

### Span Model

```python
from spark.telemetry.types import Span, SpanKind

span = Span(
    span_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    trace_id="550e8400-e29b-41d4-a716-446655440000",
    parent_span_id="6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    name="TransformNode",
    kind=SpanKind.INTERNAL,
    start_time=datetime(2025, 1, 15, 10, 0, 1),
    end_time=datetime(2025, 1, 15, 10, 0, 2),
    duration=1.234,
    status="completed",
    status_message=None,
    attributes={
        "node_id": "transform_1",
        "node_type": "TransformNode",
        "input_size": 1024,
        "output_size": 2048
    }
)
```

### Span Fields

| Field | Type | Description |
|-------|------|-------------|
| `span_id` | str (UUID) | Unique identifier for the span |
| `trace_id` | str (UUID) | Parent trace ID |
| `parent_span_id` | str (UUID) | Parent span ID (None for root spans) |
| `name` | str | Human-readable span name |
| `kind` | SpanKind | Span type (see below) |
| `start_time` | datetime | When the span started |
| `end_time` | datetime | When the span ended (None if ongoing) |
| `duration` | float | Execution time in seconds (None if ongoing) |
| `status` | str | Span status: `started`, `completed`, `failed` |
| `status_message` | str | Error message if status is `failed` |
| `attributes` | dict | Custom metadata as key-value pairs |

### Span Kinds

Spans are categorized by their role in the workflow:

```python
from spark.telemetry.types import SpanKind

class SpanKind(str, Enum):
    INTERNAL = "INTERNAL"  # Internal operation within the application
    CLIENT = "CLIENT"      # Outgoing RPC call
    SERVER = "SERVER"      # Incoming RPC request
    PRODUCER = "PRODUCER"  # Message producer (future use)
    CONSUMER = "CONSUMER"  # Message consumer (future use)
```

**INTERNAL**:
- Default span type
- Used for node execution, subgraph runs, internal operations
- Parent and child are in the same process

**CLIENT**:
- Represents outgoing RPC call
- Created by `RemoteRpcProxyNode` when calling remote service
- Duration includes network latency

**SERVER**:
- Represents incoming RPC request
- Created by `RpcNode` when handling request
- Duration includes processing time only

Example hierarchy:
```
Trace: "workflow_execution"
  └─ Span (INTERNAL): "Graph.run"
       ├─ Span (INTERNAL): "InputNode.process"
       ├─ Span (CLIENT): "RPC call to remote service"
       └─ Span (INTERNAL): "OutputNode.process"

[Remote Service]
Trace: "remote_workflow"
  └─ Span (SERVER): "RPC request handler"
       └─ Span (INTERNAL): "ProcessData"
```

## Parent-Child Relationships

Spans form a tree structure through parent-child relationships:

```
Trace
  └─ Root Span (parent_span_id = None)
       ├─ Child Span 1 (parent_span_id = root_span_id)
       │    ├─ Grandchild Span 1.1
       │    └─ Grandchild Span 1.2
       └─ Child Span 2
            └─ Grandchild Span 2.1
```

### Visualizing Span Hierarchy

```python
from spark.telemetry import TelemetryManager

async def print_span_tree(trace_id: str, indent: int = 0):
    manager = TelemetryManager.get_instance()

    # Get all spans for trace
    spans = await manager.query_spans(trace_id=trace_id)

    # Build parent-child map
    children = {}
    root_spans = []

    for span in spans:
        if span.parent_span_id is None:
            root_spans.append(span)
        else:
            children.setdefault(span.parent_span_id, []).append(span)

    # Print tree
    def print_node(span, indent):
        print("  " * indent + f"├─ {span.name} ({span.duration:.3f}s)")
        for child in children.get(span.span_id, []):
            print_node(child, indent + 1)

    for root in root_spans:
        print_node(root, 0)

# Usage
await print_span_tree(trace_id)
```

Output:
```
├─ Graph.run (5.123s)
  ├─ InputNode.process (0.123s)
  ├─ TransformNode.process (3.456s)
    ├─ DatabaseQuery (2.100s)
    └─ DataTransformation (1.200s)
  └─ OutputNode.process (0.456s)
```

## Creating Traces

### Automatic Trace Creation

Traces are automatically created when a graph runs with telemetry enabled:

```python
from spark.graphs import Graph
from spark.telemetry import TelemetryConfig

# Configure telemetry
config = TelemetryConfig.create_sqlite(db_path="telemetry.db")

# Create graph
graph = Graph(start=my_node, telemetry_config=config)

# Run graph - trace created automatically
result = await graph.run()
```

The framework creates a trace with:
- `trace_id`: Auto-generated UUID
- `name`: Graph name or class name
- `attributes`: Graph metadata (graph_id, version, etc.)

### Manual Trace Creation

Create traces manually for custom workflows:

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()

# Start trace
trace = manager.start_trace(
    name="custom_workflow",
    attributes={
        "user_id": "alice",
        "workflow_type": "data_processing",
        "priority": "high"
    }
)

try:
    # Your workflow logic
    result = await process_data()

    # End trace successfully
    manager.end_trace(trace.trace_id, status="completed")
except Exception as e:
    # End trace with failure
    manager.end_trace(
        trace.trace_id,
        status="failed",
        error_message=str(e)
    )
```

### Trace Attributes

Use attributes to add context to traces:

```python
trace = manager.start_trace(
    name="production_workflow",
    attributes={
        # Identification
        "graph_id": "production_workflow",
        "graph_version": "2.0.0",
        "trace_type": "scheduled",

        # Context
        "user_id": "alice",
        "tenant_id": "acme_corp",
        "request_id": "req_abc123",

        # Environment
        "environment": "production",
        "region": "us-east-1",
        "host": "worker-01",

        # Business context
        "customer_id": "cust_123",
        "order_id": "ord_456",
        "transaction_amount": 99.99
    }
)
```

**Best practices**:
- Use consistent attribute names across traces
- Include identification info (user, tenant, request ID)
- Add business context for filtering and analysis
- Keep attribute values simple (strings, numbers, booleans)
- Avoid large or sensitive data in attributes

## Creating Spans

### Automatic Span Creation

Spans are automatically created for:

- **Graph execution**: One span per `graph.run()` call
- **Node execution**: One span per `node.process()` call
- **RPC calls**: CLIENT span for outgoing, SERVER span for incoming

```python
from spark.nodes import Node

class MyNode(Node):
    async def process(self, context):
        # Span automatically created for this method
        result = await self.do_work()
        return {"result": result}
```

### Manual Span Creation

Create custom spans for fine-grained tracking:

```python
from spark.telemetry import TelemetryManager
from spark.nodes import Node

class DataProcessingNode(Node):
    async def process(self, context):
        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        # Span 1: Data loading
        async with manager.start_span(
            name="load_data",
            trace_id=trace_id,
            attributes={"source": "database"}
        ) as load_span:
            data = await self.load_data()
            load_span.set_attribute("rows_loaded", len(data))

        # Span 2: Data transformation
        async with manager.start_span(
            name="transform_data",
            trace_id=trace_id,
            attributes={"transformation": "normalize"}
        ) as transform_span:
            result = await self.transform(data)
            transform_span.set_attribute("rows_processed", len(result))

        # Span 3: Data saving
        async with manager.start_span(
            name="save_data",
            trace_id=trace_id,
            attributes={"destination": "cache"}
        ) as save_span:
            await self.save(result)
            save_span.set_attribute("rows_saved", len(result))

        return {"result": result}
```

### Context Manager API

The recommended way to create spans is using the async context manager:

```python
async with manager.start_span(
    name="operation_name",
    trace_id=trace_id,
    parent_span_id=None,  # Optional, auto-detected from context
    kind=SpanKind.INTERNAL,
    attributes={"key": "value"}
) as span:
    # Operation code here
    result = await do_work()

    # Add attributes during execution
    span.set_attribute("result_size", len(result))

    # Span automatically ended when context exits
```

**Benefits**:
- Automatic span ending (even on exceptions)
- Automatic duration calculation
- Automatic status setting (failed on exception)
- Clean, readable code

### Manual Span Lifecycle

For more control, manage span lifecycle manually:

```python
manager = TelemetryManager.get_instance()

# Start span
span = manager.start_span(
    name="manual_operation",
    trace_id=trace_id,
    attributes={"type": "custom"}
)

try:
    # Do work
    result = await do_work()

    # Update span
    span.set_attribute("result", "success")

    # End span successfully
    manager.end_span(span.span_id, status="completed")
except Exception as e:
    # End span with failure
    manager.end_span(
        span.span_id,
        status="failed",
        error_message=str(e)
    )
```

### Nested Spans

Create nested spans for hierarchical operations:

```python
# Parent span
async with manager.start_span("parent_operation", trace_id) as parent_span:

    # Child span 1
    async with manager.start_span(
        "child_operation_1",
        trace_id,
        parent_span_id=parent_span.span_id
    ) as child1:
        await do_child_work_1()

    # Child span 2
    async with manager.start_span(
        "child_operation_2",
        trace_id,
        parent_span_id=parent_span.span_id
    ) as child2:
        await do_child_work_2()
```

## Span Attributes

### Common Attributes

Standard attributes for node spans:

```python
span.set_attribute("node_id", "transform_1")
span.set_attribute("node_type", "TransformNode")
span.set_attribute("node_config", config_dict)
span.set_attribute("input_size", 1024)
span.set_attribute("output_size", 2048)
span.set_attribute("processing_mode", "batch")
```

### RPC Attributes

Attributes for RPC client spans:

```python
span.set_attribute("rpc.system", "json-rpc")
span.set_attribute("rpc.service", "data_service")
span.set_attribute("rpc.method", "getData")
span.set_attribute("rpc.endpoint", "http://remote:8000")
span.set_attribute("rpc.request_id", "req_123")
span.set_attribute("rpc.response_status", "success")
```

Attributes for RPC server spans:

```python
span.set_attribute("rpc.system", "json-rpc")
span.set_attribute("rpc.method", "getData")
span.set_attribute("rpc.request_size", 256)
span.set_attribute("rpc.response_size", 1024)
span.set_attribute("rpc.client_id", "client_abc")
```

### LLM Attributes

Attributes for LLM operation spans:

```python
span.set_attribute("llm.provider", "openai")
    span.set_attribute("llm.model", "gpt-5-mini")
span.set_attribute("llm.input_tokens", 1500)
span.set_attribute("llm.output_tokens", 800)
span.set_attribute("llm.cost", 0.0235)
span.set_attribute("llm.temperature", 0.7)
span.set_attribute("llm.tools_used", ["search", "calculate"])
```

### Database Attributes

Attributes for database operation spans:

```python
span.set_attribute("db.system", "postgresql")
span.set_attribute("db.operation", "SELECT")
span.set_attribute("db.table", "users")
span.set_attribute("db.rows_affected", 42)
span.set_attribute("db.query_time", 0.523)
```

### Attribute Naming Conventions

Follow these conventions for consistency:

- **Use dot notation** for namespacing: `llm.model`, `db.table`, `http.status_code`
- **Use snake_case** for attribute names: `input_size`, `rows_affected`
- **Use standard prefixes**:
  - `llm.*` - LLM operations
  - `db.*` - Database operations
  - `http.*` - HTTP operations
  - `rpc.*` - RPC operations
  - `node.*` - Node-specific attributes

## Distributed Tracing

Spark supports distributed tracing across RPC boundaries.

### Client-Side Tracing

When `RemoteRpcProxyNode` calls a remote service:

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig

# Configure proxy
proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(
        endpoint="http://remote-service:8000",
        transport="http"
    )
)

# Use in graph
local_node >> proxy

# CLIENT span created automatically when calling remote service
```

The CLIENT span captures:
- RPC method name
- Request/response sizes
- Network latency
- Error information

### Server-Side Tracing

When `RpcNode` receives a request:

```python
from spark.nodes.rpc import RpcNode

class MyRpcNode(RpcNode):
    async def rpc_process(self, params, context):
        # SERVER span created automatically for this handler
        result = await self.do_work(params)
        return {"result": result}

node = MyRpcNode(host="0.0.0.0", port=8000)
await node.start_server()
```

The SERVER span captures:
- RPC method name
- Processing time (excluding network)
- Request parameters (if configured)
- Return values

### Trace Context Propagation

Trace context is automatically propagated across RPC boundaries:

```
[Client Process]
Trace: trace_123
  └─ Span (CLIENT): "RPC call" (span_abc)

[Server Process]
Trace: trace_123
  └─ Span (SERVER): "RPC handler" (parent_span_id=span_abc)
```

This allows you to see the complete distributed workflow in a single trace.

### Manual Context Propagation

For custom RPC implementations:

```python
# Client side: Include trace context in request
trace_id = context.metadata.get('trace_id')
span_id = current_span.span_id

request = {
    "method": "process",
    "params": {...},
    "trace_context": {
        "trace_id": trace_id,
        "parent_span_id": span_id
    }
}

# Server side: Extract and use trace context
trace_context = request.get("trace_context", {})
trace_id = trace_context.get("trace_id")
parent_span_id = trace_context.get("parent_span_id")

async with manager.start_span(
    "handle_request",
    trace_id=trace_id,
    parent_span_id=parent_span_id,
    kind=SpanKind.SERVER
) as span:
    result = await handle_request(request)
```

## Querying Traces and Spans

### Query All Traces

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()
await manager.flush()

# Get all traces
traces = await manager.query_traces(limit=100)

for trace in traces:
    print(f"Trace: {trace.name}")
    print(f"  Duration: {trace.duration:.3f}s")
    print(f"  Status: {trace.status}")
```

### Filter Traces

```python
# Filter by status
failed_traces = await manager.query_traces(
    status="failed",
    limit=50
)

# Filter by time range
from datetime import datetime, timedelta

recent_traces = await manager.query_traces(
    start_time=datetime.now() - timedelta(hours=1),
    end_time=datetime.now()
)

# Filter by attributes (backend-specific)
# For SQLite/PostgreSQL with JSONB support
production_traces = await manager.query_traces(
    attributes={"environment": "production"}
)
```

### Query Spans for a Trace

```python
# Get all spans for a trace
spans = await manager.query_spans(trace_id=trace_id)

# Sort by start time
spans_sorted = sorted(spans, key=lambda s: s.start_time)

for span in spans_sorted:
    indent = "  " * get_depth(span)
    print(f"{indent}{span.name}: {span.duration:.3f}s")
```

### Find Slow Spans

```python
# Query all spans
all_spans = await manager.query_spans()

# Filter slow spans (> 1 second)
slow_spans = [s for s in all_spans if s.duration and s.duration > 1.0]

# Group by name
from collections import defaultdict
slow_by_name = defaultdict(list)
for span in slow_spans:
    slow_by_name[span.name].append(span.duration)

# Report
for name, durations in slow_by_name.items():
    avg_duration = sum(durations) / len(durations)
    print(f"{name}: {len(durations)} slow executions, avg {avg_duration:.3f}s")
```

### Find Failed Spans

```python
# Query failed spans
failed_spans = await manager.query_spans(status="failed")

for span in failed_spans:
    print(f"Failed: {span.name}")
    print(f"  Error: {span.status_message}")
    print(f"  Trace: {span.trace_id}")
```

See [Querying Telemetry](querying.md) for comprehensive query examples.

## Performance Analysis

### Critical Path Analysis

Find the critical path (slowest chain of spans):

```python
async def find_critical_path(trace_id: str):
    manager = TelemetryManager.get_instance()
    spans = await manager.query_spans(trace_id=trace_id)

    # Build span map
    span_map = {s.span_id: s for s in spans}

    # Find leaf spans (no children)
    children = {s.span_id: [] for s in spans}
    for span in spans:
        if span.parent_span_id:
            children[span.parent_span_id].append(span.span_id)

    leaf_spans = [s for s in spans if not children[s.span_id]]

    # For each leaf, trace back to root
    def get_path_duration(span_id):
        span = span_map[span_id]
        if span.parent_span_id is None:
            return [(span.name, span.duration)]
        parent_path = get_path_duration(span.parent_span_id)
        return parent_path + [(span.name, span.duration)]

    # Find longest path
    paths = [get_path_duration(s.span_id) for s in leaf_spans]
    critical_path = max(paths, key=lambda p: sum(d for _, d in p))

    return critical_path

# Usage
path = await find_critical_path(trace_id)
print("Critical path:")
for name, duration in path:
    print(f"  {name}: {duration:.3f}s")
```

### Span Duration Statistics

```python
async def analyze_span_durations(span_name: str):
    manager = TelemetryManager.get_instance()

    # Get all spans with this name
    all_spans = await manager.query_spans()
    matching_spans = [s for s in all_spans if s.name == span_name and s.duration]

    if not matching_spans:
        return None

    durations = [s.duration for s in matching_spans]

    return {
        "count": len(durations),
        "min": min(durations),
        "max": max(durations),
        "mean": sum(durations) / len(durations),
        "p50": sorted(durations)[len(durations) // 2],
        "p95": sorted(durations)[int(len(durations) * 0.95)],
        "p99": sorted(durations)[int(len(durations) * 0.99)]
    }

# Usage
stats = await analyze_span_durations("TransformNode")
print(f"TransformNode statistics:")
print(f"  Count: {stats['count']}")
print(f"  Mean: {stats['mean']:.3f}s")
print(f"  P95: {stats['p95']:.3f}s")
print(f"  P99: {stats['p99']:.3f}s")
```

## Best Practices

### Trace Naming

- Use descriptive, consistent names
- Include workflow type: `production_workflow`, `batch_processing`, `api_request`
- Avoid dynamic values in trace names (use attributes instead)

```python
# Good
trace = manager.start_trace(
    name="order_processing",
    attributes={"order_id": "ord_123"}
)

# Bad (creates too many unique trace names)
trace = manager.start_trace(name=f"order_processing_ord_123")
```

### Span Naming

- Use specific, action-oriented names
- Include operation type: `load_data`, `transform_data`, `save_data`
- For nodes: use node class name or ID
- For RPC: use method name

```python
# Good
async with manager.start_span("validate_input", trace_id) as span:
    ...

# Bad (too generic)
async with manager.start_span("process", trace_id) as span:
    ...
```

### Attribute Usage

- Add attributes that help with filtering and analysis
- Include business context
- Avoid PII (personally identifiable information) unless necessary
- Keep attribute values simple (strings, numbers, booleans)

```python
# Good attributes
span.set_attribute("user_role", "admin")
span.set_attribute("data_size_mb", 15.3)
span.set_attribute("cache_hit", True)

# Avoid
span.set_attribute("user_email", "alice@example.com")  # PII
span.set_attribute("full_payload", large_object)  # Too large
```

### Span Granularity

Balance detail with overhead:

```python
# Too fine-grained (excessive overhead)
for item in items:
    async with manager.start_span("process_item", trace_id) as span:
        process(item)

# Better (batch span)
async with manager.start_span("process_items", trace_id) as span:
    for item in items:
        process(item)
    span.set_attribute("items_processed", len(items))
```

### Error Handling

Always capture error information in spans:

```python
async with manager.start_span("risky_operation", trace_id) as span:
    try:
        result = await risky_call()
        span.set_attribute("success", True)
    except Exception as e:
        span.set_attribute("error_type", type(e).__name__)
        span.set_attribute("error_message", str(e))
        raise  # Re-raise to set span status to failed
```

## Next Steps

- **[Events and Metrics](events-metrics.md)**: Learn about events and metrics
- **[Querying Telemetry](querying.md)**: Advanced query patterns
- **[Telemetry Patterns](patterns.md)**: Common patterns and recipes
- **[Backends Reference](backends.md)**: Backend-specific features
