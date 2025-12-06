# Telemetry Classes API Reference

This document provides the complete API reference for Spark's telemetry system, including the TelemetryManager, configuration, data models (Trace, Span, Event, Metric), and backend implementations.

## Table of Contents

- [TelemetryManager](#telemetrymanager)
- [TelemetryConfig](#telemetryconfig)
- [Data Models](#data-models)
  - [Trace](#trace)
  - [Span](#span)
  - [Event](#event)
  - [Metric](#metric)
  - [SpanKind](#spankind)
  - [SpanStatus](#spanstatus)
  - [EventType](#eventtype)
- [Backend Classes](#backend-classes)
  - [MemoryBackend](#memorybackend)
  - [SQLiteBackend](#sqlitebackend)
  - [PostgreSQLBackend](#postgresqlbackend)
  - [OtlpHttpBackend](#otlphttpbackend)

---

## TelemetryManager

**Module**: `spark.telemetry.manager`

Central coordinator for telemetry collection and storage. Singleton class that manages trace/span lifecycle, buffers telemetry data, and coordinates with storage backends.

### Class Methods

#### get_instance

```python
@classmethod
def get_instance(cls, config: Optional[TelemetryConfig] = None) -> TelemetryManager
```

Get singleton instance of TelemetryManager.

**Parameters:**
- `config` (TelemetryConfig, optional): Configuration to use if creating new instance

**Returns:** TelemetryManager instance.

**Example:**
```python
from spark.telemetry import TelemetryManager, TelemetryConfig

config = TelemetryConfig.create_sqlite(db_path="telemetry.db")
manager = TelemetryManager.get_instance(config)
```

#### reset_instance

```python
@classmethod
def reset_instance(cls) -> None
```

Reset singleton instance. Useful for testing.

### Constructor

```python
def __init__(self, config: Optional[TelemetryConfig] = None) -> None
```

**Parameters:**
- `config` (TelemetryConfig, optional): Telemetry configuration (default: disabled)

**Note:** Typically accessed via `get_instance()` rather than direct instantiation.

### Trace Management

#### start_trace

```python
def start_trace(
    self,
    name: str,
    trace_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> Trace
```

Start a new trace.

**Parameters:**
- `name` (str): Trace name (e.g., "graph_run", "workflow_execution")
- `trace_id` (str, optional): Optional trace ID (generated if not provided)
- `attributes` (dict, optional): Optional key-value attributes

**Returns:** New Trace object.

**Example:**
```python
trace = manager.start_trace(
    name="graph_run",
    attributes={
        "graph_id": "my_workflow",
        "version": "1.0"
    }
)
```

#### end_trace

```python
def end_trace(
    self,
    trace_id: str,
    status: SpanStatus = SpanStatus.OK
) -> Optional[Trace]
```

End a trace.

**Parameters:**
- `trace_id` (str): Trace ID to end
- `status` (SpanStatus): Final trace status (OK, ERROR, UNSET)

**Returns:** Ended Trace object, or None if not found.

**Example:**
```python
trace = manager.start_trace("graph_run")
# ... do work ...
manager.end_trace(trace.trace_id, status=SpanStatus.OK)
```

#### get_trace

```python
def get_trace(self, trace_id: str) -> Optional[Trace]
```

Get a trace by ID.

**Parameters:**
- `trace_id` (str): Trace identifier

**Returns:** Trace object or None if not found.

### Span Management

#### start_span

```python
@asynccontextmanager
async def start_span(
    self,
    name: str,
    trace_id: str,
    kind: SpanKind = SpanKind.INTERNAL,
    parent_span_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> AsyncGenerator[Span, None]
```

Start a span as an async context manager. Automatically handles span lifecycle.

**Parameters:**
- `name` (str): Span name (e.g., "node_execution", "ProcessNode.process")
- `trace_id` (str): Associated trace ID
- `kind` (SpanKind): Span kind (INTERNAL, NODE_EXECUTION, GRAPH_RUN, etc.)
- `parent_span_id` (str, optional): Parent span ID for hierarchical spans
- `attributes` (dict, optional): Optional key-value attributes

**Returns:** Async generator yielding Span object.

**Example:**
```python
trace = manager.start_trace("graph_run")

async with manager.start_span(
    name="node_execution",
    trace_id=trace.trace_id,
    kind=SpanKind.NODE_EXECUTION,
    attributes={"node_id": "process_data", "node_type": "ProcessNode"}
) as span:
    # Do work
    result = await process_data()

    # Add more attributes
    span.set_attribute("result_count", len(result))

# Span automatically ended when context exits
```

#### Hierarchical Spans

```python
trace = manager.start_trace("graph_run")

async with manager.start_span(
    name="graph_execution",
    trace_id=trace.trace_id,
    kind=SpanKind.GRAPH_RUN
) as graph_span:
    # Child span
    async with manager.start_span(
        name="node_1",
        trace_id=trace.trace_id,
        kind=SpanKind.NODE_EXECUTION,
        parent_span_id=graph_span.span_id
    ) as node_span:
        # Nested work
        pass

manager.end_trace(trace.trace_id)
```

### Event Recording

#### record_event

```python
def record_event(
    self,
    event_type: EventType | str,
    name: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
) -> Event
```

Record a discrete event.

**Parameters:**
- `event_type` (EventType | str): Type of event
- `name` (str): Event name
- `trace_id` (str, optional): Associated trace ID
- `span_id` (str, optional): Associated span ID
- `attributes` (dict, optional): Event attributes

**Returns:** Created Event object.

**Example:**
```python
manager.record_event(
    event_type=EventType.NODE_STARTED,
    name="ProcessNode started",
    trace_id=trace.trace_id,
    attributes={
        "node_id": "process_data",
        "inputs": {"count": 100}
    }
)
```

### Metric Recording

#### record_metric

```python
def record_metric(
    self,
    name: str,
    value: float,
    unit: str = "",
    attributes: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> Metric
```

Record a numerical metric.

**Parameters:**
- `name` (str): Metric name (e.g., "execution_time", "memory_usage")
- `value` (float): Metric value
- `unit` (str): Unit of measurement (e.g., "seconds", "bytes", "count")
- `attributes` (dict, optional): Metric attributes
- `trace_id` (str, optional): Associated trace ID

**Returns:** Created Metric object.

**Example:**
```python
manager.record_metric(
    name="node_execution_time",
    value=1.234,
    unit="seconds",
    attributes={
        "node_id": "process_data",
        "node_type": "ProcessNode"
    }
)

manager.record_metric(
    name="cache_hit_rate",
    value=0.85,
    unit="ratio",
    trace_id=trace.trace_id
)
```

### Data Export and Querying

#### flush

```python
async def flush(self) -> None
```

Flush buffered telemetry data to backend. Automatically called periodically if background export is enabled.

**Example:**
```python
# Manually flush buffered data
await manager.flush()
```

#### start_background_export

```python
async def start_background_export(self) -> None
```

Start background task for periodic export. Automatically flushes data at configured intervals.

**Example:**
```python
# Enable automatic periodic flushing
await manager.start_background_export()
```

#### query_traces

```python
async def query_traces(
    self,
    trace_name: Optional[str] = None,
    status: Optional[SpanStatus] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = 100,
    offset: int = 0
) -> list[Trace]
```

Query traces from backend storage.

**Parameters:**
- `trace_name` (str, optional): Filter by trace name
- `status` (SpanStatus, optional): Filter by status
- `start_time` (float, optional): Filter by start time (Unix timestamp)
- `end_time` (float, optional): Filter by end time
- `limit` (int): Maximum results (default: 100)
- `offset` (int): Results offset for pagination (default: 0)

**Returns:** List of Trace objects.

**Example:**
```python
# Get all traces
traces = await manager.query_traces(limit=100)

# Filter by name and status
traces = await manager.query_traces(
    trace_name="graph_run",
    status=SpanStatus.ERROR,
    limit=50
)

# Time-based filtering
import time
one_hour_ago = time.time() - 3600
recent_traces = await manager.query_traces(
    start_time=one_hour_ago,
    limit=100
)
```

#### query_spans

```python
async def query_spans(
    self,
    trace_id: Optional[str] = None,
    span_name: Optional[str] = None,
    kind: Optional[SpanKind] = None,
    status: Optional[SpanStatus] = None,
    limit: int = 100,
    offset: int = 0
) -> list[Span]
```

Query spans from backend storage.

**Parameters:**
- `trace_id` (str, optional): Filter by trace ID
- `span_name` (str, optional): Filter by span name
- `kind` (SpanKind, optional): Filter by span kind
- `status` (SpanStatus, optional): Filter by status
- `limit` (int): Maximum results
- `offset` (int): Results offset

**Returns:** List of Span objects.

**Example:**
```python
# Get all spans for a trace
spans = await manager.query_spans(trace_id=trace.trace_id)

# Filter by kind
node_spans = await manager.query_spans(
    kind=SpanKind.NODE_EXECUTION,
    limit=50
)

# Find failed spans
failed_spans = await manager.query_spans(
    status=SpanStatus.ERROR,
    limit=20
)
```

#### query_events

```python
async def query_events(
    self,
    trace_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    limit: int = 100,
    offset: int = 0
) -> list[Event]
```

Query events from backend storage.

**Parameters:**
- `trace_id` (str, optional): Filter by trace ID
- `event_type` (EventType, optional): Filter by event type
- `limit` (int): Maximum results
- `offset` (int): Results offset

**Returns:** List of Event objects.

**Example:**
```python
# Get all events
events = await manager.query_events(limit=100)

# Filter by type
node_failures = await manager.query_events(
    event_type=EventType.NODE_FAILED,
    limit=50
)
```

#### query_metrics

```python
async def query_metrics(
    self,
    metric_name: Optional[str] = None,
    trace_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> list[Metric]
```

Query metrics from backend storage.

**Parameters:**
- `metric_name` (str, optional): Filter by metric name
- `trace_id` (str, optional): Filter by trace ID
- `limit` (int): Maximum results
- `offset` (int): Results offset

**Returns:** List of Metric objects.

**Example:**
```python
# Get execution time metrics
exec_times = await manager.query_metrics(
    metric_name="node_execution_time",
    limit=100
)

# Calculate average
avg_time = sum(m.value for m in exec_times) / len(exec_times)
print(f"Average execution time: {avg_time:.3f}s")
```

---

## TelemetryConfig

**Module**: `spark.telemetry.config`

Configuration for telemetry collection and export.

### Constructor

```python
@dataclass
class TelemetryConfig:
    enabled: bool = False
    backend: str = 'memory'
    backend_config: Dict[str, Any] = field(default_factory=dict)
    sampling_rate: float = 1.0
    export_interval: float = 10.0
    buffer_size: int = 1000
    max_events_per_span: int = 100
    retention_days: int = 30
    resource_attributes: Dict[str, str] = field(default_factory=dict)
    enable_metrics: bool = True
    enable_events: bool = True
    enable_traces: bool = True
    propagate_context: bool = True
    auto_instrument_nodes: bool = True
    auto_instrument_graphs: bool = True
    custom_attributes: Dict[str, Any] = field(default_factory=dict)
```

**Fields:**
- **enabled** (bool): Whether telemetry is enabled (default: False)
- **backend** (str): Backend type ('sqlite', 'postgresql', 'memory', 'noop')
- **backend_config** (dict): Backend-specific configuration
- **sampling_rate** (float): Fraction of traces to sample (0.0-1.0, default: 1.0)
- **export_interval** (float): Interval in seconds for batch export (default: 10.0)
- **buffer_size** (int): Maximum spans to buffer before flushing (default: 1000)
- **max_events_per_span** (int): Maximum events per span (default: 100)
- **retention_days** (int): Days to retain telemetry data (default: 30)
- **resource_attributes** (dict): Resource-level attributes (e.g., service name, version)
- **enable_metrics** (bool): Whether to collect metrics (default: True)
- **enable_events** (bool): Whether to collect events (default: True)
- **enable_traces** (bool): Whether to collect traces (default: True)
- **propagate_context** (bool): Whether to propagate telemetry context (default: True)
- **auto_instrument_nodes** (bool): Auto-instrument all nodes (default: True)
- **auto_instrument_graphs** (bool): Auto-instrument all graphs (default: True)
- **custom_attributes** (dict): Custom attributes to add to all telemetry

### Factory Methods

#### create_sqlite

```python
@classmethod
def create_sqlite(
    cls,
    db_path: str = "spark_telemetry.db",
    **kwargs
) -> TelemetryConfig
```

Create configuration for SQLite backend.

**Parameters:**
- `db_path` (str): Path to SQLite database file
- `**kwargs`: Additional configuration options

**Returns:** TelemetryConfig configured for SQLite.

**Example:**
```python
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    export_interval=5.0
)
```

#### create_postgresql

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

Create configuration for PostgreSQL backend.

**Parameters:**
- `host` (str): PostgreSQL host
- `port` (int): PostgreSQL port
- `database` (str): Database name
- `user` (str, optional): Username
- `password` (str, optional): Password
- `**kwargs`: Additional configuration options

**Returns:** TelemetryConfig configured for PostgreSQL.

**Example:**
```python
config = TelemetryConfig.create_postgresql(
    host="localhost",
    port=5432,
    database="spark_telemetry",
    user="postgres",
    password="password"
)
```

#### create_memory

```python
@classmethod
def create_memory(cls, **kwargs) -> TelemetryConfig
```

Create configuration for in-memory backend (testing/development).

**Returns:** TelemetryConfig configured for in-memory storage.

**Example:**
```python
config = TelemetryConfig.create_memory(
    sampling_rate=1.0,
    enable_metrics=True
)
```

#### create_noop

```python
@classmethod
def create_noop(cls) -> TelemetryConfig
```

Create configuration with telemetry disabled.

**Returns:** TelemetryConfig with telemetry disabled.

### Methods

#### should_sample

```python
def should_sample(self, trace_id: str) -> bool
```

Determine if a trace should be sampled using deterministic sampling.

**Parameters:**
- `trace_id` (str): Trace identifier

**Returns:** True if trace should be sampled.

**Example:**
```python
config = TelemetryConfig(sampling_rate=0.1)  # 10% sampling
should_sample = config.should_sample(trace_id)
```

#### to_dict

```python
def to_dict(self) -> Dict[str, Any]
```

Convert configuration to dictionary for serialization.

**Returns:** Dictionary representation of configuration.

---

## Data Models

### Trace

**Module**: `spark.telemetry.types`

Represents a top-level execution context (typically a graph run). Contains multiple spans representing individual operations.

```python
@dataclass
class Trace:
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    resource: Dict[str, str] = field(default_factory=dict)
```

**Fields:**
- **trace_id** (str): Unique identifier for the trace
- **name** (str): Human-readable name (e.g., "graph_run")
- **start_time** (float): Start timestamp (seconds since epoch)
- **end_time** (float, optional): End timestamp
- **status** (SpanStatus): Overall trace status (OK, ERROR, UNSET)
- **attributes** (dict): Key-value metadata
- **resource** (dict): Resource information (e.g., host, service name)

#### Properties

##### duration

```python
@property
def duration(self) -> Optional[float]
```

Duration in seconds. Returns None if trace not ended.

##### is_active

```python
@property
def is_active(self) -> bool
```

Whether the trace is still active (not ended).

#### Methods

##### end

```python
def end(self, status: SpanStatus = SpanStatus.OK) -> None
```

Mark the trace as ended.

**Parameters:**
- `status` (SpanStatus): Final status

##### to_dict

```python
def to_dict(self) -> Dict[str, Any]
```

Convert to dictionary for serialization.

**Returns:** Dictionary representation.

### Span

**Module**: `spark.telemetry.types`

Represents an individual operation within a trace. Spans form a tree structure with parent-child relationships.

```python
@dataclass
class Span:
    span_id: str = field(default_factory=lambda: uuid4().hex)
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Event] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None
```

**Fields:**
- **span_id** (str): Unique identifier for the span
- **trace_id** (str): Associated trace ID
- **parent_span_id** (str, optional): Parent span ID (None for root spans)
- **name** (str): Operation name (e.g., "ProcessNode.process")
- **kind** (SpanKind): Type of span (NODE_EXECUTION, GRAPH_RUN, etc.)
- **start_time** (float): Start timestamp
- **end_time** (float, optional): End timestamp
- **status** (SpanStatus): Span status (OK, ERROR, UNSET)
- **attributes** (dict): Key-value metadata
- **events** (list[Event]): Events that occurred during the span
- **error** (dict, optional): Error information if span failed

#### Properties

##### duration

```python
@property
def duration(self) -> Optional[float]
```

Duration in seconds. Returns None if span not ended.

##### is_active

```python
@property
def is_active(self) -> bool
```

Whether the span is still active.

#### Methods

##### end

```python
def end(
    self,
    status: SpanStatus = SpanStatus.OK,
    error: Optional[Exception] = None
) -> None
```

Mark the span as ended.

**Parameters:**
- `status` (SpanStatus): Final status
- `error` (Exception, optional): Exception that caused failure

##### add_event

```python
def add_event(self, event: Event) -> None
```

Add an event to this span.

**Parameters:**
- `event` (Event): Event to add

##### set_attribute

```python
def set_attribute(self, key: str, value: Any) -> None
```

Set an attribute on the span.

**Parameters:**
- `key` (str): Attribute key
- `value` (Any): Attribute value

##### set_attributes

```python
def set_attributes(self, attributes: Dict[str, Any]) -> None
```

Set multiple attributes on the span.

**Parameters:**
- `attributes` (dict): Attributes to set

##### to_dict

```python
def to_dict(self) -> Dict[str, Any]
```

Convert to dictionary for serialization.

### Event

**Module**: `spark.telemetry.types`

Represents a discrete point-in-time telemetry event.

```python
@dataclass
class Event:
    event_id: str = field(default_factory=lambda: uuid4().hex)
    event_type: EventType = EventType.CUSTOM
    name: str = ""
    timestamp: float = field(default_factory=time.time)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
```

**Fields:**
- **event_id** (str): Unique identifier
- **event_type** (EventType): Type of event
- **name** (str): Event name
- **timestamp** (float): Event timestamp
- **trace_id** (str, optional): Associated trace ID
- **span_id** (str, optional): Associated span ID
- **attributes** (dict): Event attributes

### Metric

**Module**: `spark.telemetry.types`

Represents a numerical measurement.

```python
@dataclass
class Metric:
    metric_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    value: float = 0.0
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    trace_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
```

**Fields:**
- **metric_id** (str): Unique identifier
- **name** (str): Metric name
- **value** (float): Metric value
- **unit** (str): Unit of measurement
- **timestamp** (float): Measurement timestamp
- **trace_id** (str, optional): Associated trace ID
- **attributes** (dict): Metric attributes

### SpanKind

**Module**: `spark.telemetry.types`

Enumeration of span types for categorization.

```python
class SpanKind(str, Enum):
    GRAPH_RUN = "graph_run"
    NODE_EXECUTION = "node_execution"
    EDGE_TRANSITION = "edge_transition"
    STATE_CHANGE = "state_change"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    INTERNAL = "internal"
```

### SpanStatus

**Module**: `spark.telemetry.types`

Enumeration of span statuses.

```python
class SpanStatus(str, Enum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"
```

### EventType

**Module**: `spark.telemetry.types`

Enumeration of telemetry event types.

```python
class EventType(str, Enum):
    NODE_STARTED = "node.started"
    NODE_FINISHED = "node.finished"
    NODE_FAILED = "node.failed"
    GRAPH_STARTED = "graph.started"
    GRAPH_FINISHED = "graph.finished"
    GRAPH_FAILED = "graph.failed"
    EDGE_EVALUATED = "edge.evaluated"
    EDGE_TAKEN = "edge.taken"
    STATE_UPDATED = "state.updated"
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"
    TOOL_EXECUTED = "tool.executed"
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    ERROR_OCCURRED = "error.occurred"
    RETRY_ATTEMPTED = "retry.attempted"
    CUSTOM = "custom"
```

---

## Backend Classes

### MemoryBackend

**Module**: `spark.telemetry.backends.memory`

In-memory backend for testing and development. Data is lost when process ends.

**Usage:**
```python
config = TelemetryConfig.create_memory()
```

### SQLiteBackend

**Module**: `spark.telemetry.backends.sqlite`

SQLite backend for persistent local storage with async support.

**Requirements:** `aiosqlite` package

**Configuration:**
```python
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db"
)
```

**Features:**
- Persistent storage in SQLite database
- Async I/O for non-blocking operations
- Automatic schema creation
- Suitable for development and single-node deployments

### PostgreSQLBackend

**Module**: `spark.telemetry.backends.postgresql`

PostgreSQL backend for production-grade persistent storage.

**Requirements:** `asyncpg` package

**Configuration:**
```python
config = TelemetryConfig.create_postgresql(
    host="localhost",
    port=5432,
    database="spark_telemetry",
    user="postgres",
    password="password"
)
```

**Features:**
- Production-grade persistent storage
- High-performance async I/O
- Scalable for multi-node deployments
- Advanced querying capabilities

### OtlpHttpBackend

**Module**: `spark.telemetry.backends.otlp`

OpenTelemetry Protocol (OTLP) backend for exporting to observability platforms.

**Requirements:** OpenTelemetry packages

**Configuration:**
```python
config = TelemetryConfig(
    enabled=True,
    backend='otlp_http',
    backend_config={
        'endpoint': 'http://localhost:4318',
        'headers': {'Authorization': 'Bearer token'}
    }
)
```

**Features:**
- Export to Jaeger, Zipkin, Datadog, etc.
- Standard OpenTelemetry format
- HTTP/gRPC protocols supported
- Integration with existing observability stacks

---

## Complete Example

```python
from spark.telemetry import TelemetryManager, TelemetryConfig
from spark.telemetry.types import SpanKind, SpanStatus, EventType
from spark.graphs import Graph
from spark.nodes import Node

# Configure telemetry with SQLite backend
config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    export_interval=5.0,
    enable_metrics=True,
    enable_events=True,
    resource_attributes={
        "service.name": "my_workflow",
        "service.version": "1.0.0"
    }
)

# Get telemetry manager
manager = TelemetryManager.get_instance(config)

# Start background export (optional)
await manager.start_background_export()

# Manual telemetry collection
trace = manager.start_trace(
    name="workflow_execution",
    attributes={"workflow_id": "wf123"}
)

async with manager.start_span(
    name="data_processing",
    trace_id=trace.trace_id,
    kind=SpanKind.NODE_EXECUTION,
    attributes={"node_id": "process_data"}
) as span:
    # Do work
    result = await process_data()

    # Record event
    manager.record_event(
        event_type=EventType.NODE_FINISHED,
        name="Processing complete",
        trace_id=trace.trace_id,
        span_id=span.span_id,
        attributes={"result_count": len(result)}
    )

    # Record metric
    manager.record_metric(
        name="processing_time",
        value=span.duration or 0,
        unit="seconds",
        trace_id=trace.trace_id
    )

manager.end_trace(trace.trace_id, status=SpanStatus.OK)

# Flush data to backend
await manager.flush()

# Query telemetry
traces = await manager.query_traces(limit=10)
for trace in traces:
    print(f"Trace: {trace.name} - {trace.duration:.3f}s")

    spans = await manager.query_spans(trace_id=trace.trace_id)
    for span in spans:
        print(f"  Span: {span.name} - {span.duration:.3f}s")

# Analyze performance
exec_times = await manager.query_metrics(
    metric_name="processing_time"
)
avg_time = sum(m.value for m in exec_times) / len(exec_times)
print(f"Average processing time: {avg_time:.3f}s")

# Find errors
errors = await manager.query_spans(status=SpanStatus.ERROR)
print(f"Found {len(errors)} failed spans")
```

### Automatic Instrumentation with Graphs

```python
from spark.graphs import Graph
from spark.telemetry import TelemetryConfig

# Enable telemetry for graph
config = TelemetryConfig.create_sqlite("telemetry.db")

# Graph automatically instruments all nodes
graph = Graph(start=my_node, telemetry_config=config)

# Run graph - telemetry collected automatically
result = await graph.run()

# Query results
manager = TelemetryManager.get_instance()
traces = await manager.query_traces(limit=10)
```

---

## See Also

- [Graph Classes](graphs.md) - Automatic graph instrumentation
- [Node Classes](nodes.md) - Node-level telemetry
- [RSI Classes](rsi.md) - Using telemetry for self-improvement
- [Examples](/examples/) - Complete telemetry examples
