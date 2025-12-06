---
title: Querying Telemetry Reference
parent: Telemetry
nav_order: 4
---
# Querying Telemetry Reference

## Overview

Spark provides a comprehensive query API for retrieving and analyzing telemetry data. This document covers all query operations, filtering options, and advanced patterns for traces, spans, events, and metrics.

## Query API Overview

All queries go through the `TelemetryManager`:

```python
from spark.telemetry import TelemetryManager

# Get singleton instance
manager = TelemetryManager.get_instance()

# Ensure buffered data is flushed to backend
await manager.flush()

# Query telemetry
traces = await manager.query_traces(limit=10)
spans = await manager.query_spans(trace_id=trace_id)
events = await manager.query_events(event_type="node_failed")
metrics = await manager.query_metrics(name="api_cost")
```

## Querying Traces

### Basic Query

```python
# Get all traces
traces = await manager.query_traces()

# Get limited number of traces
traces = await manager.query_traces(limit=100)

# Get traces with offset (pagination)
traces = await manager.query_traces(limit=50, offset=50)
```

### Filter by Status

```python
# Get completed traces
completed = await manager.query_traces(status="completed")

# Get failed traces
failed = await manager.query_traces(status="failed")

# Get cancelled traces
cancelled = await manager.query_traces(status="cancelled")
```

### Filter by Time Range

```python
from datetime import datetime, timedelta

# Traces from last hour
start_time = datetime.now() - timedelta(hours=1)
recent_traces = await manager.query_traces(
    start_time=start_time,
    limit=1000
)

# Traces in specific time window
start = datetime(2025, 1, 15, 10, 0, 0)
end = datetime(2025, 1, 15, 11, 0, 0)
window_traces = await manager.query_traces(
    start_time=start,
    end_time=end
)
```

### Filter by Name

```python
# Traces with specific name
workflow_traces = await manager.query_traces(
    name="production_workflow"
)

# Name pattern matching (backend-dependent)
# SQLite/PostgreSQL support LIKE patterns
api_traces = await manager.query_traces(
    name_pattern="api_%"  # Matches "api_v1", "api_v2", etc.
)
```

### Filter by Attributes

```python
# Filter by specific attribute (backend-dependent)
# PostgreSQL with JSONB support
production_traces = await manager.query_traces(
    attributes={"environment": "production"}
)

# Multiple attribute filters
user_traces = await manager.query_traces(
    attributes={
        "user_id": "alice",
        "tenant_id": "acme_corp"
    }
)
```

### Sort Results

```python
# Sort by start time (default: descending)
traces = await manager.query_traces(
    sort_by="start_time",
    sort_order="desc",
    limit=100
)

# Sort by duration
slowest_traces = await manager.query_traces(
    sort_by="duration",
    sort_order="desc",
    limit=10
)
```

### Complete Query Example

```python
# Complex query with multiple filters
traces = await manager.query_traces(
    status="completed",
    start_time=datetime.now() - timedelta(days=1),
    end_time=datetime.now(),
    attributes={"environment": "production"},
    sort_by="duration",
    sort_order="desc",
    limit=100,
    offset=0
)

print(f"Found {len(traces)} traces")
for trace in traces:
    print(f"{trace.name}: {trace.duration:.3f}s ({trace.status})")
```

## Querying Spans

### Basic Query

```python
# Get all spans
spans = await manager.query_spans()

# Get limited number of spans
spans = await manager.query_spans(limit=100)
```

### Filter by Trace

```python
# Get all spans for a specific trace
trace_spans = await manager.query_spans(trace_id=trace_id)

print(f"Trace has {len(trace_spans)} spans")
for span in trace_spans:
    print(f"  {span.name}: {span.duration:.3f}s")
```

### Filter by Span Name

```python
# Find all spans with specific name
transform_spans = await manager.query_spans(name="TransformNode")

# Calculate statistics
durations = [s.duration for s in transform_spans if s.duration]
if durations:
    avg_duration = sum(durations) / len(durations)
    print(f"TransformNode avg duration: {avg_duration:.3f}s")
```

