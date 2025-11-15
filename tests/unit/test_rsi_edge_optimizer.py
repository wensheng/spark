"""Tests for RSI edge optimizer."""

import pytest
from spark.rsi.edge_optimizer import EdgeOptimizer
from spark.rsi.types import (
    RedundantEdge,
    ShortcutOpportunity,
    OptimizedCondition,
)
from spark.nodes.spec import EdgeSpec
from spark.rsi.introspection import GraphIntrospector


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def optimizer():
    """Create edge optimizer."""
    return EdgeOptimizer(
        redundant_threshold=0.01,
        shortcut_min_frequency=100
    )


@pytest.fixture
def mock_optimizer():
    """Create optimizer in mock mode."""
    return EdgeOptimizer(enable_mock_mode=True)


@pytest.fixture
def sample_telemetry_data():
    """Create sample telemetry data."""
    return [
        {"execution_path": ["node_a", "node_b", "node_c"]},
        {"execution_path": ["node_a", "node_b", "node_c"]},
        {"execution_path": ["node_a", "node_c"]},  # Skips node_b
        {"execution_path": ["node_a", "node_b", "node_c"]},
        {"execution_path": ["node_a", "node_b", "node_c"]},
    ]


@pytest.fixture
def sample_execution_patterns():
    """Create sample execution patterns."""
    return {
        "exec_1": ["input", "transform1", "transform2", "validate", "output"],
        "exec_2": ["input", "transform1", "transform2", "validate", "output"],
        "exec_3": ["input", "transform1", "transform2", "validate", "output"],
        "exec_4": ["input", "output"],  # Direct path
        "exec_5": ["input", "transform1", "transform2", "validate", "output"],
    }


@pytest.fixture
def sample_edge_spec():
    """Create sample edge spec."""
    return EdgeSpec(
        id="edge_1",
        from_id="node_a",
        to_id="node_b",
        condition="some_condition"
    )


@pytest.fixture
def mock_graph_introspector():
    """Create mock graph introspector."""
    class MockIntrospector:
        def get_node_ids(self):
            return ["node_a", "node_b", "node_c", "node_d"]

        def get_edges_from_node(self, node_id):
            edges = {
                "node_a": [
                    {"from_id": "node_a", "to_id": "node_b", "condition": "cond1"},
                    {"from_id": "node_a", "to_id": "node_c", "condition": "cond2"},
                ],
                "node_b": [
                    {"from_id": "node_b", "to_id": "node_c", "condition": None},
                ],
                "node_c": [
                    {"from_id": "node_c", "to_id": "node_d", "condition": None},
                ],
                "node_d": []
            }
            return edges.get(node_id, [])

        def get_node_complexity(self, node_id):
            complexity_map = {
                "node_a": {"complexity_score": 1},
                "node_b": {"complexity_score": 3},
                "node_c": {"complexity_score": 2},
            }
            return complexity_map.get(node_id, {"complexity_score": 2})

    return MockIntrospector()


# ============================================================================
# Test Initialization
# ============================================================================

def test_optimizer_initialization():
    """Test optimizer initialization."""
    optimizer = EdgeOptimizer(
        redundant_threshold=0.02,
        shortcut_min_frequency=200
    )
    assert optimizer.redundant_threshold == 0.02
    assert optimizer.shortcut_min_frequency == 200
    assert not optimizer.enable_mock_mode


def test_optimizer_mock_mode():
    """Test optimizer in mock mode."""
    optimizer = EdgeOptimizer(enable_mock_mode=True)
    assert optimizer.enable_mock_mode


# ============================================================================
# Test Finding Redundant Edges
# ============================================================================

@pytest.mark.asyncio
async def test_find_redundant_edges_mock_mode(
    mock_optimizer,
    mock_graph_introspector,
    sample_telemetry_data
):
    """Test finding redundant edges in mock mode."""
    redundant_edges = await mock_optimizer.find_redundant_edges(
        mock_graph_introspector,
        sample_telemetry_data
    )

    assert len(redundant_edges) > 0
    assert all(isinstance(e, RedundantEdge) for e in redundant_edges)

    for edge in redundant_edges:
        assert edge.from_node
        assert edge.to_node
        assert 0.0 <= edge.traversal_rate <= 1.0
        assert edge.total_executions > 0
        assert edge.recommendation


@pytest.mark.asyncio
async def test_find_redundant_edges_empty_telemetry(
    optimizer,
    mock_graph_introspector
):
    """Test finding redundant edges with no telemetry data."""
    redundant_edges = await optimizer.find_redundant_edges(
        mock_graph_introspector,
        []
    )

    assert len(redundant_edges) == 0


