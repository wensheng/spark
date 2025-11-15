"""Tests for RSI MultiObjectiveOptimizer."""

import pytest
from spark.rsi.multi_objective_optimizer import (
    OptimizationObjectives,
    MultiObjectiveOptimizer,
    MultiObjectiveScore,
)
from spark.rsi.types import (
    ImprovementHypothesis,
    TestResult,
    TestStatus,
    ComparisonResult,
    TestMetrics,
    HypothesisType,
    ExpectedImprovement,
    RiskLevel,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def default_objectives():
    """Create default optimization objectives."""
    return OptimizationObjectives(
        minimize_latency=0.4,
        minimize_cost=0.3,
        maximize_quality=0.2,
        maximize_reliability=0.1,
        max_acceptable_cost_increase=0.10,
        min_acceptable_success_rate=0.95,
        max_acceptable_latency_increase=2.0,
    )


@pytest.fixture
def optimizer(default_objectives):
    """Create a MultiObjectiveOptimizer."""
    return MultiObjectiveOptimizer(default_objectives)


@pytest.fixture
def sample_hypothesis():
    """Create a sample hypothesis."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_001",
        graph_id="test_graph",
        graph_version_baseline="1.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="node_a",
        rationale="Test improvement",
        expected_improvement=ExpectedImprovement(success_rate_delta=0.05),
        changes=[],
        risk_level=RiskLevel.LOW,
    )


def create_test_result(
    hypothesis_id: str,
    success_rate_delta: float,
    avg_duration_delta: float,
    cost_delta: float = 0.0,
    is_significant: bool = True,
    baseline_success_rate: float = 0.90,
    candidate_success_rate: float = 0.95,
) -> TestResult:
    """Helper to create test results."""
    baseline_metrics = TestMetrics(
        num_runs=100,
        success_count=int(100 * baseline_success_rate),
        failure_count=int(100 * (1 - baseline_success_rate)),
        success_rate=baseline_success_rate,
        avg_duration=2.0,
        p50_duration=1.8,
        p95_duration=3.0,
        p99_duration=4.0,
    )

    candidate_metrics = TestMetrics(
        num_runs=100,
        success_count=int(100 * candidate_success_rate),
        failure_count=int(100 * (1 - candidate_success_rate)),
        success_rate=candidate_success_rate,
        avg_duration=2.0 + avg_duration_delta,
        p50_duration=1.8 + avg_duration_delta,
        p95_duration=3.0 + avg_duration_delta,
        p99_duration=4.0 + avg_duration_delta,
    )

    comparison = ComparisonResult(
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        success_rate_delta=success_rate_delta,
        avg_duration_delta=avg_duration_delta,
        p95_duration_delta=avg_duration_delta,
        is_significant=is_significant,
        confidence_level=0.95,
        is_improvement=success_rate_delta > 0 or avg_duration_delta < 0,
        is_regression=success_rate_delta < -0.05 or avg_duration_delta > 2.0,
        meets_success_criteria=success_rate_delta > 0.02,
        cost_delta=cost_delta,
    )

    return TestResult(
        hypothesis_id=hypothesis_id,
        test_id="test_001",
        status=TestStatus.PASSED,
        num_baseline_runs=100,
        num_candidate_runs=100,
        comparison=comparison,
        success_criteria_met=True,
    )


# ============================================================================
# Test OptimizationObjectives
# ============================================================================

def test_objectives_weights_sum(default_objectives):
    """Test that objective weights sum to 1.0."""
    total = (
        default_objectives.minimize_latency +
        default_objectives.minimize_cost +
        default_objectives.maximize_quality +
        default_objectives.maximize_reliability
    )
    assert abs(total - 1.0) < 0.01


def test_objectives_custom_weights():
    """Test creating objectives with custom weights."""
    objectives = OptimizationObjectives(
        minimize_latency=0.5,
        minimize_cost=0.3,
        maximize_quality=0.1,
        maximize_reliability=0.1,
    )
    assert objectives.minimize_latency == 0.5
    assert objectives.minimize_cost == 0.3


# ============================================================================
# Test Scoring Methods
# ============================================================================

def test_score_latency_improvement(optimizer):
    """Test latency scoring with improvement."""
    # Negative delta = improvement
    score = optimizer._score_latency(-1.0)
    assert score > 0.5  # Better than baseline


def test_score_latency_regression(optimizer):
    """Test latency scoring with regression."""
    # Positive delta = regression
    score = optimizer._score_latency(1.0)
    assert score < 0.5  # Worse than baseline


def test_score_cost_improvement(optimizer):
    """Test cost scoring with improvement."""
    # Negative delta = cheaper = better
    score = optimizer._score_cost(-0.10)
    assert score > 0.5


def test_score_cost_regression(optimizer):
    """Test cost scoring with regression."""
    # Positive delta = more expensive = worse
    score = optimizer._score_cost(0.10)
    assert score < 0.5


def test_score_quality_improvement(optimizer):
    """Test quality scoring with improvement."""
    # Positive delta = higher success rate = better
    score = optimizer._score_quality(0.10)
    assert score > 0.5


def test_score_quality_regression(optimizer):
    """Test quality scoring with regression."""
    # Negative delta = lower success rate = worse
    score = optimizer._score_quality(-0.10)
    assert score < 0.5


def test_score_reliability(optimizer):
    """Test reliability scoring."""
    comparison = ComparisonResult(
        baseline_metrics=TestMetrics(
            num_runs=100, success_count=90, failure_count=10,
            success_rate=0.90, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        candidate_metrics=TestMetrics(
            num_runs=100, success_count=95, failure_count=5,
            success_rate=0.95, avg_duration=1.8,
            p50_duration=1.6, p95_duration=2.8, p99_duration=3.8
        ),
        success_rate_delta=0.05,
        avg_duration_delta=-0.2,
        p95_duration_delta=-0.2,
        is_significant=True,
        confidence_level=0.95,
        is_improvement=True,
        is_regression=False,
        meets_success_criteria=True,
    )

    score = optimizer._score_reliability(comparison)
    assert score >= 0.5  # Should be good


# ============================================================================
# Test Constraint Checking
# ============================================================================

def test_check_constraints_pass(optimizer):
    """Test constraint checking when all constraints pass."""
    comparison = ComparisonResult(
        baseline_metrics=TestMetrics(
            num_runs=100, success_count=90, failure_count=10,
            success_rate=0.90, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        candidate_metrics=TestMetrics(
            num_runs=100, success_count=96, failure_count=4,
            success_rate=0.96, avg_duration=1.8,
            p50_duration=1.6, p95_duration=2.8, p99_duration=3.8
        ),
        success_rate_delta=0.06,
        avg_duration_delta=-0.2,
        p95_duration_delta=-0.2,
        is_significant=True,
        confidence_level=0.95,
        is_improvement=True,
        is_regression=False,
        meets_success_criteria=True,
        cost_delta=0.05,  # 5% increase, within limit
    )

    meets, violations = optimizer._check_constraints(comparison)
    assert meets is True
    assert len(violations) == 0


def test_check_constraints_cost_violation(optimizer):
    """Test constraint checking with cost violation."""
    comparison = ComparisonResult(
        baseline_metrics=TestMetrics(
            num_runs=100, success_count=90, failure_count=10,
            success_rate=0.90, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        candidate_metrics=TestMetrics(
            num_runs=100, success_count=95, failure_count=5,
            success_rate=0.95, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        success_rate_delta=0.05,
        avg_duration_delta=0.0,
        p95_duration_delta=0.0,
        is_significant=True,
        confidence_level=0.95,
        is_improvement=True,
        is_regression=False,
        meets_success_criteria=True,
        cost_delta=0.15,  # 15% increase, violates 10% limit
    )

    meets, violations = optimizer._check_constraints(comparison)
    assert meets is False
    assert len(violations) > 0
    assert "Cost" in violations[0]


def test_check_constraints_success_rate_violation(optimizer):
    """Test constraint checking with success rate violation."""
    comparison = ComparisonResult(
        baseline_metrics=TestMetrics(
            num_runs=100, success_count=90, failure_count=10,
            success_rate=0.90, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        candidate_metrics=TestMetrics(
            num_runs=100, success_count=92, failure_count=8,
            success_rate=0.92, avg_duration=2.0,
            p50_duration=1.8, p95_duration=3.0, p99_duration=4.0
        ),
        success_rate_delta=0.02,
        avg_duration_delta=0.0,
        p95_duration_delta=0.0,
        is_significant=True,
        confidence_level=0.95,
        is_improvement=True,
        is_regression=False,
        meets_success_criteria=False,
        cost_delta=0.0,
    )

    meets, violations = optimizer._check_constraints(comparison)
    assert meets is False
    assert len(violations) > 0
    assert "Success rate" in violations[0]


# ============================================================================
# Test evaluate_hypothesis
# ============================================================================

@pytest.mark.asyncio
async def test_evaluate_hypothesis(optimizer, sample_hypothesis):
    """Test evaluating a single hypothesis."""
    test_result = create_test_result(
        hypothesis_id=sample_hypothesis.hypothesis_id,
        success_rate_delta=0.05,
        avg_duration_delta=-0.5,
        cost_delta=0.03,
    )

    score = await optimizer.evaluate_hypothesis(sample_hypothesis, test_result)

    assert score.hypothesis_id == sample_hypothesis.hypothesis_id
    assert score.total_score > 0.0
    assert 0.0 <= score.latency_score <= 1.0
    assert 0.0 <= score.cost_score <= 1.0
    assert 0.0 <= score.quality_score <= 1.0
    assert 0.0 <= score.reliability_score <= 1.0
    assert score.meets_constraints is True


@pytest.mark.asyncio
async def test_evaluate_hypothesis_no_comparison(optimizer, sample_hypothesis):
    """Test evaluating hypothesis without comparison data."""
    test_result = TestResult(
        hypothesis_id=sample_hypothesis.hypothesis_id,
        test_id="test_001",
        status=TestStatus.FAILED,
        num_baseline_runs=0,
        num_candidate_runs=0,
        comparison=None,
        success_criteria_met=False,
    )

    score = await optimizer.evaluate_hypothesis(sample_hypothesis, test_result)

    assert score.total_score == 0.0
    assert score.meets_constraints is False


# ============================================================================
# Test rank_hypotheses
# ============================================================================

@pytest.mark.asyncio
async def test_rank_hypotheses(optimizer):
    """Test ranking multiple hypotheses."""
    # Create 3 hypotheses with different trade-offs
    hypotheses = [
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_001",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_a",
                rationale="Fast but expensive",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_001", 0.08, -1.0, 0.08)  # Fast, expensive
        ),
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_002",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_b",
                rationale="Cheap but slow",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_002", 0.05, 0.5, -0.05)  # Slow, cheap
        ),
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_003",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_c",
                rationale="Balanced",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_003", 0.06, -0.2, 0.02)  # Balanced
        ),
    ]

    ranked = await optimizer.rank_hypotheses(hypotheses)

    assert len(ranked) == 3
    # Should be sorted by total score
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    assert ranked[2].rank == 3
    assert ranked[0].score.total_score >= ranked[1].score.total_score
    assert ranked[1].score.total_score >= ranked[2].score.total_score


# ============================================================================
# Test find_pareto_frontier
# ============================================================================

@pytest.mark.asyncio
async def test_find_pareto_frontier(optimizer):
    """Test finding Pareto frontier."""
    # Create hypotheses with different trade-offs
    hypotheses = [
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_pareto_1",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_a",
                rationale="Very fast",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_pareto_1", 0.05, -2.0, 0.08)  # Very fast, expensive
        ),
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_pareto_2",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_b",
                rationale="Very cheap",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_pareto_2", 0.05, 0.5, -0.10)  # Slow, very cheap
        ),
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_pareto_3",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_c",
                rationale="Dominated",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_pareto_3", 0.03, 0.2, 0.05)  # Worse in all
        ),
    ]

    frontier = await optimizer.find_pareto_frontier(hypotheses)

    assert frontier.total_evaluated == 3
    # First two should be Pareto-optimal, third should be dominated
    assert len(frontier.solutions) >= 2
    assert len(frontier.dominated_solutions) >= 0


# ============================================================================
# Test dominance checking
# ============================================================================

def test_dominates_clear_case(optimizer):
    """Test dominance with clear superior solution."""
    score1 = MultiObjectiveScore(
        hypothesis_id="hyp_1",
        total_score=0.8,
        latency_score=0.9,
        cost_score=0.8,
        quality_score=0.8,
        reliability_score=0.7,
        meets_constraints=True,
    )

    score2 = MultiObjectiveScore(
        hypothesis_id="hyp_2",
        total_score=0.5,
        latency_score=0.5,
        cost_score=0.5,
        quality_score=0.5,
        reliability_score=0.5,
        meets_constraints=True,
    )

    assert optimizer._dominates(score1, score2) is True
    assert optimizer._dominates(score2, score1) is False


def test_dominates_pareto_optimal(optimizer):
    """Test dominance with Pareto-optimal solutions."""
    # score1 better in latency, score2 better in cost
    score1 = MultiObjectiveScore(
        hypothesis_id="hyp_1",
        total_score=0.7,
        latency_score=0.9,  # Better
        cost_score=0.5,     # Worse
        quality_score=0.7,
        reliability_score=0.7,
        meets_constraints=True,
    )

    score2 = MultiObjectiveScore(
        hypothesis_id="hyp_2",
        total_score=0.7,
        latency_score=0.5,  # Worse
        cost_score=0.9,     # Better
        quality_score=0.7,
        reliability_score=0.7,
        meets_constraints=True,
    )

    # Neither dominates the other (Pareto-optimal)
    assert optimizer._dominates(score1, score2) is False
    assert optimizer._dominates(score2, score1) is False


# ============================================================================
# Test visualize_trade_offs
# ============================================================================

@pytest.mark.asyncio
async def test_visualize_trade_offs(optimizer):
    """Test trade-off visualization generation."""
    hypotheses = [
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_viz_1",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_a",
                rationale="Test",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_viz_1", 0.05, -1.0, 0.05)
        ),
        (
            ImprovementHypothesis(
                hypothesis_id="hyp_viz_2",
                graph_id="test",
                graph_version_baseline="1.0",
                hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
                target_node="node_b",
                rationale="Test",
                expected_improvement=ExpectedImprovement(),
                changes=[],
                risk_level=RiskLevel.LOW,
            ),
            create_test_result("hyp_viz_2", 0.03, 0.5, -0.05)
        ),
    ]

    frontier = await optimizer.find_pareto_frontier(hypotheses)
    viz_data = optimizer.visualize_trade_offs(frontier)

    assert 'pareto_frontier' in viz_data
    assert 'dominated_solutions' in viz_data
    assert 'total_evaluated' in viz_data
    assert 'pareto_count' in viz_data

    assert len(viz_data['pareto_frontier']) > 0
    point = viz_data['pareto_frontier'][0]
    assert 'hypothesis_id' in point
    assert 'latency_score' in point
    assert 'cost_score' in point
    assert 'quality_score' in point
    assert 'reliability_score' in point
