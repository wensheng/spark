"""Tests for ChangeApplicator."""

import pytest
from spark.rsi.change_applicator import ChangeApplicator, ChangeApplicationError
from spark.rsi.types import (
    ImprovementHypothesis,
    ChangeSpec,
    HypothesisType,
    RiskLevel,
    ExpectedImprovement
)
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def basic_graph_spec():
    """Create a basic graph spec for testing."""
    return GraphSpec(
        id="test_graph_v1",
        spark_version="2.0",
        start="node_a",
        nodes=[
            NodeSpec(
                id="node_a",
                type="Node",
                description="First node",
                config={"prompt": "Hello", "temperature": 0.7}
            ),
            NodeSpec(
                id="node_b",
                type="Node",
                description="Second node",
                config={"max_tokens": 100}
            ),
            NodeSpec(
                id="node_c",
                type="Node",
                description="Third node"
            )
        ],
        edges=[
            EdgeSpec(
                id="edge_ab",
                from_id="node_a",
                to_id="node_b",
                condition=None
            ),
            EdgeSpec(
                id="edge_bc",
                from_id="node_b",
                to_id="node_c",
                condition={"kind": "expr", "expr": "$.outputs.continue"}
            )
        ]
    )


@pytest.fixture
def basic_hypothesis():
    """Create a basic hypothesis for testing."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_test_001",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="node_a",
        rationale="Improve prompt clarity",
        expected_improvement=ExpectedImprovement(success_rate_delta=0.05),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="prompt",
                old_value="Hello",
                new_value="Hello, how can I help you today?"
            )
        ],
        risk_level=RiskLevel.LOW
    )


# ============================================================================
# Initialization Tests
# ============================================================================

def test_change_applicator_init_default():
    """Test default initialization."""
    applicator = ChangeApplicator()
    assert applicator.validate_changes is True
    assert applicator.strict_mode is False


def test_change_applicator_init_custom():
    """Test custom initialization."""
    applicator = ChangeApplicator(validate_changes=False, strict_mode=True)
    assert applicator.validate_changes is False
    assert applicator.strict_mode is True


# ============================================================================
# Node Config Update Tests
# ============================================================================

def test_apply_node_config_update_simple(basic_graph_spec):
    """Test simple node config update."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_config_update",
        target_node_id="node_a",
        config_path="prompt",
        new_value="New prompt text"
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    # Find the modified node
    node_a = next(n for n in modified_spec.nodes if n.id == "node_a")
    assert node_a.config["prompt"] == "New prompt text"

    # Original should be unchanged
    original_node_a = next(n for n in basic_graph_spec.nodes if n.id == "node_a")
    assert original_node_a.config["prompt"] == "Hello"


def test_apply_node_config_update_nested_path(basic_graph_spec):
    """Test node config update with nested path."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_config_update",
        target_node_id="node_a",
        config_path="model.temperature",
        new_value=0.9
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    node_a = next(n for n in modified_spec.nodes if n.id == "node_a")
    assert node_a.config["model"]["temperature"] == 0.9


def test_apply_node_config_update_new_field(basic_graph_spec):
    """Test adding a new config field."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_config_update",
        target_node_id="node_c",
        config_path="new_param",
        new_value="new_value"
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    node_c = next(n for n in modified_spec.nodes if n.id == "node_c")
    assert node_c.config["new_param"] == "new_value"


def test_apply_node_config_update_missing_node(basic_graph_spec):
    """Test error when target node doesn't exist."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_config_update",
        target_node_id="nonexistent_node",
        config_path="prompt",
        new_value="New prompt"
    )

    with pytest.raises(ChangeApplicationError, match="Node not found"):
        applicator.apply_change(basic_graph_spec, change)


def test_apply_node_config_update_missing_params(basic_graph_spec):
    """Test error when required params are missing."""
    applicator = ChangeApplicator()

    # Missing target_node_id
    change1 = ChangeSpec(
        type="node_config_update",
        config_path="prompt",
        new_value="New prompt"
    )
    with pytest.raises(ChangeApplicationError, match="requires target_node_id"):
        applicator.apply_change(basic_graph_spec, change1)

    # Missing config_path
    change2 = ChangeSpec(
        type="node_config_update",
        target_node_id="node_a",
        new_value="New prompt"
    )
    with pytest.raises(ChangeApplicationError, match="requires config_path"):
        applicator.apply_change(basic_graph_spec, change2)


# ============================================================================
# Node Add Tests
# ============================================================================

def test_apply_node_add(basic_graph_spec):
    """Test adding a new node."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_add",
        additional_params={
            'node_spec': {
                'id': 'node_d',
                'type': 'Node',
                'description': 'New node',
                'config': {'param': 'value'}
            }
        }
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    # Should have 4 nodes now
    assert len(modified_spec.nodes) == 4
    node_d = next((n for n in modified_spec.nodes if n.id == "node_d"), None)
    assert node_d is not None
    assert node_d.type == "Node"
    assert node_d.config["param"] == "value"


