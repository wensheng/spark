---
title: TelemetryConfig Reference
parent: Config
nav_order: 4
---
# TelemetryConfig Reference

This document provides a complete reference for `TelemetryConfig`, the configuration class used to customize telemetry collection and export in Spark.

## Overview

`TelemetryConfig` is a dataclass that controls telemetry behavior including backend selection, sampling rates, export intervals, retention policies, and instrumentation options. Telemetry provides comprehensive observability for graph and node execution.

**Import**:
```python
from spark.telemetry import TelemetryConfig
```

**Basic Usage**:
```python
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Create telemetry config
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)

# Use with graph
graph = Graph(start=my_node, telemetry_config=config)
result = await graph.run()
```

## Factory Methods

TelemetryConfig provides factory methods for common backend configurations:

### `create_sqlite()`

Create configuration for SQLite backend (persistent local storage).

**Signature**:
```python
@classmethod
def create_sqlite(
    cls,
    db_path: str = "spark_telemetry.db",
    **kwargs
) -> TelemetryConfig
```

**Usage**:
```python
config = TelemetryConfig.create_sqlite(
    db_path="/var/lib/spark/telemetry.db",
    sampling_rate=1.0,
    retention_days=90
)
```

**Notes**:
- Requires `aiosqlite` package
- Best for local development and single-instance deployments
- Automatic database schema initialization
- Thread-safe async operations

### `create_postgresql()`

Create configuration for PostgreSQL backend (production-grade persistence).

**Signature**:
```python
@classmethod
def create_postgresql(
    cls,
    host: str = "localhost",
    port: int = 5432,
    database: str = "spark_telemetry",
    user: Optional[str] = None,
    password: Optional[str] = None,
    **kwargs
) -> TelemetryConfig
```

**Usage**:
```python
config = TelemetryConfig.create_postgresql(
    host="postgres.example.com",
    port=5432,
    database="spark_telemetry",
    user="spark",
    password=os.getenv("POSTGRES_PASSWORD"),
    sampling_rate=0.1,  # Sample 10% of traces
    retention_days=365
)
```

**Notes**:
- Requires `asyncpg` package
- Best for production deployments
- Supports connection pooling
- Scalable for high-volume telemetry

### `create_memory()`

Create configuration for in-memory backend (testing and development).

**Signature**:
```python
@classmethod
def create_memory(cls, **kwargs) -> TelemetryConfig
```

**Usage**:
```python
config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    buffer_size=1000
)
```

**Notes**:
- No external dependencies
- Data lost when process exits
- Fast for testing
- Not suitable for production

### `create_noop()`

Create configuration with telemetry disabled.

**Signature**:
```python
@classmethod
def create_noop(cls) -> TelemetryConfig
```

**Usage**:
```python
config = TelemetryConfig.create_noop()
```

**Notes**:
- Zero overhead
- No data collection
- Use when telemetry not needed

## Complete Field Reference

### Core Configuration

#### `enabled`

**Type**: `bool`
**Default**: `False`
**Description**: Whether telemetry is enabled.

**Usage**:
```python
config = TelemetryConfig(
    enabled=True,
    backend='memory'
)
```

**Notes**:
- Master switch for telemetry
- When `False`, all collection is disabled
- Factory methods set this to `True` automatically (except `create_noop()`)

#### `backend`

**Type**: `str`
**Default**: `'memory'`
**Description**: Backend type for telemetry storage.

**Valid Values**:
- `'memory'`: In-memory storage (testing)
- `'sqlite'`: SQLite database (local persistence)
- `'postgresql'`: PostgreSQL database (production)
- `'noop'`: No-op backend (disabled)

**Usage**:
```python
# SQLite backend
config = TelemetryConfig(
    enabled=True,
    backend='sqlite',
    backend_config={'db_path': 'telemetry.db'}
)

# PostgreSQL backend
config = TelemetryConfig(
    enabled=True,
    backend='postgresql',
    backend_config={
        'host': 'localhost',
        'port': 5432,
        'database': 'telemetry'
    }
)
```

**Validation**:
- Must be one of: `'sqlite'`, `'postgresql'`, `'memory'`, `'noop'`
- Raises `ValueError` if invalid

#### `backend_config`

