# Telemetry Patterns and Best Practices

## Overview

This document provides practical patterns, recipes, and best practices for using Spark's telemetry system effectively. Learn how to analyze performance, detect bottlenecks, monitor costs, build dashboards, and integrate with observability platforms.

## Performance Analysis Patterns

### Identifying Bottlenecks

Find the slowest operations in your workflow:

```python
from spark.telemetry import TelemetryManager
from collections import defaultdict

async def find_bottlenecks(trace_id: str = None, threshold_seconds: float = 1.0):
    """Identify slow spans in traces."""
    manager = TelemetryManager.get_instance()
    await manager.flush()

    # Get spans
    if trace_id:
        spans = await manager.query_spans(trace_id=trace_id)
    else:
        spans = await manager.query_spans()

    # Find slow spans
    bottlenecks = []
    for span in spans:
        if span.duration and span.duration > threshold_seconds:
            bottlenecks.append({
                "trace_id": span.trace_id,
                "span_name": span.name,
                "duration": span.duration,
                "attributes": span.attributes
            })

    # Sort by duration
    bottlenecks.sort(key=lambda x: x["duration"], reverse=True)

    # Group by span name
    by_name = defaultdict(list)
    for b in bottlenecks:
        by_name[b["span_name"]].append(b["duration"])

    # Report
    print(f"Found {len(bottlenecks)} slow operations (>{threshold_seconds}s):\n")
    for name, durations in sorted(by_name.items(), key=lambda x: sum(x[1]), reverse=True):
        total = sum(durations)
        avg = total / len(durations)
        print(f"{name}:")
        print(f"  Count: {len(durations)}")
        print(f"  Total: {total:.3f}s")
        print(f"  Average: {avg:.3f}s")
        print(f"  Max: {max(durations):.3f}s")

    return bottlenecks

# Usage
bottlenecks = await find_bottlenecks(threshold_seconds=2.0)
```

### Critical Path Analysis

Identify the critical path through your workflow:

```python
async def analyze_critical_path(trace_id: str):
    """Find the longest path through the execution tree."""
    manager = TelemetryManager.get_instance()
    spans = await manager.query_spans(trace_id=trace_id)

    if not spans:
        return None

    # Build span map and hierarchy
    span_map = {s.span_id: s for s in spans}
    children = defaultdict(list)
    for span in spans:
        if span.parent_span_id:
            children[span.parent_span_id].append(span.span_id)

    # Find root span
    root_spans = [s for s in spans if s.parent_span_id is None]
    if not root_spans:
        return None

    root = root_spans[0]

    # Calculate critical path
    def get_critical_path(span_id):
        span = span_map[span_id]
        child_ids = children.get(span_id, [])

        if not child_ids:
            # Leaf node
            return [(span.name, span.duration or 0)]

        # Find longest child path
        child_paths = [get_critical_path(child_id) for child_id in child_ids]
        longest_child_path = max(child_paths, key=lambda p: sum(d for _, d in p))

        return [(span.name, span.duration or 0)] + longest_child_path

    critical_path = get_critical_path(root.span_id)
    total_duration = sum(d for _, d in critical_path)

    # Report
    print(f"Critical path (total: {total_duration:.3f}s):")
    for i, (name, duration) in enumerate(critical_path):
        indent = "  " * i
        percent = (duration / total_duration * 100) if total_duration > 0 else 0
        print(f"{indent}└─ {name}: {duration:.3f}s ({percent:.1f}%)")

    return critical_path

# Usage
path = await analyze_critical_path(trace_id)
```

### Latency Percentiles

Calculate latency percentiles for operations:

