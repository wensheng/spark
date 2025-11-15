"""Tests for RSIMetaGraph."""

import pytest
import pytest_asyncio
from spark.rsi.rsi_meta_graph import (
    RSIMetaGraph,
    RSIMetaGraphConfig,
    AnalysisGateNode,
    ValidationGateNode,
    TestGateNode
)
from spark.rsi.experience_db import ExperienceDatabase
from spark.rsi.types import (
    DiagnosticReport,
    PerformanceSummary,
    Bottleneck,
    AnalysisPeriod,
    ImprovementHypothesis,
    HypothesisType,
    RiskLevel,
    ExpectedImprovement,
    ChangeSpec,
    TestResult,
    TestStatus,
    TestMetrics,
    ComparisonResult
)
from spark.nodes import Node
from spark.graphs import Graph
from spark.nodes.types import NodeMessage, ExecutionContext


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def experience_db():
    """Create experience database."""
    db = ExperienceDatabase()
    await db.initialize()
    return db


@pytest_asyncio.fixture
async def sample_graph():
    """Create a sample graph to improve."""
    class TestNode(Node):
        async def process(self, context):
            return {'result': 'ok'}

    node = TestNode(name="TestNode")
    return Graph(start=node)


@pytest_asyncio.fixture
def basic_config():
    """Create basic RSI config."""
    return RSIMetaGraphConfig(
        graph_id="test_graph",
        graph_version="1.0.0",
        max_hypotheses=2,
        hypothesis_types=["prompt_optimization"],
        enable_mock_mode=True,  # Use mock mode for testing
        auto_deploy=False  # Don't auto-deploy in tests
    )


@pytest_asyncio.fixture
async def sample_report():
    """Create sample diagnostic report."""
    return DiagnosticReport(
        graph_id="test_graph",
        graph_version="1.0.0",
        analysis_period=AnalysisPeriod(
            start="2025-01-01T00:00:00",
            end="2025-01-01T01:00:00"
        ),
        summary=PerformanceSummary(
            total_executions=100,
            success_rate=0.85,
            avg_duration=0.5,
            p50_duration=0.4,
            p95_duration=0.8,
            p99_duration=1.0,
            total_cost=10.0
        ),
        bottlenecks=[
            Bottleneck(
                node_id="slow_node",
                node_name="SlowNode",
                issue="high_latency",
                severity="high",
                impact_score=0.8,
                metrics={"avg_duration": 0.8}
            )
        ],
        failures=[],
        opportunities=["Optimize SlowNode"]
    )