**Type**: `Dict[str, Any]`
**Default**: `{}` (empty dict)
**Description**: Backend-specific configuration parameters.

**Usage**:

**SQLite Configuration**:
```python
backend_config = {
    'db_path': '/path/to/telemetry.db'
}
```

**PostgreSQL Configuration**:
```python
backend_config = {
    'host': 'postgres.example.com',
    'port': 5432,
    'database': 'spark_telemetry',
    'user': 'spark',
    'password': 'secure_password',
    'min_pool_size': 2,
    'max_pool_size': 10,
    'command_timeout': 30.0
}
```

**OTLP Configuration**:
```python
backend_config = {
    'endpoint': 'https://otlp.example.com:4317',
    'protocol': 'grpc',  # or 'http'
    'insecure': False,
    'timeout_seconds': 10,
    'headers': {
        'api-key': 'your-api-key'
    }
}
```

### Sampling Configuration

#### `sampling_rate`

**Type**: `float`
**Default**: `1.0`
**Description**: Fraction of traces to sample (0.0 to 1.0).

**Usage**:
```python
# Sample all traces (100%)
config = TelemetryConfig.create_sqlite(sampling_rate=1.0)

# Sample 10% of traces
config = TelemetryConfig.create_sqlite(sampling_rate=0.1)

# Sample 1% of traces (high-volume production)
config = TelemetryConfig.create_postgresql(sampling_rate=0.01)
```

**Validation**:
- Must be between 0.0 and 1.0 (inclusive)
- Raises `ValueError` if out of range

**Notes**:
- Uses deterministic sampling based on trace ID hash
- Consistent sampling across distributed systems
- Reduces overhead and storage costs
- Complete traces are sampled (not individual spans)

**Example - Sampling Strategies**:
```python
# Development: Sample everything
sampling_rate = 1.0

# Staging: Sample most traces
sampling_rate = 0.5

# Production low-traffic: Sample most traces
sampling_rate = 0.8

# Production high-traffic: Sample small fraction
sampling_rate = 0.05

# Production critical path: Sample everything
sampling_rate = 1.0
```

### Export Configuration

#### `export_interval`

**Type**: `float`
**Default**: `10.0`
**Description**: Interval in seconds for batch export.

**Usage**:
```python
# Export every 10 seconds (default)
config = TelemetryConfig.create_sqlite(export_interval=10.0)

# Frequent exports (low latency)
config = TelemetryConfig.create_sqlite(export_interval=1.0)

# Infrequent exports (batch efficiency)
config = TelemetryConfig.create_sqlite(export_interval=60.0)
```

**Validation**:
- Must be non-negative
- Raises `ValueError` if negative

**Notes**:
- Balances latency vs. efficiency
- Lower values: faster visibility, more overhead
- Higher values: better batching, slower visibility
- Zero disables interval-based export (manual flush only)

#### `buffer_size`

**Type**: `int`
**Default**: `1000`
**Description**: Maximum number of spans to buffer before flushing.

**Usage**:
```python
# Small buffer (low memory, frequent exports)
config = TelemetryConfig.create_sqlite(buffer_size=100)

# Large buffer (high throughput, batch efficiency)
config = TelemetryConfig.create_sqlite(buffer_size=10000)
```

**Validation**:
- Must be at least 1
- Raises `ValueError` if less than 1

**Notes**:
- Buffers span data before export
- Triggers export when buffer is full
- Higher values improve batching efficiency
- Lower values reduce memory usage
- Interacts with `export_interval` (whichever triggers first)

### Retention Configuration

#### `retention_days`

**Type**: `int`
**Default**: `30`
**Description**: Number of days to retain telemetry data.

**Usage**:
```python
# Short retention (7 days)
config = TelemetryConfig.create_sqlite(retention_days=7)

# Standard retention (30 days)
config = TelemetryConfig.create_sqlite(retention_days=30)

# Long retention (1 year)
config = TelemetryConfig.create_postgresql(retention_days=365)
```

**Validation**:
- Must be at least 1
- Raises `ValueError` if less than 1

**Notes**:
- Applies to persistent backends (SQLite, PostgreSQL)
- Cleanup runs periodically
- Balance between history and storage costs
- Consider compliance requirements

