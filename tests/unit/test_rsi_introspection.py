"""Unit tests for RSI GraphIntrospector."""

import pytest
from spark.rsi.introspection import GraphIntrospector
from spark.graphs import Graph
from spark.nodes import Node


# Test nodes
class TestNodeA(Node):

    __test__ = False

    async def process(self, context):
        return {'next': 'b'}


class TestNodeB(Node):

    __test__ = False

    async def process(self, context):
        return {'next': 'c'}


class TestNodeC(Node):

    __test__ = False

    async def process(self, context):
        return {'done': True}


class TestNodeD(Node):

    __test__ = False

    async def process(self, context):
        return {'done': True}


@pytest.fixture
def simple_graph():
    """Create a simple test graph: A -> B -> C"""
    node_a = TestNodeA(name="NodeA")
    node_b = TestNodeB(name="NodeB")
    node_c = TestNodeC(name="NodeC")

    node_a >> node_b >> node_c

    graph = Graph(start=node_a)
    return graph


@pytest.fixture
def branching_graph():
    """Create a branching test graph:
         A -> B
         A -> C
         B -> D
         C -> D
    """
    node_a = TestNodeA(name="NodeA")
    node_b = TestNodeB(name="NodeB")
    node_c = TestNodeC(name="NodeC")
    node_d = TestNodeD(name="NodeD")

    node_a >> node_b >> node_d
    node_a >> node_c >> node_d

    graph = Graph(start=node_a)
    return graph


@pytest.fixture
def cyclic_graph():
    """Create a graph with a cycle: A -> B -> C -> A"""
    node_a = TestNodeA(name="NodeA")
    node_b = TestNodeB(name="NodeB")
    node_c = TestNodeC(name="NodeC")

    node_a >> node_b >> node_c >> node_a

    graph = Graph(start=node_a)
    return graph


def test_introspector_initialization(simple_graph):
    """Test GraphIntrospector initialization."""
    introspector = GraphIntrospector(simple_graph)
    assert introspector.graph == simple_graph
    assert introspector.spec is None  # Not loaded yet


def test_load_spec(simple_graph):
    """Test loading graph spec."""
    introspector = GraphIntrospector(simple_graph)
    spec = introspector.load_spec()

    assert spec is not None
    assert len(spec.nodes) == 3  # A, B, C


def test_get_node_ids(simple_graph):
    """Test getting all node IDs."""
    introspector = GraphIntrospector(simple_graph)
    node_ids = introspector.get_node_ids()

    assert len(node_ids) == 3
    # IDs will be generated, but should have 3 nodes
    assert all(isinstance(nid, str) for nid in node_ids)


def test_get_node_spec(simple_graph):
    """Test getting spec for a specific node."""
    introspector = GraphIntrospector(simple_graph)
    node_ids = introspector.get_node_ids()

    # Get spec for first node
    node_spec = introspector.get_node_spec(node_ids[0])
    assert node_spec is not None
    assert node_spec.id == node_ids[0]


def test_get_node_config(simple_graph):
    """Test getting node configuration."""
    introspector = GraphIntrospector(simple_graph)
    node_ids = introspector.get_node_ids()

    config = introspector.get_node_config(node_ids[0])
    assert isinstance(config, dict)


def test_get_edges_from_node(simple_graph):
    """Test getting outgoing edges from a node."""
    introspector = GraphIntrospector(simple_graph)
    spec = introspector.load_spec()

    # Start node should have outgoing edges
    outgoing = introspector.get_edges_from_node(spec.start)
    assert len(outgoing) > 0


def test_get_edges_to_node(simple_graph):
    """Test getting incoming edges to a node."""
    introspector = GraphIntrospector(simple_graph)
    node_ids = introspector.get_node_ids()

    # End node should have incoming edges
    for node_id in node_ids:
        incoming = introspector.get_edges_to_node(node_id)
        if len(incoming) > 0:
            # Found a node with incoming edges
            assert all(hasattr(e, 'from_node') for e in incoming)
            break


def test_get_graph_depth_simple(simple_graph):
    """Test graph depth calculation for simple graph."""
    introspector = GraphIntrospector(simple_graph)
    depth = introspector.get_graph_depth()

    # A -> B -> C should have depth 2 (3 nodes, depth is 0-indexed)
    assert depth == 2


