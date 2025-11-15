"""Tests for RSI Phase 6 structural change methods in ChangeApplicator."""

import pytest
from spark.rsi.change_applicator import ChangeApplicator, ChangeApplicationError
from spark.rsi.types import (
    ChangeSpec,
    StructuralDiff,
    StructuralValidationResult,
    ParallelGraphStructure,
)
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def simple_graph_spec():
    """Create a simple graph spec for testing."""
    return GraphSpec(
        id="test_graph",
        version="1.0",
        start="node_a",
        nodes=[
            NodeSpec(id="node_a", type="InputNode", config={}),
            NodeSpec(id="node_b", type="ProcessNode", config={}),
            NodeSpec(id="node_c", type="OutputNode", config={}),
        ],
        edges=[
            EdgeSpec(id="edge_ab", from_node="node_a", to_node="node_b"),
            EdgeSpec(id="edge_bc", from_node="node_b", to_node="node_c"),
        ]
    )


@pytest.fixture
def complex_graph_spec():
    """Create a more complex graph spec with branches."""
    return GraphSpec(
        id="complex_graph",
        version="1.0",
        start="start",
        nodes=[
            NodeSpec(id="start", type="StartNode", config={}),
            NodeSpec(id="branch_point", type="BranchNode", config={}),
            NodeSpec(id="branch_a1", type="ProcessNode", config={}),
            NodeSpec(id="branch_a2", type="ProcessNode", config={}),
            NodeSpec(id="branch_b1", type="ProcessNode", config={}),
            NodeSpec(id="branch_b2", type="ProcessNode", config={}),
            NodeSpec(id="merge", type="MergeNode", config={}),
            NodeSpec(id="end", type="EndNode", config={}),
        ],
        edges=[
            EdgeSpec(id="edge_start_branch", from_node="start", to_node="branch_point"),
            EdgeSpec(id="edge_branch_a1", from_node="branch_point", to_node="branch_a1"),
            EdgeSpec(id="edge_a1_a2", from_node="branch_a1", to_node="branch_a2"),
            EdgeSpec(id="edge_branch_b1", from_node="branch_point", to_node="branch_b1"),
            EdgeSpec(id="edge_b1_b2", from_node="branch_b1", to_node="branch_b2"),
            EdgeSpec(id="edge_a2_merge", from_node="branch_a2", to_node="merge"),
            EdgeSpec(id="edge_b2_merge", from_node="branch_b2", to_node="merge"),
            EdgeSpec(id="edge_merge_end", from_node="merge", to_node="end"),
        ]
    )


@pytest.fixture
def applicator():
    """Create a ChangeApplicator instance."""
    return ChangeApplicator()


# ============================================================================
# Test validate_structural_integrity
# ============================================================================

def test_validate_valid_graph(applicator, simple_graph_spec):
    """Test validation of a valid graph."""
    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert result.is_valid
    assert len(result.errors) == 0
    assert len(result.reachable_nodes) == 3
    assert "node_a" in result.reachable_nodes
    assert "node_b" in result.reachable_nodes
    assert "node_c" in result.reachable_nodes
    assert len(result.orphaned_nodes) == 0


def test_validate_missing_start_node(applicator, simple_graph_spec):
    """Test validation when start node is missing."""
    simple_graph_spec.start = None

    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert not result.is_valid
    assert len(result.errors) > 0
    assert "no start node" in result.errors[0].lower()


def test_validate_invalid_start_node(applicator, simple_graph_spec):
    """Test validation when start node doesn't exist."""
    simple_graph_spec.start = "nonexistent_node"

    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert not result.is_valid
    assert any("does not exist" in err for err in result.errors)


def test_validate_orphaned_nodes(applicator, simple_graph_spec):
    """Test detection of orphaned nodes."""
    # Add a node not connected to the main graph
    simple_graph_spec.nodes.append(NodeSpec(id="orphan", type="OrphanNode", config={}))

    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert result.is_valid  # Orphans are warnings, not errors
    assert len(result.warnings) > 0
    assert "orphan" in result.orphaned_nodes
    assert "unreachable" in result.warnings[0].lower()


def test_validate_invalid_edge_target(applicator, simple_graph_spec):
    """Test detection of edges referencing non-existent nodes."""
    # Add edge to non-existent node
    simple_graph_spec.edges.append(
        EdgeSpec(id="bad_edge", from_node="node_c", to_node="nonexistent")
    )

    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert not result.is_valid
    assert any("non-existent" in err for err in result.errors)


