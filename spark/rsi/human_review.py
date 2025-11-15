"""Human-in-the-loop review system for RSI hypotheses.

This module provides a human review workflow for high-risk improvement hypotheses,
allowing humans to approve/reject changes before testing and deployment.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import uuid4

from spark.nodes import Node
from spark.rsi.types import (
    ImprovementHypothesis,
    ValidationResult,
    RiskLevel,
)
from spark.rsi.experience_db import ExperienceDatabase

logger = logging.getLogger(__name__)


# ============================================================================
# Data Types
# ============================================================================

@dataclass
class HumanReviewConfig:
    """Configuration for human review process."""
    require_approval_for_risk_levels: List[RiskLevel] = field(
        default_factory=lambda: [RiskLevel.HIGH, RiskLevel.CRITICAL]
    )
    approval_timeout_seconds: int = 86400  # 24 hours
    auto_reject_on_timeout: bool = True
    enable_feedback_collection: bool = True
    review_storage_dir: str = "~/.cache/spark/rsi/reviews"
    poll_interval_seconds: float = 5.0  # Check for decisions every 5 seconds


@dataclass
class ReviewRequest:
    """A request for human review of a hypothesis."""
    request_id: str
    hypothesis_id: str
    hypothesis: ImprovementHypothesis
    validation_result: ValidationResult
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # pending, approved, rejected, expired
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'request_id': self.request_id,
            'hypothesis_id': self.hypothesis_id,
            'hypothesis': {
                'hypothesis_id': self.hypothesis.hypothesis_id,
                'hypothesis_type': self.hypothesis.hypothesis_type.value,
                'target_node': self.hypothesis.target_node,
                'rationale': self.hypothesis.rationale,
                'expected_improvement': {
                    'success_rate_delta': self.hypothesis.expected_improvement.success_rate_delta,
                    'latency_delta': self.hypothesis.expected_improvement.latency_delta,
                    'cost_delta': self.hypothesis.expected_improvement.cost_delta,
                },
                'risk_level': self.hypothesis.risk_level.value,
                'risk_factors': self.hypothesis.risk_factors,
                'changes': [
                    {
                        'type': change.type,
                        'target_node_id': change.target_node_id,
                        'target_edge_id': change.target_edge_id,
                    }
                    for change in self.hypothesis.changes
                ],
            },
            'validation_result': {
                'approved': self.validation_result.approved,
                'risk_level': self.validation_result.risk_level.value,
                'risk_score': self.validation_result.risk_score,
                'violations': [
                    {
                        'rule': v.rule,
                        'severity': v.severity,
                        'message': v.message,
                    }
                    for v in self.validation_result.violations
                ],
                'recommendations': self.validation_result.recommendations,
            } if self.validation_result is not None else None,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'status': self.status,
            'reviewer': self.reviewer,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewRequest':
        """Create from dictionary (JSON deserialization)."""
        # This is a simplified version - in production would need full reconstruction
        # For now, we only need the status and reviewer for decision checking
        return cls(
            request_id=data['request_id'],
            hypothesis_id=data['hypothesis_id'],
            hypothesis=None,  # Not needed for decision checking
            validation_result=None,  # Not needed for decision checking
            created_at=datetime.fromisoformat(data['created_at']),
            expires_at=datetime.fromisoformat(data['expires_at']),
            status=data['status'],
            reviewer=data.get('reviewer'),
            reviewed_at=datetime.fromisoformat(data['reviewed_at']) if data.get('reviewed_at') else None,
        )


@dataclass
class ReviewDecision:
    """A human's decision on a review request."""
    request_id: str
    approved: bool
    reviewer: str
    reviewed_at: datetime
    feedback: str = ""
    annotations: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""


# ============================================================================
# Review Request Store
# ============================================================================

