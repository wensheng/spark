# Telemetry Backends Reference

## Overview

Spark supports multiple telemetry backends for storing and querying observability data. Choose the right backend based on your deployment environment, performance requirements, and integration needs.

## Supported Backends

| Backend | Use Case | Persistence | Query Support | Dependencies |
|---------|----------|-------------|---------------|--------------|
| Memory | Development, testing | In-memory only | Full | None |
| SQLite | Local, single-machine | File-based | Full | `aiosqlite` |
| PostgreSQL | Production, multi-machine | Database | Full | `asyncpg` |
| OTLP | External platforms | Export-only | External | OpenTelemetry packages |

## Memory Backend

In-memory storage for development and testing. Data is lost when the application exits.

### Configuration

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    buffer_size=100,
    export_interval=5.0,
    enable_metrics=True,
    enable_events=True,
    enable_traces=True
)
```

### Characteristics

**Advantages**:
- Zero dependencies - works out of the box
- Fastest performance (no I/O)
- No setup required
- Perfect for unit tests

**Limitations**:
- No persistence across restarts
- Limited by available RAM
- Single-process only
- Not suitable for production

**Performance**:
- Write latency: < 1ms
- Query latency: < 1ms
- Overhead: < 1%

### Use Cases

**Unit Testing**:
```python
import pytest
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

@pytest.fixture
def telemetry_config():
    return TelemetryConfig.create_memory(sampling_rate=1.0)

async def test_graph_execution(telemetry_config):
    graph = Graph(start=my_node, telemetry_config=telemetry_config)
    result = await graph.run()

    # Query telemetry
    from spark.telemetry import TelemetryManager
    manager = TelemetryManager.get_instance()
    traces = await manager.query_traces(limit=1)

    assert len(traces) == 1
    assert traces[0].status == "completed"
```

**Development and Debugging**:
```python
# Quick setup for local development
config = TelemetryConfig.create_memory()
graph = Graph(start=my_node, telemetry_config=config)

# Run and analyze
await graph.run()

manager = TelemetryManager.get_instance()
traces = await manager.query_traces()
print(f"Collected {len(traces)} traces")
```

## SQLite Backend

File-based persistent storage for local and single-machine deployments.

### Configuration

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",              # Database file path
    sampling_rate=1.0,                   # Sample rate
    buffer_size=100,                     # Buffer size
    export_interval=5.0,                 # Export interval
    enable_metrics=True,
    enable_events=True,
    enable_traces=True,
    metadata={                           # Global metadata
        "environment": "development",
        "version": "1.0.0"
    }
)
```

### Dependencies

```bash
pip install aiosqlite
```

### Characteristics

**Advantages**:
- Persistent storage across restarts
- Single file deployment
- Full SQL query capabilities
- No separate database server required
- Excellent for local development and testing

**Limitations**:
- Single-writer (no concurrent writes from multiple processes)
- Limited scalability for high-volume production
- File locks can cause contention
- Not suitable for distributed systems

**Performance**:
- Write latency: 1-10ms (depends on disk)
- Query latency: 1-100ms (depends on query complexity)
- Overhead: 1-3%
- Storage: ~1KB per trace, ~500B per span/event

### Database Schema

The SQLite backend automatically creates tables:

```sql
-- Traces table
CREATE TABLE traces (
    trace_id TEXT PRIMARY KEY,
    name TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration REAL,
    status TEXT,
    attributes JSON
);

-- Spans table
CREATE TABLE spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT,
    parent_span_id TEXT,
    name TEXT,
    kind TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration REAL,
    status TEXT,
    attributes JSON,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
);

-- Events table
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT,
    span_id TEXT,
    type TEXT,
    name TEXT,
    timestamp TIMESTAMP,
    attributes JSON,
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
);

-- Metrics table
CREATE TABLE metrics (
    metric_id TEXT PRIMARY KEY,
    trace_id TEXT,
    name TEXT,
    value REAL,
    unit TEXT,
    aggregation_type TEXT,
    timestamp TIMESTAMP,
    attributes JSON
);
```

Indexes are automatically created for common query patterns.

### Use Cases

**Local Development**:
```python
# Persistent telemetry for local work
config = TelemetryConfig.create_sqlite(
    db_path="dev_telemetry.db",
    sampling_rate=1.0
)

graph = Graph(start=my_node, telemetry_config=config)

# Run multiple times, data persists
for i in range(10):
    await graph.run()
```

**RSI Testing**:
```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig

# SQLite is perfect for RSI development
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="rsi_telemetry.db",
    sampling_rate=1.0
)

production_graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Collect telemetry data
for i in range(100):
    await production_graph.run()

# Run RSI analysis
rsi_config = RSIMetaGraphConfig(
    model=model,
    target_graph_id="production_workflow"
)
rsi_graph = RSIMetaGraph(config=rsi_config)
result = await rsi_graph.run_single_cycle()
```