def test_validate_cycle_detection(applicator, simple_graph_spec):
    """Test detection of cycles in graph."""
    # Create a cycle: node_c -> node_a
    simple_graph_spec.edges.append(
        EdgeSpec(id="cycle_edge", from_node="node_c", to_node="node_a")
    )

    result = applicator.validate_structural_integrity(simple_graph_spec)

    assert result.is_valid  # Cycles are warnings, not errors
    assert len(result.warnings) > 0
    assert "cycle" in result.warnings[0].lower()
    assert len(result.cycles) > 0


def test_validate_complex_graph(applicator, complex_graph_spec):
    """Test validation of a complex graph with branches."""
    result = applicator.validate_structural_integrity(complex_graph_spec)

    assert result.is_valid
    assert len(result.errors) == 0
    assert len(result.reachable_nodes) == 8
    assert len(result.orphaned_nodes) == 0


def test_validate_empty_graph(applicator):
    """Test validation of graph with no executable nodes."""
    empty_spec = GraphSpec(
        id="empty",
        version="1.0",
        start="start",
        nodes=[NodeSpec(id="start", type="StartNode", config={})],
        edges=[]
    )

    result = applicator.validate_structural_integrity(empty_spec)

    # Single node with no outgoing edges is valid
    assert result.is_valid
    assert len(result.reachable_nodes) == 1


# ============================================================================
# Test compute_structural_diff
# ============================================================================

def test_compute_diff_no_changes(applicator, simple_graph_spec):
    """Test diff computation when there are no changes."""
    import copy
    spec_copy = copy.deepcopy(simple_graph_spec)

    diff = applicator.compute_structural_diff(simple_graph_spec, spec_copy)

    assert len(diff.nodes_added) == 0
    assert len(diff.nodes_removed) == 0
    assert len(diff.nodes_modified) == 0
    assert len(diff.edges_added) == 0
    assert len(diff.edges_removed) == 0
    assert len(diff.edges_modified) == 0
    assert diff.complexity_delta == 0
    assert diff.summary == "No changes"


def test_compute_diff_node_added(applicator, simple_graph_spec):
    """Test diff computation when nodes are added."""
    import copy
    modified_spec = copy.deepcopy(simple_graph_spec)
    modified_spec.nodes.append(NodeSpec(id="node_d", type="NewNode", config={}))

    diff = applicator.compute_structural_diff(simple_graph_spec, modified_spec)

    assert len(diff.nodes_added) == 1
    assert "node_d" in diff.nodes_added
    assert diff.complexity_delta == 1
    assert "1 node(s) added" in diff.summary


def test_compute_diff_node_removed(applicator, simple_graph_spec):
    """Test diff computation when nodes are removed."""
    import copy
    modified_spec = copy.deepcopy(simple_graph_spec)
    modified_spec.nodes.pop(2)  # Remove node_c

    diff = applicator.compute_structural_diff(simple_graph_spec, modified_spec)

    assert len(diff.nodes_removed) == 1
    assert "node_c" in diff.nodes_removed
    assert diff.complexity_delta == -1
    assert "1 node(s) removed" in diff.summary


def test_compute_diff_node_modified(applicator, simple_graph_spec):
    """Test diff computation when nodes are modified."""
    import copy
    modified_spec = copy.deepcopy(simple_graph_spec)
    modified_spec.nodes[1].type = "DifferentNodeType"

    diff = applicator.compute_structural_diff(simple_graph_spec, modified_spec)

    assert len(diff.nodes_modified) > 0
    assert any(m.node_id == "node_b" and m.field == "type" for m in diff.nodes_modified)


def test_compute_diff_edge_changes(applicator, simple_graph_spec):
    """Test diff computation when edges are changed."""
    import copy
    modified_spec = copy.deepcopy(simple_graph_spec)

    # Remove one edge
    modified_spec.edges.pop(1)

    # Add a new edge
    modified_spec.edges.append(
        EdgeSpec(id="new_edge", from_node="node_a", to_node="node_c")
    )

    diff = applicator.compute_structural_diff(simple_graph_spec, modified_spec)

    assert len(diff.edges_removed) == 1
    assert "edge_bc" in diff.edges_removed
    assert len(diff.edges_added) == 1
    assert "new_edge" in diff.edges_added


