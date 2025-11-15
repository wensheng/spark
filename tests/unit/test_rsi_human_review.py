"""Tests for RSI Human Review System."""

import pytest
import asyncio
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from spark.rsi.human_review import (
    HumanReviewConfig,
    ReviewRequest,
    ReviewDecision,
    ReviewRequestStore,
    HumanReviewNode,
    FeedbackIntegrator,
)
from spark.rsi.types import (
    ImprovementHypothesis,
    ValidationResult,
    RiskLevel,
    HypothesisType,
    ExpectedImprovement,
    ChangeSpec,
    ValidationViolation,
)
from spark.rsi.experience_db import ExperienceDatabase
from spark.nodes.types import ExecutionContext, NodeMessage


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for test storage."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def review_store(temp_storage_dir):
    """Create a ReviewRequestStore for testing."""
    return ReviewRequestStore(temp_storage_dir)


@pytest.fixture
def review_config():
    """Create a HumanReviewConfig for testing."""
    return HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=10,  # Short timeout for tests
        auto_reject_on_timeout=True,
        poll_interval_seconds=0.1,  # Fast polling for tests
    )


@pytest.fixture
def low_risk_hypothesis():
    """Create a low-risk hypothesis for testing."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_low",
        graph_id="test_graph",
        graph_version_baseline="1.0",
        hypothesis_type=HypothesisType.PROMPT_OPTIMIZATION,
        target_node="node_a",
        rationale="Simple prompt improvement",
        expected_improvement=ExpectedImprovement(success_rate_delta=0.05),
        changes=[
            ChangeSpec(
                type="node_config_update",
                target_node_id="node_a",
                config_path="prompt",
                old_value="old prompt",
                new_value="new prompt"
            )
        ],
        risk_level=RiskLevel.LOW,
        risk_factors=[]
    )


@pytest.fixture
def high_risk_hypothesis():
    """Create a high-risk hypothesis for testing."""
    return ImprovementHypothesis(
        hypothesis_id="hyp_high",
        graph_id="test_graph",
        graph_version_baseline="1.0",
        hypothesis_type=HypothesisType.NODE_REPLACEMENT,
        target_node="critical_node",
        rationale="Replace critical component",
        expected_improvement=ExpectedImprovement(success_rate_delta=0.20),
        changes=[
            ChangeSpec(
                type="node_replacement",
                target_node_id="critical_node"
            )
        ],
        risk_level=RiskLevel.HIGH,
        risk_factors=["structural_change", "critical_path"]
    )


@pytest.fixture
def low_risk_validation():
    """Create a low-risk validation result."""
    return ValidationResult(
        approved=True,
        risk_level=RiskLevel.LOW,
        risk_score=0.2,
        violations=[],
        recommendations=[]
    )


@pytest.fixture
def high_risk_validation():
    """Create a high-risk validation result."""
    return ValidationResult(
        approved=True,
        risk_level=RiskLevel.HIGH,
        risk_score=0.8,
        violations=[
            ValidationViolation(
                rule="structural_complexity",
                severity="warning",
                message="Significant structural change"
            )
        ],
        recommendations=["Consider testing in staging environment first"]
    )


# ============================================================================
# Test ReviewRequestStore
# ============================================================================

@pytest.mark.asyncio
async def test_create_request(review_store, low_risk_hypothesis, low_risk_validation):
    """Test creating a review request."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_001",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    request_id = await review_store.create_request(request)

    assert request_id == "req_001"

    # Verify file was created
    request_path = review_store._get_request_path("req_001")
    assert request_path.exists()


@pytest.mark.asyncio
async def test_get_request(review_store, low_risk_hypothesis, low_risk_validation):
    """Test retrieving a review request."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_002",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    await review_store.create_request(request)

    # Retrieve request
    retrieved = await review_store.get_request("req_002")

    assert retrieved is not None
    assert retrieved.request_id == "req_002"
    assert retrieved.hypothesis_id == low_risk_hypothesis.hypothesis_id
    assert retrieved.status == "pending"


@pytest.mark.asyncio
async def test_get_nonexistent_request(review_store):
    """Test retrieving a nonexistent request."""
    retrieved = await review_store.get_request("nonexistent")
    assert retrieved is None


@pytest.mark.asyncio
async def test_get_pending_requests(review_store, low_risk_hypothesis, low_risk_validation):
    """Test listing pending requests."""
    now = datetime.now()

    # Create multiple requests
    for i in range(3):
        request = ReviewRequest(
            request_id=f"req_{i:03d}",
            hypothesis_id=f"hyp_{i}",
            hypothesis=low_risk_hypothesis,
            validation_result=low_risk_validation,
            created_at=now + timedelta(seconds=i),
            expires_at=now + timedelta(hours=24)
        )
        await review_store.create_request(request)

    pending = await review_store.get_pending_requests()

    assert len(pending) == 3
    # Should be sorted by creation time
    assert pending[0].request_id == "req_000"
    assert pending[1].request_id == "req_001"
    assert pending[2].request_id == "req_002"


@pytest.mark.asyncio
async def test_submit_decision(review_store, low_risk_hypothesis, low_risk_validation):
    """Test submitting a review decision."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_003",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    await review_store.create_request(request)

    # Submit decision
    decision = ReviewDecision(
        request_id="req_003",
        approved=True,
        reviewer="test_user",
        reviewed_at=datetime.now(),
        feedback="Looks good!",
        reason="approved"
    )

    await review_store.submit_decision(decision)

    # Verify decision file was created
    decision_path = review_store._get_decision_path("req_003")
    assert decision_path.exists()