```python
async def calculate_latency_percentiles(span_name: str, hours: int = 24):
    """Calculate P50, P95, P99 latencies for a span."""
    manager = TelemetryManager.get_instance()

    # Get spans from time window
    from datetime import datetime, timedelta
    start_time = datetime.now() - timedelta(hours=hours)

    all_spans = await manager.query_spans(
        name=span_name,
        start_time=start_time
    )

    durations = [s.duration for s in all_spans if s.duration]

    if not durations:
        print(f"No data found for {span_name}")
        return None

    # Sort durations
    sorted_durations = sorted(durations)
    n = len(sorted_durations)

    # Calculate percentiles
    stats = {
        "count": n,
        "min": min(durations),
        "max": max(durations),
        "mean": sum(durations) / n,
        "p50": sorted_durations[int(n * 0.50)],
        "p90": sorted_durations[int(n * 0.90)],
        "p95": sorted_durations[int(n * 0.95)],
        "p99": sorted_durations[int(n * 0.99)]
    }

    # Report
    print(f"Latency statistics for {span_name} (last {hours}h):")
    print(f"  Count: {stats['count']}")
    print(f"  Min: {stats['min']:.3f}s")
    print(f"  Mean: {stats['mean']:.3f}s")
    print(f"  P50: {stats['p50']:.3f}s")
    print(f"  P90: {stats['p90']:.3f}s")
    print(f"  P95: {stats['p95']:.3f}s")
    print(f"  P99: {stats['p99']:.3f}s")
    print(f"  Max: {stats['max']:.3f}s")

    return stats

# Usage
stats = await calculate_latency_percentiles("TransformNode", hours=24)
```

### Comparing Trace Versions

Compare performance across graph versions:

```python
async def compare_versions(version1: str, version2: str, hours: int = 24):
    """Compare performance between two graph versions."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta

    start_time = datetime.now() - timedelta(hours=hours)

    # Get traces for each version
    traces1 = await manager.query_traces(
        attributes={"graph_version": version1},
        start_time=start_time
    )

    traces2 = await manager.query_traces(
        attributes={"graph_version": version2},
        start_time=start_time
    )

    if not traces1 or not traces2:
        print("Insufficient data for comparison")
        return

    # Calculate statistics
    def get_stats(traces):
        durations = [t.duration for t in traces if t.duration]
        failures = len([t for t in traces if t.status == "failed"])
        return {
            "count": len(traces),
            "failures": failures,
            "failure_rate": failures / len(traces) if traces else 0,
            "mean_duration": sum(durations) / len(durations) if durations else 0,
            "p95_duration": sorted(durations)[int(len(durations) * 0.95)] if durations else 0
        }

    stats1 = get_stats(traces1)
    stats2 = get_stats(traces2)

    # Report comparison
    print(f"Version comparison (last {hours}h):\n")
    print(f"Version {version1}:")
    print(f"  Executions: {stats1['count']}")
    print(f"  Failure rate: {stats1['failure_rate']:.1%}")
    print(f"  Mean duration: {stats1['mean_duration']:.3f}s")
    print(f"  P95 duration: {stats1['p95_duration']:.3f}s")

    print(f"\nVersion {version2}:")
    print(f"  Executions: {stats2['count']}")
    print(f"  Failure rate: {stats2['failure_rate']:.1%}")
    print(f"  Mean duration: {stats2['mean_duration']:.3f}s")
    print(f"  P95 duration: {stats2['p95_duration']:.3f}s")

    # Calculate improvements
    duration_improvement = (stats1['mean_duration'] - stats2['mean_duration']) / stats1['mean_duration']
    failure_improvement = stats1['failure_rate'] - stats2['failure_rate']

    print(f"\nChanges:")
    if duration_improvement > 0:
        print(f"  Duration: {duration_improvement:.1%} faster")
    else:
        print(f"  Duration: {abs(duration_improvement):.1%} slower")

    if failure_improvement > 0:
        print(f"  Failures: {failure_improvement:.1%} fewer failures")
    else:
        print(f"  Failures: {abs(failure_improvement):.1%} more failures")

# Usage
await compare_versions("1.0.0", "2.0.0", hours=24)
```