def test_compute_diff_complex_changes(applicator, simple_graph_spec):
    """Test diff computation with multiple types of changes."""
    import copy
    modified_spec = copy.deepcopy(simple_graph_spec)

    # Add node
    modified_spec.nodes.append(NodeSpec(id="node_d", type="NewNode", config={}))

    # Remove node
    modified_spec.nodes.pop(2)  # Remove node_c

    # Modify node
    modified_spec.nodes[0].config = {"new_config": "value"}

    # Add edge
    modified_spec.edges.append(
        EdgeSpec(id="new_edge", from_node="node_b", to_node="node_d")
    )

    diff = applicator.compute_structural_diff(simple_graph_spec, modified_spec)

    assert len(diff.nodes_added) == 1
    assert len(diff.nodes_removed) == 1
    assert len(diff.nodes_modified) > 0
    assert len(diff.edges_added) == 1
    assert "added" in diff.summary and "removed" in diff.summary


# ============================================================================
# Test _apply_node_replacement
# ============================================================================

def test_apply_node_replacement_basic(applicator, simple_graph_spec):
    """Test basic node replacement."""
    replacement_spec = {
        'id': 'node_b_new',
        'type': 'BetterProcessNode',
        'config': {}
    }

    change = ChangeSpec(
        type='node_replacement',
        target_node_id='node_b',
        additional_params={'replacement_node_spec': replacement_spec}
    )

    modified_spec = applicator.apply_change(simple_graph_spec, change)

    # Check node was replaced
    assert not any(n.id == 'node_b' for n in modified_spec.nodes)
    assert any(n.id == 'node_b_new' for n in modified_spec.nodes)

    # Check edges were rewired
    assert any(
        e.from_node == 'node_a' and e.to_node == 'node_b_new'
        for e in modified_spec.edges
    )
    assert any(
        e.from_node == 'node_b_new' and e.to_node == 'node_c'
        for e in modified_spec.edges
    )


def test_apply_node_replacement_start_node(applicator, simple_graph_spec):
    """Test replacing the start node."""
    replacement_spec = {
        'id': 'node_a_new',
        'type': 'BetterInputNode',
        'config': {}
    }

    change = ChangeSpec(
        type='node_replacement',
        target_node_id='node_a',
        additional_params={'replacement_node_spec': replacement_spec}
    )

    modified_spec = applicator.apply_change(simple_graph_spec, change)

    # Check start node was updated
    assert modified_spec.start == 'node_a_new'
    assert any(n.id == 'node_a_new' for n in modified_spec.nodes)


def test_apply_node_replacement_missing_node(applicator, simple_graph_spec):
    """Test node replacement with non-existent node."""
    replacement_spec = {
        'id': 'replacement',
        'type': 'NewNode',
        'config': {}
    }

    change = ChangeSpec(
        type='node_replacement',
        target_node_id='nonexistent',
        additional_params={'replacement_node_spec': replacement_spec}
    )

    with pytest.raises(ChangeApplicationError, match="Node not found"):
        applicator.apply_change(simple_graph_spec, change)


def test_apply_node_replacement_missing_spec(applicator, simple_graph_spec):
    """Test node replacement without replacement spec."""
    change = ChangeSpec(
        type='node_replacement',
        target_node_id='node_b',
        additional_params={}
    )

    with pytest.raises(ChangeApplicationError, match="replacement_node_spec"):
        applicator.apply_change(simple_graph_spec, change)


def test_apply_node_replacement_preserves_edges(applicator, complex_graph_spec):
    """Test that node replacement preserves all edges."""
    # Count edges connected to branch_point
    original_incoming = sum(
        1 for e in complex_graph_spec.edges if e.to_node == 'branch_point'
    )
    original_outgoing = sum(
        1 for e in complex_graph_spec.edges if e.from_node == 'branch_point'
    )

    replacement_spec = {
        'id': 'branch_point_new',
        'type': 'ImprovedBranchNode',
        'config': {}
    }

    change = ChangeSpec(
        type='node_replacement',
        target_node_id='branch_point',
        additional_params={'replacement_node_spec': replacement_spec}
    )

    modified_spec = applicator.apply_change(complex_graph_spec, change)

    # Count edges connected to new node
    new_incoming = sum(
        1 for e in modified_spec.edges if e.to_node == 'branch_point_new'
    )
    new_outgoing = sum(
        1 for e in modified_spec.edges if e.from_node == 'branch_point_new'
    )

    # Should have same number of connections
    assert new_incoming == original_incoming
    assert new_outgoing == original_outgoing


