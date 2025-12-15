---
title: Telemetry
parent: Architecture
nav_order: 3
---
# Telemetry Architecture

## Overview

The Telemetry system provides comprehensive observability for graph and node execution through distributed tracing, structured events, and metrics collection. The architecture emphasizes low overhead, flexible storage backends, and rich query capabilities.

## Design Philosophy

### Observability-First

Spark treats observability as a first-class concern, not an afterthought:

- **Built-in**: Telemetry integrated into core execution, not bolted on
- **Automatic**: Zero instrumentation code in user nodes
- **Flexible**: Multiple backends (memory, SQLite, PostgreSQL, OTLP)
- **Performant**: Sampling, buffering, async export to minimize overhead
- **Standard**: OpenTelemetry-compatible data model

### Telemetry vs. Logging

**Key Differences**:

| Aspect | Logging | Telemetry |
|--------|---------|-----------|
| **Purpose** | Debugging | Performance analysis |
| **Structure** | Unstructured text | Structured data |
| **Relationships** | None | Hierarchical traces/spans |
| **Query** | Text search | Rich queries, aggregations |
| **Overhead** | High (I/O) | Low (buffered, sampled) |

Spark uses telemetry for performance and structured logging for debugging.

## Telemetry Data Model

### Hierarchical Structure

```
Trace (Workflow Execution)
  ├── Span (Graph Execution)
  │     ├── Span (Node 1 Execution)
  │     ├── Span (Node 2 Execution)
  │     └── Span (Node 3 Execution)
  ├── Event (graph_started)
  ├── Event (node_finished)
  └── Metric (execution_duration)
```

### Trace

**Purpose**: Represents a complete workflow execution from start to finish.

```python
@dataclass
class Trace:
    trace_id: str                      # Unique trace identifier
    name: str                          # Trace name (e.g., "graph_execution")
    start_time: float                  # Unix timestamp (seconds)
    end_time: Optional[float]          # Unix timestamp (seconds)
    duration: Optional[float]          # Seconds
    status: TraceStatus                # SUCCESS, ERROR, CANCELLED
    attributes: Dict[str, Any]         # Arbitrary metadata
    resource: Dict[str, Any]           # Resource attributes (service, version)
```

**Design Decision**: Traces use UUIDs as IDs for global uniqueness across distributed systems.

**Trace Lifecycle**:
```python
# Start trace
trace = manager.start_trace("my_workflow", attributes={
    "user_id": "alice",
    "environment": "production"
})

# ... work happens ...

# End trace
manager.end_trace(trace.trace_id, status=TraceStatus.SUCCESS)
```

### Span

**Purpose**: Represents a single operation within a trace (node execution, API call, etc.).

```python
@dataclass
class Span:
    span_id: str                       # Unique span identifier
    trace_id: str                      # Parent trace ID
    parent_span_id: Optional[str]      # Parent span ID (for nesting)
    name: str                          # Span name (e.g., "process_node")
    start_time: float                  # Unix timestamp
    end_time: Optional[float]          # Unix timestamp
    duration: Optional[float]          # Seconds
    status: SpanStatus                 # OK, ERROR
    kind: SpanKind                     # INTERNAL, CLIENT, SERVER
    attributes: Dict[str, Any]         # Span-specific metadata
```

**Span Kinds**:
- **INTERNAL**: Default, within-process operation
- **CLIENT**: Outbound call (RPC client, HTTP request)
- **SERVER**: Inbound call (RPC server, HTTP handler)
- **PRODUCER/CONSUMER**: Message queue operations

**Span Nesting**:
```python
# Top-level span (graph execution)
graph_span = manager.start_span("graph_run", trace_id)

# Nested spans (node executions)
node_span = manager.start_span(
    "node_process",
    trace_id,
    parent_span_id=graph_span.span_id
)
```

**Design Decision**: Spans form a tree structure via parent_span_id, enabling flame graphs and critical path analysis.