## Error Rate Monitoring

### Tracking Failure Rates

Monitor and alert on failure rates:

```python
async def monitor_failure_rate(threshold: float = 0.05, window_hours: int = 1):
    """Monitor failure rate and alert if threshold exceeded."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta

    start_time = datetime.now() - timedelta(hours=window_hours)

    # Get recent traces
    traces = await manager.query_traces(start_time=start_time)

    if not traces:
        print("No traces in window")
        return

    # Calculate failure rate
    total = len(traces)
    failed = len([t for t in traces if t.status == "failed"])
    failure_rate = failed / total

    print(f"Failure rate (last {window_hours}h): {failure_rate:.1%} ({failed}/{total})")

    if failure_rate > threshold:
        print(f"⚠️  ALERT: Failure rate {failure_rate:.1%} exceeds threshold {threshold:.1%}")

        # Analyze failures
        failed_traces = [t for t in traces if t.status == "failed"]

        # Find common patterns
        from collections import Counter
        error_types = []

        for trace in failed_traces:
            # Get failed spans for this trace
            spans = await manager.query_spans(trace_id=trace.trace_id, status="failed")
            for span in spans:
                if span.status_message:
                    error_types.append(span.status_message.split(":")[0])

        if error_types:
            common_errors = Counter(error_types).most_common(5)
            print(f"\nMost common errors:")
            for error, count in common_errors:
                print(f"  {error}: {count} occurrences")

    return failure_rate

# Usage (run periodically)
import asyncio

async def failure_monitor_loop():
    while True:
        await monitor_failure_rate(threshold=0.05, window_hours=1)
        await asyncio.sleep(300)  # Check every 5 minutes

# asyncio.create_task(failure_monitor_loop())
```

### Error Correlation

Correlate errors with system conditions:

```python
async def correlate_errors_with_load(hours: int = 24):
    """Correlate error rates with system load."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta
    from collections import defaultdict

    start_time = datetime.now() - timedelta(hours=hours)

    # Get traces
    traces = await manager.query_traces(start_time=start_time)

    # Get CPU metrics
    cpu_metrics = await manager.query_metrics(
        name="cpu_percent",
        start_time=start_time
    )

    # Group by hour
    traces_by_hour = defaultdict(list)
    cpu_by_hour = defaultdict(list)

    for trace in traces:
        hour = trace.start_time.replace(minute=0, second=0, microsecond=0)
        traces_by_hour[hour].append(trace)

    for metric in cpu_metrics:
        hour = metric.timestamp.replace(minute=0, second=0, microsecond=0)
        cpu_by_hour[hour].append(metric.value)

    # Analyze correlation
    print("Error correlation with CPU load:\n")
    print(f"{'Hour':<20} {'Traces':<10} {'Failures':<10} {'Fail Rate':<12} {'Avg CPU':<10}")
    print("-" * 72)

    for hour in sorted(traces_by_hour.keys()):
        hour_traces = traces_by_hour[hour]
        total = len(hour_traces)
        failed = len([t for t in hour_traces if t.status == "failed"])
        fail_rate = failed / total if total > 0 else 0

        avg_cpu = sum(cpu_by_hour[hour]) / len(cpu_by_hour[hour]) if cpu_by_hour[hour] else 0

        print(f"{hour.strftime('%Y-%m-%d %H:00'):<20} {total:<10} {failed:<10} {fail_rate:<12.1%} {avg_cpu:<10.1f}%")

# Usage
await correlate_errors_with_load(hours=24)
```

## Cost Analysis

### Tracking LLM Costs

Monitor and optimize LLM API costs:

```python
async def analyze_llm_costs(hours: int = 24):
    """Analyze LLM API costs and identify optimization opportunities."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta
    from collections import defaultdict

    start_time = datetime.now() - timedelta(hours=hours)

    # Get cost metrics
    cost_metrics = await manager.query_metrics(
        name="llm_api_cost",
        start_time=start_time
    )

    if not cost_metrics:
        print("No cost data available")
        return

    # Group by model
    costs_by_model = defaultdict(float)
    calls_by_model = defaultdict(int)

    for metric in cost_metrics:
        model = metric.attributes.get("model", "unknown")
        costs_by_model[model] += metric.value
        calls_by_model[model] += 1

    # Calculate totals
    total_cost = sum(costs_by_model.values())
    total_calls = sum(calls_by_model.values())

    # Report
    print(f"LLM API costs (last {hours}h):\n")
    print(f"Total cost: ${total_cost:.2f}")
    print(f"Total calls: {total_calls}\n")

    print(f"{'Model':<30} {'Calls':<10} {'Cost':<12} {'$/Call':<12} {'% of Total':<12}")
    print("-" * 76)

    for model in sorted(costs_by_model.keys(), key=lambda m: costs_by_model[m], reverse=True):
        cost = costs_by_model[model]
        calls = calls_by_model[model]
        cost_per_call = cost / calls if calls > 0 else 0
        percent = cost / total_cost * 100 if total_cost > 0 else 0

        print(f"{model:<30} {calls:<10} ${cost:<11.2f} ${cost_per_call:<11.4f} {percent:<12.1f}%")

    # Recommendations
    print("\nOptimization opportunities:")

    # Find expensive models
    expensive_models = [(m, c) for m, c in costs_by_model.items() if c / total_cost > 0.3]
    if expensive_models:
        for model, cost in expensive_models:
            percent = cost / total_cost * 100
            print(f"  • {model} accounts for {percent:.1f}% of costs (${cost:.2f})")
            print(f"    Consider using a cheaper model for non-critical operations")

    # Find high-volume models
    high_volume_models = [(m, c) for m, c in calls_by_model.items() if c / total_calls > 0.5]
    if high_volume_models:
        for model, calls in high_volume_models:
            percent = calls / total_calls * 100
            print(f"  • {model} has {percent:.1f}% of calls ({calls} calls)")
            print(f"    Consider caching or batching requests")

# Usage
await analyze_llm_costs(hours=24)
```

### Cost Budgeting

Monitor costs against budgets:

```python
async def check_cost_budget(daily_budget: float = 10.0):
    """Check if daily cost budget is exceeded."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta

    # Get today's costs
    start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cost_metrics = await manager.query_metrics(
        name="llm_api_cost",
        start_time=start_of_day
    )

    today_cost = sum(m.value for m in cost_metrics)
    percent_used = today_cost / daily_budget * 100

    print(f"Daily budget status:")
    print(f"  Budget: ${daily_budget:.2f}")
    print(f"  Spent: ${today_cost:.2f} ({percent_used:.1f}%)")
    print(f"  Remaining: ${daily_budget - today_cost:.2f}")

    if today_cost > daily_budget:
        print(f"  ⚠️  ALERT: Daily budget exceeded by ${today_cost - daily_budget:.2f}")
    elif percent_used > 80:
        print(f"  ⚠️  WARNING: {percent_used:.1f}% of daily budget used")

    return {
        "budget": daily_budget,
        "spent": today_cost,
        "remaining": daily_budget - today_cost,
        "percent_used": percent_used
    }

# Usage (run periodically)
budget_status = await check_cost_budget(daily_budget=10.0)
```

## Custom Dashboards

### Real-Time Dashboard

Build a simple real-time monitoring dashboard:

```python
import asyncio
from datetime import datetime, timedelta

class TelemetryDashboard:
    def __init__(self):
        self.manager = TelemetryManager.get_instance()

    async def get_dashboard_data(self):
        """Fetch all data for dashboard."""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)

        # Get traces
        traces = await self.manager.query_traces(start_time=last_hour)

        # Calculate stats
        total_traces = len(traces)
        completed = len([t for t in traces if t.status == "completed"])
        failed = len([t for t in traces if t.status == "failed"])
        success_rate = completed / total_traces if total_traces > 0 else 0

        durations = [t.duration for t in traces if t.duration]
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Get costs
        cost_metrics = await self.manager.query_metrics(
            name="llm_api_cost",
            start_time=last_hour
        )
        hourly_cost = sum(m.value for m in cost_metrics)

        return {
            "timestamp": now,
            "traces": {
                "total": total_traces,
                "completed": completed,
                "failed": failed,
                "success_rate": success_rate
            },
            "performance": {
                "avg_duration": avg_duration,
                "p95_duration": sorted(durations)[int(len(durations) * 0.95)] if durations else 0
            },
            "cost": {
                "hourly": hourly_cost,
                "daily_projection": hourly_cost * 24
            }
        }

    def print_dashboard(self, data):
        """Print dashboard to console."""
        print("\033[2J\033[H")  # Clear screen
        print("=" * 60)
        print("SPARK TELEMETRY DASHBOARD")
        print("=" * 60)
        print(f"Updated: {data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        print("TRACES (Last Hour)")
        print(f"  Total:        {data['traces']['total']}")
        print(f"  Completed:    {data['traces']['completed']}")
        print(f"  Failed:       {data['traces']['failed']}")
        print(f"  Success Rate: {data['traces']['success_rate']:.1%}")
        print()

        print("PERFORMANCE")
        print(f"  Avg Duration: {data['performance']['avg_duration']:.3f}s")
        print(f"  P95 Duration: {data['performance']['p95_duration']:.3f}s")
        print()

        print("COST")
        print(f"  Hourly:       ${data['cost']['hourly']:.2f}")
        print(f"  Daily (proj): ${data['cost']['daily_projection']:.2f}")
        print()

        print("Press Ctrl+C to exit")

    async def run(self, refresh_interval: int = 30):
        """Run dashboard with periodic refresh."""
        try:
            while True:
                data = await self.get_dashboard_data()
                self.print_dashboard(data)
                await asyncio.sleep(refresh_interval)
        except KeyboardInterrupt:
            print("\nDashboard stopped")

# Usage
dashboard = TelemetryDashboard()
await dashboard.run(refresh_interval=30)
```

### Exporting Dashboard Data

Export telemetry data for external dashboards:

```python
async def export_dashboard_data(output_file: str = "dashboard_data.json"):
    """Export telemetry data for external dashboard tools."""
    manager = TelemetryManager.get_instance()
    from datetime import datetime, timedelta
    import json

    # Collect data
    last_24h = datetime.now() - timedelta(hours=24)

    traces = await manager.query_traces(start_time=last_24h)
    events = await manager.query_events(start_time=last_24h)
    metrics = await manager.query_metrics(start_time=last_24h)

    # Format for export
    export_data = {
        "generated_at": datetime.now().isoformat(),
        "time_window": {
            "start": last_24h.isoformat(),
            "end": datetime.now().isoformat()
        },
        "traces": [
            {
                "trace_id": t.trace_id,
                "name": t.name,
                "duration": t.duration,
                "status": t.status,
                "start_time": t.start_time.isoformat() if t.start_time else None,
                "attributes": t.attributes
            }
            for t in traces
        ],
        "events": [
            {
                "event_id": e.event_id,
                "type": e.type,
                "name": e.name,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "attributes": e.attributes
            }
            for e in events
        ],
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "unit": m.unit,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "attributes": m.attributes
            }
            for m in metrics
        ]
    }

    # Write to file
    with open(output_file, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Dashboard data exported to {output_file}")
    print(f"  Traces: {len(export_data['traces'])}")
    print(f"  Events: {len(export_data['events'])}")
    print(f"  Metrics: {len(export_data['metrics'])}")

# Usage
await export_dashboard_data("dashboard_data.json")
```

## Integration with Observability Tools

### Grafana Integration (via PostgreSQL)