def test_get_graph_depth_branching(branching_graph):
    """Test graph depth calculation for branching graph."""
    introspector = GraphIntrospector(branching_graph)
    depth = introspector.get_graph_depth()

    # A -> B -> D (or A -> C -> D) should have depth 2
    assert depth == 2


def test_get_node_complexity(simple_graph):
    """Test node complexity analysis."""
    introspector = GraphIntrospector(simple_graph)
    node_ids = introspector.get_node_ids()

    complexity = introspector.get_node_complexity(node_ids[0])

    assert 'node_type' in complexity
    assert 'config_keys' in complexity
    assert 'incoming_edges' in complexity
    assert 'outgoing_edges' in complexity
    assert 'branching_factor' in complexity
    assert 'has_conditional_logic' in complexity


def test_find_cycles_simple(simple_graph):
    """Test cycle detection in simple graph (no cycles)."""
    introspector = GraphIntrospector(simple_graph)
    cycles = introspector.find_cycles()

    assert len(cycles) == 0  # No cycles in simple linear graph


def test_find_cycles_cyclic(cyclic_graph):
    """Test cycle detection in cyclic graph."""
    introspector = GraphIntrospector(cyclic_graph)
    cycles = introspector.find_cycles()

    # Should detect at least one cycle
    assert len(cycles) > 0


def test_get_critical_path_simple(simple_graph):
    """Test critical path identification in simple graph."""
    introspector = GraphIntrospector(simple_graph)
    critical_path = introspector.get_critical_path()

    # Should have 3 nodes in path (A -> B -> C)
    assert len(critical_path) == 3


def test_get_critical_path_branching(branching_graph):
    """Test critical path identification in branching graph."""
    introspector = GraphIntrospector(branching_graph)
    critical_path = introspector.get_critical_path()

    # Should have 3 nodes in longest path (A -> B -> D or A -> C -> D)
    assert len(critical_path) == 3


def test_get_node_stats(simple_graph):
    """Test getting overall graph statistics."""
    introspector = GraphIntrospector(simple_graph)
    stats = introspector.get_node_stats()

    assert 'total_nodes' in stats
    assert 'total_edges' in stats
    assert 'max_depth' in stats
    assert 'node_types' in stats
    assert 'leaf_nodes' in stats
    assert 'entry_nodes' in stats
    assert 'has_cycles' in stats

    assert stats['total_nodes'] == 3
    assert stats['total_edges'] == 2
    assert stats['max_depth'] == 2
    assert stats['has_cycles'] is False


def test_get_node_stats_branching(branching_graph):
    """Test statistics for branching graph."""
    introspector = GraphIntrospector(branching_graph)
    stats = introspector.get_node_stats()

    assert stats['total_nodes'] == 4
    assert stats['total_edges'] == 4  # A->B, A->C, B->D, C->D
    # Branching factor should be reflected in edges


def test_visualize_structure(simple_graph):
    """Test structure visualization."""
    introspector = GraphIntrospector(simple_graph)
    visualization = introspector.visualize_structure()

    assert isinstance(visualization, str)
    assert 'Graph:' in visualization
    assert 'Start Node:' in visualization
    assert 'Total Nodes:' in visualization
    assert 'Total Edges:' in visualization


def test_introspector_caching(simple_graph):
    """Test that spec is cached after first load."""
    introspector = GraphIntrospector(simple_graph)

    # First call loads spec
    spec1 = introspector.load_spec()
    assert introspector.spec is not None

    # Second call returns cached spec
    spec2 = introspector.load_spec()
    assert spec1 is spec2  # Same object


def test_introspector_with_invalid_node_id(simple_graph):
    """Test behavior with invalid node ID."""
    introspector = GraphIntrospector(simple_graph)

    node_spec = introspector.get_node_spec('nonexistent_node')
    assert node_spec is None

    config = introspector.get_node_config('nonexistent_node')
    assert config == {}


def test_introspector_multiple_graphs():
    """Test introspector with multiple different graphs."""
    graph1 = Graph(start=TestNodeA(name="A"))
    graph2 = Graph(start=TestNodeB(name="B"))

    introspector1 = GraphIntrospector(graph1)
    introspector2 = GraphIntrospector(graph2)

    nodes1 = introspector1.get_node_ids()
    nodes2 = introspector2.get_node_ids()

    # Different graphs should have different nodes
    assert len(nodes1) == 1
    assert len(nodes2) == 1
    assert nodes1[0] != nodes2[0]  # Different node IDs