@pytest_asyncio.fixture
def sample_hypothesis():
    """Create sample hypothesis."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_test",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="SlowNode",
        rationale="Test hypothesis",
        expected_improvement=ExpectedImprovement(
            success_rate_delta=0.05,
            latency_delta=-0.1,
            cost_delta=0.0
        ),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="slow_node",
                config_path="prompt",
                old_value="old",
                new_value="new"
            )
        ],
        risk_level=RiskLevel.LOW,
        risk_factors=[]
    )


# ============================================================================
# Initialization Tests
# ============================================================================

def test_rsi_meta_graph_init(basic_config, experience_db):
    """Test RSIMetaGraph initialization."""
    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db
    )

    assert rsi.config == basic_config
    assert rsi.experience_db == experience_db
    assert rsi.graph is not None


def test_rsi_meta_graph_with_model(basic_config, experience_db):
    """Test RSIMetaGraph initialization with model."""
    # Mock model
    class MockModel:
        pass

    model = MockModel()

    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db,
        model=model
    )

    assert rsi.model == model


def test_rsi_meta_graph_config_defaults():
    """Test RSIMetaGraphConfig defaults."""
    config = RSIMetaGraphConfig(graph_id="test")

    assert config.graph_id == "test"
    assert config.graph_version == "1.0.0"
    assert config.analysis_window_hours == 24
    assert config.max_hypotheses == 3
    assert config.hypothesis_types == ["prompt_optimization"]
    assert config.enable_pattern_learning is True
    assert config.deployment_strategy == "direct"
    assert config.auto_deploy is True
    assert config.enable_mock_mode is False


# ============================================================================
# Gate Node Tests
# ============================================================================

@pytest.mark.asyncio
async def test_analysis_gate_with_issues(sample_report):
    """Test AnalysisGateNode when issues are found."""
    gate = AnalysisGateNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'has_issues': True,
            'report': sample_report
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is True
    assert result['report'] == sample_report


@pytest.mark.asyncio
async def test_analysis_gate_without_issues():
    """Test AnalysisGateNode when no issues found."""
    gate = AnalysisGateNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'has_issues': False
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is False
    assert 'reason' in result


@pytest.mark.asyncio
async def test_validation_gate_with_approved(sample_hypothesis):
    """Test ValidationGateNode with approved hypotheses."""
    gate = ValidationGateNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypotheses': [sample_hypothesis],
            'validation_results': [
                {'approved': True, 'risk_level': 'LOW'}
            ]
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is True
    assert len(result['approved_hypotheses']) == 1
    assert result['approved_hypotheses'][0] == sample_hypothesis


@pytest.mark.asyncio
async def test_validation_gate_without_approved(sample_hypothesis):
    """Test ValidationGateNode with no approved hypotheses."""
    gate = ValidationGateNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypotheses': [sample_hypothesis],
            'validation_results': [
                {'approved': False, 'risk_level': 'HIGH'}
            ]
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is False
    assert 'reason' in result


@pytest.mark.asyncio
async def test_test_gate_with_passed(sample_hypothesis):
    """Test TestGateNode with passed tests."""
    gate = TestGateNode()

    baseline_metrics = TestMetrics(
        num_runs=20,
        success_count=17,
        failure_count=3,
        success_rate=0.85,
        avg_duration=0.5,
        p50_duration=0.4,
        p95_duration=0.7,
        p99_duration=0.8
    )
    candidate_metrics = TestMetrics(
        num_runs=20,
        success_count=19,
        failure_count=1,
        success_rate=0.95,
        avg_duration=0.4,
        p50_duration=0.3,
        p95_duration=0.6,
        p99_duration=0.7
    )

    test_result = TestResult(
        hypothesis_id="hyp_test",
        test_id="test_1",
        status=TestStatus.PASSED,
        num_baseline_runs=20,
        num_candidate_runs=20,
        comparison=ComparisonResult(
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            success_rate_delta=0.10,
            avg_duration_delta=-0.1,
            p95_duration_delta=-0.1,
            is_significant=True,
            confidence_level=0.95,
            is_improvement=True,
            is_regression=False,
            meets_success_criteria=True,
            cost_delta=0.0
        ),
        success_criteria_met=True
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'test_results': [
                {
                    'hypothesis': sample_hypothesis,
                    'test_result': test_result
                }
            ]
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is True
    assert len(result['passed_tests']) == 1


@pytest.mark.asyncio
async def test_test_gate_without_passed(sample_hypothesis):
    """Test TestGateNode with no passed tests."""
    gate = TestGateNode()

    baseline_metrics = TestMetrics(
        num_runs=20,
        success_count=17,
        failure_count=3,
        success_rate=0.85,
        avg_duration=0.5,
        p50_duration=0.4,
        p95_duration=0.7,
        p99_duration=0.8
    )
    candidate_metrics = TestMetrics(
        num_runs=20,
        success_count=10,
        failure_count=10,
        success_rate=0.50,
        avg_duration=0.6,
        p50_duration=0.5,
        p95_duration=0.9,
        p99_duration=1.0
    )

    test_result = TestResult(
        hypothesis_id="hyp_test",
        test_id="test_2",
        status=TestStatus.FAILED,
        num_baseline_runs=20,
        num_candidate_runs=20,
        comparison=ComparisonResult(
            baseline_metrics=baseline_metrics,
            candidate_metrics=candidate_metrics,
            success_rate_delta=-0.35,
            avg_duration_delta=0.1,
            p95_duration_delta=0.2,
            is_significant=True,
            confidence_level=0.95,
            is_improvement=False,
            is_regression=True,
            meets_success_criteria=False,
            cost_delta=0.0
        ),
        success_criteria_met=False
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'test_results': [
                {
                    'hypothesis': sample_hypothesis,
                    'test_result': test_result
                }
            ]
        })
    )

    result = await gate.process(context)

    assert result['should_continue'] is False
    assert 'reason' in result


# ============================================================================
# RSI Loop Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rsi_run_with_target_graph(basic_config, experience_db, sample_graph):
    """Test running RSI loop with target graph."""
    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db
    )

    # Note: This will run the full workflow in mock mode
    # It may not complete the full loop if gates stop it
    result = await rsi.run(target_graph=sample_graph)

    assert 'success' in result
    assert result['graph_id'] == basic_config.graph_id


@pytest.mark.asyncio
async def test_rsi_run_without_target_graph(basic_config, experience_db):
    """Test running RSI loop without target graph."""
    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db
    )

    result = await rsi.run()

    assert 'success' in result
    assert result['graph_id'] == basic_config.graph_id


@pytest.mark.asyncio
async def test_rsi_run_once_alias(basic_config, experience_db):
    """Test run_once alias."""
    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db
    )

    result = await rsi.run_once()

    assert 'success' in result
    assert result['graph_id'] == basic_config.graph_id


@pytest.mark.asyncio
async def test_rsi_run_continuous(basic_config, experience_db):
    """Test continuous RSI loop."""
    rsi = RSIMetaGraph(
        config=basic_config,
        experience_db=experience_db
    )

    # Run 2 iterations with short interval
    results = await rsi.run_continuous(
        interval_seconds=0.1,
        max_iterations=2
    )

    assert len(results) == 2
    for result in results:
        assert 'success' in result
        assert result['graph_id'] == basic_config.graph_id


@pytest.mark.asyncio
async def test_rsi_with_auto_deploy(experience_db, sample_graph):
    """Test RSI with auto-deploy enabled."""
    config = RSIMetaGraphConfig(
        graph_id="test_graph",
        enable_mock_mode=True,
        auto_deploy=True  # Enable auto-deploy
    )

    rsi = RSIMetaGraph(
        config=config,
        experience_db=experience_db
    )

    result = await rsi.run(target_graph=sample_graph)

    assert 'success' in result


@pytest.mark.asyncio
async def test_rsi_with_pattern_learning(experience_db, sample_graph):
    """Test RSI with pattern learning enabled."""
    # Add some experience to learn from
    for i in range(5):
        hyp_id = f"hyp_{i}"
        await experience_db.store_hypothesis(
            hypothesis_id=hyp_id,
            graph_id="test_graph",
            graph_version_baseline="1.0.0",
            hypothesis_type="prompt_optimization",
            proposal={'test': 'data'},
            target_node="node_a"
        )
        await experience_db.update_test_results(hyp_id, {
            'status': 'passed',
            'comparison': {
                'success_rate_delta': 0.05,
                'is_improvement': True
            }
        })
        await experience_db.update_deployment_outcome(
            hyp_id,
            deployed=True,
            outcome={'successful': True},
            lessons=[],
            patterns=[]
        )

    config = RSIMetaGraphConfig(
        graph_id="test_graph",
        enable_mock_mode=True,
        enable_pattern_learning=True
    )

    rsi = RSIMetaGraph(
        config=config,
        experience_db=experience_db
    )

    result = await rsi.run(target_graph=sample_graph)

    assert 'success' in result


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rsi_handles_errors_gracefully(basic_config, experience_db):
    """Test that RSI handles errors gracefully."""
    # Create RSI with invalid config
    config = RSIMetaGraphConfig(
        graph_id="",  # Invalid empty graph_id
        enable_mock_mode=True
    )

    rsi = RSIMetaGraph(
        config=config,
        experience_db=experience_db
    )

    result = await rsi.run()

    # Should not crash, may return error
    assert 'success' in result or 'error' in result
