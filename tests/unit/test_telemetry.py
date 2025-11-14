"""
Tests for Spark telemetry system.

This module tests the comprehensive telemetry implementation including:
- Telemetry data models (Trace, Span, Event, Metric)
- TelemetryManager
- Storage backends (Memory, SQLite)
- Graph and node instrumentation
- Query API
"""

import asyncio
import os
import tempfile
import pytest

from spark.telemetry import (
    TelemetryConfig,
    TelemetryManager,
    Trace,
    Span,
    Event,
    Metric,
    SpanKind,
    SpanStatus,
    EventType,
)
from spark.telemetry.backends.memory import MemoryBackend
from spark.nodes import Node
from spark.graphs import Graph


class SimpleNode(Node):
    """Simple test node."""

    async def process(self, context):
        return {'result': 'done'}


class ErrorNode(Node):
    """Node that raises an error."""

    async def process(self, context):
        raise ValueError("Test error")


# Telemetry Types Tests

def test_trace_creation():
    """Test creating a trace."""
    trace = Trace(name="test_trace")
    assert trace.name == "test_trace"
    assert trace.trace_id is not None
    assert trace.is_active
    assert trace.duration is None
    assert trace.status == SpanStatus.UNSET


def test_trace_lifecycle():
    """Test trace lifecycle."""
    trace = Trace(name="test_trace")
    assert trace.is_active

    trace.end(status=SpanStatus.OK)
    assert not trace.is_active
    assert trace.duration is not None
    assert trace.status == SpanStatus.OK


def test_span_creation():
    """Test creating a span."""
    span = Span(
        trace_id="trace123",
        name="test_span",
        kind=SpanKind.NODE_EXECUTION
    )
    assert span.name == "test_span"
    assert span.trace_id == "trace123"
    assert span.kind == SpanKind.NODE_EXECUTION
    assert span.is_active


def test_span_lifecycle():
    """Test span lifecycle."""
    span = Span(trace_id="trace123", name="test_span")
    assert span.is_active

    span.end(status=SpanStatus.OK)
    assert not span.is_active
    assert span.duration is not None
    assert span.status == SpanStatus.OK


def test_span_attributes():
    """Test span attributes."""
    span = Span(trace_id="trace123", name="test_span")
    span.set_attribute("key1", "value1")
    span.set_attributes({"key2": "value2", "key3": "value3"})

    assert span.attributes["key1"] == "value1"
    assert span.attributes["key2"] == "value2"
    assert span.attributes["key3"] == "value3"


def test_event_creation():
    """Test creating an event."""
    event = Event(
        type=EventType.NODE_STARTED,
        name="test_event",
        trace_id="trace123",
        span_id="span456"
    )
    assert event.name == "test_event"
    assert event.type == EventType.NODE_STARTED
    assert event.trace_id == "trace123"
    assert event.span_id == "span456"


def test_metric_creation():
    """Test creating a metric."""
    metric = Metric(
        name="node.execution.duration",
        value=1.234,
        unit="seconds",
        aggregation="gauge"
    )
    assert metric.name == "node.execution.duration"
    assert metric.value == 1.234
    assert metric.unit == "seconds"
    assert metric.aggregation == "gauge"


# TelemetryConfig Tests

def test_telemetry_config_defaults():
    """Test default telemetry configuration."""
    config = TelemetryConfig()
    assert not config.enabled
    assert config.backend == "memory"
    assert config.sampling_rate == 1.0


def test_telemetry_config_create_memory():
    """Test creating memory config."""
    config = TelemetryConfig.create_memory()
    assert config.enabled
    assert config.backend == "memory"


def test_telemetry_config_create_sqlite():
    """Test creating SQLite config."""
    config = TelemetryConfig.create_sqlite("/tmp/test.db")
    assert config.enabled
    assert config.backend == "sqlite"
    assert config.backend_config["db_path"] == "/tmp/test.db"