Export telemetry to Grafana using PostgreSQL backend:

```python
# 1. Configure PostgreSQL backend
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@localhost/telemetry",
    sampling_rate=0.1
)

# 2. Run graphs with telemetry
graph = Graph(start=my_node, telemetry_config=config)
await graph.run()

# 3. Create Grafana dashboard connecting to PostgreSQL
# Use queries like:

# Query for trace count over time:
"""
SELECT
  date_trunc('minute', start_time) AS time,
  COUNT(*) AS count
FROM traces
WHERE start_time > NOW() - INTERVAL '1 hour'
GROUP BY time
ORDER BY time
"""

# Query for average duration:
"""
SELECT
  date_trunc('minute', start_time) AS time,
  AVG(duration) AS avg_duration
FROM traces
WHERE start_time > NOW() - INTERVAL '1 hour'
  AND duration IS NOT NULL
GROUP BY time
ORDER BY time
"""

# Query for error rate:
"""
SELECT
  date_trunc('minute', start_time) AS time,
  COUNT(*) FILTER (WHERE status = 'failed') * 100.0 / COUNT(*) AS error_rate
FROM traces
WHERE start_time > NOW() - INTERVAL '1 hour'
GROUP BY time
ORDER BY time
"""
```

### Jaeger Integration (via OTLP)

Export traces to Jaeger for distributed tracing:

```python
# 1. Start Jaeger with OTLP support
# docker run -d --name jaeger \
#   -p 4317:4317 \
#   -p 16686:16686 \
#   jaegertracing/all-in-one:latest

# 2. Configure OTLP backend
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_otlp(
    endpoint="http://localhost:4317",
    sampling_rate=1.0,
    metadata={
        "service.name": "spark_workflow",
        "service.version": "1.0.0"
    }
)

# 3. Run graphs with telemetry
graph = Graph(start=my_node, telemetry_config=config)
await graph.run()

# 4. View traces in Jaeger UI at http://localhost:16686
```

### Honeycomb Integration

Export to Honeycomb for advanced analysis:

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_otlp(
    endpoint="https://api.honeycomb.io:443",
    sampling_rate=0.1,
    headers={
        "x-honeycomb-team": "YOUR_API_KEY",
        "x-honeycomb-dataset": "spark-telemetry"
    },
    metadata={
        "service.name": "spark_workflow",
        "environment": "production"
    }
)

graph = Graph(start=my_node, telemetry_config=config)
await graph.run()
```

### Custom Webhook Integration

Send telemetry alerts to custom webhooks:

```python
import httpx

