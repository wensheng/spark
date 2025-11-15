"""Tests for DeploymentControllerNode."""

import pytest
import pytest_asyncio
from spark.rsi.deployment_controller import (
    DeploymentControllerNode,
    DeploymentConfig,
    DeploymentRecord
)
from spark.rsi.experience_db import ExperienceDatabase
from spark.rsi.types import (
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
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.nodes.spec import GraphSpec, NodeSpec

FAST_MONITOR_DURATION = 0.02
FAST_MONITOR_INTERVAL = 0.005


# ============================================================================
# Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def experience_db():
    """Create experience database."""
    return ExperienceDatabase()


@pytest.fixture
def basic_hypothesis():
    """Create a basic hypothesis."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_deploy_001",
        graph_id="test_graph",
        graph_version_baseline="1.0.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="node_a",
        rationale="Improve performance",
        expected_improvement=ExpectedImprovement(success_rate_delta=0.05),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="prompt",
                old_value="old",
                new_value="new"
            )
        ],
        risk_level=RiskLevel.LOW
    )


@pytest.fixture
def passed_test_result():
    """Create a test result that passed."""
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

    comparison = ComparisonResult(
        baseline_metrics=baseline,
        candidate_metrics=candidate,
        success_rate_delta=0.05,
        avg_duration_delta=-0.1,
        p95_duration_delta=-0.13,
        is_significant=True,
        confidence_level=0.95,
        is_improvement=True,
        is_regression=False,
        meets_success_criteria=True
    )

    return TestResult(
        hypothesis_id="hyp_deploy_001",
        test_id="test_001",
        status=TestStatus.PASSED,
        num_baseline_runs=20,
        num_candidate_runs=20,
        comparison=comparison,
        success_criteria_met=True
    )


@pytest.fixture
def failed_test_result():
    """Create a test result that failed."""
    return TestResult(
        hypothesis_id="hyp_deploy_001",
        test_id="test_002",
        status=TestStatus.FAILED,
        num_baseline_runs=20,
        num_candidate_runs=20,
        success_criteria_met=False
    )


@pytest.fixture
def basic_graph_spec():
    """Create a basic graph spec."""
    return GraphSpec(
        id="test_graph_v1",
        spark_version="2.0",
        start="node_a",
        nodes=[
            NodeSpec(id="node_a", type="Node", config={"prompt": "old"}),
            NodeSpec(id="node_b", type="Node")
        ],
        edges=[]
    )


# ============================================================================
# Initialization Tests
# ============================================================================

def test_deployment_controller_init_default():
    """Test default initialization."""
    controller = DeploymentControllerNode()
    assert controller.name == "DeploymentController"
    assert controller.enable_monitoring is True
    assert controller.enable_rollback is True
    assert controller.deployment_config.strategy == "direct"


def test_deployment_controller_init_custom():
    """Test custom initialization."""
    config = DeploymentConfig(
        strategy="canary",
        monitoring_duration_seconds=60.0,
        max_error_rate_increase=0.3
    )

    controller = DeploymentControllerNode(
        name="CustomController",
        deployment_config=config,
        enable_monitoring=False,
        enable_rollback=False
    )

    assert controller.name == "CustomController"
    assert controller.enable_monitoring is False
    assert controller.enable_rollback is False
    assert controller.deployment_config.strategy == "canary"
    assert controller.deployment_config.monitoring_duration_seconds == 60.0


# ============================================================================
# Deployment Tests
# ============================================================================

@pytest.mark.asyncio
async def test_deploy_successful(basic_hypothesis, passed_test_result, basic_graph_spec):
    """Test successful deployment."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        )
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result,
            'baseline_spec': basic_graph_spec
        })
    )

    result = await controller.process(context)

    assert result['success'] is True
    assert 'deployment_id' in result
    assert result['rolled_back'] is False
    assert result['deployed_version'] is not None


@pytest.mark.asyncio
async def test_deploy_without_baseline_spec(basic_hypothesis, passed_test_result):
    """Test deployment without baseline spec (still succeeds but skips change application)."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        )
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
            # No baseline_spec
        })
    )

    result = await controller.process(context)

    assert result['success'] is True
    assert result['modified_spec'] is None


@pytest.mark.asyncio
async def test_deploy_with_experience_db(basic_hypothesis, passed_test_result, experience_db):
    """Test deployment with experience database integration."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        ),
        experience_db=experience_db
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is True

    # Check that experience was recorded
    experiences = await experience_db.query_hypotheses()
    assert len(experiences) > 0
    assert experiences[0]['hypothesis_id'] == basic_hypothesis.hypothesis_id


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_deploy_missing_hypothesis(passed_test_result):
    """Test error when hypothesis is missing."""
    controller = DeploymentControllerNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is False
    assert 'hypothesis is required' in result['error']


@pytest.mark.asyncio
async def test_deploy_missing_test_result(basic_hypothesis):
    """Test error when test result is missing."""
    controller = DeploymentControllerNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis
        })
    )

    result = await controller.process(context)

    assert result['success'] is False
    assert 'test_result is required' in result['error']


@pytest.mark.asyncio
async def test_deploy_failed_test(basic_hypothesis, failed_test_result):
    """Test error when test did not pass."""
    controller = DeploymentControllerNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': failed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is False
    assert 'did not pass testing' in result['error']


# ============================================================================
# Monitoring Tests
# ============================================================================