#### `max_events_per_span`

**Type**: `int`
**Default**: `100`
**Description**: Maximum number of events to store per span.

**Usage**:
```python
# Limit events (reduce storage)
config = TelemetryConfig.create_sqlite(max_events_per_span=50)

# Store many events (detailed debugging)
config = TelemetryConfig.create_sqlite(max_events_per_span=1000)
```

**Validation**:
- No explicit validation
- Higher values increase storage

**Notes**:
- Prevents unbounded event accumulation
- Older events dropped when limit exceeded
- Adjust based on debugging needs vs. storage costs

### Resource Attributes

#### `resource_attributes`

**Type**: `Dict[str, str]`
**Default**: `{}` (empty dict)
**Description**: Resource-level attributes (e.g., service name, version).

**Usage**:
```python
config = TelemetryConfig.create_sqlite(
    resource_attributes={
        'service.name': 'spark-app',
        'service.version': '2.0.0',
        'deployment.environment': 'production',
        'host.name': 'server-01',
        'cloud.provider': 'aws',
        'cloud.region': 'us-east-1'
    }
)
```

**Common Attributes** (OpenTelemetry Semantic Conventions):

| Attribute | Description | Example |
|-----------|-------------|---------|
| `service.name` | Service name | `"spark-workflow"` |
| `service.version` | Service version | `"1.0.0"` |
| `service.namespace` | Service namespace | `"production"` |
| `deployment.environment` | Deployment environment | `"production"` |
| `host.name` | Hostname | `"server-01"` |
| `host.id` | Host ID | `"i-1234567890abcdef0"` |
| `cloud.provider` | Cloud provider | `"aws"` |
| `cloud.region` | Cloud region | `"us-east-1"` |
| `container.name` | Container name | `"spark-app"` |
| `k8s.pod.name` | Kubernetes pod name | `"spark-app-abc123"` |

**Notes**:
- Attached to all telemetry from this service
- Use for filtering and grouping in observability platforms
- Follows OpenTelemetry semantic conventions
- String values only

### Feature Toggles

#### `enable_metrics`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to collect metrics.

**Usage**:
```python
# Disable metrics (traces and events only)
config = TelemetryConfig.create_sqlite(enable_metrics=False)
```

**Notes**:
- Metrics include counters, gauges, histograms
- Examples: execution count, duration, error rate
- Disable to reduce overhead or storage

#### `enable_events`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to collect events.

**Usage**:
```python
# Disable events (traces and metrics only)
config = TelemetryConfig.create_sqlite(enable_events=False)
```

**Notes**:
- Events are lifecycle moments (node started, finished, failed)
- Useful for debugging and monitoring
- Disable to reduce storage

#### `enable_traces`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to collect traces.

**Usage**:
```python
# Disable traces (metrics and events only)
config = TelemetryConfig.create_sqlite(enable_traces=False)
```

**Notes**:
- Traces track complete workflow execution
- Include spans for nodes, graphs, operations
- Disable if only metrics/events needed

### Instrumentation Configuration

#### `auto_instrument_nodes`

**Type**: `bool`
**Default**: `True`
**Description**: Automatically instrument all nodes.

**Usage**:
```python
# Disable automatic node instrumentation
config = TelemetryConfig.create_sqlite(auto_instrument_nodes=False)
```

**Notes**:
- When `True`, all nodes automatically create spans
- When `False`, manual instrumentation required
- Reduces overhead if selective instrumentation desired

#### `auto_instrument_graphs`

**Type**: `bool`
**Default**: `True`
**Description**: Automatically instrument all graphs.

**Usage**:
```python
# Disable automatic graph instrumentation
config = TelemetryConfig.create_sqlite(auto_instrument_graphs=False)
```

**Notes**:
- When `True`, all graphs automatically create traces
- When `False`, manual instrumentation required
- Useful for selective monitoring

#### `propagate_context`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to propagate telemetry context.

**Usage**:
```python
# Disable context propagation
config = TelemetryConfig.create_sqlite(propagate_context=False)
```

**Notes**:
- Enables distributed tracing across RPC boundaries
- Maintains parent-child span relationships
- Disable if not using distributed tracing

### Custom Attributes

#### `custom_attributes`