@pytest.mark.asyncio
async def test_find_redundant_edges_sorted_by_rate(
    mock_optimizer,
    mock_graph_introspector,
    sample_telemetry_data
):
    """Test that redundant edges are sorted by traversal rate."""
    redundant_edges = await mock_optimizer.find_redundant_edges(
        mock_graph_introspector,
        sample_telemetry_data
    )

    if len(redundant_edges) > 1:
        rates = [e.traversal_rate for e in redundant_edges]
        assert rates == sorted(rates)


def test_count_edge_traversals(optimizer, sample_telemetry_data):
    """Test counting edge traversals from telemetry."""
    counts = optimizer._count_edge_traversals(sample_telemetry_data)

    # node_a->node_b should have 4 traversals
    assert counts.get("node_a->node_b", 0) == 4

    # node_a->node_c should have 1 traversal (direct path)
    assert counts.get("node_a->node_c", 0) == 1

    # node_b->node_c should have 4 traversals
    assert counts.get("node_b->node_c", 0) == 4


def test_get_edge_id(optimizer):
    """Test getting edge ID."""
    edge = {"from_id": "node_a", "to_id": "node_b"}
    edge_id = optimizer._get_edge_id(edge)
    assert edge_id == "node_a->node_b"


def test_generate_redundant_edge_recommendation(optimizer):
    """Test generating recommendations for redundant edges."""
    edge = {"from_id": "node_a", "to_id": "node_b"}

    # Never traversed
    rec = optimizer._generate_redundant_edge_recommendation(edge, 0.0)
    assert "never" in rec.lower()

    # Rarely traversed
    rec = optimizer._generate_redundant_edge_recommendation(edge, 0.003)
    assert "rarely" in rec.lower()

    # Low traversal
    rec = optimizer._generate_redundant_edge_recommendation(edge, 0.008)
    assert "low" in rec.lower()


# ============================================================================
# Test Finding Shortcut Opportunities
# ============================================================================

@pytest.mark.asyncio
async def test_find_shortcut_opportunities_mock_mode(
    mock_optimizer,
    mock_graph_introspector,
    sample_execution_patterns
):
    """Test finding shortcut opportunities in mock mode."""
    shortcuts = await mock_optimizer.find_shortcut_opportunities(
        mock_graph_introspector,
        sample_execution_patterns
    )

    assert len(shortcuts) > 0
    assert all(isinstance(s, ShortcutOpportunity) for s in shortcuts)

    for shortcut in shortcuts:
        assert shortcut.from_node
        assert shortcut.to_node
        assert len(shortcut.skipped_nodes) > 0
        assert shortcut.frequency >= 0
        assert shortcut.potential_latency_savings >= 0.0
        assert 0.0 <= shortcut.confidence <= 1.0


def test_count_pattern_frequencies(optimizer, sample_execution_patterns):
    """Test counting pattern frequencies."""
    frequencies = optimizer._count_pattern_frequencies(sample_execution_patterns)

    # Pattern "input->transform1->transform2" appears 4 times
    pattern = "input->transform1->transform2"
    assert frequencies.get(pattern, 0) == 4

    # Full path appears 4 times
    full_path = "input->transform1->transform2->validate->output"
    assert frequencies.get(full_path, 0) == 4


def test_shortcut_exists(optimizer, mock_graph_introspector):
    """Test checking if shortcut already exists."""
    # Edge from node_a to node_b exists
    exists = optimizer._shortcut_exists(
        mock_graph_introspector,
        "node_a",
        "node_b"
    )
    assert exists

    # Edge from node_a to node_d doesn't exist directly
    exists = optimizer._shortcut_exists(
        mock_graph_introspector,
        "node_a",
        "node_d"
    )
    assert not exists


def test_estimate_latency_savings(optimizer, mock_graph_introspector):
    """Test estimating latency savings."""
    skipped_nodes = ["node_b", "node_c"]
    savings = optimizer._estimate_latency_savings(
        skipped_nodes,
        mock_graph_introspector
    )

    # Should have positive savings
    assert savings > 0.0

    # node_b has complexity 3, node_c has complexity 2
    # Expected: (3 * 0.1) + (2 * 0.1) = 0.5
    assert savings >= 0.4  # Allow some tolerance


def test_suggest_shortcut_condition(optimizer):
    """Test suggesting shortcut condition."""
    condition = optimizer._suggest_shortcut_condition(
        "input",
        "output",
        "input->transform->output"
    )

    assert isinstance(condition, str)
    assert len(condition) > 0


def test_calculate_shortcut_confidence(optimizer):
    """Test calculating shortcut confidence."""
    # High frequency, many skipped nodes, high savings
    confidence = optimizer._calculate_shortcut_confidence(
        frequency=1500,
        num_skipped=6,
        latency_savings=2.5
    )
    assert confidence >= 0.8

    # Low frequency, few nodes, low savings
    confidence = optimizer._calculate_shortcut_confidence(
        frequency=50,
        num_skipped=1,
        latency_savings=0.2
    )
    assert confidence < 0.3


