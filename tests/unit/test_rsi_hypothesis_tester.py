"""Tests for HypothesisTesterNode."""

import pytest
import pytest_asyncio
from spark.rsi.hypothesis_tester import HypothesisTesterNode
from spark.rsi.types import (
    ImprovementHypothesis,
    HypothesisType,
    RiskLevel,
    ExpectedImprovement,
    ChangeSpec,
    TestStatus,
    TestMetrics,
)
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.nodes import Node
from spark.graphs import Graph


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def basic_hypothesis():
    """Create a basic hypothesis for testing."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_test_001",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="TestNode",
        rationale="Improve performance",
        expected_improvement=ExpectedImprovement(
            success_rate_delta=0.05,
            latency_delta=-0.1
        ),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="test_node",
                config_path="prompt_template",
                old_value="old",
                new_value="new"
            )
        ],
        risk_level=RiskLevel.LOW
    )


@pytest_asyncio.fixture
async def simple_graph():
    """Create a simple graph for testing."""
    class TestNode(Node):
        async def process(self, context):
            return {"result": "success"}

    node = TestNode(name="TestNode")
    return Graph(start=node)


# ============================================================================
# Initialization Tests
# ============================================================================

def test_init_default():
    """Test initialization with default configuration."""
    tester = HypothesisTesterNode()

    assert tester.name == "HypothesisTester"
    assert tester.num_baseline_runs == 20
    assert tester.num_candidate_runs == 20
    assert tester.confidence_level == 0.95
    assert tester.enable_mock_mode is False
    assert 'min_success_rate_improvement' in tester.success_criteria


def test_init_custom():
    """Test initialization with custom configuration."""
    criteria = {
        'min_success_rate_improvement': 0.1,
        'max_latency_increase': 0.15
    }

    tester = HypothesisTesterNode(
        name="CustomTester",
        num_baseline_runs=10,
        num_candidate_runs=15,
        success_criteria=criteria,
        confidence_level=0.99,
        enable_mock_mode=True
    )

    assert tester.name == "CustomTester"
    assert tester.num_baseline_runs == 10
    assert tester.num_candidate_runs == 15
    assert tester.confidence_level == 0.99
    assert tester.enable_mock_mode is True
    assert tester.success_criteria['min_success_rate_improvement'] == 0.1


# ============================================================================
# Mock Testing Tests
# ============================================================================

@pytest.mark.asyncio
async def test_mock_test_basic(basic_hypothesis):
    """Test basic mock testing."""
    tester = HypothesisTesterNode(
        num_baseline_runs=20,
        num_candidate_runs=20,
        enable_mock_mode=True
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await tester.process(context)

    # Verify result structure
    assert 'test_result' in result
    assert 'status' in result
    assert 'passed' in result
    assert 'is_improvement' in result

    # Verify test result
    test_result = result['test_result']
    assert test_result is not None
    assert test_result.hypothesis_id == basic_hypothesis.hypothesis_id
    assert test_result.status in [TestStatus.PASSED, TestStatus.FAILED, TestStatus.INCONCLUSIVE]


@pytest.mark.asyncio
async def test_mock_test_creates_comparison(basic_hypothesis):
    """Test that mock testing creates comparison results."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await tester.process(context)

    test_result = result['test_result']
    assert test_result.comparison is not None

    comparison = test_result.comparison
    assert comparison.baseline_metrics is not None
    assert comparison.candidate_metrics is not None
    assert comparison.success_rate_delta is not None
    assert comparison.avg_duration_delta is not None