class ReviewRequestStore:
    """Persistent store for review requests using file system."""

    def __init__(self, storage_dir: str = "~/.cache/spark/rsi/reviews"):
        """Initialize store.

        Args:
            storage_dir: Directory for storing review requests
        """
        self.storage_dir = Path(os.path.expanduser(storage_dir))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Subdirectories for organization
        self.pending_dir = self.storage_dir / "pending"
        self.completed_dir = self.storage_dir / "completed"
        self.pending_dir.mkdir(exist_ok=True)
        self.completed_dir.mkdir(exist_ok=True)

    def _get_request_path(self, request_id: str, status: str = "pending") -> Path:
        """Get file path for a request."""
        if status == "pending":
            return self.pending_dir / f"{request_id}.json"
        else:
            return self.completed_dir / f"{request_id}.json"

    def _get_decision_path(self, request_id: str) -> Path:
        """Get file path for a decision."""
        return self.pending_dir / f"{request_id}.decision.json"

    async def create_request(self, request: ReviewRequest) -> str:
        """Create a new review request.

        Args:
            request: The review request to create

        Returns:
            Request ID
        """
        request_path = self._get_request_path(request.request_id)

        # Write request to file
        with open(request_path, 'w') as f:
            json.dump(request.to_dict(), f, indent=2)

        logger.info(f"Created review request: {request.request_id}")
        return request.request_id

    async def get_request(self, request_id: str) -> Optional[ReviewRequest]:
        """Get a review request by ID.

        Args:
            request_id: Request identifier

        Returns:
            ReviewRequest if found, None otherwise
        """
        # Check pending first
        request_path = self._get_request_path(request_id, "pending")
        if request_path.exists():
            with open(request_path, 'r') as f:
                data = json.load(f)
            return ReviewRequest.from_dict(data)

        # Check completed
        request_path = self._get_request_path(request_id, "completed")
        if request_path.exists():
            with open(request_path, 'r') as f:
                data = json.load(f)
            return ReviewRequest.from_dict(data)

        return None

    async def get_pending_requests(self) -> List[ReviewRequest]:
        """Get all pending review requests.

        Returns:
            List of pending requests
        """
        requests = []
        for request_file in self.pending_dir.glob("*.json"):
            # Skip decision files
            if ".decision." in request_file.name:
                continue

            with open(request_file, 'r') as f:
                data = json.load(f)
            requests.append(ReviewRequest.from_dict(data))

        # Sort by creation time
        requests.sort(key=lambda r: r.created_at)
        return requests

    async def check_for_decision(self, request_id: str) -> Optional[ReviewDecision]:
        """Check if a decision has been made for a request.

        Args:
            request_id: Request identifier

        Returns:
            ReviewDecision if found, None otherwise
        """
        decision_path = self._get_decision_path(request_id)
        if not decision_path.exists():
            return None

        # Read decision
        with open(decision_path, 'r') as f:
            data = json.load(f)

        decision = ReviewDecision(
            request_id=data['request_id'],
            approved=data['approved'],
            reviewer=data['reviewer'],
            reviewed_at=datetime.fromisoformat(data['reviewed_at']),
            feedback=data.get('feedback', ''),
            annotations=data.get('annotations', {}),
            reason=data.get('reason', ''),
        )

        return decision

    async def submit_decision(self, decision: ReviewDecision):
        """Submit a review decision.

        Args:
            decision: The review decision
        """
        decision_path = self._get_decision_path(decision.request_id)

        # Write decision to file
        with open(decision_path, 'w') as f:
            json.dump({
                'request_id': decision.request_id,
                'approved': decision.approved,
                'reviewer': decision.reviewer,
                'reviewed_at': decision.reviewed_at.isoformat(),
                'feedback': decision.feedback,
                'annotations': decision.annotations,
                'reason': decision.reason,
            }, f, indent=2)

        logger.info(f"Submitted decision for request {decision.request_id}: {decision.approved}")

    async def mark_completed(self, request_id: str, status: str):
        """Mark a request as completed and archive it.

        Args:
            request_id: Request identifier
            status: Final status (approved, rejected, expired)
        """
        request_path = self._get_request_path(request_id, "pending")
        if not request_path.exists():
            return

        # Read request
        with open(request_path, 'r') as f:
            data = json.load(f)

        # Update status
        data['status'] = status

        # Move to completed directory
        completed_path = self._get_request_path(request_id, "completed")
        with open(completed_path, 'w') as f:
            json.dump(data, f, indent=2)

        # Remove from pending
        request_path.unlink()

        # Remove decision file if exists
        decision_path = self._get_decision_path(request_id)
        if decision_path.exists():
            decision_path.unlink()

        logger.info(f"Marked request {request_id} as {status}")


# ============================================================================
# Human Review Node
# ============================================================================