### Event

**Purpose**: Represents a discrete point-in-time occurrence.

```python
@dataclass
class Event:
    event_id: str                      # Unique event identifier
    trace_id: str                      # Associated trace
    span_id: Optional[str]             # Associated span
    event_type: str                    # Event category
    name: str                          # Event name
    timestamp: float                   # Unix timestamp
    attributes: Dict[str, Any]         # Event data
```

**Event Types**:
- **graph_started**: Graph execution began
- **graph_finished**: Graph execution completed
- **graph_failed**: Graph execution failed
- **node_started**: Node execution began
- **node_finished**: Node execution completed
- **node_failed**: Node execution failed
- **checkpoint_created**: Checkpoint saved
- **custom**: User-defined events

**Events vs. Spans**:
- **Events**: Point in time (log entry)
- **Spans**: Duration (operation lifecycle)

### Metric

**Purpose**: Numerical measurement over time.

```python
@dataclass
class Metric:
    metric_id: str                     # Unique metric identifier
    trace_id: str                      # Associated trace
    name: str                          # Metric name
    value: float                       # Metric value
    unit: str                          # Unit (seconds, count, bytes)
    timestamp: float                   # Unix timestamp
    aggregation: MetricAggregation     # GAUGE, COUNTER, HISTOGRAM
    attributes: Dict[str, Any]         # Metric dimensions
```

**Metric Types**:
- **GAUGE**: Point-in-time value (memory usage, queue depth)
- **COUNTER**: Monotonically increasing value (requests, errors)
- **HISTOGRAM**: Distribution (latency percentiles)

**Example Metrics**:
```python
# Execution duration
manager.record_metric(
    "execution.duration",
    value=1.234,
    unit="seconds",
    aggregation=MetricAggregation.HISTOGRAM
)

# Token count
manager.record_metric(
    "llm.tokens",
    value=1500,
    unit="count",
    aggregation=MetricAggregation.COUNTER,
    attributes={"model": "gpt-5-mini"}
)
```

## TelemetryManager Design

### Singleton Pattern

**Design Decision**: Use singleton pattern for global access.

```python
class TelemetryManager:
    _instance: Optional['TelemetryManager'] = None

    @classmethod
    def get_instance(cls) -> 'TelemetryManager':
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        if cls._instance:
            cls._instance.shutdown()
        cls._instance = None
```

**Rationale**:
- Global accessibility from any component
- Single configuration point
- Consistent telemetry across entire application
- Easy testing (reset between tests)

**Trade-off**: Singletons make testing harder, but telemetry benefits from global coordination.

### Manager Responsibilities

```python
class TelemetryManager:
    def __init__(self, config: Optional[TelemetryConfig] = None):
        self.config = config or TelemetryConfig()
        self.backend = self._create_backend()
        self.sampler = self._create_sampler()
        self._buffers = {
            'traces': [],
            'spans': [],
            'events': [],
            'metrics': []
        }
        self._export_task = None

    # Trace management
    def start_trace(self, name: str, **kwargs) -> Trace
    def end_trace(self, trace_id: str, **kwargs) -> None

    # Span management
    def start_span(self, name: str, trace_id: str, **kwargs) -> Span
    def end_span(self, span_id: str, **kwargs) -> None

    # Event recording
    def record_event(self, event_type: str, name: str, **kwargs) -> None

    # Metric recording
    def record_metric(self, name: str, value: float, **kwargs) -> None

    # Query API
    async def query_traces(self, **filters) -> List[Trace]
    async def query_spans(self, **filters) -> List[Span]
    async def query_events(self, **filters) -> List[Event]
    async def query_metrics(self, **filters) -> List[Metric]

    # Lifecycle
    async def flush(self) -> None
    def shutdown(self) -> None
```

## Backend Abstraction Layer

### Backend Interface

