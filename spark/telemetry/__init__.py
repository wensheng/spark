"""
Comprehensive telemetry system for Spark.

This package provides observability for Spark graphs and nodes through:
- Distributed tracing (traces and spans)
- Event collection
- Metrics aggregation
- Multiple storage backends (SQLite, PostgreSQL, in-memory)

Usage:
    from spark.telemetry import TelemetryManager, TelemetryConfig

    # Configure telemetry
    config = TelemetryConfig.create_sqlite("telemetry.db")

    # Create manager
    manager = TelemetryManager.get_instance(config)

    # Use with graphs
    graph = Graph(start=my_node, telemetry_config=config)
    result = await graph.run()

    # Query telemetry
    traces = await manager.query_traces(start_time=...)
"""

from spark.telemetry.types import (
    Trace,
    Span,
    Event,
    Metric,
    TelemetryContext,
    SpanKind,
    SpanStatus,
    EventType,
)
from spark.telemetry.config import TelemetryConfig
from spark.telemetry.manager import TelemetryManager

__all__ = [
    'Trace',
    'Span',
    'Event',
    'Metric',
    'TelemetryContext',
    'SpanKind',
    'SpanStatus',
    'EventType',
    'TelemetryConfig',
    'TelemetryManager',
]