def test_apply_node_add_duplicate_id(basic_graph_spec):
    """Test error when adding node with duplicate ID."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_add",
        additional_params={
            'node_spec': {
                'id': 'node_a',  # Already exists
                'type': 'Node'
            }
        }
    )

    with pytest.raises(ChangeApplicationError, match="already exists"):
        applicator.apply_change(basic_graph_spec, change)


def test_apply_node_add_missing_spec(basic_graph_spec):
    """Test error when node_spec is missing."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_add",
        additional_params={}
    )

    with pytest.raises(ChangeApplicationError, match="requires 'node_spec'"):
        applicator.apply_change(basic_graph_spec, change)


# ============================================================================
# Node Remove Tests
# ============================================================================

def test_apply_node_remove(basic_graph_spec):
    """Test removing a node."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_remove",
        target_node_id="node_c"
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    # Should have 2 nodes now
    assert len(modified_spec.nodes) == 2
    assert not any(n.id == "node_c" for n in modified_spec.nodes)

    # Edge to node_c should be removed
    assert len(modified_spec.edges) == 1
    assert not any(e.to_node == "node_c" for e in modified_spec.edges)


def test_apply_node_remove_start_node(basic_graph_spec):
    """Test error when trying to remove start node."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_remove",
        target_node_id="node_a"  # This is the start node
    )

    with pytest.raises(ChangeApplicationError, match="Cannot remove start node"):
        applicator.apply_change(basic_graph_spec, change)


def test_apply_node_remove_nonexistent(basic_graph_spec):
    """Test error when removing non-existent node."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="node_remove",
        target_node_id="nonexistent"
    )

    with pytest.raises(ChangeApplicationError, match="Node not found"):
        applicator.apply_change(basic_graph_spec, change)


# ============================================================================
# Edge Add Tests
# ============================================================================

def test_apply_edge_add(basic_graph_spec):
    """Test adding a new edge."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_add",
        additional_params={
            'edge_spec': {
                'id': 'edge_ac',
                'from_id': 'node_a',
                'to_id': 'node_c',
                'condition': None
            }
        }
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    # Should have 3 edges now
    assert len(modified_spec.edges) == 3
    edge_ac = next((e for e in modified_spec.edges if e.id == "edge_ac"), None)
    assert edge_ac is not None
    assert edge_ac.from_node == "node_a"
    assert edge_ac.to_node == "node_c"


def test_apply_edge_add_invalid_nodes(basic_graph_spec):
    """Test error when adding edge with invalid node references."""
    applicator = ChangeApplicator()

    # Invalid source node
    change1 = ChangeSpec(
        type="edge_add",
        additional_params={
            'edge_spec': {
                'id': 'edge_xy',
                'from_id': 'nonexistent',
                'to_id': 'node_a'
            }
        }
    )
    with pytest.raises(ChangeApplicationError, match="Source node not found"):
        applicator.apply_change(basic_graph_spec, change1)

    # Invalid target node
    change2 = ChangeSpec(
        type="edge_add",
        additional_params={
            'edge_spec': {
                'id': 'edge_xy',
                'from_id': 'node_a',
                'to_id': 'nonexistent'
            }
        }
    )
    with pytest.raises(ChangeApplicationError, match="Target node not found"):
        applicator.apply_change(basic_graph_spec, change2)


def test_apply_edge_add_duplicate_id(basic_graph_spec):
    """Test error when adding edge with duplicate ID."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_add",
        additional_params={
            'edge_spec': {
                'id': 'edge_ab',  # Already exists
                'from_id': 'node_a',
                'to_id': 'node_c'
            }
        }
    )

    with pytest.raises(ChangeApplicationError, match="already exists"):
        applicator.apply_change(basic_graph_spec, change)


# ============================================================================
# Edge Remove Tests
# ============================================================================

def test_apply_edge_remove(basic_graph_spec):
    """Test removing an edge."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_remove",
        target_edge_id="edge_bc"
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    # Should have 1 edge now
    assert len(modified_spec.edges) == 1
    assert not any(e.id == "edge_bc" for e in modified_spec.edges)