**Type**: `Dict[str, Any]`
**Default**: `{}` (empty dict)
**Description**: Custom attributes to add to all telemetry.

**Usage**:
```python
config = TelemetryConfig.create_sqlite(
    custom_attributes={
        'team': 'data-science',
        'project': 'ml-pipeline',
        'cost_center': 'engineering',
        'criticality': 'high',
        'sla_tier': 'gold'
    }
)
```

**Notes**:
- Attached to all spans, events, and metrics
- Useful for organization-specific metadata
- Can include any JSON-serializable values
- Different from `resource_attributes` (which are strings only)

## Complete Configuration Example

```python
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Production configuration
config = TelemetryConfig(
    # Core configuration
    enabled=True,
    backend='postgresql',
    backend_config={
        'host': 'postgres.prod.example.com',
        'port': 5432,
        'database': 'spark_telemetry',
        'user': 'spark',
        'password': os.getenv('POSTGRES_PASSWORD'),
        'min_pool_size': 5,
        'max_pool_size': 20
    },

    # Sampling configuration
    sampling_rate=0.1,  # Sample 10% of traces

    # Export configuration
    export_interval=30.0,  # Export every 30 seconds
    buffer_size=5000,  # Buffer up to 5000 spans

    # Retention configuration
    retention_days=90,  # Keep 90 days of data
    max_events_per_span=200,

    # Resource attributes
    resource_attributes={
        'service.name': 'spark-workflow',
        'service.version': '2.0.0',
        'deployment.environment': 'production',
        'cloud.provider': 'aws',
        'cloud.region': 'us-east-1'
    },

    # Feature toggles
    enable_metrics=True,
    enable_events=True,
    enable_traces=True,

    # Instrumentation
    auto_instrument_nodes=True,
    auto_instrument_graphs=True,
    propagate_context=True,

    # Custom attributes
    custom_attributes={
        'team': 'platform',
        'project': 'ml-pipeline',
        'criticality': 'high'
    }
)

# Use with graph
graph = Graph(start=my_node, telemetry_config=config)
result = await graph.run()
```

## Configuration Patterns

### Development Configuration

```python
# In-memory, sample everything, frequent export
config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    export_interval=1.0,
    buffer_size=100,
    enable_metrics=True,
    enable_events=True,
    enable_traces=True
)
```

### Staging Configuration

```python
# SQLite, high sampling, moderate retention
config = TelemetryConfig.create_sqlite(
    db_path='/var/lib/spark/staging_telemetry.db',
    sampling_rate=0.5,  # Sample 50%
    export_interval=10.0,
    buffer_size=1000,
    retention_days=30,
    resource_attributes={
        'service.name': 'spark-app',
        'deployment.environment': 'staging'
    }
)
```

### Production Configuration

```python
# PostgreSQL, low sampling, long retention
config = TelemetryConfig.create_postgresql(
    host='postgres.prod.example.com',
    database='spark_telemetry',
    user='spark',
    password=os.getenv('POSTGRES_PASSWORD'),
    sampling_rate=0.05,  # Sample 5%
    export_interval=30.0,
    buffer_size=10000,
    retention_days=365,
    resource_attributes={
        'service.name': 'spark-app',
        'service.version': '2.0.0',
        'deployment.environment': 'production',
        'cloud.provider': 'aws',
        'cloud.region': 'us-east-1'
    },
    custom_attributes={
        'team': 'platform',
        'criticality': 'high'
    }
)
```

### High-Volume Production

```python
# Aggressive sampling, large buffers, selective instrumentation
config = TelemetryConfig.create_postgresql(
    host='postgres.prod.example.com',
    database='spark_telemetry',
    user='spark',
    password=os.getenv('POSTGRES_PASSWORD'),
    sampling_rate=0.01,  # Sample 1%
    export_interval=60.0,  # Export every minute
    buffer_size=50000,  # Large buffer
    retention_days=30,  # Short retention
    enable_metrics=True,
    enable_events=False,  # Disable events to reduce volume
    enable_traces=True,
    max_events_per_span=50,  # Limit events
    resource_attributes={
        'service.name': 'spark-high-volume',
        'deployment.environment': 'production'
    }
)
```

### Testing Configuration

