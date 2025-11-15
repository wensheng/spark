"""Edge optimization for RSI system.

This module analyzes graph edges to identify:
- Redundant edges (rarely/never traversed)
- Shortcut opportunities (frequently taken paths)
- Edge condition optimizations
"""

from typing import Dict, List, Optional, Any
from spark.rsi.types import (
    RedundantEdge,
    ShortcutOpportunity,
    OptimizedCondition,
)
from spark.rsi.introspection import GraphIntrospector
from spark.nodes.spec import EdgeSpec


class EdgeOptimizer:
    """Analyzes and optimizes graph edges.

    Capabilities:
    - Identify redundant edges (paths that are never taken)
    - Find shortcut opportunities (skip intermediate nodes)
    - Optimize edge conditions (simplify or strengthen)
    - Detect dead code paths
    """

    def __init__(
        self,
        redundant_threshold: float = 0.01,  # 1% traversal rate
        shortcut_min_frequency: int = 100,  # Minimum times path is taken
        enable_mock_mode: bool = False
    ):
        """Initialize the edge optimizer.

        Args:
            redundant_threshold: Max traversal rate to consider edge redundant
            shortcut_min_frequency: Minimum frequency to suggest shortcut
            enable_mock_mode: If True, use mock data instead of real analysis
        """
        self.redundant_threshold = redundant_threshold
        self.shortcut_min_frequency = shortcut_min_frequency
        self.enable_mock_mode = enable_mock_mode

    async def find_redundant_edges(
        self,
        graph_introspector: GraphIntrospector,
        telemetry_data: List[Dict[str, Any]]
    ) -> List[RedundantEdge]:
        """Find edges that are never or rarely traversed.

        Args:
            graph_introspector: Graph introspector with structure info
            telemetry_data: List of execution traces

        Returns:
            List of redundant edges with traversal statistics
        """
        if self.enable_mock_mode:
            return self._generate_mock_redundant_edges()

        redundant_edges = []

        # Get all edges from graph by iterating through nodes
        all_edges = []
        node_ids = graph_introspector.get_node_ids()
        for node_id in node_ids:
            edges_from_node = graph_introspector.get_edges_from_node(node_id)
            all_edges.extend(edges_from_node)

        # Count edge traversals from telemetry
        edge_traversal_counts = self._count_edge_traversals(telemetry_data)

        # Total number of executions
        total_executions = len(telemetry_data)

        if total_executions == 0:
            return redundant_edges

        # Analyze each edge
        for edge in all_edges:
            edge_id = self._get_edge_id(edge)
            traversal_count = edge_traversal_counts.get(edge_id, 0)
            traversal_rate = traversal_count / total_executions

            # Check if edge is redundant
            if traversal_rate <= self.redundant_threshold:
                recommendation = self._generate_redundant_edge_recommendation(
                    edge, traversal_rate
                )

                redundant_edge = RedundantEdge(
                    from_node=edge.get("from_node", edge.get("from_id", "")),
                    to_node=edge.get("to_node", edge.get("to_id", "")),
                    edge_condition=edge.get("condition"),
                    traversal_count=traversal_count,
                    total_executions=total_executions,
                    traversal_rate=traversal_rate,
                    recommendation=recommendation
                )
                redundant_edges.append(redundant_edge)

        # Sort by traversal rate (lowest first)
        redundant_edges.sort(key=lambda e: e.traversal_rate)

        return redundant_edges

    def _count_edge_traversals(
        self,
        telemetry_data: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Count how many times each edge was traversed.

        Args:
            telemetry_data: List of execution traces

        Returns:
            Dict mapping edge ID to traversal count
        """
        edge_counts: Dict[str, int] = {}

        for trace in telemetry_data:
            # Get execution path from trace
            path = trace.get("execution_path", [])
            if not path:
                continue

            # Count transitions between nodes (edges)
            for i in range(len(path) - 1):
                from_node = path[i]
                to_node = path[i + 1]
                edge_id = f"{from_node}->{to_node}"
                edge_counts[edge_id] = edge_counts.get(edge_id, 0) + 1

        return edge_counts

    def _get_edge_id(self, edge: Dict[str, Any]) -> str:
        """Get unique identifier for an edge.

        Args:
            edge: Edge specification

        Returns:
            Edge ID string
        """
        from_node = edge.get("from_node", edge.get("from_id", ""))
        to_node = edge.get("to_node", edge.get("to_id", ""))
        return f"{from_node}->{to_node}"

    def _generate_redundant_edge_recommendation(
        self,
        edge: Dict[str, Any],
        traversal_rate: float
    ) -> str:
        """Generate recommendation for redundant edge.

        Args:
            edge: Edge specification
            traversal_rate: How often edge is traversed

        Returns:
            Recommendation string
        """
        if traversal_rate == 0.0:
            return "Never traversed - consider removing unless needed for edge cases"
        elif traversal_rate < 0.005:  # Less than 0.5%
            return f"Rarely traversed ({traversal_rate:.2%}) - verify if necessary"
        else:
            return f"Low traversal rate ({traversal_rate:.2%}) - monitor for removal"

    async def find_shortcut_opportunities(
        self,
        graph_introspector: GraphIntrospector,
        execution_patterns: Dict[str, List[str]]
    ) -> List[ShortcutOpportunity]:
        """Identify paths that can be shortened with shortcuts.

        Args:
            graph_introspector: Graph introspector with structure info
            execution_patterns: Common execution patterns (node sequences)

        Returns:
            List of shortcut opportunities
        """
        if self.enable_mock_mode:
            return self._generate_mock_shortcut_opportunities()

        shortcut_opportunities = []

        # Analyze execution patterns for common paths
        pattern_frequencies = self._count_pattern_frequencies(execution_patterns)

        # Find patterns that could benefit from shortcuts
        for pattern, frequency in pattern_frequencies.items():
            if frequency < self.shortcut_min_frequency:
                continue

            # Pattern is a sequence of nodes
            nodes = pattern.split("->")
            if len(nodes) < 3:
                # Need at least 3 nodes to create a shortcut
                continue

            # Check if shortcut already exists
            from_node = nodes[0]
            to_node = nodes[-1]
            if self._shortcut_exists(graph_introspector, from_node, to_node):
                continue

            # Calculate potential benefit
            skipped_nodes = nodes[1:-1]
            potential_latency_savings = self._estimate_latency_savings(
                skipped_nodes, graph_introspector
            )

            # Determine condition for shortcut
            condition_suggestion = self._suggest_shortcut_condition(
                from_node, to_node, pattern
            )

            # Calculate confidence
            confidence = self._calculate_shortcut_confidence(
                frequency, len(skipped_nodes), potential_latency_savings
            )

            shortcut = ShortcutOpportunity(
                from_node=from_node,
                to_node=to_node,
                skipped_nodes=skipped_nodes,
                frequency=frequency,
                potential_latency_savings=potential_latency_savings,
                confidence=confidence,
                condition_suggestion=condition_suggestion
            )
            shortcut_opportunities.append(shortcut)

        # Sort by potential benefit (latency * frequency)
        shortcut_opportunities.sort(
            key=lambda s: s.potential_latency_savings * s.frequency,
            reverse=True
        )

        return shortcut_opportunities

    def _count_pattern_frequencies(
        self,
        execution_patterns: Dict[str, List[str]]
    ) -> Dict[str, int]:
        """Count frequency of execution patterns.

        Args:
            execution_patterns: Dict of execution ID to node sequence

        Returns:
            Dict of pattern string to frequency
        """
        pattern_counts: Dict[str, int] = {}

        for execution_id, path in execution_patterns.items():
            # Generate all subpaths of length 3+
            for length in range(3, len(path) + 1):
                for i in range(len(path) - length + 1):
                    subpath = path[i:i + length]
                    pattern = "->".join(subpath)
                    pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        return pattern_counts

    def _shortcut_exists(
        self,
        graph_introspector: GraphIntrospector,
        from_node: str,
        to_node: str
    ) -> bool:
        """Check if direct edge already exists between nodes.

        Args:
            graph_introspector: Graph introspector
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            True if direct edge exists
        """
        # Get edges from the source node
        edges = graph_introspector.get_edges_from_node(from_node)

        for edge in edges:
            edge_to = edge.get("to_node", edge.get("to_id", ""))

            if edge_to == to_node:
                return True

        return False

    def _estimate_latency_savings(
        self,
        skipped_nodes: List[str],
        graph_introspector: GraphIntrospector
    ) -> float:
        """Estimate latency savings from skipping nodes.

        Args:
            skipped_nodes: List of node IDs that would be skipped
            graph_introspector: Graph introspector with metrics

        Returns:
            Estimated latency savings in seconds
        """
        # Get average latency for each skipped node
        total_savings = 0.0

        for node_id in skipped_nodes:
            # Try to get node complexity as a proxy for latency
            complexity = graph_introspector.get_node_complexity(node_id)
            if complexity:
                # Use complexity score as proxy (higher = slower)
                score = complexity.get("complexity_score", 2)
                # Map complexity score to seconds (rough estimate)
                avg_duration = score * 0.1  # 0.1s per complexity point
                total_savings += avg_duration
            else:
                # Assume 0.2s per node if no data
                total_savings += 0.2

        return total_savings

    def _suggest_shortcut_condition(
        self,
        from_node: str,
        to_node: str,
        pattern: str
    ) -> str:
        """Suggest condition for shortcut edge.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            pattern: Execution pattern that triggers shortcut

        Returns:
            Suggested condition expression
        """
        # For now, suggest a simple condition
        # In practice, this would analyze when the pattern occurs
        return f"shortcut_to_{to_node}"

    def _calculate_shortcut_confidence(
        self,
        frequency: int,
        num_skipped: int,
        latency_savings: float
    ) -> float:
        """Calculate confidence score for shortcut opportunity.

        Args:
            frequency: How often pattern occurs
            num_skipped: Number of nodes skipped
            latency_savings: Estimated latency savings

        Returns:
            Confidence score from 0.0 to 1.0
        """
        confidence = 0.0

        # Frequency contribution (max 0.4)
        if frequency >= 1000:
            confidence += 0.4
        elif frequency >= 500:
            confidence += 0.3
        elif frequency >= 100:
            confidence += 0.2

        # Skipped nodes contribution (max 0.3)
        if num_skipped >= 5:
            confidence += 0.3
        elif num_skipped >= 3:
            confidence += 0.2
        elif num_skipped >= 2:
            confidence += 0.1

        # Latency savings contribution (max 0.3)
        if latency_savings >= 2.0:
            confidence += 0.3
        elif latency_savings >= 1.0:
            confidence += 0.2
        elif latency_savings >= 0.5:
            confidence += 0.1

        return min(confidence, 1.0)

    async def optimize_edge_condition(
        self,
        edge_spec: EdgeSpec,
        traversal_stats: Dict[str, float]
    ) -> Optional[OptimizedCondition]:
        """Suggest optimized edge condition.

        Args:
            edge_spec: Edge specification
            traversal_stats: Statistics about edge traversal

        Returns:
            Optimized condition suggestion, or None if no optimization needed
        """
        if self.enable_mock_mode:
            return self._generate_mock_optimized_condition(edge_spec)

        # Get current condition
        current_condition = edge_spec.condition
        if not current_condition:
            return None  # No condition to optimize

        # Convert to string if needed
        if isinstance(current_condition, dict):
            condition_str = str(current_condition)
        else:
            condition_str = str(current_condition)

        # Analyze traversal stats
        traversal_rate = traversal_stats.get("traversal_rate", 0.5)
        avg_eval_time = traversal_stats.get("avg_evaluation_time", 0.001)

        # Determine optimization type
        if traversal_rate > 0.95:
            # Almost always true - simplify or strengthen
            return self._create_simplified_condition(condition_str, traversal_rate)
        elif traversal_rate < 0.05:
            # Almost never true - consider strengthening or removing
            return self._create_strengthened_condition(condition_str, traversal_rate)
        elif avg_eval_time > 0.01:
            # Slow condition evaluation - try to simplify
            return self._create_simplified_condition(
                condition_str, traversal_rate, focus="performance"
            )

        return None  # No optimization needed

    def _create_simplified_condition(
        self,
        original: str,
        traversal_rate: float,
        focus: str = "logic"
    ) -> OptimizedCondition:
        """Create simplified condition suggestion.

        Args:
            original: Original condition string
            traversal_rate: How often condition is true
            focus: "logic" or "performance"

        Returns:
            Optimized condition
        """
        if focus == "performance":
            # Suggest caching or pre-computation
            optimized = f"cached({original})"
            rationale = f"Condition evaluation is slow, suggest caching"
        else:
            # Suggest logical simplification
            optimized = "true"  # Placeholder
            rationale = f"Condition is true {traversal_rate:.1%} of the time"

        return OptimizedCondition(
            original_condition=original,
            optimized_condition=optimized,
            improvement_type="simplify",
            expected_benefit=f"Reduce condition evaluation overhead",
            rationale=rationale
        )

    def _create_strengthened_condition(
        self,
        original: str,
        traversal_rate: float
    ) -> OptimizedCondition:
        """Create strengthened condition suggestion.

        Args:
            original: Original condition string
            traversal_rate: How often condition is true

        Returns:
            Optimized condition
        """
        optimized = f"{original} && additional_check"
        rationale = f"Condition is rarely true ({traversal_rate:.1%}), may need strengthening"

        return OptimizedCondition(
            original_condition=original,
            optimized_condition=optimized,
            improvement_type="strengthen",
            expected_benefit="More precise routing",
            rationale=rationale
        )

    # ========================================================================
    # Mock Mode Helpers
    # ========================================================================

    def _generate_mock_redundant_edges(self) -> List[RedundantEdge]:
        """Generate mock redundant edges for testing."""
        return [
            RedundantEdge(
                from_node="node_a",
                to_node="node_b",
                edge_condition="error_path",
                traversal_count=0,
                total_executions=1000,
                traversal_rate=0.0,
                recommendation="Never traversed - consider removing unless needed for edge cases"
            ),
            RedundantEdge(
                from_node="node_c",
                to_node="node_d",
                edge_condition="backup_path",
                traversal_count=5,
                total_executions=1000,
                traversal_rate=0.005,
                recommendation="Rarely traversed (0.50%) - verify if necessary"
            )
        ]

    def _generate_mock_shortcut_opportunities(self) -> List[ShortcutOpportunity]:
        """Generate mock shortcut opportunities for testing."""
        return [
            ShortcutOpportunity(
                from_node="input",
                to_node="output",
                skipped_nodes=["transform1", "transform2", "validate"],
                frequency=350,
                potential_latency_savings=1.5,
                confidence=0.75,
                condition_suggestion="fast_path_enabled"
            ),
            ShortcutOpportunity(
                from_node="router",
                to_node="final_node",
                skipped_nodes=["intermediate"],
                frequency=150,
                potential_latency_savings=0.3,
                confidence=0.50,
                condition_suggestion="skip_intermediate"
            )
        ]

    def _generate_mock_optimized_condition(
        self,
        edge_spec: EdgeSpec
    ) -> OptimizedCondition:
        """Generate mock optimized condition for testing."""
        original = str(edge_spec.condition) if edge_spec.condition else "unknown"

        return OptimizedCondition(
            original_condition=original,
            optimized_condition=f"simplified({original})",
            improvement_type="simplify",
            expected_benefit="Reduce condition evaluation overhead by 40%",
            rationale="Mock mode: Simulated optimization"
        )