def test_apply_edge_remove_nonexistent(basic_graph_spec):
    """Test error when removing non-existent edge."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_remove",
        target_edge_id="nonexistent"
    )

    with pytest.raises(ChangeApplicationError, match="Edge not found"):
        applicator.apply_change(basic_graph_spec, change)


# ============================================================================
# Edge Modify Tests
# ============================================================================

def test_apply_edge_modify(basic_graph_spec):
    """Test modifying an edge."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_modify",
        target_edge_id="edge_bc",
        additional_params={
            'condition': {"kind": "expr", "expr": "$.outputs.ready"},
            'priority': 10,
            'description': "Modified edge"
        }
    )

    modified_spec = applicator.apply_change(basic_graph_spec, change)

    edge_bc = next(e for e in modified_spec.edges if e.id == "edge_bc")
    assert edge_bc.condition == {"kind": "expr", "expr": "$.outputs.ready"}
    assert edge_bc.priority == 10
    assert edge_bc.description == "Modified edge"


def test_apply_edge_modify_nonexistent(basic_graph_spec):
    """Test error when modifying non-existent edge."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="edge_modify",
        target_edge_id="nonexistent",
        additional_params={'priority': 10}
    )

    with pytest.raises(ChangeApplicationError, match="Edge not found"):
        applicator.apply_change(basic_graph_spec, change)


# ============================================================================
# Hypothesis Application Tests
# ============================================================================

def test_apply_hypothesis_single_change(basic_graph_spec, basic_hypothesis):
    """Test applying hypothesis with single change."""
    applicator = ChangeApplicator()

    modified_spec, diff = applicator.apply_hypothesis(basic_graph_spec, basic_hypothesis)

    # Check that change was applied
    node_a = next(n for n in modified_spec.nodes if n.id == "node_a")
    assert node_a.config["prompt"] == "Hello, how can I help you today?"

    # Check diff record
    assert diff['hypothesis_id'] == "hyp_test_001"
    assert diff['changes_applied'] == 1
    assert diff['changes_failed'] == 0


def test_apply_hypothesis_multiple_changes(basic_graph_spec):
    """Test applying hypothesis with multiple changes."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_multi",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PARAMETER_TUNING,
        rationale="Multiple improvements",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="temperature",
                new_value=0.9
            ),
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_b",
                config_path="max_tokens",
                new_value=200
            ),
        ],
        risk_level=RiskLevel.LOW
    )

    applicator = ChangeApplicator()
    modified_spec, diff = applicator.apply_hypothesis(basic_graph_spec, hypothesis)

    # Both changes should be applied
    node_a = next(n for n in modified_spec.nodes if n.id == "node_a")
    node_b = next(n for n in modified_spec.nodes if n.id == "node_b")
    assert node_a.config["temperature"] == 0.9
    assert node_b.config["max_tokens"] == 200

    assert diff['changes_applied'] == 2
    assert diff['changes_failed'] == 0


def test_apply_hypothesis_with_failure_non_strict(basic_graph_spec):
    """Test applying hypothesis with one failing change in non-strict mode."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_partial",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PARAMETER_TUNING,
        rationale="Partial success test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="temperature",
                new_value=0.9
            ),
            ChangeSpec(
                type="node_config_update",
                target_node_id="nonexistent_node",  # This will fail
                config_path="param",
                new_value="value"
            ),
        ],
        risk_level=RiskLevel.LOW
    )

    applicator = ChangeApplicator(strict_mode=False)
    modified_spec, diff = applicator.apply_hypothesis(basic_graph_spec, hypothesis)

    # First change should succeed
    assert diff['changes_applied'] == 1
    assert diff['changes_failed'] == 1

    # Modified spec should have the successful change
    node_a = next(n for n in modified_spec.nodes if n.id == "node_a")
    assert node_a.config["temperature"] == 0.9


def test_apply_hypothesis_with_failure_strict(basic_graph_spec):
    """Test applying hypothesis with failure in strict mode."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_strict",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PARAMETER_TUNING,
        rationale="Strict mode test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="nonexistent_node",
                config_path="param",
                new_value="value"
            ),
        ],
        risk_level=RiskLevel.LOW
    )

    applicator = ChangeApplicator(strict_mode=True)

    with pytest.raises(ChangeApplicationError, match="Failed to apply change"):
        applicator.apply_hypothesis(basic_graph_spec, hypothesis)


