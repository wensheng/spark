"""Tests for advanced edge semantics: event routing and temporal delays."""

import asyncio

import pytest

from spark.graphs import Graph
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext


class PassThroughNode(Node):
    async def process(self, context: ExecutionContext):
        value = context.inputs.content.get('value', 0)
        return {'value': value + 1}


class CollectorNode(Node):
    def __init__(self):
        super().__init__()
        self.collected = []

    async def process(self, context: ExecutionContext):
        self.collected.append(context.inputs.content)
        return {'collected': len(self.collected)}


class PublisherNode(Node):
    async def process(self, context: ExecutionContext):
        await self.publish_event('metrics', {'value': context.inputs.content.get('value', 0)})
        return {'published': True}


@pytest.mark.asyncio
async def test_delayed_edge_execution():
    start = PassThroughNode()
    sink = CollectorNode()

    # Wire edge with delay
    start >> sink
    start.edges[0].delay_seconds = 0.05

    graph = Graph(start=start)
    await graph.run({'value': 1})

    # Collector should run exactly once and process delayed payload
    assert sink.collected
    assert sink.collected[0]['value'] == 2


@pytest.mark.asyncio
async def test_event_edge_routing():
    publisher = PublisherNode()
    collector = CollectorNode()

    publisher >> collector
    publisher.edges[0].event_topic = 'metrics'

    graph = Graph(start=publisher)
    result = await graph.run({'value': 5})

    assert collector.collected
    assert collector.collected[0]['value'] == 5
    assert result.content['collected'] == 1
