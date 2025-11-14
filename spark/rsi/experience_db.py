"""Experience database for storing RSI learning data.

Phase 1: Basic in-memory implementation
Phase 2+: Will add SQLite and PostgreSQL backends
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import asdict
import logging

logger = logging.getLogger(__name__)


class ExperienceDatabase:
    """Stores outcomes of improvement attempts for learning.

    Phase 1 implementation: In-memory storage
    This provides the interface that will be used by future phases.
    """

    def __init__(self):
        """Initialize experience database with in-memory storage."""
        self._hypotheses: Dict[str, Dict[str, Any]] = {}
        self._patterns: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Initialize the database.

        For in-memory implementation, this is a no-op.
        SQLite/PostgreSQL implementations will create tables here.
        """
        logger.info("Initialized in-memory experience database")

    async def store_hypothesis(
        self,
        hypothesis_id: str,
        graph_id: str,
        graph_version_baseline: str,
        hypothesis_type: str,
        proposal: Dict[str, Any],
        target_node: Optional[str] = None
    ):
        """Store a new hypothesis.

        Args:
            hypothesis_id: Unique hypothesis identifier
            graph_id: Graph being improved
            graph_version_baseline: Baseline version
            hypothesis_type: Type of improvement
            proposal: Full proposal details
            target_node: Specific node being modified (optional)
        """
        self._hypotheses[hypothesis_id] = {
            'hypothesis_id': hypothesis_id,
            'timestamp': datetime.now().timestamp(),
            'graph_id': graph_id,
            'graph_version_baseline': graph_version_baseline,
            'hypothesis_type': hypothesis_type,
            'target_node': target_node,
            'proposal': proposal,
            'test_results': None,
            'deployed': False,
            'outcome': None,
            'lessons': [],
            'patterns': [],
            'created_at': datetime.now().isoformat(),
        }

        logger.info(f"Stored hypothesis {hypothesis_id} for graph {graph_id}")

    async def update_test_results(
        self,
        hypothesis_id: str,
        test_results: Dict[str, Any]
    ):
        """Update hypothesis with test results.

        Args:
            hypothesis_id: Hypothesis to update
            test_results: Test results data
        """
        if hypothesis_id not in self._hypotheses:
            logger.warning(f"Hypothesis {hypothesis_id} not found")
            return

        self._hypotheses[hypothesis_id]['test_results'] = test_results
        logger.info(f"Updated test results for hypothesis {hypothesis_id}")

    async def update_deployment_outcome(
        self,
        hypothesis_id: str,
        deployed: bool,
        outcome: Dict[str, Any],
        lessons: List[str],
        patterns: List[str]
    ):
        """Update hypothesis with deployment outcome and learnings.

        Args:
            hypothesis_id: Hypothesis to update
            deployed: Whether it was deployed
            outcome: Deployment outcome data
            lessons: Learned lessons
            patterns: Identified patterns
        """
        if hypothesis_id not in self._hypotheses:
            logger.warning(f"Hypothesis {hypothesis_id} not found")
            return

        self._hypotheses[hypothesis_id].update({
            'deployed': deployed,
            'outcome': outcome,
            'lessons': lessons,
            'patterns': patterns,
        })

        logger.info(
            f"Updated outcome for hypothesis {hypothesis_id}: "
            f"deployed={deployed}, {len(lessons)} lessons, {len(patterns)} patterns"
        )

    async def query_hypotheses(
        self,
        graph_id: Optional[str] = None,
        hypothesis_type: Optional[str] = None,
        deployed: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query hypotheses.

        Args:
            graph_id: Filter by graph ID
            hypothesis_type: Filter by type
            deployed: Filter by deployment status
            limit: Maximum results

        Returns:
            List of hypothesis records
        """
        results = []

        for hyp in self._hypotheses.values():
            # Apply filters
            if graph_id is not None and hyp['graph_id'] != graph_id:
                continue
            if hypothesis_type is not None and hyp['hypothesis_type'] != hypothesis_type:
                continue
            if deployed is not None and hyp['deployed'] != deployed:
                continue

            results.append(hyp.copy())

        # Sort by timestamp (most recent first)
        results.sort(key=lambda x: x['timestamp'], reverse=True)

        # Limit results
        return results[:limit]

    async def query_successful_patterns(
        self,
        hypothesis_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query successful improvement patterns.

        Args:
            hypothesis_type: Filter by hypothesis type
            limit: Maximum results

        Returns:
            List of successful patterns
        """
        results = []

        for hyp in self._hypotheses.values():
            # Only include successfully deployed hypotheses
            if not hyp['deployed']:
                continue

            # Filter by type
            if hypothesis_type is not None and hyp['hypothesis_type'] != hypothesis_type:
                continue

            # Extract pattern information
            if hyp.get('patterns'):
                results.append({
                    'hypothesis_type': hyp['hypothesis_type'],
                    'target_node': hyp['target_node'],
                    'patterns': hyp['patterns'],
                    'outcome': hyp['outcome'],
                    'timestamp': hyp['timestamp'],
                })

        # Sort by timestamp (most recent first)
        results.sort(key=lambda x: x['timestamp'], reverse=True)

        return results[:limit]

    async def query_failure_patterns(
        self,
        hypothesis_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query failed improvement attempts to learn what doesn't work.

        Args:
            hypothesis_type: Filter by hypothesis type
            limit: Maximum results

        Returns:
            List of failure patterns
        """
        results = []

        for hyp in self._hypotheses.values():
            # Only include tested but not deployed hypotheses
            if hyp['deployed'] or hyp['test_results'] is None:
                continue

            # Filter by type
            if hypothesis_type is not None and hyp['hypothesis_type'] != hypothesis_type:
                continue

            results.append({
                'hypothesis_type': hyp['hypothesis_type'],
                'target_node': hyp['target_node'],
                'proposal': hyp['proposal'],
                'test_results': hyp['test_results'],
                'timestamp': hyp['timestamp'],
            })

        # Sort by timestamp (most recent first)
        results.sort(key=lambda x: x['timestamp'], reverse=True)

        return results[:limit]

    async def store_pattern(
        self,
        pattern_id: str,
        pattern_name: str,
        pattern_type: str,
        condition: Dict[str, Any],
        recommendation: Dict[str, Any],
        applicable_to_graphs: Optional[List[str]] = None
    ):
        """Store a learned pattern.

        Args:
            pattern_id: Unique pattern identifier
            pattern_name: Human-readable name
            pattern_type: Type of pattern (hypothesis type)
            condition: When this pattern applies
            recommendation: What to do
            applicable_to_graphs: Graph IDs this works for
        """
        self._patterns[pattern_id] = {
            'pattern_id': pattern_id,
            'pattern_name': pattern_name,
            'pattern_type': pattern_type,
            'condition': condition,
            'recommendation': recommendation,
            'success_count': 0,
            'failure_count': 0,
            'applicable_to_graphs': applicable_to_graphs or [],
            'discovered_at': datetime.now().isoformat(),
            'last_used': None,
            'usage_count': 0,
        }

        logger.info(f"Stored pattern {pattern_id}: {pattern_name}")

    async def query_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_success_rate: float = 0.5,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query learned patterns.

        Args:
            pattern_type: Filter by pattern type
            min_success_rate: Minimum success rate
            limit: Maximum results

        Returns:
            List of patterns
        """
        results = []

        for pattern in self._patterns.values():
            # Filter by type
            if pattern_type is not None and pattern['pattern_type'] != pattern_type:
                continue

            # Calculate success rate
            total = pattern['success_count'] + pattern['failure_count']
            success_rate = pattern['success_count'] / total if total > 0 else 0

            # Filter by success rate
            if success_rate < min_success_rate:
                continue

            # Add success rate to result
            result = pattern.copy()
            result['success_rate'] = success_rate
            results.append(result)

        # Sort by success rate, then usage count
        results.sort(
            key=lambda x: (x['success_rate'], x['usage_count']),
            reverse=True
        )

        return results[:limit]

    async def update_pattern_stats(
        self,
        pattern_id: str,
        success: bool
    ):
        """Update pattern statistics after use.

        Args:
            pattern_id: Pattern that was used
            success: Whether it was successful
        """
        if pattern_id not in self._patterns:
            logger.warning(f"Pattern {pattern_id} not found")
            return

        pattern = self._patterns[pattern_id]

        if success:
            pattern['success_count'] += 1
        else:
            pattern['failure_count'] += 1

        pattern['usage_count'] += 1
        pattern['last_used'] = datetime.now().isoformat()

        logger.info(
            f"Updated pattern {pattern_id} stats: "
            f"success_count={pattern['success_count']}, "
            f"failure_count={pattern['failure_count']}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics about stored data.

        Returns:
            Dict with database statistics
        """
        total_hypotheses = len(self._hypotheses)
        deployed_count = sum(1 for h in self._hypotheses.values() if h['deployed'])
        tested_count = sum(1 for h in self._hypotheses.values() if h['test_results'] is not None)

        # Count by hypothesis type
        type_counts = {}
        for hyp in self._hypotheses.values():
            hyp_type = hyp['hypothesis_type']
            type_counts[hyp_type] = type_counts.get(hyp_type, 0) + 1

        return {
            'total_hypotheses': total_hypotheses,
            'deployed_count': deployed_count,
            'tested_count': tested_count,
            'total_patterns': len(self._patterns),
            'hypothesis_types': type_counts,
        }

    async def close(self):
        """Close database connection.

        For in-memory implementation, this is a no-op.
        SQLite/PostgreSQL implementations will close connections here.
        """
        logger.info("Closed experience database")