**Single-Machine Production**:
```python
# Small-scale production deployments
config = TelemetryConfig.create_sqlite(
    db_path="/var/lib/myapp/telemetry.db",
    sampling_rate=0.1,  # Sample 10% to reduce storage
    buffer_size=500,
    export_interval=30.0
)
```

## PostgreSQL Backend

Production-grade persistent storage for multi-machine and high-volume deployments.

### Configuration

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:password@localhost:5432/telemetry",
    sampling_rate=0.1,                   # Sample 10% in production
    buffer_size=1000,                    # Larger buffer for batching
    export_interval=30.0,                # Less frequent exports
    enable_metrics=True,
    enable_events=True,
    enable_traces=True,
    metadata={
        "environment": "production",
        "datacenter": "us-east-1"
    }
)
```

### Dependencies

```bash
pip install asyncpg
```

### Connection String Format

```
postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&...]
```

Examples:
```python
# Local development
"postgresql://localhost/telemetry"

# With authentication
"postgresql://user:password@localhost:5432/telemetry"

# Production with SSL
"postgresql://user:password@prod-db.example.com:5432/telemetry?sslmode=require"

# Connection pooling
"postgresql://user:password@localhost/telemetry?min_size=10&max_size=20"
```

### Characteristics

**Advantages**:
- Concurrent writes from multiple processes/machines
- Excellent scalability for high-volume production
- Full ACID transactions
- Advanced query capabilities (aggregations, joins)
- Standard monitoring and backup tools
- Battle-tested for production workloads

**Limitations**:
- Requires separate database server
- More complex deployment
- Higher operational overhead
- Network latency for remote database

**Performance**:
- Write latency: 5-50ms (depends on network and load)
- Query latency: 10-500ms (depends on query complexity and indexes)
- Overhead: 2-5%
- Scales to millions of traces

### Database Setup

Create database and schema:

```sql
-- Create database
CREATE DATABASE telemetry;

-- Connect to database
\c telemetry

-- Tables are automatically created by Spark
-- Alternatively, run schema creation manually:

CREATE TABLE traces (
    trace_id UUID PRIMARY KEY,
    name VARCHAR(255),
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    duration DOUBLE PRECISION,
    status VARCHAR(50),
    attributes JSONB
);

CREATE TABLE spans (
    span_id UUID PRIMARY KEY,
    trace_id UUID REFERENCES traces(trace_id),
    parent_span_id UUID,
    name VARCHAR(255),
    kind VARCHAR(50),
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,
    duration DOUBLE PRECISION,
    status VARCHAR(50),
    attributes JSONB
);

CREATE TABLE events (
    event_id UUID PRIMARY KEY,
    trace_id UUID REFERENCES traces(trace_id),
    span_id UUID,
    type VARCHAR(100),
    name VARCHAR(255),
    timestamp TIMESTAMPTZ,
    attributes JSONB
);

CREATE TABLE metrics (
    metric_id UUID PRIMARY KEY,
    trace_id UUID,
    name VARCHAR(255),
    value DOUBLE PRECISION,
    unit VARCHAR(50),
    aggregation_type VARCHAR(50),
    timestamp TIMESTAMPTZ,
    attributes JSONB
);

-- Create indexes for common queries
CREATE INDEX idx_traces_start_time ON traces(start_time);
CREATE INDEX idx_traces_status ON traces(status);
CREATE INDEX idx_spans_trace_id ON spans(trace_id);
CREATE INDEX idx_spans_parent_span_id ON spans(parent_span_id);
CREATE INDEX idx_events_trace_id ON events(trace_id);
CREATE INDEX idx_events_type ON events(type);
CREATE INDEX idx_metrics_name ON metrics(name);
CREATE INDEX idx_metrics_timestamp ON metrics(timestamp);

-- JSONB indexes for attribute queries
CREATE INDEX idx_traces_attributes ON traces USING GIN(attributes);
CREATE INDEX idx_spans_attributes ON spans USING GIN(attributes);
```

### Use Cases

**Multi-Machine Production**:
```python
# Production configuration
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://telemetry_user:secure_pass@db.prod.example.com:5432/telemetry?sslmode=require",
    sampling_rate=0.1,      # Sample 10% to reduce load
    buffer_size=1000,       # Large batches
    export_interval=30.0,   # Less frequent exports
)