def test_apply_node_replacement_immutability(applicator, simple_graph_spec):
    """Test that node replacement doesn't modify original spec."""
    import copy
    original_nodes = copy.deepcopy(simple_graph_spec.nodes)
    original_edges = copy.deepcopy(simple_graph_spec.edges)

    replacement_spec = {
        'id': 'node_b_new',
        'type': 'BetterNode',
        'config': {}
    }

    change = ChangeSpec(
        type='node_replacement',
        target_node_id='node_b',
        additional_params={'replacement_node_spec': replacement_spec}
    )

    applicator.apply_change(simple_graph_spec, change)

    # Original spec should be unchanged
    assert any(n.id == 'node_b' for n in simple_graph_spec.nodes)
    assert len(simple_graph_spec.nodes) == len(original_nodes)


# ============================================================================
# Test _apply_edge_batch_modifications
# ============================================================================

def test_apply_edge_batch_remove(applicator, simple_graph_spec):
    """Test batch edge removal."""
    edge_modifications = [
        {'type': 'remove', 'edge_id': 'edge_bc'}
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    modified_spec = applicator.apply_change(simple_graph_spec, change)

    assert not any(e.id == 'edge_bc' for e in modified_spec.edges)
    assert len(modified_spec.edges) == len(simple_graph_spec.edges) - 1


def test_apply_edge_batch_add(applicator, simple_graph_spec):
    """Test batch edge addition."""
    edge_modifications = [
        {
            'type': 'add',
            'edge_spec': {
                'id': 'shortcut_ac',
                'from_node': 'node_a',
                'to_node': 'node_c'
            }
        }
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    modified_spec = applicator.apply_change(simple_graph_spec, change)

    assert any(e.id == 'shortcut_ac' for e in modified_spec.edges)
    assert len(modified_spec.edges) == len(simple_graph_spec.edges) + 1


def test_apply_edge_batch_modify(applicator, simple_graph_spec):
    """Test batch edge modification."""
    edge_modifications = [
        {
            'type': 'modify',
            'edge_id': 'edge_ab',
            'updates': {'condition': 'new_condition', 'priority': 10}
        }
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    modified_spec = applicator.apply_change(simple_graph_spec, change)

    edge = next(e for e in modified_spec.edges if e.id == 'edge_ab')
    assert edge.condition == 'new_condition'
    assert edge.priority == 10


def test_apply_edge_batch_multiple_operations(applicator, complex_graph_spec):
    """Test batch with multiple different operations."""
    edge_modifications = [
        {'type': 'remove', 'edge_id': 'edge_a1_a2'},
        {
            'type': 'add',
            'edge_spec': {
                'id': 'direct_a',
                'from_node': 'branch_a1',
                'to_node': 'merge'
            }
        },
        {
            'type': 'modify',
            'edge_id': 'edge_branch_a1',
            'updates': {'priority': 1}
        }
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    modified_spec = applicator.apply_change(complex_graph_spec, change)

    # Check all operations applied
    assert not any(e.id == 'edge_a1_a2' for e in modified_spec.edges)
    assert any(e.id == 'direct_a' for e in modified_spec.edges)
    edge = next(e for e in modified_spec.edges if e.id == 'edge_branch_a1')
    assert edge.priority == 1


def test_apply_edge_batch_invalid_operation(applicator, simple_graph_spec):
    """Test batch fails on invalid operation."""
    edge_modifications = [
        {'type': 'remove', 'edge_id': 'nonexistent_edge'}
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    with pytest.raises(ChangeApplicationError, match="Edge not found"):
        applicator.apply_change(simple_graph_spec, change)


def test_apply_edge_batch_atomic_failure(applicator, simple_graph_spec):
    """Test batch is atomic - fails if any operation invalid."""
    edge_modifications = [
        {'type': 'remove', 'edge_id': 'edge_ab'},  # Valid
        {'type': 'remove', 'edge_id': 'nonexistent'}  # Invalid
    ]

    change = ChangeSpec(
        type='edge_batch_modifications',
        additional_params={'edge_modifications': edge_modifications}
    )

    with pytest.raises(ChangeApplicationError):
        applicator.apply_change(simple_graph_spec, change)

    # Original spec should be unchanged (all-or-nothing)
    assert any(e.id == 'edge_ab' for e in simple_graph_spec.edges)


# ============================================================================
# Test _apply_parallelization
# ============================================================================

def test_apply_parallelization_basic(applicator, complex_graph_spec):
    """Test basic parallelization of branches."""
    parallel_structure = {
        'parallel_branches': [
            ['branch_a1', 'branch_a2'],
            ['branch_b1', 'branch_b2']
        ],
        'merge_node_id': 'merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'branch_point'
        }
    )

    modified_spec = applicator.apply_change(complex_graph_spec, change)

    # Check parallel edges created from entry node
    parallel_edges = [
        e for e in modified_spec.edges
        if e.from_node == 'branch_point'
    ]
    assert len(parallel_edges) == 2  # One to each branch


def test_apply_parallelization_creates_merge_edges(applicator, complex_graph_spec):
    """Test that parallelization creates edges to merge node."""
    parallel_structure = {
        'parallel_branches': [
            ['branch_a1', 'branch_a2'],
            ['branch_b1', 'branch_b2']
        ],
        'merge_node_id': 'merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'branch_point'
        }
    )

    modified_spec = applicator.apply_change(complex_graph_spec, change)

    # Check edges to merge node
    merge_edges = [
        e for e in modified_spec.edges
        if e.to_node == 'merge' and (
            e.from_node == 'branch_a2' or e.from_node == 'branch_b2'
        )
    ]
    assert len(merge_edges) == 2  # One from each branch end


def test_apply_parallelization_creates_merge_node(applicator):
    """Test that parallelization creates merge node if needed."""
    spec = GraphSpec(
        id="test",
        version="1.0",
        start="start",
        nodes=[
            NodeSpec(id="start", type="StartNode", config={}),
            NodeSpec(id="a", type="Node", config={}),
            NodeSpec(id="b", type="Node", config={}),
        ],
        edges=[]
    )

    parallel_structure = {
        'parallel_branches': [['a'], ['b']],
        'merge_node_id': 'new_merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'start'
        }
    )

    modified_spec = applicator.apply_change(spec, change)

    # Check merge node was created
    assert any(n.id == 'new_merge' for n in modified_spec.nodes)
    merge_node = next(n for n in modified_spec.nodes if n.id == 'new_merge')
    assert merge_node.type == 'MergeNode'


def test_apply_parallelization_missing_entry_node(applicator, simple_graph_spec):
    """Test parallelization fails with missing entry node."""
    parallel_structure = {
        'parallel_branches': [['node_b'], ['node_c']],
        'merge_node_id': 'merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'nonexistent'
        }
    )

    with pytest.raises(ChangeApplicationError, match="Entry node not found"):
        applicator.apply_change(simple_graph_spec, change)


def test_apply_parallelization_missing_branch_node(applicator, simple_graph_spec):
    """Test parallelization fails with missing branch node."""
    parallel_structure = {
        'parallel_branches': [['node_b'], ['nonexistent']],
        'merge_node_id': 'merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'node_a'
        }
    )

    with pytest.raises(ChangeApplicationError, match="Branch node not found"):
        applicator.apply_change(simple_graph_spec, change)