@pytest.mark.asyncio
async def test_mock_test_passed_status(basic_hypothesis):
    """Test that mock test can produce PASSED status."""
    tester = HypothesisTesterNode(
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.0,
            'max_latency_increase': 1.0
        }
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await tester.process(context)

    # Mock should show improvement (0.9 -> 0.95 success, 0.5 -> 0.4 latency)
    assert result['passed'] is True
    assert result['is_improvement'] is True
    assert result['test_result'].status == TestStatus.PASSED


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_missing_hypothesis():
    """Test error handling when hypothesis is missing."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    context = ExecutionContext(
        inputs=NodeMessage(content={})  # Missing hypothesis
    )

    result = await tester.process(context)

    assert result['passed'] is False
    assert 'error' in result
    assert result['test_result'] is None


@pytest.mark.asyncio
async def test_missing_graph_without_mock(basic_hypothesis):
    """Test error when graph missing and not in mock mode."""
    tester = HypothesisTesterNode(enable_mock_mode=False)

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await tester.process(context)

    assert result['passed'] is False
    assert 'error' in result


# ============================================================================
# Metrics Calculation Tests
# ============================================================================

def test_test_metrics_structure():
    """Test TestMetrics structure."""
    metrics = TestMetrics(
        num_runs=20,
        success_count=18,
        failure_count=2,
        success_rate=0.9,
        avg_duration=0.5,
        p50_duration=0.48,
        p95_duration=0.65,
        p99_duration=0.70
    )

    assert metrics.num_runs == 20
    assert metrics.success_count == 18
    assert metrics.failure_count == 2
    assert metrics.success_rate == 0.9
    assert metrics.avg_duration == 0.5


def test_compare_metrics_improvement():
    """Test comparison when candidate is better."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20,
        success_count=18,
        failure_count=2,
        success_rate=0.9,
        avg_duration=0.5,
        p50_duration=0.48,
        p95_duration=0.65,
        p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=20,
        success_count=19,
        failure_count=1,
        success_rate=0.95,
        avg_duration=0.4,
        p50_duration=0.38,
        p95_duration=0.52,
        p99_duration=0.58
    )

    comparison = tester._compare_metrics(baseline, candidate)

    # Verify deltas (use approx for floating point)
    assert comparison.success_rate_delta == pytest.approx(0.05, abs=1e-6)  # 0.95 - 0.9
    assert comparison.avg_duration_delta == pytest.approx(-0.1, abs=1e-6)  # 0.4 - 0.5

    # Verify verdicts
    assert comparison.is_improvement is True
    assert comparison.is_regression is False


def test_compare_metrics_regression():
    """Test comparison when candidate is worse."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20,
        success_count=19,
        failure_count=1,
        success_rate=0.95,
        avg_duration=0.4,
        p50_duration=0.38,
        p95_duration=0.52,
        p99_duration=0.58
    )

    candidate = TestMetrics(
        num_runs=20,
        success_count=16,  # Worse
        failure_count=4,
        success_rate=0.8,  # Worse
        avg_duration=0.7,  # Worse
        p50_duration=0.65,
        p95_duration=0.85,
        p99_duration=0.95
    )

    comparison = tester._compare_metrics(baseline, candidate)

    # Verify deltas
    assert comparison.success_rate_delta < 0  # Decreased
    assert comparison.avg_duration_delta > 0  # Increased (worse)

    # Verify verdicts
    assert comparison.is_improvement is False
    assert comparison.is_regression is True


def test_compare_metrics_mixed_results():
    """Test comparison with mixed results."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20,
        success_count=18,
        failure_count=2,
        success_rate=0.9,
        avg_duration=0.5,
        p50_duration=0.48,
        p95_duration=0.65,
        p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=20,
        success_count=19,  # Better
        failure_count=1,
        success_rate=0.95,  # Better
        avg_duration=0.6,  # Worse (slower)
        p50_duration=0.58,
        p95_duration=0.72,
        p99_duration=0.80
    )

    comparison = tester._compare_metrics(baseline, candidate)

    # Success rate improved but latency got worse
    assert comparison.success_rate_delta > 0
    assert comparison.avg_duration_delta > 0

    # Not a pure improvement since latency increased
    assert comparison.is_improvement is False


# ============================================================================
# Statistical Significance Tests
# ============================================================================