def test_telemetry_config_create_noop():
    """Test creating noop config."""
    config = TelemetryConfig.create_noop()
    assert not config.enabled
    assert config.backend == "noop"


def test_telemetry_config_validation():
    """Test config validation."""
    # Invalid sampling rate
    with pytest.raises(ValueError, match="sampling_rate"):
        TelemetryConfig(sampling_rate=1.5)

    # Invalid buffer size
    with pytest.raises(ValueError, match="buffer_size"):
        TelemetryConfig(buffer_size=0)

    # Invalid backend
    with pytest.raises(ValueError, match="backend"):
        TelemetryConfig(backend="invalid")


def test_telemetry_config_sampling():
    """Test sampling decision."""
    config = TelemetryConfig(sampling_rate=0.5)

    # Test deterministic sampling
    trace_id = "test_trace_123"
    result1 = config.should_sample(trace_id)
    result2 = config.should_sample(trace_id)
    assert result1 == result2  # Deterministic


# TelemetryManager Tests

@pytest.mark.asyncio
async def test_telemetry_manager_singleton():
    """Test TelemetryManager singleton."""
    TelemetryManager.reset_instance()

    config = TelemetryConfig.create_memory()
    manager1 = TelemetryManager.get_instance(config)
    manager2 = TelemetryManager.get_instance()

    assert manager1 is manager2

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_telemetry_manager_trace_lifecycle():
    """Test trace lifecycle management."""
    TelemetryManager.reset_instance()
    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)

    # Start trace
    trace = manager.start_trace("test_trace")
    assert trace.name == "test_trace"
    assert trace.is_active

    # Get trace
    retrieved = manager.get_trace(trace.trace_id)
    assert retrieved is trace

    # End trace
    ended = manager.end_trace(trace.trace_id, status=SpanStatus.OK)
    assert ended is trace
    assert not ended.is_active

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_telemetry_manager_span_context_manager():
    """Test span creation with context manager."""
    TelemetryManager.reset_instance()
    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)

    trace = manager.start_trace("test_trace")

    async with manager.start_span("test_span", trace.trace_id) as span:
        assert span.name == "test_span"
        assert span.is_active
        span.set_attribute("key", "value")

    assert not span.is_active
    assert span.status == SpanStatus.OK
    assert span.attributes["key"] == "value"

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_telemetry_manager_event_recording():
    """Test event recording."""
    TelemetryManager.reset_instance()
    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)

    trace = manager.start_trace("test_trace")

    event = manager.record_event(
        type=EventType.NODE_STARTED,
        name="test_event",
        trace_id=trace.trace_id,
        attributes={"node_id": "abc123"}
    )

    assert event.type == EventType.NODE_STARTED
    assert event.name == "test_event"
    assert event.trace_id == trace.trace_id
    assert event.attributes["node_id"] == "abc123"

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_telemetry_manager_metric_recording():
    """Test metric recording."""
    TelemetryManager.reset_instance()
    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)

    metric = manager.record_metric(
        name="test.metric",
        value=42.0,
        unit="count",
        attributes={"service": "test"}
    )

    assert metric.name == "test.metric"
    assert metric.value == 42.0
    assert metric.unit == "count"
    assert metric.attributes["service"] == "test"

    TelemetryManager.reset_instance()


# Backend Tests

@pytest.mark.asyncio
async def test_memory_backend():
    """Test memory backend."""
    backend = MemoryBackend()

    # Write traces
    traces = [Trace(name=f"trace{i}") for i in range(3)]
    await backend.write_traces(traces)

    # Query traces
    results = await backend.query_traces(limit=10)
    assert len(results) == 3

    # Write spans
    spans = [Span(trace_id=traces[0].trace_id, name=f"span{i}") for i in range(5)]
    await backend.write_spans(spans)

    # Query spans
    results = await backend.query_spans(trace_id=traces[0].trace_id)
    assert len(results) == 5

    # Get stats
    stats = backend.get_stats()
    assert stats["traces"] == 3
    assert stats["spans"] == 5


