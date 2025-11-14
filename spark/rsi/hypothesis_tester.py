"""Hypothesis tester for automated testing of improvement proposals."""

from spark.nodes import Node
from spark.rsi.types import (
    ImprovementHypothesis,
    TestResult,
    TestStatus,
    TestMetrics,
    ComparisonResult,
)
from spark.graphs import BaseGraph
from typing import Dict, Any, Optional, List, Tuple
import logging
import asyncio
import statistics
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


class HypothesisTesterNode(Node):
    """Tests improvement hypotheses through automated A/B testing.

    This node implements Phase 3 of RSI by:
    1. Running baseline graph multiple times to collect metrics
    2. Applying hypothesis changes to create candidate graph
    3. Running candidate graph multiple times
    4. Comparing performance with statistical significance testing
    5. Determining if hypothesis improves the graph

    Usage:
        tester = HypothesisTesterNode(
            num_baseline_runs=20,
            num_candidate_runs=20,
            success_criteria={
                'min_success_rate_improvement': 0.05,  # 5% improvement required
                'max_latency_increase': 0.1,  # 10% increase tolerated
                'confidence_level': 0.95  # 95% confidence
            }
        )

        result = await tester.run({
            'hypothesis': hypothesis,
            'graph': graph
        })

        if result['test_result'].status == TestStatus.PASSED:
            # Deploy hypothesis
            pass
    """

    def __init__(
        self,
        name: str = "HypothesisTester",
        num_baseline_runs: int = 20,
        num_candidate_runs: int = 20,
        success_criteria: Optional[Dict[str, Any]] = None,
        confidence_level: float = 0.95,
        enable_mock_mode: bool = False,
        **kwargs
    ):
        """Initialize HypothesisTesterNode.

        Args:
            name: Node name
            num_baseline_runs: Number of times to run baseline
            num_candidate_runs: Number of times to run candidate
            success_criteria: Dict of success criteria for improvements
            confidence_level: Statistical confidence level (e.g., 0.95 for 95%)
            enable_mock_mode: If True, use mock testing without actually running graphs
            **kwargs: Additional node configuration
        """
        super().__init__(name=name, **kwargs)
        self.num_baseline_runs = num_baseline_runs
        self.num_candidate_runs = num_candidate_runs
        self.confidence_level = confidence_level
        self.enable_mock_mode = enable_mock_mode

        # Default success criteria
        self.success_criteria = success_criteria or {
            'min_success_rate_improvement': 0.0,  # Any improvement
            'max_latency_increase': 0.2,  # 20% increase tolerated
            'min_confidence_level': confidence_level
        }

    async def process(self, context):
        """Test an improvement hypothesis.

        Args:
            context: Execution context with inputs:
                - hypothesis: ImprovementHypothesis (required)
                - graph: BaseGraph (required)
                - test_inputs: Optional list of test inputs

        Returns:
            Dict with:
                - test_result: TestResult
                - status: str
                - passed: bool
                - is_improvement: bool
        """
        # Get inputs
        hypothesis = context.inputs.content.get('hypothesis')
        graph = context.inputs.content.get('graph')
        test_inputs = context.inputs.content.get('test_inputs')

        if hypothesis is None:
            logger.error("hypothesis is required")
            return {
                'test_result': None,
                'status': 'error',
                'passed': False,
                'error': 'hypothesis is required'
            }

        if graph is None and not self.enable_mock_mode:
            logger.error("graph is required for testing")
            return {
                'test_result': None,
                'status': 'error',
                'passed': False,
                'error': 'graph is required'
            }

        test_id = f"test_{uuid4().hex[:8]}"
        started_at = datetime.now()

        logger.info(
            f"Starting test {test_id} for hypothesis {hypothesis.hypothesis_id}"
        )

        try:
            if self.enable_mock_mode:
                # Mock testing for unit tests
                test_result = self._mock_test_hypothesis(
                    hypothesis, test_id, started_at
                )
            else:
                # Real testing
                test_result = await self._test_hypothesis(
                    hypothesis, graph, test_inputs, test_id, started_at
                )

            # Determine status
            passed = test_result.status == TestStatus.PASSED
            is_improvement = (
                test_result.comparison.is_improvement
                if test_result.comparison
                else False
            )

            logger.info(
                f"Test {test_id} completed: status={test_result.status.value}, "
                f"passed={passed}, is_improvement={is_improvement}"
            )

            return {
                'test_result': test_result,
                'status': test_result.status.value,
                'passed': passed,
                'is_improvement': is_improvement
            }

        except Exception as e:
            logger.error(f"Error testing hypothesis: {e}", exc_info=True)

            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            test_result = TestResult(
                hypothesis_id=hypothesis.hypothesis_id,
                test_id=test_id,
                status=TestStatus.ERROR,
                num_baseline_runs=self.num_baseline_runs,
                num_candidate_runs=self.num_candidate_runs,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                error_message=str(e)
            )

            return {
                'test_result': test_result,
                'status': 'error',
                'passed': False,
                'error': str(e)
            }

    async def _test_hypothesis(
        self,
        hypothesis: ImprovementHypothesis,
        graph: BaseGraph,
        test_inputs: Optional[List[Any]],
        test_id: str,
        started_at: datetime
    ) -> TestResult:
        """Test hypothesis by running baseline and candidate graphs.

        Args:
            hypothesis: Hypothesis to test
            graph: Baseline graph
            test_inputs: Optional test inputs
            test_id: Test identifier
            started_at: Test start time

        Returns:
            TestResult with comparison
        """
        # Run baseline
        logger.info(f"Running baseline ({self.num_baseline_runs} runs)")
        baseline_metrics = await self._run_graph_multiple_times(
            graph, self.num_baseline_runs, test_inputs
        )

        # Apply hypothesis changes (Phase 3: simplified - just mock for now)
        # In Phase 4+, this would actually modify the graph
        logger.info(f"Applying hypothesis changes (mock)")
        candidate_graph = graph  # For now, just use same graph

        # Run candidate
        logger.info(f"Running candidate ({self.num_candidate_runs} runs)")
        candidate_metrics = await self._run_graph_multiple_times(
            candidate_graph, self.num_candidate_runs, test_inputs
        )

        # Compare results
        comparison = self._compare_metrics(baseline_metrics, candidate_metrics)

        # Determine status
        status = self._determine_test_status(comparison)

        # Generate recommendations
        recommendations = self._generate_test_recommendations(comparison)

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        return TestResult(
            hypothesis_id=hypothesis.hypothesis_id,
            test_id=test_id,
            status=status,
            num_baseline_runs=self.num_baseline_runs,
            num_candidate_runs=self.num_candidate_runs,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            comparison=comparison,
            success_criteria_met=comparison.meets_success_criteria,
            success_criteria=self.success_criteria,
            recommendations=recommendations
        )

    async def _run_graph_multiple_times(
        self,
        graph: BaseGraph,
        num_runs: int,
        test_inputs: Optional[List[Any]]
    ) -> TestMetrics:
        """Run graph multiple times and collect metrics.

        Args:
            graph: Graph to run
            num_runs: Number of runs
            test_inputs: Optional test inputs

        Returns:
            TestMetrics with aggregated results
        """
        durations = []
        successes = 0
        failures = 0
        error_types = {}

        for i in range(num_runs):
            try:
                start = asyncio.get_event_loop().time()

                # Run graph
                if test_inputs and i < len(test_inputs):
                    result = await graph.run(test_inputs[i])
                else:
                    result = await graph.run()

                end = asyncio.get_event_loop().time()
                duration = end - start

                durations.append(duration)
                successes += 1

            except Exception as e:
                failures += 1
                error_type = type(e).__name__
                error_types[error_type] = error_types.get(error_type, 0) + 1

        # Calculate metrics
        success_rate = successes / num_runs if num_runs > 0 else 0.0

        if durations:
            avg_duration = statistics.mean(durations)
            sorted_durations = sorted(durations)
            p50_duration = sorted_durations[len(sorted_durations) // 2]
            p95_idx = int(len(sorted_durations) * 0.95)
            p95_duration = sorted_durations[p95_idx] if p95_idx < len(sorted_durations) else sorted_durations[-1]
            p99_idx = int(len(sorted_durations) * 0.99)
            p99_duration = sorted_durations[p99_idx] if p99_idx < len(sorted_durations) else sorted_durations[-1]
        else:
            avg_duration = 0.0
            p50_duration = 0.0
            p95_duration = 0.0
            p99_duration = 0.0

        return TestMetrics(
            num_runs=num_runs,
            success_count=successes,
            failure_count=failures,
            success_rate=success_rate,
            avg_duration=avg_duration,
            p50_duration=p50_duration,
            p95_duration=p95_duration,
            p99_duration=p99_duration,
            error_types=error_types
        )

    def _compare_metrics(
        self,
        baseline: TestMetrics,
        candidate: TestMetrics
    ) -> ComparisonResult:
        """Compare baseline and candidate metrics.

        Args:
            baseline: Baseline metrics
            candidate: Candidate metrics

        Returns:
            ComparisonResult with statistical analysis
        """
        # Calculate deltas
        success_rate_delta = candidate.success_rate - baseline.success_rate
        avg_duration_delta = candidate.avg_duration - baseline.avg_duration
        p95_duration_delta = candidate.p95_duration - baseline.p95_duration

        # Calculate relative changes
        success_rate_pct_change = (
            success_rate_delta / baseline.success_rate
            if baseline.success_rate > 0 else 0.0
        )
        avg_duration_pct_change = (
            avg_duration_delta / baseline.avg_duration
            if baseline.avg_duration > 0 else 0.0
        )

        # Simplified statistical significance test
        # For Phase 3, use simplified heuristic
        # In production, would use proper t-test or Mann-Whitney U test
        is_significant = self._check_statistical_significance(
            baseline, candidate
        )

        # Determine if improvement or regression
        is_improvement = (
            success_rate_delta >= 0 and  # Success rate didn't decrease
            avg_duration_delta <= 0  # Latency improved (decreased)
        )

        is_regression = (
            success_rate_delta < -0.05 or  # >5% decrease in success rate
            avg_duration_pct_change > 0.5  # >50% increase in latency
        )

        # Check success criteria
        meets_criteria = self._check_success_criteria(
            success_rate_delta,
            avg_duration_pct_change,
            is_significant
        )

        # Generate summary
        summary = self._generate_comparison_summary(
            success_rate_delta,
            avg_duration_delta,
            is_improvement,
            is_regression
        )

        # Generate warnings
        warnings = []
        if not is_significant:
            warnings.append("Results are not statistically significant")
        if is_regression:
            warnings.append("Candidate shows regression in performance")
        if candidate.failure_count > baseline.failure_count:
            warnings.append(
                f"Candidate has more failures ({candidate.failure_count} vs "
                f"{baseline.failure_count})"
            )

        return ComparisonResult(
            baseline_metrics=baseline,
            candidate_metrics=candidate,
            success_rate_delta=success_rate_delta,
            avg_duration_delta=avg_duration_delta,
            p95_duration_delta=p95_duration_delta,
            is_significant=is_significant,
            confidence_level=self.confidence_level,
            is_improvement=is_improvement,
            is_regression=is_regression,
            meets_success_criteria=meets_criteria,
            summary=summary,
            warnings=warnings
        )

    def _check_statistical_significance(
        self,
        baseline: TestMetrics,
        candidate: TestMetrics
    ) -> bool:
        """Check if difference is statistically significant.

        Simplified check for Phase 3.
        In production, would use proper statistical tests.

        Args:
            baseline: Baseline metrics
            candidate: Candidate metrics

        Returns:
            True if significant
        """
        # Simplified: Consider significant if we have enough samples
        # and the difference is non-trivial
        min_samples = 10
        if baseline.num_runs < min_samples or candidate.num_runs < min_samples:
            return False

        # Check if differences are large enough to be meaningful
        success_rate_diff = abs(candidate.success_rate - baseline.success_rate)
        duration_diff_pct = abs(
            (candidate.avg_duration - baseline.avg_duration) / baseline.avg_duration
            if baseline.avg_duration > 0 else 0
        )

        # Significant if >2% success rate change OR >10% duration change
        return success_rate_diff > 0.02 or duration_diff_pct > 0.10

    def _check_success_criteria(
        self,
        success_rate_delta: float,
        avg_duration_pct_change: float,
        is_significant: bool
    ) -> bool:
        """Check if results meet success criteria.

        Args:
            success_rate_delta: Change in success rate
            avg_duration_pct_change: Percentage change in duration
            is_significant: Whether results are statistically significant

        Returns:
            True if criteria met
        """
        # Must be statistically significant
        if not is_significant:
            return False

        # Check success rate improvement
        min_improvement = self.success_criteria.get(
            'min_success_rate_improvement', 0.0
        )
        if success_rate_delta < min_improvement:
            return False

        # Check latency doesn't increase too much
        max_increase = self.success_criteria.get('max_latency_increase', 0.2)
        if avg_duration_pct_change > max_increase:
            return False

        return True

    def _generate_comparison_summary(
        self,
        success_rate_delta: float,
        avg_duration_delta: float,
        is_improvement: bool,
        is_regression: bool
    ) -> str:
        """Generate human-readable comparison summary.

        Args:
            success_rate_delta: Change in success rate
            avg_duration_delta: Change in duration
            is_improvement: Whether it's an improvement
            is_regression: Whether it's a regression

        Returns:
            Summary string
        """
        parts = []

        # Success rate
        if abs(success_rate_delta) > 0.01:
            direction = "improved" if success_rate_delta > 0 else "decreased"
            parts.append(
                f"Success rate {direction} by {abs(success_rate_delta):.1%}"
            )

        # Latency
        if abs(avg_duration_delta) > 0.001:
            direction = "improved" if avg_duration_delta < 0 else "increased"
            parts.append(
                f"Latency {direction} by {abs(avg_duration_delta):.3f}s"
            )

        # Overall verdict
        if is_improvement:
            verdict = "Overall improvement"
        elif is_regression:
            verdict = "Overall regression"
        else:
            verdict = "Mixed results"

        if parts:
            return f"{verdict}: {', '.join(parts)}"
        else:
            return verdict

    def _determine_test_status(self, comparison: ComparisonResult) -> TestStatus:
        """Determine overall test status from comparison.

        Args:
            comparison: Comparison result

        Returns:
            TestStatus
        """
        if comparison.is_regression:
            return TestStatus.FAILED
        elif comparison.meets_success_criteria:
            return TestStatus.PASSED
        elif comparison.is_improvement and comparison.is_significant:
            return TestStatus.PASSED
        elif not comparison.is_significant:
            return TestStatus.INCONCLUSIVE
        else:
            return TestStatus.FAILED

    def _generate_test_recommendations(
        self,
        comparison: ComparisonResult
    ) -> List[str]:
        """Generate recommendations based on test results.

        Args:
            comparison: Comparison result

        Returns:
            List of recommendations
        """
        recommendations = []

        if comparison.meets_success_criteria:
            recommendations.append(
                "Hypothesis passed all criteria - recommend deployment"
            )

        if comparison.is_improvement and not comparison.meets_success_criteria:
            recommendations.append(
                "Shows improvement but doesn't meet all criteria - "
                "consider adjusting criteria or re-testing"
            )

        if not comparison.is_significant:
            recommendations.append(
                "Results not statistically significant - "
                "consider running more tests or increasing sample size"
            )

        if comparison.is_regression:
            recommendations.append(
                "Hypothesis causes regression - DO NOT deploy"
            )

        if comparison.warnings:
            recommendations.append(
                f"Review warnings: {', '.join(comparison.warnings)}"
            )

        return recommendations

    def _mock_test_hypothesis(
        self,
        hypothesis: ImprovementHypothesis,
        test_id: str,
        started_at: datetime
    ) -> TestResult:
        """Mock test for unit testing without running actual graphs.

        Args:
            hypothesis: Hypothesis to test
            test_id: Test identifier
            started_at: Test start time

        Returns:
            TestResult with mock data
        """
        # Create mock baseline metrics
        baseline = TestMetrics(
            num_runs=self.num_baseline_runs,
            success_count=18,
            failure_count=2,
            success_rate=0.9,
            avg_duration=0.5,
            p50_duration=0.48,
            p95_duration=0.65,
            p99_duration=0.70
        )

        # Create mock candidate metrics (improved)
        candidate = TestMetrics(
            num_runs=self.num_candidate_runs,
            success_count=19,
            failure_count=1,
            success_rate=0.95,
            avg_duration=0.4,
            p50_duration=0.38,
            p95_duration=0.52,
            p99_duration=0.58
        )

        # Compare
        comparison = self._compare_metrics(baseline, candidate)

        # Determine status
        status = self._determine_test_status(comparison)

        # Generate recommendations
        recommendations = self._generate_test_recommendations(comparison)

        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()

        return TestResult(
            hypothesis_id=hypothesis.hypothesis_id,
            test_id=test_id,
            status=status,
            num_baseline_runs=self.num_baseline_runs,
            num_candidate_runs=self.num_candidate_runs,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            comparison=comparison,
            success_criteria_met=comparison.meets_success_criteria,
            success_criteria=self.success_criteria,
            recommendations=recommendations
        )