# ============================================================================
# Test Edge Condition Optimization
# ============================================================================

@pytest.mark.asyncio
async def test_optimize_edge_condition_mock_mode(
    mock_optimizer,
    sample_edge_spec
):
    """Test optimizing edge condition in mock mode."""
    traversal_stats = {
        "traversal_rate": 0.75,
        "avg_evaluation_time": 0.005
    }

    optimized = await mock_optimizer.optimize_edge_condition(
        sample_edge_spec,
        traversal_stats
    )

    assert isinstance(optimized, OptimizedCondition)
    assert optimized.original_condition
    assert optimized.optimized_condition
    assert optimized.improvement_type in ["simplify", "strengthen", "weaken"]
    assert optimized.expected_benefit
    assert optimized.rationale


@pytest.mark.asyncio
async def test_optimize_edge_condition_no_condition(optimizer):
    """Test optimizing edge with no condition returns None."""
    edge = EdgeSpec(
        id="edge_1",
        from_id="node_a",
        to_id="node_b",
        condition=None
    )

    optimized = await optimizer.optimize_edge_condition(edge, {})
    assert optimized is None


@pytest.mark.asyncio
async def test_optimize_edge_condition_always_true(optimizer):
    """Test optimizing condition that's almost always true."""
    edge = EdgeSpec(
        id="edge_1",
        from_id="node_a",
        to_id="node_b",
        condition="some_condition"
    )

    traversal_stats = {
        "traversal_rate": 0.98,  # Almost always true
        "avg_evaluation_time": 0.002
    }

    optimized = await optimizer.optimize_edge_condition(edge, traversal_stats)

    assert optimized is not None
    assert optimized.improvement_type == "simplify"


@pytest.mark.asyncio
async def test_optimize_edge_condition_rarely_true(optimizer):
    """Test optimizing condition that's rarely true."""
    edge = EdgeSpec(
        id="edge_1",
        from_id="node_a",
        to_id="node_b",
        condition="rare_condition"
    )

    traversal_stats = {
        "traversal_rate": 0.02,  # Rarely true
        "avg_evaluation_time": 0.002
    }

    optimized = await optimizer.optimize_edge_condition(edge, traversal_stats)

    assert optimized is not None
    assert optimized.improvement_type == "strengthen"


@pytest.mark.asyncio
async def test_optimize_edge_condition_slow_evaluation(optimizer):
    """Test optimizing condition with slow evaluation."""
    edge = EdgeSpec(
        id="edge_1",
        from_id="node_a",
        to_id="node_b",
        condition="complex_condition"
    )

    traversal_stats = {
        "traversal_rate": 0.50,
        "avg_evaluation_time": 0.015  # Slow evaluation
    }

    optimized = await optimizer.optimize_edge_condition(edge, traversal_stats)

    assert optimized is not None
    assert optimized.improvement_type == "simplify"


def test_create_simplified_condition(optimizer):
    """Test creating simplified condition."""
    optimized = optimizer._create_simplified_condition(
        "complex && (a || b) && (c || d)",
        0.95,
        focus="logic"
    )

    assert optimized.improvement_type == "simplify"
    assert "0.95" in optimized.rationale or "95" in optimized.rationale


def test_create_strengthened_condition(optimizer):
    """Test creating strengthened condition."""
    optimized = optimizer._create_strengthened_condition(
        "basic_condition",
        0.03
    )

    assert optimized.improvement_type == "strengthen"
    assert "rarely" in optimized.rationale.lower()


# ============================================================================
# Test Mock Mode
# ============================================================================

def test_generate_mock_redundant_edges(mock_optimizer):
    """Test generating mock redundant edges."""
    edges = mock_optimizer._generate_mock_redundant_edges()

    assert len(edges) > 0
    for edge in edges:
        assert edge.from_node
        assert edge.to_node
        assert edge.recommendation


def test_generate_mock_shortcut_opportunities(mock_optimizer):
    """Test generating mock shortcut opportunities."""
    shortcuts = mock_optimizer._generate_mock_shortcut_opportunities()

    assert len(shortcuts) > 0
    for shortcut in shortcuts:
        assert shortcut.from_node
        assert shortcut.to_node
        assert len(shortcut.skipped_nodes) > 0
        assert shortcut.confidence > 0.0


def test_generate_mock_optimized_condition(mock_optimizer, sample_edge_spec):
    """Test generating mock optimized condition."""
    optimized = mock_optimizer._generate_mock_optimized_condition(sample_edge_spec)

    assert optimized.original_condition
    assert optimized.optimized_condition
    assert optimized.improvement_type
    assert "mock" in optimized.rationale.lower()
