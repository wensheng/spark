"""Tests for advanced edge semantics: event routing and temporal delays."""

import asyncio

import pytest

from spark.graphs import Graph
from spark.nodes.conditions import ConditionLibrary
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

    # Wire edge with declarative timer
    start.on_timer(0.05) >> sink

    graph = Graph(start=start)
    await graph.run({'value': 1})

    # Collector should run exactly once and process delayed payload
    assert sink.collected
    assert sink.collected[0]['value'] == 2


@pytest.mark.asyncio
async def test_event_edge_routing():
    publisher = PublisherNode()
    collector = CollectorNode()

    publisher.on_event('metrics') >> collector

    graph = Graph(start=publisher)
    result = await graph.run({'value': 5})

    assert collector.collected
    assert collector.collected[0]['value'] == 5
    assert result.content['collected'] == 1


@pytest.mark.asyncio
async def test_event_edge_filtering_with_condition_library():
    class MultiPublisher(Node):
        async def process(self, context):  # type: ignore[override]
            for value in context.inputs.content.get('values', []):
                await self.publish_event('metrics', {'value': value})
            return {'published': len(context.inputs.content.get('values', []))}

    class MetadataCollector(Node):
        def __init__(self):
            super().__init__()
            self.events = []

        async def process(self, context):  # type: ignore[override]
            self.events.append((context.inputs.content['value'], context.inputs.metadata.get('event', {})))
            return {'count': len(self.events)}

    publisher = MultiPublisher()
    collector = MetadataCollector()

    publisher.on_event('metrics', event_filter=ConditionLibrary.threshold('value', value=2)) >> collector

    graph = Graph(start=publisher)
    await graph.run({'values': [1, 2, 3]})

    assert [value for value, _ in collector.events] == [2, 3]
    assert collector.events[0][1]['topic'] == 'metrics'