def test_statistical_significance_with_enough_samples():
    """Test significance check with sufficient samples."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20,  # Enough samples
        success_count=18,
        failure_count=2,
        success_rate=0.9,
        avg_duration=0.5,
        p50_duration=0.48,
        p95_duration=0.65,
        p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=20,
        success_count=19,
        failure_count=1,
        success_rate=0.95,  # 5% improvement - significant
        avg_duration=0.4,  # 20% improvement - significant
        p50_duration=0.38,
        p95_duration=0.52,
        p99_duration=0.58
    )

    is_significant = tester._check_statistical_significance(baseline, candidate)

    # Should be significant due to large improvement
    assert is_significant is True


def test_statistical_significance_insufficient_samples():
    """Test significance check with insufficient samples."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=5,  # Too few samples
        success_count=4,
        failure_count=1,
        success_rate=0.8,
        avg_duration=0.5,
        p50_duration=0.48,
        p95_duration=0.65,
        p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=5,
        success_count=5,
        failure_count=0,
        success_rate=1.0,
        avg_duration=0.3,
        p50_duration=0.28,
        p95_duration=0.42,
        p99_duration=0.48
    )

    is_significant = tester._check_statistical_significance(baseline, candidate)

    # Should not be significant due to small sample size
    assert is_significant is False


# ============================================================================
# Success Criteria Tests
# ============================================================================

def test_success_criteria_met():
    """Test success criteria checking when criteria are met."""
    tester = HypothesisTesterNode(
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.03,
            'max_latency_increase': 0.2
        }
    )

    # 5% success rate improvement, 20% latency improvement
    meets_criteria = tester._check_success_criteria(
        success_rate_delta=0.05,
        avg_duration_pct_change=-0.20,
        is_significant=True
    )

    assert meets_criteria is True


def test_success_criteria_not_met_insufficient_improvement():
    """Test when improvement is insufficient."""
    tester = HypothesisTesterNode(
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.10,  # Require 10%
            'max_latency_increase': 0.2
        }
    )

    # Only 2% improvement - insufficient
    meets_criteria = tester._check_success_criteria(
        success_rate_delta=0.02,
        avg_duration_pct_change=0.0,
        is_significant=True
    )

    assert meets_criteria is False


def test_success_criteria_not_met_latency_increase():
    """Test when latency increases too much."""
    tester = HypothesisTesterNode(
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.0,
            'max_latency_increase': 0.1  # Max 10% increase
        }
    )

    # 30% latency increase - too much
    meets_criteria = tester._check_success_criteria(
        success_rate_delta=0.05,
        avg_duration_pct_change=0.30,
        is_significant=True
    )

    assert meets_criteria is False


def test_success_criteria_not_met_not_significant():
    """Test when results are not statistically significant."""
    tester = HypothesisTesterNode(
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.0,
            'max_latency_increase': 0.2
        }
    )

    # Good improvement but not significant
    meets_criteria = tester._check_success_criteria(
        success_rate_delta=0.10,
        avg_duration_pct_change=-0.20,
        is_significant=False  # Not significant
    )

    assert meets_criteria is False


# ============================================================================
# Test Status Determination Tests
# ============================================================================

def test_determine_status_passed():
    """Test status determination for passed test."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20, success_count=18, failure_count=2,
        success_rate=0.9, avg_duration=0.5,
        p50_duration=0.48, p95_duration=0.65, p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=20, success_count=19, failure_count=1,
        success_rate=0.95, avg_duration=0.4,
        p50_duration=0.38, p95_duration=0.52, p99_duration=0.58
    )

    comparison = tester._compare_metrics(baseline, candidate)
    status = tester._determine_test_status(comparison)

    # Should pass - shows improvement and meets criteria
    assert status == TestStatus.PASSED


def test_determine_status_failed_regression():
    """Test status determination for failed test (regression)."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20, success_count=19, failure_count=1,
        success_rate=0.95, avg_duration=0.4,
        p50_duration=0.38, p95_duration=0.52, p99_duration=0.58
    )

    candidate = TestMetrics(
        num_runs=20, success_count=15, failure_count=5,  # Much worse
        success_rate=0.75, avg_duration=0.8,
        p50_duration=0.75, p95_duration=1.2, p99_duration=1.5
    )

    comparison = tester._compare_metrics(baseline, candidate)
    status = tester._determine_test_status(comparison)

    # Should fail - shows regression
    assert status == TestStatus.FAILED