@pytest.mark.asyncio
async def test_memory_backend_filtering():
    """Test memory backend filtering."""
    backend = MemoryBackend()

    # Create traces with different statuses
    trace1 = Trace(name="trace1")
    trace1.end(status=SpanStatus.OK)

    trace2 = Trace(name="trace2")
    trace2.end(status=SpanStatus.ERROR)

    await backend.write_traces([trace1, trace2])

    # Filter by status
    ok_traces = await backend.query_traces(status=SpanStatus.OK)
    assert len(ok_traces) == 1
    assert ok_traces[0].name == "trace1"

    error_traces = await backend.query_traces(status=SpanStatus.ERROR)
    assert len(error_traces) == 1
    assert error_traces[0].name == "trace2"


# Graph Integration Tests

@pytest.mark.asyncio
async def test_graph_with_telemetry():
    """Test graph execution with telemetry enabled."""
    TelemetryManager.reset_instance()

    config = TelemetryConfig.create_memory()
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2

    graph = Graph(start=node1, telemetry_config=config)

    result = await graph.run()
    assert result.content == {'result': 'done'}

    # Query telemetry
    manager = TelemetryManager.get_instance()

    # Flush to ensure data is written to backend
    await manager.flush()

    # Longer delay to ensure all async writes complete
    await asyncio.sleep(0.5)

    traces = await manager.query_traces()

    assert len(traces) > 0
    trace = traces[0]
    assert trace.name == "graph_run"
    assert not trace.is_active

    # Query spans
    spans = await manager.query_spans(trace_id=trace.trace_id)
    assert len(spans) > 0

    # Query events
    events = await manager.query_events(trace_id=trace.trace_id)
    assert len(events) > 0

    # Check for graph started and finished events
    event_types = {e.type for e in events}
    assert EventType.GRAPH_STARTED in event_types
    assert EventType.GRAPH_FINISHED in event_types

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_graph_without_telemetry():
    """Test graph execution without telemetry."""
    TelemetryManager.reset_instance()

    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2

    graph = Graph(start=node1)  # No telemetry config

    result = await graph.run()
    assert result.content == {'result': 'done'}

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_graph_telemetry_with_error():
    """Test telemetry captures errors."""
    TelemetryManager.reset_instance()

    config = TelemetryConfig.create_memory()
    node1 = SimpleNode()
    node2 = ErrorNode()
    node1 >> node2

    graph = Graph(start=node1, telemetry_config=config)

    with pytest.raises(ValueError, match="Test error"):
        await graph.run()

    # Query telemetry
    manager = TelemetryManager.get_instance()

    # Flush to ensure data is written to backend
    await manager.flush()

    # Longer delay to ensure all async writes complete
    await asyncio.sleep(0.5)

    traces = await manager.query_traces()

    assert len(traces) > 0
    trace = traces[0]

    # Query events
    events = await manager.query_events(trace_id=trace.trace_id)

    # Check for graph failed event
    event_types = {e.type for e in events}
    assert EventType.GRAPH_FAILED in event_types

    TelemetryManager.reset_instance()


@pytest.mark.asyncio
async def test_telemetry_flush():
    """Test telemetry buffer flushing."""
    TelemetryManager.reset_instance()

    config = TelemetryConfig.create_memory(buffer_size=5)
    manager = TelemetryManager.get_instance(config)

    # Create events that will be buffered
    trace = manager.start_trace("test_trace")
    for i in range(10):
        manager.record_event(
            type=EventType.CUSTOM,
            name=f"event{i}",
            trace_id=trace.trace_id
        )

    # Flush
    await manager.flush()

    # Query backend directly
    backend = manager._backend
    events = await backend.query_events(trace_id=trace.trace_id)
    assert len(events) == 10

    TelemetryManager.reset_instance()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