```python
class TelemetryBackend(ABC):
    @abstractmethod
    async def export_traces(self, traces: List[Trace]) -> None:
        """Export traces to backend."""
        pass

    @abstractmethod
    async def export_spans(self, spans: List[Span]) -> None:
        """Export spans to backend."""
        pass

    @abstractmethod
    async def export_events(self, events: List[Event]) -> None:
        """Export events to backend."""
        pass

    @abstractmethod
    async def export_metrics(self, metrics: List[Metric]) -> None:
        """Export metrics to backend."""
        pass

    @abstractmethod
    async def query_traces(self, **filters) -> List[Trace]:
        """Query traces from backend."""
        pass

    # ... additional query methods
```

**Design Rationale**:
- Decouple telemetry collection from storage
- Enable multiple backends (development vs. production)
- Allow custom backends (company-specific systems)
- Consistent API across all backends

### Backend Implementations

#### MemoryBackend

**Purpose**: In-memory storage for testing and development.

```python
class MemoryBackend(TelemetryBackend):
    def __init__(self):
        self._traces: List[Trace] = []
        self._spans: List[Span] = []
        self._events: List[Event] = []
        self._metrics: List[Metric] = []
        self._lock = asyncio.Lock()

    async def export_traces(self, traces: List[Trace]) -> None:
        async with self._lock:
            self._traces.extend(traces)

    async def query_traces(self, limit: int = 100, **filters) -> List[Trace]:
        async with self._lock:
            result = self._traces
            # Apply filters
            if 'status' in filters:
                result = [t for t in result if t.status == filters['status']]
            return result[:limit]
```

**Trade-offs**:
- **Pro**: Zero setup, fast, great for testing
- **Con**: Data lost on restart, no persistence, memory bound
- **Use**: Development, testing, demos

#### SQLiteBackend

**Purpose**: Persistent local storage with SQL query capabilities.

**Schema Design**:
```sql
CREATE TABLE traces (
    trace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    duration REAL,
    status TEXT,
    attributes TEXT,  -- JSON
    resource TEXT     -- JSON
);

CREATE TABLE spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_span_id TEXT,
    name TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    duration REAL,
    status TEXT,
    kind TEXT,
    attributes TEXT,  -- JSON
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
);

CREATE INDEX idx_spans_trace_id ON spans(trace_id);
CREATE INDEX idx_spans_start_time ON spans(start_time);

-- Similar tables for events and metrics
```

**Implementation**:
```python
class SQLiteBackend(TelemetryBackend):
    def __init__(self, db_path: str = "telemetry.db"):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def _ensure_connection(self):
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            await self._create_tables()

    async def export_traces(self, traces: List[Trace]) -> None:
        await self._ensure_connection()
        async with self._connection.execute_batch(
            "INSERT OR REPLACE INTO traces VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(t.trace_id, t.name, t.start_time, t.end_time, t.duration,
              t.status.value, json.dumps(t.attributes), json.dumps(t.resource))
             for t in traces]
        ):
            pass
        await self._connection.commit()

    async def query_traces(self, limit: int = 100, **filters) -> List[Trace]:
        await self._ensure_connection()
        query = "SELECT * FROM traces WHERE 1=1"
        params = []

        if 'status' in filters:
            query += " AND status = ?"
            params.append(filters['status'].value)

        query += f" ORDER BY start_time DESC LIMIT {limit}"

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_trace(row) for row in rows]
```

**Trade-offs**:
- **Pro**: Persistent, SQL queries, good for single machine
- **Con**: Not distributed, file I/O overhead
- **Use**: Production (single machine), development, testing

#### PostgreSQLBackend

**Purpose**: Production-grade persistent storage with distributed query.

**Implementation**: Similar to SQLite but uses `asyncpg` and production-optimized schema with partitioning, indexes.

**Trade-offs**:
- **Pro**: Distributed, highly available, complex queries, aggregations
- **Con**: Requires PostgreSQL setup, network latency
- **Use**: Production (multi-machine), data warehouse

#### OTLPBackend