graph = Graph(start=my_node, telemetry_config=config)
```

**High-Volume Systems**:
```python
# Optimized for high throughput
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@db.example.com/telemetry?max_size=50",
    sampling_rate=0.05,     # Sample 5%
    buffer_size=5000,       # Very large batches
    export_interval=60.0,   # Export once per minute
    enable_events=False,    # Disable events to reduce volume
)
```

**Distributed RSI**:
```python
# RSI with centralized telemetry
telemetry_config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@central-db.example.com/telemetry",
    sampling_rate=1.0  # Full sampling for RSI
)

# Multiple production graphs report to same database
graph1 = Graph(start=workflow1, telemetry_config=telemetry_config)
graph2 = Graph(start=workflow2, telemetry_config=telemetry_config)

# RSI analyzes data from all graphs
rsi_graph = RSIMetaGraph(config=rsi_config)
```

## OTLP Backend

Export telemetry to external observability platforms using OpenTelemetry Protocol.

### Configuration

```python
from spark.telemetry import TelemetryConfig

config = TelemetryConfig.create_otlp(
    endpoint="http://localhost:4317",   # OTLP gRPC endpoint
    sampling_rate=0.1,
    buffer_size=100,
    export_interval=10.0,
    headers={                           # Optional authentication headers
        "Authorization": "Bearer token123"
    },
    metadata={
        "service.name": "spark_workflow",
        "service.version": "1.0.0"
    }
)
```

### Dependencies

```bash
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

### Characteristics

**Advantages**:
- Integrates with existing observability infrastructure
- Support for popular platforms (Jaeger, Grafana Tempo, Honeycomb, etc.)
- No local storage required
- Industry-standard protocol
- Rich ecosystem of tools

**Limitations**:
- No local query API (query via external platform)
- Requires external service
- Network dependency
- Export-only (cannot query from Spark)

**Performance**:
- Write latency: 10-100ms (depends on network and endpoint)
- No query support from Spark
- Overhead: 3-8%

### Supported Platforms

**Jaeger**:
```python
config = TelemetryConfig.create_otlp(
    endpoint="http://jaeger-collector:4317",
    sampling_rate=0.1,
    metadata={
        "service.name": "spark_workflow"
    }
)
```

**Grafana Tempo**:
```python
config = TelemetryConfig.create_otlp(
    endpoint="http://tempo:4317",
    sampling_rate=0.1,
    metadata={
        "service.name": "spark_workflow",
        "environment": "production"
    }
)
```

**Honeycomb**:
```python
config = TelemetryConfig.create_otlp(
    endpoint="https://api.honeycomb.io:443",
    sampling_rate=0.1,
    headers={
        "x-honeycomb-team": "your-api-key",
        "x-honeycomb-dataset": "spark-telemetry"
    },
    metadata={
        "service.name": "spark_workflow"
    }
)
```

**New Relic**:
```python
config = TelemetryConfig.create_otlp(
    endpoint="https://otlp.nr-data.net:4317",
    sampling_rate=0.1,
    headers={
        "api-key": "your-license-key"
    }
)
```

### Use Cases

**Integration with Existing Infrastructure**:
```python
# Export to existing Jaeger/Tempo deployment
config = TelemetryConfig.create_otlp(
    endpoint="http://observability.example.com:4317",
    sampling_rate=0.1
)

graph = Graph(start=my_node, telemetry_config=config)
```

**Hybrid Setup**:
```python
# Use multiple backends simultaneously
from spark.telemetry import TelemetryManager

# Configure both SQLite (for RSI) and OTLP (for monitoring)
sqlite_config = TelemetryConfig.create_sqlite(db_path="rsi_telemetry.db")
otlp_config = TelemetryConfig.create_otlp(endpoint="http://jaeger:4317")

# Note: Currently only one backend per graph
# Use separate graphs or implement custom multi-backend solution
```

## Backend Selection Guidelines

### Decision Tree

```
Do you need persistence?
├─ No → Memory backend
└─ Yes
   │
   Is this production?
   ├─ No → SQLite backend
   └─ Yes
      │
      Single machine or distributed?
      ├─ Single → SQLite backend (if low volume) or PostgreSQL
      └─ Distributed → PostgreSQL backend
         │
         Do you have existing observability infrastructure?
         ├─ Yes → OTLP backend (export to existing)
         └─ No → PostgreSQL backend
```

### Recommendations by Use Case

| Use Case | Recommended Backend | Rationale |
|----------|-------------------|-----------|
| Unit tests | Memory | Fast, no dependencies, ephemeral |
| Local development | SQLite | Persistent, single file, easy setup |
| RSI development | SQLite | Full query support, persistent |
| Single-machine production | SQLite or PostgreSQL | SQLite for low volume, PostgreSQL for high |
| Multi-machine production | PostgreSQL | Concurrent writes, scalability |
| Microservices | PostgreSQL + OTLP | Central storage + platform integration |
| CI/CD pipelines | Memory or SQLite | Fast, simple, disposable |
| Performance testing | Memory | Minimal overhead |

