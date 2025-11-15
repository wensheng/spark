"""Multi-objective optimization for RSI hypothesis selection.

This module provides utilities for optimizing across multiple competing objectives
(speed, cost, quality, reliability) when selecting improvement hypotheses.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

from spark.rsi.types import (
    ImprovementHypothesis,
    TestResult,
    ComparisonResult,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Types
# ============================================================================

@dataclass
class OptimizationObjectives:
    """Defines optimization objectives and weights.

    Weights should sum to 1.0 for normalized scoring.
    """
    minimize_latency: float = 0.4
    minimize_cost: float = 0.3
    maximize_quality: float = 0.2
    maximize_reliability: float = 0.1

    # Constraints (hard limits)
    max_acceptable_cost_increase: float = 0.10  # 10%
    min_acceptable_success_rate: float = 0.95
    max_acceptable_latency_increase: float = 2.0  # seconds

    def __post_init__(self):
        """Validate weights."""
        total = (
            self.minimize_latency +
            self.minimize_cost +
            self.maximize_quality +
            self.maximize_reliability
        )
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Objective weights sum to {total:.2f}, not 1.0")


@dataclass
class MultiObjectiveScore:
    """Score for a hypothesis across multiple objectives."""
    hypothesis_id: str
    total_score: float

    # Individual objective scores (0-1, higher is better)
    latency_score: float
    cost_score: float
    quality_score: float
    reliability_score: float

    # Constraint satisfaction
    meets_constraints: bool
    constraint_violations: List[str] = field(default_factory=list)

    # Raw metrics
    latency_delta: float = 0.0
    cost_delta: float = 0.0
    success_rate_delta: float = 0.0


@dataclass
class RankedHypothesis:
    """A hypothesis ranked by multi-objective score."""
    hypothesis: ImprovementHypothesis
    test_result: TestResult
    score: MultiObjectiveScore
    rank: int


@dataclass
class ParetoFrontier:
    """Pareto-optimal solutions (no solution dominates another)."""
    solutions: List[RankedHypothesis]
    dominated_solutions: List[RankedHypothesis]
    total_evaluated: int


# ============================================================================
# Multi-Objective Optimizer
# ============================================================================

class MultiObjectiveOptimizer:
    """Optimizes for multiple competing objectives.

    Uses weighted sum approach for scoring and Pareto frontier analysis
    for finding optimal trade-offs.
    """

    def __init__(self, objectives: OptimizationObjectives):
        """Initialize optimizer.

        Args:
            objectives: Optimization objectives and weights
        """
        self.objectives = objectives

    async def evaluate_hypothesis(
        self,
        hypothesis: ImprovementHypothesis,
        test_result: TestResult
    ) -> MultiObjectiveScore:
        """Evaluate hypothesis against all objectives.

        Args:
            hypothesis: The hypothesis
            test_result: Test result with comparison

        Returns:
            Multi-objective score
        """
        if test_result.comparison is None:
            logger.warning(f"No comparison available for hypothesis {hypothesis.hypothesis_id}")
            return MultiObjectiveScore(
                hypothesis_id=hypothesis.hypothesis_id,
                total_score=0.0,
                latency_score=0.0,
                cost_score=0.0,
                quality_score=0.0,
                reliability_score=0.0,
                meets_constraints=False,
                constraint_violations=["No comparison data available"]
            )

        comparison = test_result.comparison

        # Calculate objective scores (0-1, higher is better)
        latency_score = self._score_latency(comparison.avg_duration_delta)
        cost_score = self._score_cost(comparison.cost_delta if comparison.cost_delta else 0.0)
        quality_score = self._score_quality(comparison.success_rate_delta)
        reliability_score = self._score_reliability(comparison)

        # Weighted sum
        total_score = (
            self.objectives.minimize_latency * latency_score +
            self.objectives.minimize_cost * cost_score +
            self.objectives.maximize_quality * quality_score +
            self.objectives.maximize_reliability * reliability_score
        )

        # Check constraints
        meets_constraints, violations = self._check_constraints(comparison)

        return MultiObjectiveScore(
            hypothesis_id=hypothesis.hypothesis_id,
            total_score=total_score,
            latency_score=latency_score,
            cost_score=cost_score,
            quality_score=quality_score,
            reliability_score=reliability_score,
            meets_constraints=meets_constraints,
            constraint_violations=violations,
            latency_delta=comparison.avg_duration_delta,
            cost_delta=comparison.cost_delta if comparison.cost_delta else 0.0,
            success_rate_delta=comparison.success_rate_delta,
        )

    async def rank_hypotheses(
        self,
        hypotheses: List[Tuple[ImprovementHypothesis, TestResult]]
    ) -> List[RankedHypothesis]:
        """Rank hypotheses by multi-objective scores.

        Args:
            hypotheses: List of (hypothesis, test_result) tuples

        Returns:
            List of ranked hypotheses, sorted by total score descending
        """
        scored = []

        for hypothesis, test_result in hypotheses:
            score = await self.evaluate_hypothesis(hypothesis, test_result)
            scored.append(RankedHypothesis(
                hypothesis=hypothesis,
                test_result=test_result,
                score=score,
                rank=0  # Will be set after sorting
            ))

        # Sort by total score (descending)
        scored.sort(key=lambda x: x.score.total_score, reverse=True)

        # Assign ranks
        for i, ranked_hyp in enumerate(scored, 1):
            ranked_hyp.rank = i

        return scored

    async def find_pareto_frontier(
        self,
        hypotheses: List[Tuple[ImprovementHypothesis, TestResult]]
    ) -> ParetoFrontier:
        """Find Pareto-optimal solutions.

        A solution is Pareto-optimal if no other solution is strictly better
        in all objectives.

        Args:
            hypotheses: List of (hypothesis, test_result) tuples

        Returns:
            Pareto frontier with optimal and dominated solutions
        """
        # Evaluate all hypotheses
        scored = []
        for hypothesis, test_result in hypotheses:
            score = await self.evaluate_hypothesis(hypothesis, test_result)
            ranked_hyp = RankedHypothesis(
                hypothesis=hypothesis,
                test_result=test_result,
                score=score,
                rank=0
            )
            scored.append(ranked_hyp)

        # Find Pareto frontier
        pareto_optimal = []
        dominated = []

        for i, candidate in enumerate(scored):
            is_dominated = False

            for j, other in enumerate(scored):
                if i == j:
                    continue

                # Check if 'other' dominates 'candidate'
                # (strictly better in all objectives)
                if self._dominates(other.score, candidate.score):
                    is_dominated = True
                    break

            if is_dominated:
                dominated.append(candidate)
            else:
                pareto_optimal.append(candidate)

        # Sort Pareto frontier by total score
        pareto_optimal.sort(key=lambda x: x.score.total_score, reverse=True)

        # Assign ranks
        for i, hyp in enumerate(pareto_optimal, 1):
            hyp.rank = i

        return ParetoFrontier(
            solutions=pareto_optimal,
            dominated_solutions=dominated,
            total_evaluated=len(scored)
        )

    def visualize_trade_offs(
        self,
        pareto_frontier: ParetoFrontier
    ) -> Dict[str, Any]:
        """Generate trade-off visualization data.

        Returns data structure for 2D/3D scatter plots showing trade-offs
        between objectives.

        Args:
            pareto_frontier: Pareto frontier

        Returns:
            Visualization data
        """
        points = []

        for solution in pareto_frontier.solutions:
            score = solution.score
            points.append({
                'hypothesis_id': solution.hypothesis.hypothesis_id,
                'latency_score': score.latency_score,
                'cost_score': score.cost_score,
                'quality_score': score.quality_score,
                'reliability_score': score.reliability_score,
                'total_score': score.total_score,
                'meets_constraints': score.meets_constraints,
                # Raw metrics for tooltips
                'latency_delta': score.latency_delta,
                'cost_delta': score.cost_delta,
                'success_rate_delta': score.success_rate_delta,
            })

        return {
            'pareto_frontier': points,
            'dominated_solutions': [
                {
                    'hypothesis_id': s.hypothesis.hypothesis_id,
                    'total_score': s.score.total_score,
                }
                for s in pareto_frontier.dominated_solutions
            ],
            'total_evaluated': pareto_frontier.total_evaluated,
            'pareto_count': len(pareto_frontier.solutions),
        }

    # ========================================================================
    # Scoring Methods
    # ========================================================================

    def _score_latency(self, latency_delta: float) -> float:
        """Score latency improvement (0-1, higher is better).

        Negative delta = faster = better score.

        Args:
            latency_delta: Change in latency (seconds)

        Returns:
            Score (0-1)
        """
        # Normalize: -2s = 1.0, 0s = 0.5, +2s = 0.0
        normalized = 0.5 - (latency_delta / 4.0)
        return max(0.0, min(1.0, normalized))

    def _score_cost(self, cost_delta: float) -> float:
        """Score cost improvement (0-1, higher is better).

        Negative delta = cheaper = better score.

        Args:
            cost_delta: Change in cost (percentage)

        Returns:
            Score (0-1)
        """
        # Normalize: -20% = 1.0, 0% = 0.5, +20% = 0.0
        normalized = 0.5 - (cost_delta / 0.4)
        return max(0.0, min(1.0, normalized))

    def _score_quality(self, success_rate_delta: float) -> float:
        """Score quality improvement (0-1, higher is better).

        Positive delta = higher success rate = better score.

        Args:
            success_rate_delta: Change in success rate

        Returns:
            Score (0-1)
        """
        # Normalize: +20% = 1.0, 0% = 0.5, -20% = 0.0
        normalized = 0.5 + (success_rate_delta / 0.4)
        return max(0.0, min(1.0, normalized))

    def _score_reliability(self, comparison: ComparisonResult) -> float:
        """Score reliability improvement (0-1, higher is better).

        Based on statistical significance and consistency.

        Args:
            comparison: Comparison result

        Returns:
            Score (0-1)
        """
        score = 0.5  # Baseline

        # Bonus for statistical significance
        if comparison.is_significant:
            score += 0.2

        # Bonus for no regression
        if not comparison.is_regression:
            score += 0.2

        # Bonus for meeting success criteria
        if comparison.meets_success_criteria:
            score += 0.1

        return max(0.0, min(1.0, score))

    # ========================================================================
    # Constraint Checking
    # ========================================================================

    def _check_constraints(
        self,
        comparison: ComparisonResult
    ) -> Tuple[bool, List[str]]:
        """Check if solution meets all constraints.

        Args:
            comparison: Comparison result

        Returns:
            Tuple of (meets_constraints, violation_messages)
        """
        violations = []

        # Cost constraint
        cost_delta = comparison.cost_delta if comparison.cost_delta else 0.0
        if cost_delta > self.objectives.max_acceptable_cost_increase:
            violations.append(
                f"Cost increase {cost_delta:+.1%} exceeds limit {self.objectives.max_acceptable_cost_increase:.1%}"
            )

        # Success rate constraint
        candidate_success_rate = comparison.candidate_metrics.success_rate
        if candidate_success_rate < self.objectives.min_acceptable_success_rate:
            violations.append(
                f"Success rate {candidate_success_rate:.1%} below minimum {self.objectives.min_acceptable_success_rate:.1%}"
            )

        # Latency constraint
        if comparison.avg_duration_delta > self.objectives.max_acceptable_latency_increase:
            violations.append(
                f"Latency increase {comparison.avg_duration_delta:+.2f}s exceeds limit {self.objectives.max_acceptable_latency_increase:.2f}s"
            )

        return (len(violations) == 0, violations)

    def _dominates(self, score1: MultiObjectiveScore, score2: MultiObjectiveScore) -> bool:
        """Check if score1 dominates score2 (strictly better in all objectives).

        Args:
            score1: First score
            score2: Second score

        Returns:
            True if score1 dominates score2
        """
        # Must be strictly better in at least one objective
        # and better or equal in all others

        better_in_some = False
        worse_in_any = False

        objectives = [
            ('latency_score', score1.latency_score, score2.latency_score),
            ('cost_score', score1.cost_score, score2.cost_score),
            ('quality_score', score1.quality_score, score2.quality_score),
            ('reliability_score', score1.reliability_score, score2.reliability_score),
        ]

        for name, val1, val2 in objectives:
            if val1 > val2:
                better_in_some = True
            elif val1 < val2:
                worse_in_any = True

        return better_in_some and not worse_in_any