# ============================================================================
# Validation Tests
# ============================================================================

def test_validation_after_changes(basic_graph_spec):
    """Test that node removal automatically cleans up connected edges."""
    # When removing a node, connected edges should be removed automatically
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_cleanup",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.CUSTOM,
        rationale="Test edge cleanup on node removal",
        changes=[
            ChangeSpec(
                type="node_remove",
                target_node_id="node_b"
            ),
            # edge_ab and edge_bc should be automatically removed
        ],
        risk_level=RiskLevel.HIGH
    )

    applicator = ChangeApplicator(validate_changes=True)

    # Should succeed with automatic edge cleanup
    modified_spec, diff = applicator.apply_hypothesis(basic_graph_spec, hypothesis)

    # Verify node_b was removed
    assert not any(n.id == "node_b" for n in modified_spec.nodes)

    # Verify edges to/from node_b were removed
    assert not any(e.from_node == "node_b" or e.to_node == "node_b" for e in modified_spec.edges)

    # Original spec should have 2 edges, modified should have 0 (both edges connected to node_b)
    assert len(basic_graph_spec.edges) == 2
    assert len(modified_spec.edges) == 0  # edge_ab and edge_bc both removed


def test_validation_disabled(basic_graph_spec):
    """Test that validation can be disabled."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_no_validate",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PARAMETER_TUNING,
        rationale="No validation test",
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="param",
                new_value="value"
            ),
        ],
        risk_level=RiskLevel.LOW
    )

    applicator = ChangeApplicator(validate_changes=False)
    modified_spec, diff = applicator.apply_hypothesis(basic_graph_spec, hypothesis)

    # Should succeed even though we disabled validation
    assert diff['changes_applied'] == 1


# ============================================================================
# Diff Generation Tests
# ============================================================================

def test_diff_record_structure(basic_graph_spec, basic_hypothesis):
    """Test that diff record has correct structure."""
    applicator = ChangeApplicator()
    _, diff = applicator.apply_hypothesis(basic_graph_spec, basic_hypothesis)

    # Check all required fields
    assert 'hypothesis_id' in diff
    assert 'baseline_version' in diff
    assert 'modified_version' in diff
    assert 'timestamp' in diff
    assert 'changes_applied' in diff
    assert 'changes_failed' in diff
    assert 'applied_changes' in diff
    assert 'failed_changes' in diff
    assert 'summary' in diff

    # Check summary structure
    summary = diff['summary']
    assert 'nodes_added' in summary
    assert 'nodes_removed' in summary
    assert 'nodes_modified' in summary
    assert 'edges_added' in summary
    assert 'edges_removed' in summary
    assert 'edges_modified' in summary


def test_diff_summary_counts(basic_graph_spec):
    """Test that diff summary counts are correct."""
    hypothesis = ImprovementHypothesis(
        hypothesis_id="hyp_counts",
        graph_id="test_graph_v1",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.CUSTOM,
        rationale="Count test",
        changes=[
            ChangeSpec(type="node_config_update", target_node_id="node_a", config_path="p", new_value="v"),
            ChangeSpec(type="node_add", additional_params={'node_spec': {'id': 'node_d', 'type': 'Node'}}),
            ChangeSpec(type="edge_add", additional_params={'edge_spec': {'id': 'e_ac', 'from_id': 'node_a', 'to_id': 'node_c'}}),
        ],
        risk_level=RiskLevel.LOW
    )

    applicator = ChangeApplicator()
    _, diff = applicator.apply_hypothesis(basic_graph_spec, hypothesis)

    summary = diff['summary']
    assert summary['nodes_modified'] == 1
    assert summary['nodes_added'] == 1
    assert summary['edges_added'] == 1


# ============================================================================
# Unsupported Change Type Test
# ============================================================================

def test_unsupported_change_type(basic_graph_spec):
    """Test error for unsupported change type."""
    applicator = ChangeApplicator()
    change = ChangeSpec(
        type="unsupported_type",
        target_node_id="node_a"
    )

    with pytest.raises(ChangeApplicationError, match="Unsupported change type"):
        applicator.apply_change(basic_graph_spec, change)