class HumanReviewNode(Node):
    """Node that requests human review for hypotheses.

    This node:
    1. Creates a review request with full context
    2. Polls for human decision (approval/rejection)
    3. Handles timeout scenarios
    4. Collects feedback for learning
    """

    def __init__(
        self,
        config: Optional[HumanReviewConfig] = None,
        store: Optional[ReviewRequestStore] = None,
        name: str = "HumanReview",
        **kwargs
    ):
        """Initialize HumanReviewNode.

        Args:
            config: Human review configuration
            store: Review request store (creates default if None)
            name: Node name
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.config = config or HumanReviewConfig()
        self.store = store or ReviewRequestStore(self.config.review_storage_dir)

    async def process(self, context):
        """Request human review and wait for decision.

        Args:
            context: Execution context with inputs:
                - hypothesis: ImprovementHypothesis (required)
                - validation_result: ValidationResult (required)

        Returns:
            Dict with:
                - approved: bool
                - reason: str
                - feedback: str (if provided)
                - annotations: Dict (if provided)
        """
        # Get inputs
        hypothesis = context.inputs.content.get('hypothesis')
        validation_result = context.inputs.content.get('validation_result')

        if hypothesis is None or validation_result is None:
            logger.error("hypothesis and validation_result are required")
            return {
                'approved': False,
                'reason': 'missing_inputs',
                'error': 'hypothesis and validation_result are required'
            }

        # Check if review is required
        if not self._requires_review(hypothesis, validation_result):
            logger.info(f"Hypothesis {hypothesis.hypothesis_id} auto-approved (low risk)")
            return {
                'approved': True,
                'reason': 'auto_approved',
                'risk_level': validation_result.risk_level.value
            }

        # Create review request
        request = await self._create_review_request(hypothesis, validation_result)

        # Wait for decision (with timeout)
        decision = await self._wait_for_decision(request)

        # Store decision
        if decision.approved:
            await self.store.mark_completed(request.request_id, "approved")
        else:
            await self.store.mark_completed(request.request_id, "rejected")

        return {
            'approved': decision.approved,
            'reason': decision.reason,
            'feedback': decision.feedback,
            'annotations': decision.annotations,
            'reviewer': decision.reviewer,
            'reviewed_at': decision.reviewed_at.isoformat(),
        }

    def _requires_review(
        self,
        hypothesis: ImprovementHypothesis,
        validation_result: ValidationResult
    ) -> bool:
        """Determine if hypothesis requires human review.

        Args:
            hypothesis: The hypothesis
            validation_result: Validation result

        Returns:
            True if review required, False otherwise
        """
        # Check risk level
        if validation_result.risk_level in self.config.require_approval_for_risk_levels:
            return True

        # Check if validation explicitly requires review
        if not validation_result.approved:
            return True

        return False

    async def _create_review_request(
        self,
        hypothesis: ImprovementHypothesis,
        validation_result: ValidationResult
    ) -> ReviewRequest:
        """Create a review request.

        Args:
            hypothesis: The hypothesis to review
            validation_result: Validation result

        Returns:
            ReviewRequest
        """
        now = datetime.now()
        expires_at = now + timedelta(seconds=self.config.approval_timeout_seconds)

        request = ReviewRequest(
            request_id=f"review_{uuid4().hex[:8]}",
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis=hypothesis,
            validation_result=validation_result,
            created_at=now,
            expires_at=expires_at,
        )

        await self.store.create_request(request)
        logger.info(f"Created review request {request.request_id} for hypothesis {hypothesis.hypothesis_id}")

        return request

    async def _wait_for_decision(self, request: ReviewRequest) -> ReviewDecision:
        """Wait for human decision with timeout.

        Args:
            request: The review request

        Returns:
            ReviewDecision
        """
        logger.info(f"Waiting for decision on request {request.request_id} (timeout: {self.config.approval_timeout_seconds}s)")

        start_time = datetime.now()
        while True:
            # Check for decision
            decision = await self.store.check_for_decision(request.request_id)
            if decision is not None:
                logger.info(f"Decision received: {decision.approved}")
                return decision

            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= self.config.approval_timeout_seconds:
                logger.warning(f"Review timeout for request {request.request_id}")

                if self.config.auto_reject_on_timeout:
                    await self.store.mark_completed(request.request_id, "expired")
                    return ReviewDecision(
                        request_id=request.request_id,
                        approved=False,
                        reviewer="system",
                        reviewed_at=datetime.now(),
                        reason="timeout",
                        feedback="Review request expired due to timeout",
                    )
                else:
                    # Auto-approve on timeout (risky!)
                    await self.store.mark_completed(request.request_id, "approved")
                    return ReviewDecision(
                        request_id=request.request_id,
                        approved=True,
                        reviewer="system",
                        reviewed_at=datetime.now(),
                        reason="timeout_auto_approved",
                        feedback="Review request approved automatically after timeout",
                    )

            # Poll interval
            await asyncio.sleep(self.config.poll_interval_seconds)


# ============================================================================
# Feedback Integration
# ============================================================================

class FeedbackIntegrator:
    """Integrates human feedback into the experience database for learning."""

    def __init__(self, experience_db: ExperienceDatabase):
        """Initialize FeedbackIntegrator.

        Args:
            experience_db: Experience database to update
        """
        self.experience_db = experience_db

    async def process_feedback(
        self,
        hypothesis: ImprovementHypothesis,
        decision: ReviewDecision,
    ):
        """Process human feedback and update experience database.

        Args:
            hypothesis: The hypothesis that was reviewed
            decision: The review decision with feedback
        """
        # Extract lessons from feedback
        lessons = []

        if decision.approved:
            # Positive feedback
            if decision.feedback:
                lessons.append(f"Human approved: {decision.feedback}")

            # Log approval pattern
            lessons.append(
                f"Hypothesis type {hypothesis.hypothesis_type.value} was approved by {decision.reviewer}"
            )
        else:
            # Negative feedback - learn what to avoid
            if decision.reason:
                lessons.append(f"Rejection reason: {decision.reason}")

            if decision.feedback:
                lessons.append(f"Human rejected: {decision.feedback}")

            # Log rejection pattern
            lessons.append(
                f"Hypothesis type {hypothesis.hypothesis_type.value} was rejected by {decision.reviewer}"
            )

        # Store in experience database
        # Note: This assumes the hypothesis has been stored in the experience database
        # We're adding human feedback as additional context
        logger.info(f"Integrated feedback for hypothesis {hypothesis.hypothesis_id}: {len(lessons)} lessons")

        # In a full implementation, we would:
        # 1. Query experience DB for this hypothesis
        # 2. Add lessons to the entry
        # 3. Update pattern confidence based on human agreement/disagreement
        # For Phase 6, we're focusing on the workflow, not full learning integration