### Performance Comparison

| Operation | Memory | SQLite | PostgreSQL | OTLP |
|-----------|--------|--------|------------|------|
| Write trace | 0.1ms | 2ms | 10ms | 20ms |
| Write 100 spans | 1ms | 20ms | 50ms | 100ms |
| Query 10 traces | 0.5ms | 10ms | 30ms | N/A |
| Complex aggregation | 5ms | 100ms | 200ms | N/A |
| Overhead | <1% | 1-3% | 2-5% | 3-8% |

### Storage Requirements

| Backend | Storage per Trace | Storage per Span | Retention |
|---------|------------------|------------------|-----------|
| Memory | RAM only | RAM only | Until restart |
| SQLite | ~1KB | ~500B | Manual cleanup |
| PostgreSQL | ~1KB | ~500B | Automated policies |
| OTLP | N/A | N/A | Platform-specific |

## Configuration Examples

### Development Setup

```python
# Fast, persistent, zero config
config = TelemetryConfig.create_sqlite(
    db_path="dev_telemetry.db",
    sampling_rate=1.0,
    buffer_size=50,
    export_interval=1.0  # Fast export for debugging
)
```

### Staging Environment

```python
# Similar to production but full sampling
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@staging-db.example.com/telemetry",
    sampling_rate=1.0,      # Full sampling in staging
    buffer_size=500,
    export_interval=10.0
)
```

### Production Environment

```python
# Optimized for high volume
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@prod-db.example.com/telemetry?sslmode=require",
    sampling_rate=0.1,      # Sample 10%
    buffer_size=2000,       # Large batches
    export_interval=60.0,   # Infrequent exports
    enable_events=False,    # Reduce volume
    metadata={
        "environment": "production",
        "region": "us-east-1",
        "version": "2.0.0"
    }
)
```

### Observability Platform Integration

```python
# Export to Grafana stack
config = TelemetryConfig.create_otlp(
    endpoint="http://tempo:4317",
    sampling_rate=0.1,
    buffer_size=200,
    export_interval=15.0,
    metadata={
        "service.name": "spark_workflow",
        "service.namespace": "production",
        "service.version": "2.0.0",
        "deployment.environment": "production"
    }
)
```

## Migration Between Backends

### From Memory to SQLite

```python
# Step 1: Change config
old_config = TelemetryConfig.create_memory()
new_config = TelemetryConfig.create_sqlite(db_path="telemetry.db")

# Step 2: Update graph
graph = Graph(start=my_node, telemetry_config=new_config)

# No data migration needed (memory data is ephemeral)
```

### From SQLite to PostgreSQL

```python
# Step 1: Export SQLite data
import sqlite3
import asyncpg

# Read from SQLite
conn = sqlite3.connect("telemetry.db")
traces = conn.execute("SELECT * FROM traces").fetchall()
spans = conn.execute("SELECT * FROM spans").fetchall()
events = conn.execute("SELECT * FROM events").fetchall()

# Write to PostgreSQL
pg_conn = await asyncpg.connect("postgresql://user:pass@localhost/telemetry")
for trace in traces:
    await pg_conn.execute(
        "INSERT INTO traces VALUES ($1, $2, $3, $4, $5, $6, $7)",
        *trace
    )
# ... repeat for spans, events, metrics

# Step 2: Update config
new_config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@localhost/telemetry"
)
graph = Graph(start=my_node, telemetry_config=new_config)
```

## Troubleshooting

### SQLite: Database Locked Error

```python
# Increase timeout
import sqlite3
sqlite3.connect("telemetry.db", timeout=30.0)

# Or reduce concurrency
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    buffer_size=1000,      # Larger batches
    export_interval=10.0   # Less frequent writes
)
```

### PostgreSQL: Connection Pool Exhausted

```python
# Increase connection pool size
config = TelemetryConfig.create_postgresql(
    connection_string="postgresql://user:pass@localhost/telemetry?min_size=10&max_size=50"
)
```

### OTLP: Connection Refused

```python
# Check endpoint and add timeout
config = TelemetryConfig.create_otlp(
    endpoint="http://localhost:4317",
    headers={"timeout": "30"}  # Add timeout
)

# Verify OTLP collector is running:
# docker run -p 4317:4317 otel/opentelemetry-collector
```

## Next Steps

- **[Traces and Spans](traces-spans.md)**: Deep dive into trace/span model
- **[Events and Metrics](events-metrics.md)**: Event and metric reference
- **[Querying Telemetry](querying.md)**: Query API for each backend
- **[Telemetry Patterns](patterns.md)**: Best practices by backend type