### Filter by Span Kind

```python
from spark.telemetry.types import SpanKind

# Get all RPC client spans
client_spans = await manager.query_spans(kind=SpanKind.CLIENT)

# Get all RPC server spans
server_spans = await manager.query_spans(kind=SpanKind.SERVER)

# Get all internal spans
internal_spans = await manager.query_spans(kind=SpanKind.INTERNAL)
```

### Filter by Status

```python
# Get failed spans
failed_spans = await manager.query_spans(status="failed")

for span in failed_spans:
    print(f"Failed: {span.name}")
    print(f"  Error: {span.status_message}")
    print(f"  Trace: {span.trace_id}")
```

### Filter by Parent

```python
# Get child spans of a specific parent
child_spans = await manager.query_spans(parent_span_id=parent_span_id)

print(f"Parent has {len(child_spans)} children")
for child in child_spans:
    print(f"  {child.name}: {child.duration:.3f}s")
```

### Filter by Time Range

```python
# Spans started in last hour
recent_spans = await manager.query_spans(
    start_time=datetime.now() - timedelta(hours=1)
)
```

### Filter by Duration

```python
# Backend-specific: direct duration filter may not be supported
# Alternative: fetch and filter in Python

all_spans = await manager.query_spans()
slow_spans = [s for s in all_spans if s.duration and s.duration > 1.0]

print(f"Found {len(slow_spans)} slow spans (>1s)")
for span in slow_spans:
    print(f"{span.name}: {span.duration:.3f}s")
```

### Complete Query Example

```python
# Find slow RPC calls in production
from datetime import datetime, timedelta

# Get recent traces for production
traces = await manager.query_traces(
    attributes={"environment": "production"},
    start_time=datetime.now() - timedelta(hours=1)
)

# For each trace, get RPC client spans
slow_rpc_calls = []

for trace in traces:
    spans = await manager.query_spans(
        trace_id=trace.trace_id,
        kind=SpanKind.CLIENT
    )

    for span in spans:
        if span.duration and span.duration > 2.0:
            slow_rpc_calls.append({
                "trace": trace.name,
                "span": span.name,
                "duration": span.duration,
                "endpoint": span.attributes.get("rpc.endpoint")
            })

# Sort by duration
slow_rpc_calls.sort(key=lambda x: x["duration"], reverse=True)

print(f"Top 10 slow RPC calls:")
for call in slow_rpc_calls[:10]:
    print(f"{call['span']}: {call['duration']:.3f}s -> {call['endpoint']}")
```

## Querying Events

### Basic Query

```python
# Get all events
events = await manager.query_events()

# Get limited number of events
events = await manager.query_events(limit=100)
```

### Filter by Event Type

```python
# Get node failure events
failures = await manager.query_events(event_type="node_failed")

print(f"Found {len(failures)} node failures")
for event in failures:
    print(f"{event.timestamp}: {event.attributes['node_id']}")
```

### Filter by Trace

```python
# Get all events for a trace
trace_events = await manager.query_events(trace_id=trace_id)

# Sort by timestamp
trace_events.sort(key=lambda e: e.timestamp)

print(f"Trace timeline:")
for event in trace_events:
    print(f"{event.timestamp}: {event.name} ({event.type})")
```

### Filter by Span

```python
# Get events within a specific span
span_events = await manager.query_events(span_id=span_id)
```

### Filter by Time Range

```python
# Events from last hour
recent_events = await manager.query_events(
    start_time=datetime.now() - timedelta(hours=1)
)

# Events in specific window
window_events = await manager.query_events(
    start_time=datetime(2025, 1, 15, 10, 0, 0),
    end_time=datetime(2025, 1, 15, 11, 0, 0)
)
```

### Filter by Event Name

