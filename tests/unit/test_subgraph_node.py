import asyncio

import pytest

from spark.nodes import Node
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.graphs import Graph
from spark.graphs.graph import SubgraphNode
from spark.nodes.spec import GraphSpec, NodeSpec, GraphStateSpec
from spark.nodes.serde import graph_to_spec
from spark.kit.loader import SpecLoader


class SeedCounterNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        await context.graph_state.set('counter', 1)
        return NodeMessage(content={'seeded': True}, metadata={})


class IncrementCounterNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        counter = await context.graph_state.get('counter', 0)
        counter += 1
        await context.graph_state.set('counter', counter)
        return NodeMessage(content={'counter': counter}, metadata={})


class ResultNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        counter = await context.graph_state.get('counter', 0)
        return NodeMessage(content={'counter': counter}, metadata={})


class EchoQueryNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        query = context.inputs.content.get('query_text')
        return NodeMessage(content={'response': f"processed:{query}"}, metadata={})


def build_increment_graph() -> Graph:
    return Graph(start=IncrementCounterNode())


@pytest.mark.asyncio
async def test_subgraph_shared_state_updates_parent():
    seed = SeedCounterNode()
    subgraph = Graph(start=IncrementCounterNode())
    capture = ResultNode()

    sub_node = SubgraphNode(graph=subgraph)
    seed.goto(sub_node)
    sub_node.goto(capture)

    graph = Graph(start=seed, initial_state={'counter': 0})
    result = await graph.run()
    assert isinstance(result.content, dict)
    assert result.content['counter'] == 2
    assert await graph.get_state('counter') == 2


@pytest.mark.asyncio
async def test_subgraph_input_output_mapping():
    subgraph = Graph(start=EchoQueryNode())
    sub_node = SubgraphNode(
        graph=subgraph,
        input_mapping={'query': 'query_text'},
        output_mapping={'response': 'answer'},
    )
    graph = Graph(start=sub_node)
    result = await graph.run({'query': 'pizza'})
    assert isinstance(result.content, dict)
    assert result.content['answer'] == 'processed:pizza'


@pytest.mark.asyncio
async def test_subgraph_round_trip_through_spec_loader():
    seed = SeedCounterNode()
    subgraph = Graph(start=IncrementCounterNode())
    capture = ResultNode()
    sub_node = SubgraphNode(graph=subgraph)
    seed.goto(sub_node)
    sub_node.goto(capture)
    parent_graph = Graph(start=seed, initial_state={'counter': 0})

    spec = graph_to_spec(parent_graph)
    node_spec = next(node for node in spec.nodes if node.type == 'SubgraphNode')
    assert 'graph_spec' in (node_spec.config or {})

    loader = SpecLoader(import_policy='allow_all')
    loaded = loader.load_graph(spec)
    assert any(isinstance(node, SubgraphNode) for node in loaded.nodes)


@pytest.mark.asyncio
async def test_subgraph_from_graph_source_reference():
    sub_node_spec = NodeSpec(
        id='nested',
        type='SubgraphNode',
        config={
            'graph_source': 'tests.unit.test_subgraph_node:build_increment_graph',
            'share_state': True,
        },
    )
    spec = GraphSpec(
        spark_version='2.0',
        id='subgraph-source',
        start='nested',
        nodes=[sub_node_spec],
        edges=[],
        graph_state=GraphStateSpec(initial_state={'counter': 0}),
    )
    loader = SpecLoader(import_policy='allow_all')
    graph = loader.load_graph(spec)
    result = await graph.run()
    assert result.content['counter'] == 1