**Purpose**: Export to OpenTelemetry Protocol (OTLP) compatible systems.

**Supported Targets**:
- Jaeger
- Zipkin
- Prometheus
- Grafana
- Cloud observability platforms (Datadog, New Relic, etc.)

**Implementation**:
```python
class OTLPBackend(TelemetryBackend):
    def __init__(self, endpoint: str, headers: Dict[str, str] = None):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.client = httpx.AsyncClient()

    async def export_traces(self, traces: List[Trace]) -> None:
        """Export traces in OTLP format."""
        payload = self._convert_to_otlp_format(traces)

        await self.client.post(
            f"{self.endpoint}/v1/traces",
            json=payload,
            headers=self.headers
        )

    def _convert_to_otlp_format(self, traces: List[Trace]) -> Dict:
        """Convert Spark traces to OTLP format."""
        # OTLP format conversion
        pass
```

**Trade-offs**:
- **Pro**: Standard protocol, wide ecosystem, vendor-agnostic
- **Con**: Network dependency, format conversion overhead
- **Use**: Production with existing observability infrastructure

## Sampling and Buffering Strategy

### Sampling

**Purpose**: Reduce overhead by collecting only a percentage of traces.

```python
class Sampler(ABC):
    @abstractmethod
    def should_sample(self, trace_id: str, name: str,
                      attributes: Dict) -> bool:
        """Decide whether to sample this trace."""
        pass

class ProbabilitySampler(Sampler):
    def __init__(self, sampling_rate: float):
        self.sampling_rate = sampling_rate  # 0.0 to 1.0

    def should_sample(self, trace_id: str, name: str,
                      attributes: Dict) -> bool:
        # Deterministic sampling based on trace_id
        hash_value = int(hashlib.md5(trace_id.encode()).hexdigest(), 16)
        return (hash_value % 1000) < (self.sampling_rate * 1000)
```

**Sampling Strategies**:
- **Probability**: Sample X% of traces (e.g., 10%)
- **Rate-Limiting**: Sample at most N traces per second
- **Adaptive**: Sample more when error rate increases
- **Always-Sample**: Sample all traces (development)

**Design Decision**: Use deterministic sampling based on trace_id so all spans/events for a sampled trace are collected.

### Buffering

**Purpose**: Batch telemetry data before export to reduce I/O overhead.

```python
class TelemetryManager:
    def __init__(self, config: TelemetryConfig):
        self.config = config
        self._buffers = {
            'traces': deque(maxlen=config.buffer_size),
            'spans': deque(maxlen=config.buffer_size),
            'events': deque(maxlen=config.buffer_size),
            'metrics': deque(maxlen=config.buffer_size)
        }
        self._last_export = time.time()

    def _should_export(self) -> bool:
        """Check if buffers should be exported."""
        # Export if buffer full
        if any(len(buf) >= self.config.buffer_size for buf in self._buffers.values()):
            return True

        # Export if interval elapsed
        if time.time() - self._last_export >= self.config.export_interval:
            return True

        return False

    async def _maybe_export(self) -> None:
        """Export buffers if conditions met."""
        if self._should_export():
            await self.flush()

    async def flush(self) -> None:
        """Force export of all buffered data."""
        if self._buffers['traces']:
            await self.backend.export_traces(list(self._buffers['traces']))
            self._buffers['traces'].clear()

        # Same for spans, events, metrics
        self._last_export = time.time()
```

**Buffer Configuration**:
```python
@dataclass
class TelemetryConfig:
    buffer_size: int = 1000           # Max items before export
    export_interval: float = 30.0     # Seconds between exports
```

**Trade-offs**:
- **Larger buffer**: Lower overhead, higher memory, longer delay
- **Smaller buffer**: Higher overhead, lower memory, shorter delay

## Instrumentation Integration

### Automatic Instrumentation