@pytest.mark.asyncio
async def test_monitoring_no_rollback(basic_hypothesis, passed_test_result):
    """Test monitoring without triggering rollback."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        ),
        enable_monitoring=True,
        enable_rollback=True
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is True
    assert result['rolled_back'] is False

    # Check deployment record
    deployment_record = result['deployment_record']
    assert deployment_record.status == "completed"
    assert deployment_record.rollback_reason is None


@pytest.mark.asyncio
async def test_monitoring_disabled(basic_hypothesis, passed_test_result):
    """Test deployment with monitoring disabled."""
    controller = DeploymentControllerNode(
        enable_monitoring=False
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is True
    # Should complete quickly without monitoring


# ============================================================================
# Rollback Tests
# ============================================================================

def test_should_rollback_error_rate_increase():
    """Test rollback trigger due to error rate increase."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(max_error_rate_increase=0.5)
    )

    baseline_metrics = {
        'success_rate': 0.9,  # 10% error rate
        'avg_duration': 0.5
    }

    current_metrics = {
        'success_rate': 0.85,  # 15% error rate (50% increase)
        'avg_duration': 0.5
    }

    should_rollback, reason = controller._should_rollback(baseline_metrics, current_metrics)

    assert should_rollback is True
    assert 'Error rate increased' in reason


def test_should_rollback_latency_increase():
    """Test rollback trigger due to latency increase."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(max_latency_multiplier=2.0)
    )

    baseline_metrics = {
        'success_rate': 0.95,
        'avg_duration': 0.5
    }

    current_metrics = {
        'success_rate': 0.95,
        'avg_duration': 1.2  # More than 2x
    }

    should_rollback, reason = controller._should_rollback(baseline_metrics, current_metrics)

    assert should_rollback is True
    assert 'Latency increased' in reason


def test_should_rollback_success_rate_minimum():
    """Test rollback trigger due to success rate below minimum."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(min_success_rate=0.7)
    )

    baseline_metrics = {
        'success_rate': 0.95,
        'avg_duration': 0.5
    }

    current_metrics = {
        'success_rate': 0.65,  # Below minimum
        'avg_duration': 0.5
    }

    should_rollback, reason = controller._should_rollback(baseline_metrics, current_metrics)

    assert should_rollback is True
    assert 'below minimum' in reason


def test_should_rollback_no_trigger():
    """Test no rollback when metrics are acceptable."""
    controller = DeploymentControllerNode()

    baseline_metrics = {
        'success_rate': 0.9,
        'avg_duration': 0.5
    }

    current_metrics = {
        'success_rate': 0.92,  # Better
        'avg_duration': 0.48  # Better
    }

    should_rollback, reason = controller._should_rollback(baseline_metrics, current_metrics)

    assert should_rollback is False
    assert reason is None


# ============================================================================
# Deployment Strategy Tests
# ============================================================================

@pytest.mark.asyncio
async def test_deploy_direct_strategy(basic_hypothesis, passed_test_result):
    """Test direct deployment strategy."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            strategy="direct",
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        )
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    assert result['success'] is True
    assert result['deployment_record'].strategy == "direct"


@pytest.mark.asyncio
async def test_deploy_canary_strategy_simplified(basic_hypothesis, passed_test_result):
    """Test canary strategy (simplified to direct in Phase 4)."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            strategy="canary",
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        )
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    # Should succeed (simplified to direct)
    assert result['success'] is True


# ============================================================================
# Deployment Record Tests
# ============================================================================

@pytest.mark.asyncio
async def test_deployment_record_tracking(basic_hypothesis, passed_test_result):
    """Test that deployment records are tracked."""
    controller = DeploymentControllerNode(
        deployment_config=DeploymentConfig(
            monitoring_duration_seconds=FAST_MONITOR_DURATION,
            monitoring_interval_seconds=FAST_MONITOR_INTERVAL
        )
    )

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': basic_hypothesis,
            'test_result': passed_test_result
        })
    )

    result = await controller.process(context)

    deployment_id = result['deployment_id']

    # Retrieve record
    record = controller.get_deployment_record(deployment_id)
    assert record is not None
    assert record.hypothesis_id == basic_hypothesis.hypothesis_id
    assert record.status == "completed"

    # Check all deployments
    all_deployments = controller.get_all_deployments()
    assert len(all_deployments) == 1
    assert all_deployments[0].deployment_id == deployment_id


def test_deployment_record_structure():
    """Test DeploymentRecord structure."""
    from datetime import datetime

    record = DeploymentRecord(
        deployment_id="deploy_123",
        hypothesis_id="hyp_456",
        baseline_version="1.0.0",
        deployed_version="1.0.1",
        strategy="direct",
        started_at=datetime.now()
    )

    assert record.deployment_id == "deploy_123"
    assert record.hypothesis_id == "hyp_456"
    assert record.status == "in_progress"
    assert record.completed_at is None


# ============================================================================
# Config Tests
# ============================================================================

def test_deployment_config_defaults():
    """Test DeploymentConfig default values."""
    config = DeploymentConfig()

    assert config.strategy == "direct"
    assert config.monitoring_duration_seconds == 300.0
    assert config.monitoring_interval_seconds == 10.0
    assert config.max_error_rate_increase == 0.5
    assert config.max_latency_multiplier == 2.0
    assert config.min_success_rate == 0.7
    assert config.canary_percentage == 0.10
    assert config.canary_stages == [0.10, 0.25, 0.50, 1.0]


def test_deployment_config_custom():
    """Test DeploymentConfig custom values."""
    config = DeploymentConfig(
        strategy="canary",
        monitoring_duration_seconds=60.0,
        max_error_rate_increase=0.3,
        canary_stages=[0.05, 0.25, 1.0]
    )

    assert config.strategy == "canary"
    assert config.monitoring_duration_seconds == 60.0
    assert config.max_error_rate_increase == 0.3
    assert config.canary_stages == [0.05, 0.25, 1.0]