```python
# Events with specific name
checkpoint_events = await manager.query_events(
    name="Data Validation Complete"
)
```

### Complete Query Example

```python
# Analyze checkpoint completion across traces

# Get all checkpoint events from last day
checkpoints = await manager.query_events(
    event_type="checkpoint",
    start_time=datetime.now() - timedelta(days=1)
)

# Group by trace
from collections import defaultdict
checkpoints_by_trace = defaultdict(list)

for event in checkpoints:
    checkpoints_by_trace[event.trace_id].append({
        "name": event.name,
        "timestamp": event.timestamp,
        "attributes": event.attributes
    })

# Analyze completion
expected = ["data_loaded", "data_validated", "data_transformed", "data_saved"]
incomplete_traces = []

for trace_id, events in checkpoints_by_trace.items():
    completed = {e["attributes"].get("stage") for e in events}
    missing = set(expected) - completed

    if missing:
        incomplete_traces.append({
            "trace_id": trace_id,
            "completed": completed,
            "missing": missing
        })

print(f"Found {len(incomplete_traces)} incomplete traces")
for trace in incomplete_traces[:10]:
    print(f"Trace {trace['trace_id']}: missing {trace['missing']}")
```

## Querying Metrics

### Basic Query

```python
# Get all metrics
metrics = await manager.query_metrics()

# Get limited number of metrics
metrics = await manager.query_metrics(limit=100)
```

### Filter by Metric Name

```python
# Get specific metric
cache_hits = await manager.query_metrics(name="cache_hits")

total = sum(m.value for m in cache_hits)
print(f"Total cache hits: {total}")
```

### Filter by Trace

```python
# Get metrics for a specific trace
trace_metrics = await manager.query_metrics(trace_id=trace_id)

for metric in trace_metrics:
    print(f"{metric.name}: {metric.value} {metric.unit}")
```

### Filter by Time Range

```python
# Metrics from last hour
recent_metrics = await manager.query_metrics(
    start_time=datetime.now() - timedelta(hours=1)
)
```

### Filter by Aggregation Type

```python
# Get all counter metrics
counters = await manager.query_metrics(aggregation_type="counter")

# Get all gauge metrics
gauges = await manager.query_metrics(aggregation_type="gauge")

# Get all histogram metrics
histograms = await manager.query_metrics(aggregation_type="histogram")
```

### Filter by Attributes

```python
# Metrics for specific node
node_metrics = await manager.query_metrics(
    attributes={"node_id": "transform_1"}
)
```

### Complete Query Example

```python
# Analyze API costs by model over time

# Get cost metrics from last 24 hours
cost_metrics = await manager.query_metrics(
    name="llm_api_cost",
    start_time=datetime.now() - timedelta(days=1)
)

# Group by model and hour
from collections import defaultdict
costs_by_model_hour = defaultdict(lambda: defaultdict(float))

for metric in cost_metrics:
    model = metric.attributes.get("model", "unknown")
    hour = metric.timestamp.replace(minute=0, second=0, microsecond=0)
    costs_by_model_hour[model][hour] += metric.value

# Print summary
print("API costs by model (last 24 hours):")
for model in sorted(costs_by_model_hour.keys()):
    total_cost = sum(costs_by_model_hour[model].values())
    print(f"\n{model}: ${total_cost:.2f} total")

    for hour in sorted(costs_by_model_hour[model].keys()):
        cost = costs_by_model_hour[model][hour]
        print(f"  {hour.strftime('%Y-%m-%d %H:00')}: ${cost:.2f}")
```

## Advanced Query Patterns

### Pagination

```python
# Paginate through large result sets
page_size = 100
offset = 0
all_traces = []

while True:
    page = await manager.query_traces(limit=page_size, offset=offset)
    if not page:
        break

    all_traces.extend(page)
    offset += page_size

    if len(page) < page_size:
        break  # Last page

print(f"Total traces: {len(all_traces)}")
```

### Joining Data

