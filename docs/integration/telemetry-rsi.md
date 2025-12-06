---
title: Telemetry and RSI Integration
nav_order: 14
---
# Telemetry and RSI Integration

This guide covers how telemetry and the Recursive Self-Improvement (RSI) system work together to enable autonomous graph optimization through performance monitoring and analysis.

## Table of Contents

- [Overview](#overview)
- [Enabling Telemetry for RSI](#enabling-telemetry-for-rsi)
- [Telemetry Requirements](#telemetry-requirements)
- [Automatic Instrumentation](#automatic-instrumentation)
- [Custom Metrics for RSI](#custom-metrics-for-rsi)
- [Telemetry Backend Selection](#telemetry-backend-selection)
- [Performance Overhead](#performance-overhead)

## Overview

The RSI system depends on comprehensive telemetry data to analyze graph performance, identify bottlenecks, and generate improvement hypotheses. Telemetry provides the observability foundation that makes autonomous optimization possible.

**How They Work Together**:
- **Telemetry**: Collects execution data (traces, spans, events, metrics)
- **RSI Phase 1**: Analyzes telemetry to identify performance issues
- **RSI Phases 2-6**: Generate, test, and deploy improvements
- **Continuous Loop**: Improved graphs generate new telemetry, enabling ongoing optimization

## Enabling Telemetry for RSI

### Basic Setup

To use RSI, telemetry must be enabled on the target graph:

```python
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph
from spark.nodes import Node

# Create target graph with telemetry
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,  # Sample 100% for RSI
    enable_metrics=True,
    enable_events=True
)

# Your production graph
target_graph = Graph(
    start=my_start_node,
    telemetry_config=telemetry_config
)

# Run graph to collect telemetry
for i in range(100):  # Collect baseline data
    await target_graph.run({'query': f'request_{i}'})
```

### RSI Configuration

Configure RSI to use the same telemetry backend:

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")

rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="production_workflow",  # Graph identifier
    target_graph_version="1.0.0",           # Version tracking
    analysis_window_hours=24,               # Analyze last 24 hours
    min_executions=100,                     # Require 100+ runs
    telemetry_backend_config=telemetry_config  # Same backend
)

rsi_graph = RSIMetaGraph(config=rsi_config)
```

## Telemetry Requirements

RSI requires specific telemetry data to function effectively:

### 1. Required Trace Attributes

Each graph execution must create a trace with these attributes:

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()

trace = manager.start_trace(
    name="production_workflow",
    attributes={
        'graph_id': 'production_workflow',     # Required: graph identifier
        'graph_version': '1.0.0',              # Required: version tracking
        'graph_type': 'sequential',            # Optional: execution mode
        'environment': 'production'            # Optional: deployment env
    }
)
```

When using `Graph` with telemetry enabled, these attributes are added automatically:

```python
graph = Graph(
    start=my_node,
    name="production_workflow",
    version="1.0.0",
    telemetry_config=telemetry_config
)
# Traces automatically include graph_id and graph_version
```

### 2. Required Span Data

Node execution spans must capture:

```python
async with manager.start_span(
    name="ProcessingNode",
    trace_id=trace.trace_id,
    kind=SpanKind.INTERNAL,
    attributes={
        'node_name': 'ProcessingNode',      # Required: node identifier
        'node_type': 'ProcessingNode',      # Required: node class
        'success': True,                     # Required: execution status
        'error_type': None,                  # If failed: error type
        'retry_count': 0                     # Optional: retry attempts
    }
) as span:
    # Node execution
    result = await node.process(context)
    span.set_attribute('output_size', len(result))
```

Spans are created automatically by `Graph` during execution.

### 3. Required Metrics

RSI analyzes these key metrics:

```python
# Automatically collected by Graph
manager.record_metric("node.duration", value=0.5, unit="seconds")
manager.record_metric("node.success", value=1, aggregation="counter")
manager.record_metric("node.error", value=0, aggregation="counter")

# Custom metrics for specific analysis
manager.record_metric("node.cache_hit", value=1, aggregation="counter")
manager.record_metric("node.cost", value=0.001, unit="usd")
manager.record_metric("node.tokens", value=500, aggregation="gauge")
```

### 4. Required Events

Lifecycle events for performance analysis:

```python
# Automatically emitted by Graph
manager.record_event(
    type=EventType.GRAPH_STARTED,
    name="production_workflow",
    trace_id=trace.trace_id
)

manager.record_event(
    type=EventType.NODE_FINISHED,
    name="ProcessingNode",
    trace_id=trace.trace_id,
    attributes={'duration': 0.5}
)

manager.record_event(
    type=EventType.NODE_FAILED,
    name="ProcessingNode",
    trace_id=trace.trace_id,
    attributes={'error': 'Connection timeout'}
)
```

## Automatic Instrumentation

When telemetry is enabled on a Graph, instrumentation is automatic:

### What Gets Instrumented

```python
telemetry_config = TelemetryConfig.create_sqlite("telemetry.db")
graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Automatic instrumentation includes:
# - Trace creation for each graph.run()
# - Span creation for each node execution
# - Events for graph/node lifecycle
# - Metrics for duration, success/failure
# - Error tracking and stack traces
# - Input/output sizes (optional)
```

### Instrumentation Levels

Control what gets instrumented:

```python
# Full instrumentation (default for RSI)
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    enable_metrics=True,
    enable_events=True,
    capture_inputs=False,      # Don't log sensitive inputs
    capture_outputs=False,     # Don't log sensitive outputs
    capture_errors=True        # Do log errors
)

# Minimal instrumentation (lower overhead)
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=0.1,         # Sample 10%
    enable_metrics=True,
    enable_events=False,       # Skip events
    capture_inputs=False,
    capture_outputs=False
)
```

## Custom Metrics for RSI

Add custom metrics for RSI-specific analysis:

### Domain-Specific Metrics

```python
class BusinessMetricsNode(Node):
    """Node that tracks business metrics for RSI."""

    async def process(self, context):
        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        # Process request
        result = await self.do_work(context.inputs.content)

        # Record business metrics
        manager.record_metric(
            name="business.revenue_generated",
            value=result['revenue'],
            unit="usd",
            aggregation="counter",
            attributes={'trace_id': trace_id}
        )

        manager.record_metric(
            name="business.customer_satisfaction",
            value=result['satisfaction_score'],
            aggregation="gauge",
            attributes={'trace_id': trace_id}
        )

        # RSI can optimize for business metrics, not just latency
        return result

# Configure RSI to consider business metrics
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="business_workflow",
    optimization_objectives={
        'latency': {'weight': 0.3, 'direction': 'minimize'},
        'cost': {'weight': 0.2, 'direction': 'minimize'},
        'business.revenue_generated': {'weight': 0.5, 'direction': 'maximize'}
    }
)
```

### Quality Metrics

Track output quality for RSI optimization:

```python
class QualityTrackingNode(Node):
    """Track output quality for RSI analysis."""

    async def process(self, context):
        result = await self.agent.run(context.inputs.content['query'])

        # Evaluate quality
        quality_score = self.evaluate_quality(result.output)

        # Record for RSI
        manager = TelemetryManager.get_instance()
        manager.record_metric(
            name="agent.output_quality",
            value=quality_score,
            aggregation="gauge",
            attributes={
                'agent_name': self.agent.config.name,
                'trace_id': context.metadata.get('trace_id')
            }
        )

        return {'output': result.output, 'quality': quality_score}

    def evaluate_quality(self, output: str) -> float:
        """Evaluate output quality (0.0 to 1.0)."""
        # Simple heuristics or more sophisticated evaluation
        return len(output) / 1000  # Example: longer = better
```

### Cost Tracking for RSI

Track API costs for cost-aware optimization:

```python
class CostTrackingAgentNode(Node):
    """Agent node with cost tracking for RSI."""

    async def process(self, context):
        # Run agent
        result = await self.agent.run(context.inputs.content['query'])

        # Get cost statistics
        cost_stats = self.agent.get_cost_stats()

        # Record for RSI
        manager = TelemetryManager.get_instance()
        manager.record_metric(
            name="agent.cost",
            value=cost_stats.total_cost,
            unit="usd",
            aggregation="counter",
            attributes={
                'agent_name': self.agent.config.name,
                'model': self.agent.config.model.model_id,
                'trace_id': context.metadata.get('trace_id')
            }
        )

        manager.record_metric(
            name="agent.tokens",
            value=cost_stats.total_tokens,
            aggregation="counter"
        )

        return {'output': result.output}

# RSI will consider cost in optimization
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="agent_workflow",
    optimization_objectives={
        'latency': {'weight': 0.4, 'direction': 'minimize'},
        'agent.cost': {'weight': 0.4, 'direction': 'minimize'},
        'agent.output_quality': {'weight': 0.2, 'direction': 'maximize'}
    }
)
```

## Telemetry Backend Selection

Choose the right backend for RSI requirements:

### Memory Backend (Development)

```python
# Quick testing, no persistence
config = TelemetryConfig.create_memory(
    sampling_rate=1.0
)

# Pros: Fast, no dependencies
# Cons: Data lost on restart, limited to single process
# Use for: Local development, unit tests
```

### SQLite Backend (Single Instance)

```python
# Persistent, single-machine deployment
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    buffer_size=100,
    export_interval=5.0
)

# Pros: Persistent, no external dependencies, good for single instance
# Cons: Not suitable for distributed systems, can become bottleneck
# Use for: Single-server deployments, small to medium workloads
# Required for: RSI (needs persistent historical data)
```

### PostgreSQL Backend (Production)

```python
# Scalable, production-grade
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@host:5432/telemetry",
    sampling_rate=1.0,
    buffer_size=1000,
    export_interval=10.0
)

# Pros: Scalable, distributed, ACID guarantees, advanced queries
# Cons: Requires PostgreSQL server, more complex setup
# Use for: Production deployments, distributed systems, large scale
# Recommended for: Production RSI systems
```

### Backend Configuration for RSI

```python
# Development setup (SQLite)
dev_config = TelemetryConfig.create_sqlite(
    db_path="/tmp/dev_telemetry.db",
    sampling_rate=1.0  # Sample everything in dev
)

# Staging setup (PostgreSQL)
staging_config = TelemetryConfig.create_postgresql(
    connection_string=os.getenv("STAGING_DB"),
    sampling_rate=1.0  # Full sampling for testing
)

# Production setup (PostgreSQL with sampling)
prod_config = TelemetryConfig.create_postgresql(
    connection_string=os.getenv("PROD_DB"),
    sampling_rate=0.1,  # Sample 10% to reduce overhead
    buffer_size=5000,
    export_interval=30.0
)

# RSI uses the same backend
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="production_workflow",
    telemetry_backend_config=prod_config  # Same as production graph
)
```

## Performance Overhead

Understanding and minimizing telemetry overhead:

### Overhead Analysis

```python
# Typical overhead by configuration:

# No telemetry
# Overhead: 0%

# Memory backend, 100% sampling
# Overhead: ~5-10% (minimal)

# SQLite backend, 100% sampling
# Overhead: ~10-20% (I/O bound)

# PostgreSQL backend, 100% sampling
# Overhead: ~5-15% (network + I/O)

# PostgreSQL backend, 10% sampling
# Overhead: ~1-2% (acceptable for production)
```

### Optimizing for RSI

Balance data collection with performance:

```python
# Strategy 1: Sampling with guaranteed coverage
config = TelemetryConfig.create_postgresql(
    connection_string=prod_db,
    sampling_rate=0.1,  # Sample 10%
    force_sample_on_error=True,  # Always sample failures
    buffer_size=10000,  # Large buffer
    export_interval=60.0  # Batch writes
)

# Strategy 2: Adaptive sampling
config = TelemetryConfig.create_postgresql(
    connection_string=prod_db,
    sampling_rate=0.05,  # Base 5% rate
    enable_adaptive_sampling=True,  # Increase for slow requests
    slow_threshold_seconds=1.0,  # Sample all requests > 1s
    error_sample_rate=1.0  # Sample all errors
)

# Strategy 3: Separate telemetry graph
# Run telemetry collection in separate process
telemetry_graph = Graph(
    start=telemetry_collector_node,
    telemetry_config=None  # No telemetry on telemetry graph!
)

# Production graph publishes to queue
production_graph = Graph(
    start=production_node,
    telemetry_config=config
)
```

### Async Export

Minimize impact on request latency:

```python
config = TelemetryConfig.create_postgresql(
    connection_string=prod_db,
    sampling_rate=1.0,
    buffer_size=1000,
    export_interval=10.0,
    async_export=True,  # Export in background
    max_queue_size=10000  # Limit memory usage
)

# Telemetry exports don't block graph execution
# Buffered data exports every 10 seconds in background
```

### Selective Instrumentation

Instrument only what RSI needs:

```python
config = TelemetryConfig.create_postgresql(
    connection_string=prod_db,
    sampling_rate=1.0,
    enable_metrics=True,      # RSI needs metrics
    enable_events=False,      # Skip events (not used by RSI)
    capture_inputs=False,     # Skip inputs (privacy)
    capture_outputs=False,    # Skip outputs (privacy)
    capture_errors=True,      # Keep errors (RSI uses)
    instrument_nodes=['CriticalNode1', 'CriticalNode2']  # Only specific nodes
)
```

### Monitoring Telemetry Performance

Track telemetry system itself:

```python
from spark.telemetry import TelemetryManager

manager = TelemetryManager.get_instance()

# Get telemetry stats
stats = manager.get_stats()
print(f"Traces collected: {stats['traces_count']}")
print(f"Buffer size: {stats['buffer_size']}")
print(f"Export latency: {stats['avg_export_latency']:.3f}s")
print(f"Dropped items: {stats['dropped_count']}")

# Alert if telemetry falling behind
if stats['buffer_size'] > 0.9 * config.buffer_size:
    print("WARNING: Telemetry buffer nearly full!")

if stats['dropped_count'] > 0:
    print(f"WARNING: Dropped {stats['dropped_count']} telemetry items!")
```

## Complete RSI Integration Example

Full example with telemetry and RSI:

```python
from spark.telemetry import TelemetryConfig, TelemetryManager
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig
from spark.graphs import Graph
from spark.models.openai import OpenAIModel

# 1. Setup telemetry for production graph
telemetry_config = TelemetryConfig.create_postgresql(
    connection_string=os.getenv("TELEMETRY_DB"),
    sampling_rate=1.0,
    enable_metrics=True,
    enable_events=True,
    buffer_size=1000,
    export_interval=10.0
)

# 2. Create production graph with telemetry
production_graph = Graph(
    start=my_start_node,
    name="production_workflow",
    version="1.0.0",
    telemetry_config=telemetry_config
)

# 3. Run production graph to collect baseline data
print("Collecting baseline telemetry...")
for i in range(200):
    await production_graph.run({'request_id': i})

# Ensure data is written
manager = TelemetryManager.get_instance()
await manager.flush()

# 4. Setup RSI with same telemetry backend
model = OpenAIModel(model_id="gpt-4o")
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="production_workflow",
    target_graph_version="1.0.0",
    analysis_window_hours=24,
    min_executions=100,
    telemetry_backend_config=telemetry_config,
    optimization_objectives={
        'latency': {'weight': 0.5, 'direction': 'minimize'},
        'cost': {'weight': 0.3, 'direction': 'minimize'},
        'quality': {'weight': 0.2, 'direction': 'maximize'}
    }
)

# 5. Run RSI analysis and optimization
rsi_graph = RSIMetaGraph(config=rsi_config)

print("Running RSI analysis...")
result = await rsi_graph.run_single_cycle()

if result['improvements_deployed']:
    print(f"Deployed {result['num_improvements']} improvements!")
    for improvement in result['improvements']:
        print(f"- {improvement['hypothesis']['rationale']}")
        print(f"  Impact: {improvement['impact']}")

# 6. Continue collecting telemetry on improved graph
# RSI creates new graph version automatically
print("Monitoring improved graph...")
for i in range(200):
    await production_graph.run({'request_id': i + 200})

# 7. RSI can run continuously for ongoing optimization
print("Starting continuous improvement...")
await rsi_graph.run_continuous_improvement()
```

## Best Practices

1. **Enable Telemetry First**: Collect baseline data before running RSI
2. **Use Persistent Backend**: SQLite or PostgreSQL required for RSI
3. **Sample Appropriately**: 100% in dev, 10-20% in production
4. **Buffer Exports**: Use large buffers and batch exports
5. **Monitor Overhead**: Track telemetry system performance
6. **Custom Metrics**: Add domain-specific metrics for better optimization
7. **Version Tracking**: Use graph versions to track improvements
8. **Separate Databases**: Consider separate DBs for telemetry vs application data

## Related Documentation

- [Telemetry System Reference](/docs/telemetry/overview.md) - Complete telemetry guide
- [RSI System Reference](/docs/rsi/overview.md) - Complete RSI guide
- [Performance Optimization](/docs/best-practices/performance.md) - Optimization strategies
- [Telemetry Configuration](/docs/config/telemetry-config.md) - Configuration reference