**Graph Execution**:
```python
class Graph:
    async def run(self, task: Task) -> NodeMessage:
        # Start trace
        trace = None
        if self.telemetry_config:
            manager = TelemetryManager.get_instance()
            trace = manager.start_trace(
                f"graph_run:{self.graph_id}",
                attributes={
                    'graph_id': self.graph_id,
                    'task_type': task.type.value
                }
            )

        try:
            result = await self._execute(task, trace_id=trace.trace_id)

            if trace:
                manager.end_trace(trace.trace_id, status=TraceStatus.SUCCESS)

            return result

        except Exception as e:
            if trace:
                manager.end_trace(
                    trace.trace_id,
                    status=TraceStatus.ERROR,
                    attributes={'error': str(e)}
                )
            raise
```

**Node Execution**:
```python
class Graph:
    async def _execute_node(self, node: Node, context: ExecutionContext):
        manager = TelemetryManager.get_instance()

        # Start span
        span = manager.start_span(
            f"node:{node.node_id}",
            trace_id=context.trace_id,
            parent_span_id=context.span_id,
            attributes={
                'node_id': node.node_id,
                'node_type': type(node).__name__
            }
        )

        try:
            result = await node.process(context)

            manager.end_span(span.span_id, status=SpanStatus.OK)
            return result

        except Exception as e:
            manager.end_span(
                span.span_id,
                status=SpanStatus.ERROR,
                attributes={'error': str(e)}
            )
            raise
```

**Design Decision**: Instrumentation is automatic and transparent to user code. No manual span creation needed in nodes.

### Custom Instrumentation

**Manual Spans**:
```python
class MyNode(Node):
    async def work(self, context):
        manager = TelemetryManager.get_instance()

        # Custom span for expensive operation
        async with manager.start_span(
            "expensive_computation",
            trace_id=context.trace_id
        ) as span:
            result = await self._expensive_computation()

        return {'result': result}
```

**Custom Metrics**:
```python
class MyNode(Node):
    async def work(self, context):
        manager = TelemetryManager.get_instance()

        # Record custom metric
        manager.record_metric(
            "cache_hit_rate",
            value=0.85,
            unit="ratio",
            aggregation=MetricAggregation.GAUGE,
            attributes={'cache_type': 'redis'}
        )
```

## Query API Design

### Query Interface

```python
class TelemetryManager:
    async def query_traces(
        self,
        trace_ids: Optional[List[str]] = None,
        status: Optional[TraceStatus] = None,
        start_time_after: Optional[float] = None,
        start_time_before: Optional[float] = None,
        name_pattern: Optional[str] = None,
        attribute_filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "start_time",
        order_desc: bool = True
    ) -> List[Trace]:
        """Query traces with filters."""
        return await self.backend.query_traces(
            trace_ids=trace_ids,
            status=status,
            start_time_after=start_time_after,
            start_time_before=start_time_before,
            name_pattern=name_pattern,
            attribute_filters=attribute_filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=order_desc
        )
```

### Query Examples

**Find slow traces**:
```python
slow_traces = await manager.query_traces(
    attribute_filters={'duration__gt': 5.0},
    order_by='duration',
    order_desc=True,
    limit=10
)
```

**Find failed executions**:
```python
failed_traces = await manager.query_traces(
    status=TraceStatus.ERROR,
    start_time_after=time.time() - 86400,  # Last 24 hours
    limit=100
)
```

**Find spans for specific node**:
```python
node_spans = await manager.query_spans(
    trace_id=trace_id,
    attribute_filters={'node_id': 'node_123'}
)
```

**Aggregate metrics**:
```python
# Backend-specific aggregation
metrics = await manager.query_metrics(
    name='llm.tokens',
    aggregation=MetricAggregation.COUNTER,
    start_time_after=start_of_day
)

total_tokens = sum(m.value for m in metrics)
```

## Performance Considerations

### Overhead Analysis

**Per-Trace Overhead**:
- Trace creation: ~50µs
- Span creation: ~30µs
- Event recording: ~20µs
- Metric recording: ~10µs

