"""Tests for telemetry instrumentation hooks."""

import pytest

from spark.graphs import Graph
from spark.nodes import Node
from spark.nodes.types import ExecutionContext
from spark.telemetry import TelemetryManager, TelemetryConfig, EventType, SpanKind


class SourceNode(Node):
    async def process(self, context: ExecutionContext):
        return {'value': 'ok'}


class TargetNode(Node):
    async def process(self, context: ExecutionContext):
        return context.inputs.content


@pytest.mark.asyncio
async def test_telemetry_records_spans_and_edge_events():
    TelemetryManager.reset_instance()
    config = TelemetryConfig(enabled=True, backend='memory')
    manager = TelemetryManager.get_instance(config)

    source = SourceNode()
    target = TargetNode()
    source.goto(target)
    graph = Graph(start=source, telemetry_config=config)

    await graph.run()
    await manager.flush()

    backend = manager._backend
    spans = await backend.query_spans(kind=SpanKind.NODE_EXECUTION)
    assert spans, "Expected node execution spans"

    edge_events = await backend.query_events(type=EventType.EDGE_TAKEN)
    assert edge_events, "Expected edge telemetry events"

    await manager.shutdown()
    TelemetryManager.reset_instance()