async def send_alert_webhook(alert_data: dict, webhook_url: str):
    """Send alert to custom webhook."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                webhook_url,
                json=alert_data,
                timeout=10.0
            )
            response.raise_for_status()
            print(f"Alert sent successfully")
        except Exception as e:
            print(f"Failed to send alert: {e}")

# Usage in monitoring
async def monitor_with_alerts(webhook_url: str):
    manager = TelemetryManager.get_instance()

    while True:
        # Check failure rate
        failure_rate = await monitor_failure_rate(threshold=0.05)

        if failure_rate > 0.05:
            # Send alert
            alert = {
                "alert_type": "high_failure_rate",
                "severity": "warning",
                "failure_rate": failure_rate,
                "timestamp": datetime.now().isoformat(),
                "message": f"Failure rate {failure_rate:.1%} exceeds threshold"
            }
            await send_alert_webhook(alert, webhook_url)

        await asyncio.sleep(300)

# Run monitor
# await monitor_with_alerts("https://your-webhook-url.com/alerts")
```

## Alerting Strategies

### Threshold-Based Alerts

```python
class ThresholdAlertMonitor:
    def __init__(self):
        self.manager = TelemetryManager.get_instance()
        self.thresholds = {
            "failure_rate": 0.05,
            "p95_latency": 5.0,
            "hourly_cost": 2.0
        }

    async def check_all_thresholds(self):
        """Check all thresholds and return alerts."""
        alerts = []

        # Check failure rate
        from datetime import datetime, timedelta
        last_hour = datetime.now() - timedelta(hours=1)

        traces = await self.manager.query_traces(start_time=last_hour)
        if traces:
            failed = len([t for t in traces if t.status == "failed"])
            failure_rate = failed / len(traces)

            if failure_rate > self.thresholds["failure_rate"]:
                alerts.append({
                    "type": "failure_rate",
                    "value": failure_rate,
                    "threshold": self.thresholds["failure_rate"],
                    "message": f"Failure rate {failure_rate:.1%} exceeds threshold"
                })

        # Check latency
        durations = [t.duration for t in traces if t.duration]
        if durations:
            p95 = sorted(durations)[int(len(durations) * 0.95)]

            if p95 > self.thresholds["p95_latency"]:
                alerts.append({
                    "type": "p95_latency",
                    "value": p95,
                    "threshold": self.thresholds["p95_latency"],
                    "message": f"P95 latency {p95:.3f}s exceeds threshold"
                })

        # Check cost
        cost_metrics = await self.manager.query_metrics(
            name="llm_api_cost",
            start_time=last_hour
        )
        hourly_cost = sum(m.value for m in cost_metrics)

        if hourly_cost > self.thresholds["hourly_cost"]:
            alerts.append({
                "type": "hourly_cost",
                "value": hourly_cost,
                "threshold": self.thresholds["hourly_cost"],
                "message": f"Hourly cost ${hourly_cost:.2f} exceeds threshold"
            })

        return alerts

    async def run(self, check_interval: int = 300):
        """Run continuous monitoring."""
        while True:
            alerts = await self.check_all_thresholds()

            if alerts:
                print(f"\n⚠️  {len(alerts)} alerts detected:")
                for alert in alerts:
                    print(f"  • {alert['message']}")
                # Send to notification system
            else:
                print("✓ All thresholds OK")

            await asyncio.sleep(check_interval)

# Usage
monitor = ThresholdAlertMonitor()
# await monitor.run(check_interval=300)
```

## Best Practices Summary

### Configuration

**Development**:
```python
config = TelemetryConfig.create_sqlite(
    db_path="dev_telemetry.db",
    sampling_rate=1.0,
    buffer_size=50,
    export_interval=1.0
)
```

**Production**:
```python
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@db.example.com/telemetry",
    sampling_rate=0.1,
    buffer_size=1000,
    export_interval=30.0,
    enable_events=False  # Reduce overhead
)
```

### Attribute Naming

```python
# Good: consistent, namespaced attributes
span.set_attribute("node.id", "transform_1")
span.set_attribute("node.type", "TransformNode")
span.set_attribute("llm.model", "gpt-4o")
span.set_attribute("llm.tokens", 1500)
span.set_attribute("db.table", "users")

# Avoid: inconsistent naming
span.set_attribute("nodeId", "transform_1")
span.set_attribute("Node_Type", "TransformNode")
span.set_attribute("model", "gpt-4o")
```

### Query Optimization

```python
# Good: narrow time window, limit results
traces = await manager.query_traces(
    start_time=datetime.now() - timedelta(hours=1),
    limit=100
)

# Avoid: unbounded queries
traces = await manager.query_traces()  # May return millions of traces
```

### Error Handling

```python
# Always handle query failures gracefully
try:
    traces = await manager.query_traces()
except Exception as e:
    logger.error(f"Telemetry query failed: {e}")
    traces = []  # Fallback to empty list
```

## Next Steps

- **[Overview](overview.md)**: Telemetry system overview
- **[Backends Reference](backends.md)**: Backend selection and configuration
- **[Querying Telemetry](querying.md)**: Advanced query patterns
- **[RSI Documentation](../rsi/overview.md)**: Using telemetry for autonomous improvement