**Buffering Overhead**:
- Memory: Buffer size * item size (traces ~1KB, spans ~500B)
- CPU: Minimal (append to deque)

**Export Overhead**:
- Memory backend: ~1ms per 1000 items
- SQLite backend: ~50ms per 1000 items
- PostgreSQL backend: ~100ms per 1000 items
- OTLP backend: ~200ms per 1000 items (network)

**Optimization Strategies**:
- **Sampling**: Reduce by 10x-100x with 10%-1% sampling
- **Buffering**: Batch exports reduce overhead
- **Async Export**: Non-blocking background export
- **Selective Recording**: Disable events/metrics if not needed

### Configuration for Different Scenarios

**Development** (high fidelity):
```python
config = TelemetryConfig(
    sampling_rate=1.0,           # Sample everything
    buffer_size=100,             # Small buffer (fast export)
    export_interval=1.0,         # Export frequently
    enable_events=True,
    enable_metrics=True
)
```

**Production** (low overhead):
```python
config = TelemetryConfig(
    sampling_rate=0.1,           # Sample 10%
    buffer_size=10000,           # Large buffer
    export_interval=60.0,        # Export every minute
    enable_events=False,         # Disable events
    enable_metrics=True          # Keep metrics
)
```

**Performance Testing** (minimal overhead):
```python
config = TelemetryConfig(
    sampling_rate=0.01,          # Sample 1%
    buffer_size=50000,           # Very large buffer
    export_interval=300.0,       # Export every 5 minutes
    enable_events=False,
    enable_metrics=False
)
```

## Distributed Tracing

### Trace Context Propagation

**W3C Trace Context Standard**:
```python
@dataclass
class TraceContext:
    trace_id: str        # 32-character hex
    parent_id: str       # 16-character hex (span_id of parent)
    trace_flags: int     # 8-bit flags (sampled, etc.)
```

**HTTP Header Propagation**:
```
traceparent: 00-{trace_id}-{parent_id}-{flags}
```

**RPC Integration**:
```python
class RpcNode:
    async def rpc_method(self, params, context):
        # Extract trace context from RPC metadata
        trace_id = context.metadata.get('trace_id')
        parent_span_id = context.metadata.get('span_id')

        # Create span for RPC call
        manager = TelemetryManager.get_instance()
        span = manager.start_span(
            f"rpc:{self.method_name}",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            kind=SpanKind.SERVER
        )

        try:
            result = await self._handle_request(params)
            manager.end_span(span.span_id, status=SpanStatus.OK)
            return result
        except Exception as e:
            manager.end_span(span.span_id, status=SpanStatus.ERROR)
            raise
```

**Client Side**:
```python
class RemoteRpcProxyNode:
    async def work(self, context):
        # Propagate trace context in RPC call
        manager = TelemetryManager.get_instance()
        span = manager.start_span(
            f"rpc_call:{self.endpoint}",
            trace_id=context.trace_id,
            kind=SpanKind.CLIENT
        )

        metadata = {
            'trace_id': context.trace_id,
            'span_id': span.span_id
        }

        result = await self.rpc_client.call(
            method=self.method,
            params=params,
            metadata=metadata
        )

        manager.end_span(span.span_id)
        return result
```

## Summary

The Telemetry system provides:

1. **Structured Data Model**: Traces, spans, events, metrics with relationships
2. **Backend Abstraction**: Pluggable storage (Memory, SQLite, PostgreSQL, OTLP)
3. **Low Overhead**: Sampling, buffering, async export
4. **Automatic Instrumentation**: Transparent telemetry collection
5. **Rich Query API**: Filter, aggregate, analyze telemetry data
6. **Distributed Tracing**: Trace context propagation across RPC boundaries
7. **OpenTelemetry Compatible**: Standard data model and OTLP export

These architectural choices enable production-grade observability with minimal performance impact and maximum flexibility.
