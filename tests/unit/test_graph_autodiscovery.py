"""
Tests for BaseGraph auto-discovery feature.
"""

import pytest
from spark.nodes import Node
from spark.graphs.graph import Graph
from spark.nodes.base import ExecutionContext, EdgeCondition


class SimpleNode(Node):
    async def process(self, context: ExecutionContext):
        return context.inputs or {}


def test_graph_autodiscovery_with_start_node_only():
    """Test that Graph auto-discovers nodes and edges when only start_node is provided."""
    # Create a simple linear graph: a -> b -> c
    a = SimpleNode()
    b = SimpleNode()
    c = SimpleNode()

    a >> b >> c

    # Create graph with only start_node (no explicit edges)
    graph = Graph(start=a)

    # Verify all nodes were discovered
    assert len(graph.nodes) == 3
    assert a in graph.nodes
    assert b in graph.nodes
    assert c in graph.nodes

    # Verify all edges were discovered
    assert len(graph.edges) == 2
    edge_pairs = {(e.from_node, e.to_node) for e in graph.edges}
    assert (a, b) in edge_pairs
    assert (b, c) in edge_pairs

    # Verify start node is set correctly
    assert graph.start == a


def test_graph_autodiscovery_with_branching():
    """Test auto-discovery with a branching graph structure."""
    # Create a branching graph: start -> [a, b]
    start = SimpleNode()
    a = SimpleNode()
    b = SimpleNode()

    start.on(action='left') >> a
    start.on(action='right') >> b

    # Create graph with only start_node
    graph = Graph(start=start)

    # Verify all nodes were discovered
    assert len(graph.nodes) == 3
    assert start in graph.nodes
    assert a in graph.nodes
    assert b in graph.nodes

    # Verify all edges were discovered
    assert len(graph.edges) == 2


def test_graph_autodiscovery_with_complex_structure():
    """Test auto-discovery with a more complex graph structure."""
    # Create: start -> router -> [search, answer] -> end
    start = SimpleNode()
    router = SimpleNode()
    search = SimpleNode()
    answer = SimpleNode()
    end = SimpleNode()

    start >> router
    router.on(action='search') >> search
    router.on(action='answer') >> answer
    search >> end
    answer >> end

    # Create graph with only start_node
    graph = Graph(start=start)

    # Verify all nodes were discovered
    assert len(graph.nodes) == 5
    assert all(node in graph.nodes for node in [start, router, search, answer, end])

    # Verify all edges were discovered
    assert len(graph.edges) == 5


def test_graph_autodiscovery_with_cycles():
    """Test auto-discovery handles graphs with cycles correctly."""
    # Create a graph with a cycle: a -> b -> c -> a
    a = SimpleNode()
    b = SimpleNode()
    c = SimpleNode()

    a >> b >> c
    c.goto(a)  # Create cycle back to a

    # Create graph with only start_node
    graph = Graph(start=a)

    # Verify all nodes were discovered (no infinite loop)
    assert len(graph.nodes) == 3
    assert all(node in graph.nodes for node in [a, b, c])

    # Verify all edges were discovered including the cycle edge
    assert len(graph.edges) == 3


def test_graph_autodiscovery_single_node():
    """Test auto-discovery with a single node (no edges)."""
    node = SimpleNode()

    # Create graph with only start_node
    graph = Graph(start=node)

    # Verify the single node was discovered
    assert len(graph.nodes) == 1
    assert node in graph.nodes

    # Verify no edges
    assert len(graph.edges) == 0

    # Verify start_node is set
    assert graph.start == node


def test_graph_with_explicit_edges_no_autodiscovery():
    """Test that auto-discovery doesn't run when edges are explicitly provided."""
    # Create nodes with edges
    a = SimpleNode()
    b = SimpleNode()
    c = SimpleNode()

    edge1 = a.goto(b)
    a.goto(c)  # This edge won't be in the graph

    # Create graph with explicit edges (should not auto-discover)
    graph = Graph(edge1, start=a)

    # Verify only explicitly provided edges are present
    assert len(graph.edges) == 1
    assert graph.edges[0] == edge1

    # Verify only nodes from explicit edges are present
    assert len(graph.nodes) == 2
    assert a in graph.nodes
    assert b in graph.nodes
    assert c not in graph.nodes  # Not discovered because edge not provided


def test_graph_autodiscovery_with_dangling_edges():
    """Test auto-discovery with edges that have no to_node."""
    a = SimpleNode()
    b = SimpleNode()

    # Create edge with to_node
    a >> b

    # Create dangling edge (no to_node)
    a.on(action='dangling')

    # Create graph with only start_node
    graph = Graph(start=a)

    # Verify nodes were discovered
    assert len(graph.nodes) == 2
    assert a in graph.nodes
    assert b in graph.nodes

    # Verify edges include both complete and dangling edges
    assert len(graph.edges) == 2

    # Verify dangling edge is present but doesn't cause issues
    dangling_edges = [e for e in graph.edges if e.to_node is None]
    assert len(dangling_edges) == 1


def test_graph_autodiscovery_with_goto_and_on():
    """Test that both goto() and on() edges are discovered."""
    start = SimpleNode()
    a = SimpleNode()
    b = SimpleNode()

    # Mix of goto and on
    start.on(action='a') >> a
    cond = EdgeCondition(expr="$.outputs.action == 'b'")
    start.goto(b, condition=cond)

    # Create graph with only start_node
    graph = Graph(start=start)

    # Verify all nodes discovered
    assert len(graph.nodes) == 3

    # Verify both edges discovered
    assert len(graph.edges) == 2


@pytest.mark.asyncio
async def test_graph_autodiscovery_runtime_execution():
    """Test that auto-discovered graph can execute correctly."""
    # Create a simple flow
    class CounterNode(Node):
        async def process(self, context: ExecutionContext):
            count = context.inputs.content.get('count', 0)
            return {'count': count + 1}

    a = CounterNode()
    b = CounterNode()
    c = CounterNode()

    a >> b >> c

    # Create graph with auto-discovery
    graph = Graph(start=a)

    # Run the graph
    await graph.run({'count': 0})

    # Verify the flow executed correctly
    assert c.outputs.content == {'count': 3}


@pytest.mark.asyncio
async def test_graph_run_returns_last_node_output():
    """Graph.run should return the outputs of the final node when determinable."""
    class CounterNode(Node):
        async def process(self, context: ExecutionContext):
            count = context.inputs.content.get('count', 0)
            return {'count': count + 1}

    a = CounterNode()
    b = CounterNode()

    a >> b

    graph = Graph(start=a)

    result = await graph.run({'count': 0})

    assert result is not None
    assert result.content == {'count': 2}


@pytest.mark.asyncio
async def test_graph_run_cycle_returns_last_output():
    """Graphs with cycles should still produce the last node output."""

    class LoopNode(Node):
        async def process(self, context: ExecutionContext):
            count = context.inputs.content.get('count', 0) + 1
            continue_flag = count < 2
            return {'count': count, 'continue': continue_flag}

    a = LoopNode()
    b = LoopNode()

    a.goto(b)
    b.goto(a, condition=EdgeCondition(lambda n: n.outputs.content.get('continue', False)))

    graph = Graph(start=a)

    result = await graph.run({'count': 0})

    assert result is not None
    assert result.content == {'count': 2, 'continue': False}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
