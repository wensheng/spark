"""Deployment controller for RSI system.

This module provides the DeploymentControllerNode that safely deploys tested
hypotheses to production with monitoring and automatic rollback capabilities.
"""

import logging
import asyncio
from typing import Any, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

from spark.nodes import Node
from spark.nodes.types import ExecutionContext
from spark.rsi.types import ImprovementHypothesis, TestResult, TestStatus
from spark.rsi.change_applicator import ChangeApplicator
from spark.rsi.experience_db import ExperienceDatabase
from spark.nodes.spec import GraphSpec

logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Configuration for deployment."""
    strategy: str = "direct"  # direct, canary, shadow
    monitoring_duration_seconds: float = 300.0  # 5 minutes
    monitoring_interval_seconds: float = 10.0  # Check every 10 seconds

    # Rollback thresholds
    max_error_rate_increase: float = 0.5  # 50% increase triggers rollback
    max_latency_multiplier: float = 2.0  # 2x latency triggers rollback
    min_success_rate: float = 0.7  # Below 70% triggers rollback

    # Canary config (for future use)
    canary_percentage: float = 0.10  # Start with 10%
    canary_stages: list = None  # [0.10, 0.25, 0.50, 1.0]

    def __post_init__(self):
        if self.canary_stages is None:
            self.canary_stages = [0.10, 0.25, 0.50, 1.0]


@dataclass
class DeploymentRecord:
    """Record of a deployment."""
    deployment_id: str
    hypothesis_id: str
    baseline_version: str
    deployed_version: str
    strategy: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # in_progress, completed, failed, rolled_back
    baseline_metrics: Optional[Dict[str, Any]] = None
    deployed_metrics: Optional[Dict[str, Any]] = None
    rollback_reason: Optional[str] = None
    error_message: Optional[str] = None


class DeploymentControllerNode(Node):
    """Deploys tested hypotheses with monitoring and rollback.

    The DeploymentController is responsible for:
    1. Taking a tested hypothesis that passed validation
    2. Applying the changes to create a new graph version
    3. Deploying the new version using the configured strategy
    4. Monitoring post-deployment performance
    5. Automatically rolling back if metrics degrade
    6. Recording deployment outcomes to experience database

    Deployment Strategies:
    - direct: Immediate full deployment (for low-risk changes)
    - canary: Gradual rollout with staged traffic increases (Phase 5+)
    - shadow: Run alongside production without affecting output (Phase 5+)

    Example:
        controller = DeploymentControllerNode(
            deployment_config=DeploymentConfig(
                strategy="direct",
                monitoring_duration_seconds=300
            ),
            experience_db=experience_db
        )

        result = await controller.run({
            'hypothesis': hypothesis,
            'test_result': test_result,
            'baseline_spec': graph_spec
        })
    """

    def __init__(
        self,
        name: str = "DeploymentController",
        deployment_config: Optional[DeploymentConfig] = None,
        experience_db: Optional[ExperienceDatabase] = None,
        enable_monitoring: bool = True,
        enable_rollback: bool = True,
        **kwargs
    ):
        """Initialize the DeploymentController.

        Args:
            name: Node name
            deployment_config: Deployment configuration
            experience_db: Experience database for learning
            enable_monitoring: Whether to monitor post-deployment (default: True)
            enable_rollback: Whether to enable automatic rollback (default: True)
        """
        super().__init__(name=name, **kwargs)
        self.deployment_config = deployment_config or DeploymentConfig()
        self.experience_db = experience_db
        self.enable_monitoring = enable_monitoring
        self.enable_rollback = enable_rollback
        self.change_applicator = ChangeApplicator()

        # Track deployments
        self.deployments: Dict[str, DeploymentRecord] = {}

    async def process(self, context: ExecutionContext) -> Dict[str, Any]:
        """Deploy a tested hypothesis.

        Expected inputs:
            hypothesis: ImprovementHypothesis to deploy
            test_result: TestResult from hypothesis testing
            baseline_spec: Current graph specification (optional)

        Returns:
            Dictionary with deployment status and details
        """
        hypothesis = context.inputs.content.get('hypothesis')
        test_result = context.inputs.content.get('test_result')
        baseline_spec = context.inputs.content.get('baseline_spec')

        if not hypothesis:
            return {
                'success': False,
                'error': 'hypothesis is required'
            }

        if not test_result:
            return {
                'success': False,
                'error': 'test_result is required'
            }

        # Verify test passed
        if test_result.status != TestStatus.PASSED:
            return {
                'success': False,
                'error': f'Cannot deploy hypothesis that did not pass testing (status: {test_result.status.value})'
            }

        logger.info(f"Starting deployment of hypothesis: {hypothesis.hypothesis_id}")

        # Create deployment record
        deployment_id = f"deploy_{hypothesis.hypothesis_id}_{int(datetime.now().timestamp())}"
        deployment_record = DeploymentRecord(
            deployment_id=deployment_id,
            hypothesis_id=hypothesis.hypothesis_id,
            baseline_version=hypothesis.graph_version_baseline,
            deployed_version=f"{hypothesis.graph_version_baseline}.next",
            strategy=self.deployment_config.strategy,
            started_at=datetime.now()
        )
        self.deployments[deployment_id] = deployment_record

        try:
            # Step 1: Apply changes to create new version
            if baseline_spec:
                logger.info("Applying changes to baseline spec")
                modified_spec, diff = self.change_applicator.apply_hypothesis(
                    baseline_spec, hypothesis
                )
                deployment_record.deployed_version = modified_spec.id
            else:
                logger.warning("No baseline_spec provided, skipping change application")
                modified_spec = None
                diff = None

            # Step 2: Deploy based on strategy
            if self.deployment_config.strategy == "direct":
                deploy_success = await self._deploy_direct(
                    hypothesis, test_result, modified_spec, deployment_record
                )
            elif self.deployment_config.strategy == "canary":
                # Simplified for Phase 4 - full canary implementation in Phase 5
                logger.warning("Canary deployment simplified to direct for Phase 4")
                deploy_success = await self._deploy_direct(
                    hypothesis, test_result, modified_spec, deployment_record
                )
            else:
                raise ValueError(f"Unsupported deployment strategy: {self.deployment_config.strategy}")

            if not deploy_success:
                deployment_record.status = "failed"
                deployment_record.completed_at = datetime.now()
                return {
                    'success': False,
                    'deployment_id': deployment_id,
                    'deployment_record': deployment_record,
                    'error': 'Deployment failed'
                }

            # Step 3: Record to experience database
            if self.experience_db:
                await self._record_deployment_outcome(hypothesis, test_result, deployment_record)

            deployment_record.status = "completed"
            deployment_record.completed_at = datetime.now()

            logger.info(f"Deployment {deployment_id} completed successfully")

            return {
                'success': True,
                'deployment_id': deployment_id,
                'deployment_record': deployment_record,
                'deployed_version': deployment_record.deployed_version,
                'modified_spec': modified_spec,
                'diff': diff,
                'rolled_back': False
            }

        except Exception as e:
            logger.error(f"Deployment failed with error: {e}", exc_info=True)
            deployment_record.status = "failed"
            deployment_record.error_message = str(e)
            deployment_record.completed_at = datetime.now()

            return {
                'success': False,
                'deployment_id': deployment_id,
                'deployment_record': deployment_record,
                'error': str(e)
            }

    async def _deploy_direct(
        self,
        hypothesis: ImprovementHypothesis,
        test_result: TestResult,
        modified_spec: Optional[GraphSpec],
        deployment_record: DeploymentRecord
    ) -> bool:
        """Execute direct deployment strategy.

        Args:
            hypothesis: The hypothesis being deployed
            test_result: Test results
            modified_spec: Modified graph specification (if available)
            deployment_record: Deployment record to update

        Returns:
            True if deployment successful, False otherwise
        """
        logger.info(f"Executing direct deployment for {hypothesis.hypothesis_id}")

        # For Phase 4, we simulate deployment since we don't have actual graph execution
        # In a real implementation, this would:
        # 1. Create new graph instance from modified_spec
        # 2. Perform health checks
        # 3. Swap traffic to new version
        # 4. Monitor for regressions

        # Store baseline metrics from test
        if test_result.comparison:
            deployment_record.baseline_metrics = {
                'success_rate': test_result.comparison.baseline_metrics.success_rate,
                'avg_duration': test_result.comparison.baseline_metrics.avg_duration,
                'p95_duration': test_result.comparison.baseline_metrics.p95_duration
            }

        # Simulate monitoring period
        if self.enable_monitoring:
            logger.info(f"Monitoring deployment for {self.deployment_config.monitoring_duration_seconds}s")

            rolled_back = await self._monitor_deployment(
                hypothesis, test_result, deployment_record
            )

            if rolled_back:
                return False  # Deployment failed due to rollback

        return True

    async def _monitor_deployment(
        self,
        hypothesis: ImprovementHypothesis,
        test_result: TestResult,
        deployment_record: DeploymentRecord
    ) -> bool:
        """Monitor deployment and rollback if metrics degrade.

        Args:
            hypothesis: The hypothesis being deployed
            test_result: Test results with expected improvements
            deployment_record: Deployment record to update

        Returns:
            True if rolled back, False if monitoring completed successfully
        """
        monitoring_duration = self.deployment_config.monitoring_duration_seconds
        interval = self.deployment_config.monitoring_interval_seconds

        start_time = asyncio.get_event_loop().time()
        checks_performed = 0

        while (asyncio.get_event_loop().time() - start_time) < monitoring_duration:
            await asyncio.sleep(interval)
            checks_performed += 1

            # Simulate metric collection
            # In real implementation, this would query telemetry for actual metrics
            current_metrics = self._simulate_current_metrics(test_result, checks_performed)

            # Check for regressions
            should_rollback, reason = self._should_rollback(
                baseline_metrics=deployment_record.baseline_metrics,
                current_metrics=current_metrics
            )

            if should_rollback and self.enable_rollback:
                logger.warning(f"Rollback triggered: {reason}")
                deployment_record.status = "rolled_back"
                deployment_record.rollback_reason = reason
                deployment_record.deployed_metrics = current_metrics

                await self._execute_rollback(hypothesis, deployment_record)

                return True  # Rolled back

            logger.debug(f"Monitoring check {checks_performed}: metrics OK")

        logger.info(f"Monitoring completed successfully after {checks_performed} checks")
        return False  # Not rolled back

    def _should_rollback(
        self,
        baseline_metrics: Optional[Dict[str, Any]],
        current_metrics: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Determine if rollback should be triggered.

        Args:
            baseline_metrics: Metrics from baseline (test results)
            current_metrics: Current production metrics

        Returns:
            Tuple of (should_rollback, reason)
        """
        if not baseline_metrics:
            return False, None

        current_success_rate = current_metrics.get('success_rate', 1.0)
        current_error_rate = 1.0 - current_success_rate
        current_latency = current_metrics.get('avg_duration', 0.0)

        baseline_success_rate = baseline_metrics.get('success_rate', 1.0)
        baseline_error_rate = 1.0 - baseline_success_rate
        baseline_latency = baseline_metrics.get('avg_duration', 1.0)

        config = self.deployment_config

        # Check success rate minimum threshold
        if current_success_rate < config.min_success_rate:
            return True, f"Success rate {current_success_rate:.1%} below minimum {config.min_success_rate:.1%}"

        # Check error rate increase
        if baseline_error_rate > 0 and current_error_rate > baseline_error_rate * (1 + config.max_error_rate_increase):
            return True, f"Error rate increased by {((current_error_rate / baseline_error_rate - 1) * 100):.0f}%"

        # Check latency increase
        if baseline_latency > 0 and current_latency > baseline_latency * config.max_latency_multiplier:
            return True, f"Latency increased by {((current_latency / baseline_latency - 1) * 100):.0f}%"

        return False, None

    def _simulate_current_metrics(
        self,
        test_result: TestResult,
        check_number: int
    ) -> Dict[str, Any]:
        """Simulate current metrics for Phase 4.

        In real implementation, this would query telemetry database.
        For Phase 4, we simulate metrics that match the test predictions.

        Args:
            test_result: Test results with predictions
            check_number: Number of monitoring checks performed

        Returns:
            Simulated metrics dictionary
        """
        if test_result.comparison and test_result.comparison.candidate_metrics:
            # Use candidate metrics as simulated production metrics
            return {
                'success_rate': test_result.comparison.candidate_metrics.success_rate,
                'avg_duration': test_result.comparison.candidate_metrics.avg_duration,
                'p95_duration': test_result.comparison.candidate_metrics.p95_duration
            }
        else:
            # Default safe metrics
            return {
                'success_rate': 0.95,
                'avg_duration': 0.5,
                'p95_duration': 0.7
            }

    async def _execute_rollback(
        self,
        hypothesis: ImprovementHypothesis,
        deployment_record: DeploymentRecord
    ) -> None:
        """Execute rollback to previous version.

        Args:
            hypothesis: The hypothesis that was deployed
            deployment_record: Deployment record
        """
        logger.warning(f"Executing rollback for deployment {deployment_record.deployment_id}")

        # In real implementation, this would:
        # 1. Stop traffic to new version
        # 2. Restore previous version
        # 3. Verify restoration successful
        # 4. Clean up new version resources

        # For Phase 4, we just log and update status
        logger.info(f"Rolled back to version {deployment_record.baseline_version}")

    async def _record_deployment_outcome(
        self,
        hypothesis: ImprovementHypothesis,
        test_result: TestResult,
        deployment_record: DeploymentRecord
    ) -> None:
        """Record deployment outcome to experience database.

        Args:
            hypothesis: The deployed hypothesis
            test_result: Test results
            deployment_record: Deployment record
        """
        if not self.experience_db:
            return

        logger.info(f"Recording deployment outcome to experience database")

        # Store hypothesis first
        proposal = {
            'rationale': hypothesis.rationale,
            'expected_improvement': {
                'success_rate_delta': hypothesis.expected_improvement.success_rate_delta if hypothesis.expected_improvement else 0,
                'latency_delta': hypothesis.expected_improvement.latency_delta if hypothesis.expected_improvement else 0,
            } if hypothesis.expected_improvement else None,
            'changes': [
                {
                    'type': change.type,
                    'target_node_id': change.target_node_id,
                    'target_edge_id': change.target_edge_id
                }
                for change in hypothesis.changes
            ],
            'risk_level': hypothesis.risk_level.value
        }

        await self.experience_db.store_hypothesis(
            hypothesis_id=hypothesis.hypothesis_id,
            graph_id=hypothesis.graph_id,
            graph_version_baseline=hypothesis.graph_version_baseline,
            hypothesis_type=hypothesis.hypothesis_type.value,
            proposal=proposal,
            target_node=hypothesis.target_node
        )

        # Update with test results
        test_results_data = {
            'status': test_result.status.value,
            'num_baseline_runs': test_result.num_baseline_runs,
            'num_candidate_runs': test_result.num_candidate_runs,
            'comparison': {
                'success_rate_delta': test_result.comparison.success_rate_delta if test_result.comparison else 0,
                'avg_duration_delta': test_result.comparison.avg_duration_delta if test_result.comparison else 0,
                'is_improvement': test_result.comparison.is_improvement if test_result.comparison else False,
                'is_regression': test_result.comparison.is_regression if test_result.comparison else False,
            } if test_result.comparison else None
        }

        await self.experience_db.update_test_results(
            hypothesis_id=hypothesis.hypothesis_id,
            test_results=test_results_data
        )

        # Update with deployment outcome
        outcome = {
            'deployment_id': deployment_record.deployment_id,
            'status': deployment_record.status,
            'strategy': deployment_record.strategy,
            'rolled_back': deployment_record.status == "rolled_back",
            'rollback_reason': deployment_record.rollback_reason,
            'deployed_version': deployment_record.deployed_version,
            'successful': deployment_record.status == "completed",
            'failure_reason': deployment_record.rollback_reason or deployment_record.error_message
        }

        lessons = []
        patterns = []

        # Extract lessons from deployment
        if deployment_record.status == "completed":
            lessons.append(f"{hypothesis.hypothesis_type.value} successfully deployed")
            patterns.append(f"{hypothesis.hypothesis_type.value}_success")
        elif deployment_record.status == "rolled_back":
            lessons.append(f"Deployment rolled back: {deployment_record.rollback_reason}")
            patterns.append(f"{hypothesis.hypothesis_type.value}_rollback")

        await self.experience_db.update_deployment_outcome(
            hypothesis_id=hypothesis.hypothesis_id,
            deployed=deployment_record.status in ("completed", "rolled_back"),
            outcome=outcome,
            lessons=lessons,
            patterns=patterns
        )

        logger.info("Deployment outcome recorded to experience database")

    def get_deployment_record(self, deployment_id: str) -> Optional[DeploymentRecord]:
        """Get deployment record by ID.

        Args:
            deployment_id: Deployment identifier

        Returns:
            DeploymentRecord if found, None otherwise
        """
        return self.deployments.get(deployment_id)

    def get_all_deployments(self) -> list[DeploymentRecord]:
        """Get all deployment records.

        Returns:
            List of all deployment records
        """
        return list(self.deployments.values())