```python
# Memory backend, no sampling, immediate export
config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    export_interval=0.1,  # Export very frequently
    buffer_size=10,  # Small buffer
    enable_metrics=True,
    enable_events=True,
    enable_traces=True
)
```

## Backend-Specific Considerations

### SQLite Backend

**Pros**:
- Simple setup (single file)
- No external dependencies (except `aiosqlite`)
- Good for local development
- Automatic schema initialization

**Cons**:
- Not suitable for high concurrency
- Limited scalability
- Single-instance only

**Best For**:
- Local development
- Single-instance deployments
- Low-volume workloads

**Configuration Example**:
```python
config = TelemetryConfig.create_sqlite(
    db_path='/var/lib/spark/telemetry.db',
    sampling_rate=1.0,
    retention_days=30
)
```

### PostgreSQL Backend

**Pros**:
- Production-grade reliability
- Scalable for high volumes
- Multi-instance support
- Connection pooling
- Advanced querying

**Cons**:
- Requires external database
- More complex setup
- Higher resource usage

**Best For**:
- Production deployments
- High-volume telemetry
- Multi-instance applications

**Configuration Example**:
```python
config = TelemetryConfig.create_postgresql(
    host='postgres.example.com',
    port=5432,
    database='spark_telemetry',
    user='spark',
    password=os.getenv('POSTGRES_PASSWORD'),
    sampling_rate=0.1,
    retention_days=90
)
```

### Memory Backend

**Pros**:
- Zero setup
- Fast performance
- No external dependencies

**Cons**:
- Data lost on restart
- Limited by available memory
- Not suitable for production

**Best For**:
- Testing
- Development
- CI/CD pipelines

**Configuration Example**:
```python
config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    buffer_size=1000
)
```

## Performance Tuning

### Reduce Overhead

```python
# Low-overhead configuration
config = TelemetryConfig.create_postgresql(
    sampling_rate=0.01,  # Sample 1%
    export_interval=120.0,  # Export every 2 minutes
    buffer_size=100000,  # Large buffer
    enable_events=False,  # Disable events
    max_events_per_span=10  # Limit events
)
```

### Maximize Visibility

```python
# High-visibility configuration
config = TelemetryConfig.create_postgresql(
    sampling_rate=1.0,  # Sample 100%
    export_interval=5.0,  # Export frequently
    buffer_size=1000,  # Smaller buffer
    enable_metrics=True,
    enable_events=True,
    enable_traces=True,
    max_events_per_span=1000  # Keep many events
)
```

### Balance Cost and Insight

```python
# Balanced configuration
config = TelemetryConfig.create_postgresql(
    sampling_rate=0.1,  # Sample 10%
    export_interval=30.0,
    buffer_size=5000,
    retention_days=60,
    enable_metrics=True,
    enable_events=True,
    enable_traces=True
)
```

## Validation

TelemetryConfig validates configuration in `__post_init__()`:

**Validation Rules**:
- `sampling_rate` must be 0.0 ≤ rate ≤ 1.0
- `buffer_size` must be ≥ 1
- `export_interval` must be ≥ 0
- `retention_days` must be ≥ 1
- `backend` must be valid enum value

**Example Validation Errors**:
```python
# Error: Invalid sampling rate
config = TelemetryConfig(sampling_rate=1.5)
# ValueError: sampling_rate must be between 0.0 and 1.0

# Error: Invalid buffer size
config = TelemetryConfig(buffer_size=0)
# ValueError: buffer_size must be at least 1

# Error: Invalid backend
config = TelemetryConfig(backend='invalid')
# ValueError: backend must be one of {'sqlite', 'postgresql', 'memory', 'noop'}
```

## Serialization

TelemetryConfig supports conversion to dictionary:

```python
# Convert to dict
config_dict = config.to_dict()

# Reconstruct from dict
config = TelemetryConfig(**config_dict)
```

## See Also

- [Telemetry Guide](../telemetry/telemetry.md) - Telemetry architecture and usage
- [Telemetry Backends](../telemetry/backends.md) - Backend implementations
- [Telemetry Queries](../telemetry/queries.md) - Querying telemetry data
- [RSI System](../rsi/rsi.md) - Uses telemetry for performance analysis
- [Environment Variables](environment.md) - Environment-based configuration
