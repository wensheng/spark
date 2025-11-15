"""Pattern extraction for RSI learning.

This module provides pattern extraction from experience database to improve
hypothesis generation over time through meta-learning.
"""

import logging
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass

from spark.rsi.experience_db import ExperienceDatabase

logger = logging.getLogger(__name__)


@dataclass
class ExtractedPattern:
    """A pattern extracted from experience."""
    pattern_id: str
    pattern_type: str  # success, failure, improvement, regression
    hypothesis_type: str  # What type of hypothesis this pattern applies to
    context: Dict[str, Any]  # Context in which pattern applies
    recommendation: str  # What to do when this pattern is detected
    confidence: float  # 0.0 to 1.0
    evidence_count: int  # Number of examples supporting this pattern
    success_rate: float  # Success rate when this pattern is followed


class PatternExtractor:
    """Extracts learnable patterns from experience database.

    The PatternExtractor analyzes historical hypothesis attempts to identify:
    1. Successful patterns: What works and should be repeated
    2. Failure patterns: What doesn't work and should be avoided
    3. Improvement patterns: What leads to actual improvements
    4. Regression patterns: What causes regressions

    These patterns are used to improve future hypothesis generation through
    meta-learning, making the system smarter over time.

    Example:
        extractor = PatternExtractor(experience_db)
        patterns = await extractor.extract_patterns()

        # Use patterns to guide hypothesis generation
        for pattern in patterns:
            if pattern.pattern_type == 'success':
                # Apply this pattern to new hypotheses
                ...
    """

    def __init__(
        self,
        experience_db: ExperienceDatabase,
        min_evidence_count: int = 3,
        min_confidence: float = 0.6
    ):
        """Initialize the PatternExtractor.

        Args:
            experience_db: Experience database to extract from
            min_evidence_count: Minimum examples needed to establish pattern
            min_confidence: Minimum confidence threshold for patterns
        """
        self.experience_db = experience_db
        self.min_evidence_count = min_evidence_count
        self.min_confidence = min_confidence

    async def extract_patterns(
        self,
        graph_id: Optional[str] = None
    ) -> List[ExtractedPattern]:
        """Extract all patterns from experience database.

        Args:
            graph_id: Optional filter for specific graph

        Returns:
            List of extracted patterns
        """
        logger.info("Extracting patterns from experience database")

        patterns = []

        # Extract different pattern types
        patterns.extend(await self._extract_success_patterns(graph_id))
        patterns.extend(await self._extract_failure_patterns(graph_id))
        patterns.extend(await self._extract_improvement_patterns(graph_id))
        patterns.extend(await self._extract_regression_patterns(graph_id))

        # Filter by confidence and evidence
        filtered_patterns = [
            p for p in patterns
            if p.confidence >= self.min_confidence
            and p.evidence_count >= self.min_evidence_count
        ]

        logger.info(
            f"Extracted {len(filtered_patterns)} patterns "
            f"({len(patterns)} total, {len(patterns) - len(filtered_patterns)} filtered out)"
        )

        return filtered_patterns

    async def _extract_success_patterns(
        self,
        graph_id: Optional[str] = None
    ) -> List[ExtractedPattern]:
        """Extract patterns from successful deployments.

        Analyzes what types of changes tend to succeed and why.
        """
        patterns = []

        # Query successful hypotheses
        successful = await self.experience_db.query_hypotheses(
            graph_id=graph_id,
            deployed=True
        )

        # Filter to only successful deployments (not rolled back)
        successful = [
            h for h in successful
            if h.get('outcome') and h['outcome'].get('successful', False)
        ]

        if not successful:
            return patterns

        # Group by hypothesis type
        by_type = defaultdict(list)
        for hyp in successful:
            by_type[hyp['hypothesis_type']].append(hyp)

        # Extract patterns for each type
        for hyp_type, hypotheses in by_type.items():
            if len(hypotheses) < self.min_evidence_count:
                continue

            # Calculate success rate for this type
            success_rate = len(hypotheses) / max(
                len(await self.experience_db.query_hypotheses(
                    graph_id=graph_id,
                    hypothesis_type=hyp_type
                )), 1
            )

            if success_rate >= self.min_confidence:
                patterns.append(ExtractedPattern(
                    pattern_id=f"success_{hyp_type}",
                    pattern_type="success",
                    hypothesis_type=hyp_type,
                    context={'graph_id': graph_id} if graph_id else {},
                    recommendation=f"Continue using {hyp_type} - high success rate",
                    confidence=success_rate,
                    evidence_count=len(hypotheses),
                    success_rate=success_rate
                ))

        return patterns

    async def _extract_failure_patterns(
        self,
        graph_id: Optional[str] = None
    ) -> List[ExtractedPattern]:
        """Extract patterns from failed deployments.

        Analyzes what types of changes tend to fail and should be avoided.
        """
        patterns = []

        # Query all hypotheses
        all_hypotheses = await self.experience_db.query_hypotheses(
            graph_id=graph_id
        )

        # Find failed ones (rolled back or never deployed due to test failure)
        failed = []
        for hyp in all_hypotheses:
            # Check if rolled back
            if hyp.get('outcome') and hyp['outcome'].get('rolled_back', False):
                failed.append(hyp)
            # Check if test failed
            elif hyp.get('test_results') and not hyp.get('deployed', False):
                test_status = hyp['test_results'].get('status')
                if test_status in ('failed', 'inconclusive'):
                    failed.append(hyp)

        if not failed:
            return patterns

        # Group by hypothesis type
        by_type = defaultdict(list)
        for hyp in failed:
            by_type[hyp['hypothesis_type']].append(hyp)

        # Extract failure patterns
        for hyp_type, hypotheses in by_type.items():
            if len(hypotheses) < self.min_evidence_count:
                continue

            # Calculate failure rate
            total_of_type = len([
                h for h in all_hypotheses
                if h['hypothesis_type'] == hyp_type
            ])
            failure_rate = len(hypotheses) / max(total_of_type, 1)

            if failure_rate >= self.min_confidence:
                # Analyze failure reasons
                rollback_reasons = [
                    hyp.get('outcome', {}).get('rollback_reason')
                    for hyp in hypotheses
                    if hyp.get('outcome', {}).get('rollback_reason')
                ]
                common_reasons = Counter(rollback_reasons).most_common(3)

                patterns.append(ExtractedPattern(
                    pattern_id=f"failure_{hyp_type}",
                    pattern_type="failure",
                    hypothesis_type=hyp_type,
                    context={
                        'graph_id': graph_id,
                        'common_reasons': [r[0] for r in common_reasons]
                    } if graph_id else {
                        'common_reasons': [r[0] for r in common_reasons]
                    },
                    recommendation=f"Avoid {hyp_type} - high failure rate",
                    confidence=failure_rate,
                    evidence_count=len(hypotheses),
                    success_rate=1.0 - failure_rate
                ))

        return patterns

    async def _extract_improvement_patterns(
        self,
        graph_id: Optional[str] = None
    ) -> List[ExtractedPattern]:
        """Extract patterns about what actually improves performance.

        Analyzes test results to see which types of changes lead to
        measurable improvements.
        """
        patterns = []

        # Query hypotheses with test results
        all_hypotheses = await self.experience_db.query_hypotheses(
            graph_id=graph_id
        )

        # Find ones with positive improvements
        improved = []
        for hyp in all_hypotheses:
            test_results = hyp.get('test_results')
            if not test_results or not test_results.get('comparison'):
                continue

            comp = test_results['comparison']
            if comp.get('is_improvement', False):
                improved.append({
                    'hypothesis': hyp,
                    'success_rate_delta': comp.get('success_rate_delta', 0),
                    'latency_delta': comp.get('avg_duration_delta', 0)
                })

        if not improved:
            return patterns

        # Group by hypothesis type
        by_type = defaultdict(list)
        for item in improved:
            hyp_type = item['hypothesis']['hypothesis_type']
            by_type[hyp_type].append(item)

        # Extract improvement patterns
        for hyp_type, items in by_type.items():
            if len(items) < self.min_evidence_count:
                continue

            # Calculate average improvements
            avg_success_delta = sum(
                item['success_rate_delta'] for item in items
            ) / len(items)
            avg_latency_delta = sum(
                item['latency_delta'] for item in items
            ) / len(items)

            # Confidence based on consistency
            success_deltas = [item['success_rate_delta'] for item in items]
            consistency = 1.0 - (max(success_deltas) - min(success_deltas))
            confidence = min(max(consistency, 0.0), 1.0)

            if confidence >= self.min_confidence:
                patterns.append(ExtractedPattern(
                    pattern_id=f"improvement_{hyp_type}",
                    pattern_type="improvement",
                    hypothesis_type=hyp_type,
                    context={
                        'graph_id': graph_id,
                        'avg_success_delta': avg_success_delta,
                        'avg_latency_delta': avg_latency_delta
                    } if graph_id else {
                        'avg_success_delta': avg_success_delta,
                        'avg_latency_delta': avg_latency_delta
                    },
                    recommendation=f"Prioritize {hyp_type} - consistently improves performance",
                    confidence=confidence,
                    evidence_count=len(items),
                    success_rate=1.0  # All showed improvement
                ))

        return patterns

    async def _extract_regression_patterns(
        self,
        graph_id: Optional[str] = None
    ) -> List[ExtractedPattern]:
        """Extract patterns about what causes regressions.

        Analyzes deployment rollbacks to identify problematic patterns.
        """
        patterns = []

        # Query rolled back deployments
        all_hypotheses = await self.experience_db.query_hypotheses(
            graph_id=graph_id,
            deployed=True
        )

        # Find rolled back ones
        rolled_back = [
            hyp for hyp in all_hypotheses
            if hyp.get('outcome', {}).get('rolled_back', False)
        ]

        if not rolled_back:
            return patterns

        # Group by hypothesis type
        by_type = defaultdict(list)
        for hyp in rolled_back:
            by_type[hyp['hypothesis_type']].append(hyp)

        # Extract regression patterns
        for hyp_type, hypotheses in by_type.items():
            if len(hypotheses) < self.min_evidence_count:
                continue

            # Get rollback reasons
            reasons = [
                hyp.get('outcome', {}).get('rollback_reason')
                for hyp in hypotheses
            ]
            reason_counts = Counter(reasons)
            most_common_reason = reason_counts.most_common(1)[0] if reason_counts else (None, 0)

            # Confidence based on how often this type is rolled back
            total_deployed = len([
                h for h in all_hypotheses
                if h['hypothesis_type'] == hyp_type
            ])
            rollback_rate = len(hypotheses) / max(total_deployed, 1)

            if rollback_rate >= self.min_confidence:
                patterns.append(ExtractedPattern(
                    pattern_id=f"regression_{hyp_type}",
                    pattern_type="regression",
                    hypothesis_type=hyp_type,
                    context={
                        'graph_id': graph_id,
                        'common_reason': most_common_reason[0] if most_common_reason[0] else "Unknown"
                    } if graph_id else {
                        'common_reason': most_common_reason[0] if most_common_reason[0] else "Unknown"
                    },
                    recommendation=f"Be cautious with {hyp_type} - high rollback rate",
                    confidence=rollback_rate,
                    evidence_count=len(hypotheses),
                    success_rate=1.0 - rollback_rate
                ))

        return patterns

    def get_recommendations_for_hypothesis_type(
        self,
        patterns: List[ExtractedPattern],
        hypothesis_type: str
    ) -> List[str]:
        """Get recommendations for a specific hypothesis type.

        Args:
            patterns: Extracted patterns
            hypothesis_type: Type of hypothesis

        Returns:
            List of recommendations
        """
        recommendations = []

        for pattern in patterns:
            if pattern.hypothesis_type == hypothesis_type:
                rec = f"[{pattern.pattern_type.upper()}] {pattern.recommendation}"
                rec += f" (confidence: {pattern.confidence:.1%}, evidence: {pattern.evidence_count})"
                recommendations.append(rec)

        return recommendations

    def should_avoid_hypothesis_type(
        self,
        patterns: List[ExtractedPattern],
        hypothesis_type: str,
        threshold: float = 0.7
    ) -> bool:
        """Determine if a hypothesis type should be avoided.

        Args:
            patterns: Extracted patterns
            hypothesis_type: Type to check
            threshold: Confidence threshold for avoidance

        Returns:
            True if should avoid, False otherwise
        """
        for pattern in patterns:
            if pattern.hypothesis_type == hypothesis_type:
                if pattern.pattern_type in ('failure', 'regression'):
                    if pattern.confidence >= threshold:
                        return True
        return False

    def get_priority_score(
        self,
        patterns: List[ExtractedPattern],
        hypothesis_type: str
    ) -> float:
        """Calculate priority score for a hypothesis type.

        Higher score means higher priority. Considers success patterns,
        improvement patterns, and avoids failure/regression patterns.

        Args:
            patterns: Extracted patterns
            hypothesis_type: Type to score

        Returns:
            Priority score (0.0 to 1.0, higher is better)
        """
        score = 0.5  # Start neutral

        for pattern in patterns:
            if pattern.hypothesis_type != hypothesis_type:
                continue

            if pattern.pattern_type == 'success':
                score += 0.2 * pattern.confidence
            elif pattern.pattern_type == 'improvement':
                score += 0.3 * pattern.confidence
            elif pattern.pattern_type == 'failure':
                score -= 0.3 * pattern.confidence
            elif pattern.pattern_type == 'regression':
                score -= 0.2 * pattern.confidence

        # Clamp to [0, 1]
        return max(0.0, min(1.0, score))