```python
# Get trace with all related data
async def get_trace_details(trace_id: str):
    # Get trace
    traces = await manager.query_traces(trace_id=trace_id)
    if not traces:
        return None

    trace = traces[0]

    # Get spans
    spans = await manager.query_spans(trace_id=trace_id)

    # Get events
    events = await manager.query_events(trace_id=trace_id)

    # Get metrics
    metrics = await manager.query_metrics(trace_id=trace_id)

    return {
        "trace": trace,
        "spans": spans,
        "events": events,
        "metrics": metrics
    }

# Usage
details = await get_trace_details(trace_id)
print(f"Trace: {details['trace'].name}")
print(f"  Spans: {len(details['spans'])}")
print(f"  Events: {len(details['events'])}")
print(f"  Metrics: {len(details['metrics'])}")
```

### Aggregations

```python
# Calculate statistics across queries

# Get all execution duration metrics
durations = await manager.query_metrics(name="node_duration")

# Group by node
from collections import defaultdict
durations_by_node = defaultdict(list)

for metric in durations:
    node_id = metric.attributes.get("node_id")
    durations_by_node[node_id].append(metric.value)

# Calculate statistics per node
for node_id, values in durations_by_node.items():
    print(f"\n{node_id}:")
    print(f"  Count: {len(values)}")
    print(f"  Min: {min(values):.3f}s")
    print(f"  Max: {max(values):.3f}s")
    print(f"  Avg: {sum(values) / len(values):.3f}s")

    # Calculate percentiles
    sorted_values = sorted(values)
    p50_idx = len(sorted_values) // 2
    p95_idx = int(len(sorted_values) * 0.95)
    p99_idx = int(len(sorted_values) * 0.99)

    print(f"  P50: {sorted_values[p50_idx]:.3f}s")
    print(f"  P95: {sorted_values[p95_idx]:.3f}s")
    print(f"  P99: {sorted_values[p99_idx]:.3f}s")
```

### Time Series Analysis

```python
# Create time series from metrics
from datetime import datetime, timedelta

async def get_time_series(metric_name: str, hours: int = 24, bucket_minutes: int = 5):
    # Query metrics
    start_time = datetime.now() - timedelta(hours=hours)
    metrics = await manager.query_metrics(
        name=metric_name,
        start_time=start_time
    )

    # Create buckets
    bucket_size = timedelta(minutes=bucket_minutes)
    buckets = defaultdict(list)

    for metric in metrics:
        # Round timestamp to bucket
        bucket = metric.timestamp.replace(
            minute=(metric.timestamp.minute // bucket_minutes) * bucket_minutes,
            second=0,
            microsecond=0
        )
        buckets[bucket].append(metric.value)

    # Calculate averages
    time_series = []
    for bucket in sorted(buckets.keys()):
        values = buckets[bucket]
        avg = sum(values) / len(values)
        time_series.append({"timestamp": bucket, "value": avg})

    return time_series

# Usage
series = await get_time_series("cpu_percent", hours=24, bucket_minutes=5)
for point in series:
    print(f"{point['timestamp']}: {point['value']:.1f}%")
```

### Correlation Analysis

```python
# Correlate traces with high latency and errors

async def analyze_trace_correlation():
    # Get all traces from last hour
    traces = await manager.query_traces(
        start_time=datetime.now() - timedelta(hours=1)
    )

    # Separate by status
    successful = [t for t in traces if t.status == "completed"]
    failed = [t for t in traces if t.status == "failed"]

    # Compare durations
    if successful and failed:
        avg_success_duration = sum(t.duration for t in successful if t.duration) / len(successful)
        avg_failed_duration = sum(t.duration for t in failed if t.duration) / len(failed)

        print(f"Duration comparison:")
        print(f"  Successful traces: {avg_success_duration:.3f}s (n={len(successful)})")
        print(f"  Failed traces: {avg_failed_duration:.3f}s (n={len(failed)})")

        if avg_failed_duration > avg_success_duration:
            print(f"  Failed traces are {avg_failed_duration / avg_success_duration:.1f}x slower")

    # Find common attributes in failed traces
    if failed:
        # Count attribute values
        attribute_counts = defaultdict(lambda: defaultdict(int))

        for trace in failed:
            for key, value in trace.attributes.items():
                attribute_counts[key][value] += 1

        print(f"\nCommon attributes in failed traces:")
        for attr, values in attribute_counts.items():
            most_common = max(values.items(), key=lambda x: x[1])
            print(f"  {attr}: {most_common[0]} ({most_common[1]} occurrences)")

# Usage
await analyze_trace_correlation()
```