def test_apply_parallelization_internal_branch_edges(applicator):
    """Test that parallelization creates internal edges within branches."""
    spec = GraphSpec(
        id="test",
        version="1.0",
        start="start",
        nodes=[
            NodeSpec(id="start", type="StartNode", config={}),
            NodeSpec(id="a1", type="Node", config={}),
            NodeSpec(id="a2", type="Node", config={}),
            NodeSpec(id="b1", type="Node", config={}),
        ],
        edges=[]
    )

    parallel_structure = {
        'parallel_branches': [
            ['a1', 'a2'],  # Two-node branch
            ['b1']  # Single-node branch
        ],
        'merge_node_id': 'merge',
        'requires_merge': True,
        'merge_strategy': 'wait_all'
    }

    change = ChangeSpec(
        type='parallelization',
        additional_params={
            'parallel_structure': parallel_structure,
            'entry_node': 'start'
        }
    )

    modified_spec = applicator.apply_change(spec, change)

    # Check internal edge created within branch 0 (a1 -> a2)
    assert any(
        e.from_node == 'a1' and e.to_node == 'a2'
        for e in modified_spec.edges
    )

    # Branch 1 has only one node, so no internal edges needed
    assert not any(
        e.from_node == 'b1' and e.to_node != 'merge'
        for e in modified_spec.edges
    )