@pytest.mark.asyncio
async def test_check_for_decision(review_store, low_risk_hypothesis, low_risk_validation):
    """Test checking for a decision."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_004",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    await review_store.create_request(request)

    # No decision yet
    decision = await review_store.check_for_decision("req_004")
    assert decision is None

    # Submit decision
    decision_submitted = ReviewDecision(
        request_id="req_004",
        approved=True,
        reviewer="test_user",
        reviewed_at=datetime.now(),
        feedback="LGTM",
        reason="approved"
    )
    await review_store.submit_decision(decision_submitted)

    # Check for decision
    decision = await review_store.check_for_decision("req_004")
    assert decision is not None
    assert decision.approved is True
    assert decision.reviewer == "test_user"
    assert decision.feedback == "LGTM"


@pytest.mark.asyncio
async def test_mark_completed(review_store, low_risk_hypothesis, low_risk_validation):
    """Test marking a request as completed."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_005",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    await review_store.create_request(request)

    # Mark as completed
    await review_store.mark_completed("req_005", "approved")

    # Should be moved to completed directory
    pending_path = review_store._get_request_path("req_005", "pending")
    completed_path = review_store._get_request_path("req_005", "completed")

    assert not pending_path.exists()
    assert completed_path.exists()


# ============================================================================
# Test HumanReviewNode
# ============================================================================

@pytest.mark.asyncio
async def test_auto_approve_low_risk(review_config, low_risk_hypothesis, low_risk_validation, temp_storage_dir):
    """Test that low-risk hypotheses are auto-approved."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': low_risk_hypothesis,
            'validation_result': low_risk_validation
        })
    )

    result = await node.process(context)

    assert result['approved'] is True
    assert result['reason'] == 'auto_approved'
    assert result['risk_level'] == 'low'


@pytest.mark.asyncio
async def test_require_review_high_risk(review_config, high_risk_hypothesis, high_risk_validation, temp_storage_dir):
    """Test that high-risk hypotheses require review."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=2,
        auto_reject_on_timeout=True,
        poll_interval_seconds=0.1,
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)

    # Create context
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': high_risk_hypothesis,
            'validation_result': high_risk_validation
        })
    )

    # Run in background (will timeout)
    async def run_review():
        return await node.process(context)

    result = await run_review()

    # Should timeout and auto-reject
    assert result['approved'] is False
    assert result['reason'] == 'timeout'


@pytest.mark.asyncio
async def test_approval_workflow(review_config, high_risk_hypothesis, high_risk_validation, temp_storage_dir):
    """Test complete approval workflow."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=5,
        poll_interval_seconds=0.1,
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)
    store = node.store

    # Create context
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': high_risk_hypothesis,
            'validation_result': high_risk_validation
        })
    )

    # Start review in background
    async def run_review():
        return await node.process(context)

    review_task = asyncio.create_task(run_review())

    # Wait a bit for request to be created
    await asyncio.sleep(0.2)

    # Find the pending request
    pending = await store.get_pending_requests()
    assert len(pending) == 1
    request_id = pending[0].request_id

    # Submit approval
    decision = ReviewDecision(
        request_id=request_id,
        approved=True,
        reviewer="test_reviewer",
        reviewed_at=datetime.now(),
        feedback="Approved after review",
        reason="approved"
    )
    await store.submit_decision(decision)

    # Wait for review to complete
    result = await review_task

    assert result['approved'] is True
    assert result['reviewer'] == 'test_reviewer'
    assert result['feedback'] == 'Approved after review'


@pytest.mark.asyncio
async def test_rejection_workflow(review_config, high_risk_hypothesis, high_risk_validation, temp_storage_dir):
    """Test complete rejection workflow."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=5,
        poll_interval_seconds=0.1,
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)
    store = node.store

    # Create context
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': high_risk_hypothesis,
            'validation_result': high_risk_validation
        })
    )

    # Start review in background
    async def run_review():
        return await node.process(context)

    review_task = asyncio.create_task(run_review())

    # Wait a bit for request to be created
    await asyncio.sleep(0.2)

    # Find the pending request
    pending = await store.get_pending_requests()
    assert len(pending) == 1
    request_id = pending[0].request_id

    # Submit rejection
    decision = ReviewDecision(
        request_id=request_id,
        approved=False,
        reviewer="test_reviewer",
        reviewed_at=datetime.now(),
        feedback="Too risky for production",
        reason="high_risk"
    )
    await store.submit_decision(decision)

    # Wait for review to complete
    result = await review_task

    assert result['approved'] is False
    assert result['reviewer'] == 'test_reviewer'
    assert result['reason'] == 'high_risk'
    assert result['feedback'] == 'Too risky for production'


