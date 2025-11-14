"""
Telemetry data models for comprehensive observability in Spark.

This module defines the core telemetry abstractions:
- Trace: Top-level execution context (graph run)
- Span: Individual operation (node execution, edge transition, etc.)
- Event: Point-in-time telemetry data
- Metrics: Aggregated statistics

These models follow OpenTelemetry conventions for compatibility with
observability tools like Jaeger, Zipkin, and Datadog.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class SpanKind(str, Enum):
    """Type of span for categorization."""
    GRAPH_RUN = "graph_run"
    NODE_EXECUTION = "node_execution"
    EDGE_TRANSITION = "edge_transition"
    STATE_CHANGE = "state_change"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    INTERNAL = "internal"


class SpanStatus(str, Enum):
    """Status of a span."""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class EventType(str, Enum):
    """Type of telemetry event."""
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


@dataclass
class Trace:
    """Represents a top-level execution context (typically a graph run).

    A trace captures the complete execution of a workflow, containing
    multiple spans representing individual operations.

    Attributes:
        trace_id: Unique identifier for the trace
        name: Human-readable name (e.g., "graph_run")
        start_time: Start timestamp (seconds since epoch)
        end_time: End timestamp (seconds since epoch)
        status: Overall trace status
        attributes: Key-value metadata
        resource: Resource information (e.g., host, service name)
    """
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    resource: Dict[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> Optional[float]:
        """Duration in seconds."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    @property
    def is_active(self) -> bool:
        """Whether the trace is still active."""
        return self.end_time is None

    def end(self, status: SpanStatus = SpanStatus.OK) -> None:
        """Mark the trace as ended."""
        self.end_time = time.time()
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'trace_id': self.trace_id,
            'name': self.name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'status': self.status.value,
            'attributes': self.attributes,
            'resource': self.resource,
        }


@dataclass
class Span:
    """Represents an individual operation within a trace.

    Spans form a tree structure with parent-child relationships,
    allowing detailed tracing of execution flow.

    Attributes:
        span_id: Unique identifier for the span
        trace_id: Associated trace ID
        parent_span_id: Parent span ID (None for root spans)
        name: Operation name (e.g., "ProcessNode.process")
        kind: Type of span (node, edge, etc.)
        start_time: Start timestamp
        end_time: End timestamp
        status: Span status
        attributes: Key-value metadata
        events: List of events that occurred during the span
        error: Error information if span failed
    """
    span_id: str = field(default_factory=lambda: uuid4().hex)
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List['Event'] = field(default_factory=list)
    error: Optional[Dict[str, Any]] = None

    @property
    def duration(self) -> Optional[float]:
        """Duration in seconds."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    @property
    def is_active(self) -> bool:
        """Whether the span is still active."""
        return self.end_time is None

    def end(self, status: SpanStatus = SpanStatus.OK, error: Optional[Exception] = None) -> None:
        """Mark the span as ended.

        Args:
            status: Final status of the span
            error: Optional exception that caused failure
        """
        self.end_time = time.time()
        self.status = status
        if error:
            self.error = {
                'type': type(error).__name__,
                'message': str(error),
                'traceback': getattr(error, '__traceback__', None),
            }

    def add_event(self, event: 'Event') -> None:
        """Add an event to this span."""
        self.events.append(event)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        """Set multiple attributes on the span."""
        self.attributes.update(attributes)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'span_id': self.span_id,
            'trace_id': self.trace_id,
            'parent_span_id': self.parent_span_id,
            'name': self.name,
            'kind': self.kind.value,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'status': self.status.value,
            'attributes': self.attributes,
            'events': [e.to_dict() for e in self.events],
            'error': self.error,
        }


@dataclass
class Event:
    """Represents a point-in-time occurrence within a span.

    Events capture specific moments during execution, such as
    state changes, message passing, or errors.

    Attributes:
        event_id: Unique identifier for the event
        timestamp: When the event occurred
        type: Type of event
        name: Event name
        attributes: Key-value metadata
        span_id: Associated span ID (if part of a span)
        trace_id: Associated trace ID
    """
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time.time)
    type: EventType = EventType.CUSTOM
    name: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    span_id: Optional[str] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp,
            'type': self.type.value,
            'name': self.name,
            'attributes': self.attributes,
            'span_id': self.span_id,
            'trace_id': self.trace_id,
        }


@dataclass
class Metric:
    """Represents aggregated statistics.

    Metrics provide numerical measurements over time, such as
    execution counts, durations, and success rates.

    Attributes:
        name: Metric name (e.g., "node.execution.duration")
        value: Metric value
        unit: Unit of measurement (e.g., "seconds", "count")
        timestamp: When the metric was recorded
        attributes: Key-value metadata (dimensions)
        aggregation: Type of aggregation (sum, avg, min, max, count)
    """
    name: str
    value: float
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    attributes: Dict[str, Any] = field(default_factory=dict)
    aggregation: str = "gauge"  # gauge, counter, histogram

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'value': self.value,
            'unit': self.unit,
            'timestamp': self.timestamp,
            'attributes': self.attributes,
            'aggregation': self.aggregation,
        }


@dataclass
class TelemetryContext:
    """Context information propagated through execution.

    TelemetryContext is passed through the execution stack to maintain
    trace and span relationships.

    Attributes:
        trace_id: Current trace ID
        span_id: Current span ID
        parent_span_id: Parent span ID (for creating child spans)
        baggage: Additional context data to propagate
    """
    trace_id: str
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    baggage: Dict[str, Any] = field(default_factory=dict)

    def create_child_context(self, new_span_id: str) -> 'TelemetryContext':
        """Create a child context for a new span.

        Args:
            new_span_id: ID for the new child span

        Returns:
            New TelemetryContext with updated span hierarchy
        """
        return TelemetryContext(
            trace_id=self.trace_id,
            span_id=new_span_id,
            parent_span_id=self.span_id,
            baggage=dict(self.baggage),  # Copy baggage
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'baggage': self.baggage,
        }
