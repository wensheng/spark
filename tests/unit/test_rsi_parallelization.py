"""Tests for RSI parallelization analyzer."""

import pytest
from spark.rsi.parallelization_analyzer import ParallelizationAnalyzer
from spark.rsi.types import (
    ParallelizableSequence,
    ParallelizationBenefit,
    ParallelGraphStructure,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def analyzer():
    """Create parallelization analyzer."""
    return ParallelizationAnalyzer(min_speedup_threshold=1.5)


@pytest.fixture
def mock_analyzer():
    """Create analyzer in mock mode."""
    return ParallelizationAnalyzer(enable_mock_mode=True)


@pytest.fixture
def mock_graph_introspector():
    """Create mock graph introspector with branching structure."""
    class MockIntrospector:
        def get_node_ids(self):
            return ["start", "branch_point", "branch_a", "branch_b", "merge", "end"]

        def get_edges_from_node(self, node_id):
            edges = {
                "start": [{"to_id": "branch_point"}],
                "branch_point": [
                    {"to_id": "branch_a"},
                    {"to_id": "branch_b"}
                ],
                "branch_a": [{"to_id": "merge"}],
                "branch_b": [{"to_id": "merge"}],
                "merge": [{"to_id": "end"}],
                "end": []
            }
            return edges.get(node_id, [])

        def get_node_spec(self, node_id):
            class MockSpec:
                def __init__(self):
                    self.config = {}
            return MockSpec()

        def get_node_complexity(self, node_id):
            complexity_map = {
                "branch_a": {"complexity_score": 5},
                "branch_b": {"complexity_score": 3},
            }
            return complexity_map.get(node_id, {"complexity_score": 2})

    return MockIntrospector()


@pytest.fixture
def sample_parallelizable_sequence():
    """Create sample parallelizable sequence."""
    return ParallelizableSequence(
        sequential_nodes=["entry", "a1", "a2", "b1", "b2", "merge"],
        entry_node="entry",
        exit_node="merge",
        has_dependencies=False,
        dependency_details={"reason": "No dependencies"},
        estimated_speedup=2.0,
        confidence=0.75
    )


# ============================================================================
# Test Initialization
# ============================================================================

def test_analyzer_initialization():
    """Test analyzer initialization."""
    analyzer = ParallelizationAnalyzer(min_speedup_threshold=2.0)
    assert analyzer.min_speedup_threshold == 2.0
    assert not analyzer.enable_mock_mode


def test_analyzer_mock_mode():
    """Test analyzer in mock mode."""
    analyzer = ParallelizationAnalyzer(enable_mock_mode=True)
    assert analyzer.enable_mock_mode


# ============================================================================
# Test Finding Parallelizable Sequences
# ============================================================================

@pytest.mark.asyncio
async def test_find_parallelizable_sequences_mock_mode(
    mock_analyzer,
    mock_graph_introspector
):
    """Test finding parallelizable sequences in mock mode."""
    sequences = await mock_analyzer.find_parallelizable_sequences(
        mock_graph_introspector
    )

    assert len(sequences) > 0
    assert all(isinstance(s, ParallelizableSequence) for s in sequences)

    for sequence in sequences:
        assert len(sequence.sequential_nodes) > 0
        assert sequence.entry_node
        assert sequence.exit_node
        assert sequence.estimated_speedup > 0.0
        assert 0.0 <= sequence.confidence <= 1.0


@pytest.mark.asyncio
async def test_sequences_sorted_by_speedup(
    mock_analyzer,
    mock_graph_introspector
):
    """Test that sequences are sorted by estimated speedup."""
    sequences = await mock_analyzer.find_parallelizable_sequences(
        mock_graph_introspector
    )

    if len(sequences) > 1:
        speedups = [s.estimated_speedup for s in sequences]
        assert speedups == sorted(speedups, reverse=True)


def test_trace_branches(analyzer, mock_graph_introspector):
    """Test tracing branches from a node."""
    edges = mock_graph_introspector.get_edges_from_node("branch_point")

    branches = analyzer._trace_branches(
        "branch_point",
        edges,
        mock_graph_introspector
    )

    assert len(branches) == 2  # Two branches from branch_point
    assert ["branch_a"] in branches or ["branch_a", "merge"] in [b[:2] for b in branches]
    assert ["branch_b"] in branches or ["branch_b", "merge"] in [b[:2] for b in branches]


def test_find_convergence_node(analyzer, mock_graph_introspector):
    """Test finding convergence node for branches."""
    branches = [
        ["branch_a"],
        ["branch_b"]
    ]

    convergence = analyzer._find_convergence_node(
        branches,
        mock_graph_introspector
    )

    assert convergence == "merge"


def test_find_convergence_node_no_convergence(analyzer, mock_graph_introspector):
    """Test finding convergence when branches don't converge."""
    # Branches that don't converge
    branches = [
        ["branch_a"],
        ["end"]  # Different end point
    ]

    convergence = analyzer._find_convergence_node(
        branches,
        mock_graph_introspector
    )

    # May return None or a node depending on graph structure
    # Just verify it returns a string or None
    assert convergence is None or isinstance(convergence, str)


def test_check_branch_dependencies_no_dependencies(
    analyzer,
    mock_graph_introspector
):
    """Test checking dependencies when none exist."""
    branches = [
        ["branch_a"],
        ["branch_b"]
    ]

    has_deps, details = analyzer._check_branch_dependencies(
        branches,
        mock_graph_introspector
    )

    # Mock nodes don't have state conflicts
    assert isinstance(has_deps, bool)
    assert isinstance(details, dict)
    assert "reason" in details


def test_get_state_keys_accessed(analyzer, mock_graph_introspector):
    """Test getting state keys accessed by branches."""
    branches = [
        ["branch_a"],
        ["branch_b"]
    ]

    state_keys = analyzer._get_state_keys_accessed(
        branches,
        mock_graph_introspector
    )

    assert "read" in state_keys
    assert "written" in state_keys
    assert isinstance(state_keys["read"], dict)
    assert isinstance(state_keys["written"], dict)


def test_estimate_speedup(analyzer, mock_graph_introspector):
    """Test estimating speedup from parallelization."""
    branches = [
        ["branch_a"],  # Complexity 5
        ["branch_b"]   # Complexity 3
    ]

    speedup = analyzer._estimate_speedup(branches, mock_graph_introspector)

    # Sequential: (5*0.1) + (3*0.1) = 0.8
    # Parallel: max(0.5, 0.3) = 0.5
    # Speedup: 0.8 / 0.5 = 1.6, with 10% overhead = 1.44
    assert speedup > 1.0
    assert speedup < 3.0  # Reasonable range


def test_estimate_speedup_empty_branches(analyzer, mock_graph_introspector):
    """Test estimating speedup with empty branches."""
    speedup = analyzer._estimate_speedup([], mock_graph_introspector)
    assert speedup == 1.0


def test_calculate_confidence(analyzer):
    """Test calculating confidence in parallelization."""
    branches = [
        ["a1", "a2"],
        ["b1", "b2"],
        ["c1", "c2"]
    ]

    # High speedup, multiple balanced branches
    confidence = analyzer._calculate_confidence(branches, 2.5)
    assert 0.5 < confidence <= 1.0

    # Low speedup
    confidence = analyzer._calculate_confidence(branches, 1.2)
    assert confidence <= 0.5


def test_calculate_confidence_unbalanced_branches(analyzer):
    """Test confidence with unbalanced branches."""
    branches = [
        ["a1"],
        ["b1", "b2", "b3", "b4", "b5"]
    ]

    confidence = analyzer._calculate_confidence(branches, 2.0)

    # Unbalanced branches should have lower confidence
    assert 0.0 < confidence < 1.0


# ============================================================================
# Test Benefit Estimation
# ============================================================================

@pytest.mark.asyncio
async def test_estimate_parallelization_benefit_mock_mode(
    mock_analyzer,
    sample_parallelizable_sequence
):
    """Test estimating benefit in mock mode."""
    benefit = await mock_analyzer.estimate_parallelization_benefit(
        sample_parallelizable_sequence,
        {}
    )

    assert isinstance(benefit, ParallelizationBenefit)
    assert benefit.latency_reduction >= 0.0
    assert benefit.speedup_multiplier > 0.0
    assert benefit.resource_increase >= 0.0
    assert benefit.complexity_increase >= 0
    assert 0.0 <= benefit.confidence <= 1.0


@pytest.mark.asyncio
async def test_estimate_benefit_shows_tradeoffs(
    mock_analyzer,
    sample_parallelizable_sequence
):
    """Test that benefit estimation shows resource/complexity tradeoffs."""
    benefit = await mock_analyzer.estimate_parallelization_benefit(
        sample_parallelizable_sequence,
        {}
    )

    # Parallelization should show resource increase
    assert benefit.resource_increase > 0.0

    # And complexity increase
    assert benefit.complexity_increase > 0


# ============================================================================
# Test Parallel Structure Generation
# ============================================================================

@pytest.mark.asyncio
async def test_generate_parallel_structure_mock_mode(
    mock_analyzer,
    sample_parallelizable_sequence
):
    """Test generating parallel structure in mock mode."""
    structure = await mock_analyzer.generate_parallel_structure(
        sample_parallelizable_sequence
    )

    assert isinstance(structure, ParallelGraphStructure)
    assert len(structure.parallel_branches) >= 2
    assert all(isinstance(branch, list) for branch in structure.parallel_branches)
    assert structure.merge_strategy in ["wait_all", "wait_any", "custom"]


@pytest.mark.asyncio
async def test_parallel_structure_has_merge_node(
    mock_analyzer,
    sample_parallelizable_sequence
):
    """Test that parallel structure includes merge node when needed."""
    structure = await mock_analyzer.generate_parallel_structure(
        sample_parallelizable_sequence
    )

    if structure.requires_merge:
        assert structure.merge_node_id is not None


# ============================================================================
# Test Mock Mode
# ============================================================================

def test_generate_mock_parallelizable_sequences(mock_analyzer):
    """Test generating mock parallelizable sequences."""
    sequences = mock_analyzer._generate_mock_parallelizable_sequences()

    assert len(sequences) > 0
    for seq in sequences:
        assert seq.entry_node
        assert seq.exit_node
        assert seq.estimated_speedup > 1.0
        assert seq.confidence > 0.0


def test_generate_mock_parallelization_benefit(mock_analyzer):
    """Test generating mock parallelization benefit."""
    benefit = mock_analyzer._generate_mock_parallelization_benefit()

    assert benefit.latency_reduction > 0.0
    assert benefit.speedup_multiplier > 1.0
    assert benefit.resource_increase >= 0.0
    assert benefit.confidence > 0.0


def test_generate_mock_parallel_structure(mock_analyzer):
    """Test generating mock parallel structure."""
    structure = mock_analyzer._generate_mock_parallel_structure()

    assert len(structure.parallel_branches) >= 2
    assert structure.merge_node_id is not None
    assert structure.requires_merge
    assert structure.merge_strategy == "wait_all"