@pytest.mark.asyncio
async def test_timeout_auto_reject(review_config, high_risk_hypothesis, high_risk_validation, temp_storage_dir):
    """Test that timeout results in auto-rejection."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=1,  # Very short timeout
        auto_reject_on_timeout=True,
        poll_interval_seconds=0.1,
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': high_risk_hypothesis,
            'validation_result': high_risk_validation
        })
    )

    result = await node.process(context)

    assert result['approved'] is False
    assert result['reason'] == 'timeout'
    assert 'timeout' in result['feedback'].lower()


@pytest.mark.asyncio
async def test_timeout_auto_approve(review_config, high_risk_hypothesis, high_risk_validation, temp_storage_dir):
    """Test that timeout can result in auto-approval if configured."""
    config = HumanReviewConfig(
        require_approval_for_risk_levels=[RiskLevel.HIGH, RiskLevel.CRITICAL],
        approval_timeout_seconds=1,
        auto_reject_on_timeout=False,  # Auto-approve instead
        poll_interval_seconds=0.1,
        review_storage_dir=temp_storage_dir
    )

    node = HumanReviewNode(config=config)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'hypothesis': high_risk_hypothesis,
            'validation_result': high_risk_validation
        })
    )

    result = await node.process(context)

    assert result['approved'] is True
    assert result['reason'] == 'timeout_auto_approved'


@pytest.mark.asyncio
async def test_missing_inputs(review_config, temp_storage_dir):
    """Test handling of missing inputs."""
    node = HumanReviewNode(config=review_config)

    # Missing hypothesis
    context = ExecutionContext(
        inputs=NodeMessage(content={
            'validation_result': ValidationResult(
                approved=True,
                risk_level=RiskLevel.LOW,
                risk_score=0.2
            )
        })
    )

    result = await node.process(context)

    assert result['approved'] is False
    assert result['reason'] == 'missing_inputs'
    assert 'error' in result


# ============================================================================
# Test FeedbackIntegrator
# ============================================================================

@pytest.mark.asyncio
async def test_feedback_integrator_approval(low_risk_hypothesis):
    """Test feedback integration for approval."""
    experience_db = ExperienceDatabase()
    integrator = FeedbackIntegrator(experience_db)

    decision = ReviewDecision(
        request_id="req_test",
        approved=True,
        reviewer="test_user",
        reviewed_at=datetime.now(),
        feedback="Good improvement, well-justified",
        reason="approved"
    )

    # Process feedback (should not raise exception)
    await integrator.process_feedback(low_risk_hypothesis, decision)
    # Note: Full integration with experience DB would be tested in integration tests


@pytest.mark.asyncio
async def test_feedback_integrator_rejection(high_risk_hypothesis):
    """Test feedback integration for rejection."""
    experience_db = ExperienceDatabase()
    integrator = FeedbackIntegrator(experience_db)

    decision = ReviewDecision(
        request_id="req_test",
        approved=False,
        reviewer="test_user",
        reviewed_at=datetime.now(),
        feedback="Changes are too aggressive",
        reason="high_risk"
    )

    # Process feedback (should not raise exception)
    await integrator.process_feedback(high_risk_hypothesis, decision)


# ============================================================================
# Test Review Request Serialization
# ============================================================================

def test_review_request_to_dict(low_risk_hypothesis, low_risk_validation):
    """Test ReviewRequest serialization to dict."""
    now = datetime.now()
    request = ReviewRequest(
        request_id="req_serial",
        hypothesis_id=low_risk_hypothesis.hypothesis_id,
        hypothesis=low_risk_hypothesis,
        validation_result=low_risk_validation,
        created_at=now,
        expires_at=now + timedelta(hours=24)
    )

    data = request.to_dict()

    assert data['request_id'] == 'req_serial'
    assert data['hypothesis_id'] == low_risk_hypothesis.hypothesis_id
    assert 'hypothesis' in data
    assert 'validation_result' in data
    assert data['status'] == 'pending'


def test_review_request_from_dict():
    """Test ReviewRequest deserialization from dict."""
    now = datetime.now()
    data = {
        'request_id': 'req_deserial',
        'hypothesis_id': 'hyp_test',
        'created_at': now.isoformat(),
        'expires_at': (now + timedelta(hours=24)).isoformat(),
        'status': 'pending',
        'reviewer': None,
        'reviewed_at': None
    }

    request = ReviewRequest.from_dict(data)

    assert request.request_id == 'req_deserial'
    assert request.hypothesis_id == 'hyp_test'
    assert request.status == 'pending'