## Query Optimization

### Backend-Specific Optimizations

**Memory Backend**:
```python
# Memory backend: all queries are in-memory
# Optimize by reducing data volume
config = TelemetryConfig.create_memory(
    buffer_size=1000,  # Limit in-memory storage
)
```

**SQLite Backend**:
```python
# SQLite: optimize with indexes (automatic)
# Reduce query scope for better performance
traces = await manager.query_traces(
    start_time=datetime.now() - timedelta(hours=1),  # Narrow time window
    limit=100  # Limit results
)
```

**PostgreSQL Backend**:
```python
# PostgreSQL: use attribute filters efficiently
# Backend should have JSONB indexes
traces = await manager.query_traces(
    attributes={"environment": "production"},
    start_time=datetime.now() - timedelta(hours=1)
)
```

### Batch Queries

```python
# Instead of querying in a loop
# Bad:
for trace_id in trace_ids:
    spans = await manager.query_spans(trace_id=trace_id)
    # ... process spans

# Better: fetch all at once and filter
all_spans = await manager.query_spans()
spans_by_trace = defaultdict(list)
for span in all_spans:
    if span.trace_id in trace_ids:
        spans_by_trace[span.trace_id].append(span)

for trace_id in trace_ids:
    spans = spans_by_trace[trace_id]
    # ... process spans
```

### Caching Results

```python
# Cache query results for repeated access
from functools import lru_cache
from datetime import datetime

class TelemetryCache:
    def __init__(self):
        self._cache = {}
        self._cache_time = {}

    async def get_traces_cached(self, manager, ttl_seconds=60):
        key = "all_traces"
        now = datetime.now()

        # Check cache
        if key in self._cache:
            cache_age = (now - self._cache_time[key]).total_seconds()
            if cache_age < ttl_seconds:
                return self._cache[key]

        # Fetch and cache
        traces = await manager.query_traces()
        self._cache[key] = traces
        self._cache_time[key] = now

        return traces

# Usage
cache = TelemetryCache()
traces = await cache.get_traces_cached(manager, ttl_seconds=60)
```

## Error Handling

### Handle Missing Data

```python
# Gracefully handle queries with no results
traces = await manager.query_traces(status="failed")

if not traces:
    print("No failed traces found")
else:
    print(f"Found {len(traces)} failed traces")
    for trace in traces:
        print(f"  {trace.name}: {trace.duration:.3f}s")
```

### Handle Backend Errors

```python
try:
    traces = await manager.query_traces()
except Exception as e:
    print(f"Query failed: {e}")
    # Fallback or retry logic
```

### Validate Query Parameters

```python
# Validate time ranges
start_time = datetime.now() - timedelta(hours=24)
end_time = datetime.now()

if start_time > end_time:
    raise ValueError("start_time must be before end_time")

traces = await manager.query_traces(
    start_time=start_time,
    end_time=end_time
)
```

## Next Steps

- **[Telemetry Patterns](patterns.md)**: Common analysis patterns and recipes
- **[Traces and Spans](traces-spans.md)**: Deep dive into traces and spans
- **[Events and Metrics](events-metrics.md)**: Events and metrics reference
- **[Backends Reference](backends.md)**: Backend-specific query capabilities