def test_determine_status_inconclusive():
    """Test status determination for inconclusive test."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    # Very small sample sizes - not significant
    baseline = TestMetrics(
        num_runs=3, success_count=3, failure_count=0,
        success_rate=1.0, avg_duration=0.5,
        p50_duration=0.5, p95_duration=0.5, p99_duration=0.5
    )

    candidate = TestMetrics(
        num_runs=3, success_count=3, failure_count=0,
        success_rate=1.0, avg_duration=0.45,
        p50_duration=0.45, p95_duration=0.45, p99_duration=0.45
    )

    comparison = tester._compare_metrics(baseline, candidate)
    status = tester._determine_test_status(comparison)

    # Should be inconclusive - not enough data
    assert status == TestStatus.INCONCLUSIVE


# ============================================================================
# Recommendations Tests
# ============================================================================

def test_recommendations_for_passed_test():
    """Test recommendations for passed test."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20, success_count=18, failure_count=2,
        success_rate=0.9, avg_duration=0.5,
        p50_duration=0.48, p95_duration=0.65, p99_duration=0.70
    )

    candidate = TestMetrics(
        num_runs=20, success_count=19, failure_count=1,
        success_rate=0.95, avg_duration=0.4,
        p50_duration=0.38, p95_duration=0.52, p99_duration=0.58
    )

    comparison = tester._compare_metrics(baseline, candidate)
    recommendations = tester._generate_test_recommendations(comparison)

    assert len(recommendations) > 0

    # Should recommend deployment
    has_deployment_rec = any(
        "deploy" in rec.lower() for rec in recommendations
    )
    assert has_deployment_rec


def test_recommendations_for_regression():
    """Test recommendations for regression."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    baseline = TestMetrics(
        num_runs=20, success_count=19, failure_count=1,
        success_rate=0.95, avg_duration=0.4,
        p50_duration=0.38, p95_duration=0.52, p99_duration=0.58
    )

    candidate = TestMetrics(
        num_runs=20, success_count=15, failure_count=5,
        success_rate=0.75, avg_duration=0.8,
        p50_duration=0.75, p95_duration=1.2, p99_duration=1.5
    )

    comparison = tester._compare_metrics(baseline, candidate)
    recommendations = tester._generate_test_recommendations(comparison)

    assert len(recommendations) > 0

    # Should recommend NOT deploying
    has_no_deploy_rec = any(
        "do not deploy" in rec.lower() for rec in recommendations
    )
    assert has_no_deploy_rec


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_workflow_mock_mode(basic_hypothesis):
    """Test complete workflow in mock mode."""
    tester = HypothesisTesterNode(
        num_baseline_runs=20,
        num_candidate_runs=20,
        enable_mock_mode=True,
        success_criteria={
            'min_success_rate_improvement': 0.0,
            'max_latency_increase': 0.5
        }
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={'hypothesis': basic_hypothesis})
    )

    result = await tester.process(context)

    # Verify complete result
    assert result['test_result'] is not None
    assert result['status'] in ['passed', 'failed', 'inconclusive']
    assert isinstance(result['passed'], bool)
    assert isinstance(result['is_improvement'], bool)

    # Verify test result details
    test_result = result['test_result']
    assert test_result.hypothesis_id == basic_hypothesis.hypothesis_id
    assert test_result.test_id.startswith('test_')
    assert test_result.comparison is not None
    assert len(test_result.recommendations) > 0
    assert test_result.started_at is not None
    assert test_result.completed_at is not None


@pytest.mark.asyncio
async def test_comparison_summary_generation():
    """Test that comparison summary is generated correctly."""
    tester = HypothesisTesterNode(enable_mock_mode=True)

    summary = tester._generate_comparison_summary(
        success_rate_delta=0.05,
        avg_duration_delta=-0.1,
        is_improvement=True,
        is_regression=False
    )

    assert "improved" in summary.lower()
    assert len(summary) > 0
