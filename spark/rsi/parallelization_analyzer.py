"""Parallelization analysis for RSI system.

This module identifies opportunities to convert sequential node execution
into parallel execution for improved performance.
"""

from typing import Dict, List, Optional, Any, Set
from spark.rsi.types import (
    ParallelizableSequence,
    ParallelizationBenefit,
    ParallelGraphStructure,
)
from spark.rsi.introspection import GraphIntrospector


class ParallelizationAnalyzer:
    """Identifies opportunities for parallel execution.

    Capabilities:
    - Detect independent sequential operations
    - Validate no shared state conflicts
    - Estimate parallelization benefits
    - Generate parallel execution patterns
    """

    def __init__(
        self,
        min_speedup_threshold: float = 1.5,  # Minimum 1.5x speedup
        enable_mock_mode: bool = False
    ):
        """Initialize the parallelization analyzer.

        Args:
            min_speedup_threshold: Minimum speedup multiplier to suggest parallelization
            enable_mock_mode: If True, use mock data instead of real analysis
        """
        self.min_speedup_threshold = min_speedup_threshold
        self.enable_mock_mode = enable_mock_mode

    async def find_parallelizable_sequences(
        self,
        graph_introspector: GraphIntrospector
    ) -> List[ParallelizableSequence]:
        """Find sequences that can run in parallel.

        Identifies patterns where multiple sequential branches could
        be executed concurrently.

        Args:
            graph_introspector: Graph introspector with structure info

        Returns:
            List of parallelizable sequences
        """
        if self.enable_mock_mode:
            return self._generate_mock_parallelizable_sequences()

        parallelizable = []

        # Get all nodes
        node_ids = graph_introspector.get_node_ids()

        # Find branch points (nodes with multiple outgoing edges)
        for node_id in node_ids:
            edges_from_node = graph_introspector.get_edges_from_node(node_id)

            if len(edges_from_node) < 2:
                continue  # Not a branch point

            # Check if branches are independent
            branches = self._trace_branches(node_id, edges_from_node, graph_introspector)

            if len(branches) < 2:
                continue  # Need at least 2 branches

            # Check for convergence point
            convergence_node = self._find_convergence_node(branches, graph_introspector)

            if not convergence_node:
                continue  # Branches don't converge

            # Analyze dependencies between branches
            has_dependencies, dependency_details = self._check_branch_dependencies(
                branches, graph_introspector
            )

            if has_dependencies:
                # Has dependencies, cannot safely parallelize
                continue

            # Get all nodes in the parallelizable sequence
            all_nodes = [node_id]
            for branch in branches:
                all_nodes.extend(branch)
            all_nodes.append(convergence_node)

            # Estimate speedup
            estimated_speedup = self._estimate_speedup(branches, graph_introspector)

            if estimated_speedup < self.min_speedup_threshold:
                continue  # Not enough benefit

            # Create parallelizable sequence
            sequence = ParallelizableSequence(
                sequential_nodes=all_nodes,
                entry_node=node_id,
                exit_node=convergence_node,
                has_dependencies=has_dependencies,
                dependency_details=dependency_details,
                estimated_speedup=estimated_speedup,
                confidence=self._calculate_confidence(branches, estimated_speedup)
            )
            parallelizable.append(sequence)

        # Sort by estimated speedup (highest first)
        parallelizable.sort(key=lambda s: s.estimated_speedup, reverse=True)

        return parallelizable

    def _trace_branches(
        self,
        start_node: str,
        edges: List[Dict[str, Any]],
        graph_introspector: GraphIntrospector
    ) -> List[List[str]]:
        """Trace each branch from a node until convergence or end.

        Args:
            start_node: Starting node ID
            edges: Outgoing edges from start node
            graph_introspector: Graph introspector

        Returns:
            List of branches, each branch is a list of node IDs
        """
        branches = []

        for edge in edges:
            branch_nodes = []
            current_node = edge.get("to_node", edge.get("to_id"))

            if not current_node:
                continue

            # Trace this branch
            visited = {start_node}
            while current_node and current_node not in visited:
                branch_nodes.append(current_node)
                visited.add(current_node)

                # Get outgoing edges
                next_edges = graph_introspector.get_edges_from_node(current_node)

                if len(next_edges) != 1:
                    # Branch point or end - stop tracing
                    break

                # Continue to next node
                current_node = next_edges[0].get("to_node", next_edges[0].get("to_id"))

            if branch_nodes:
                branches.append(branch_nodes)

        return branches

    def _find_convergence_node(
        self,
        branches: List[List[str]],
        graph_introspector: GraphIntrospector
    ) -> Optional[str]:
        """Find node where all branches converge.

        Args:
            branches: List of branch node sequences
            graph_introspector: Graph introspector

        Returns:
            Convergence node ID, or None if branches don't converge
        """
        if not branches:
            return None

        # Get last node from each branch
        branch_ends = [branch[-1] for branch in branches]

        # Find common successors
        successor_sets = []
        for branch_end in branch_ends:
            edges = graph_introspector.get_edges_from_node(branch_end)
            successors = {e.get("to_node", e.get("to_id")) for e in edges}
            successor_sets.append(successors)

        # Find intersection of all successor sets
        if not successor_sets:
            return None

        common_successors = successor_sets[0]
        for successors in successor_sets[1:]:
            common_successors &= successors

        if not common_successors:
            return None

        # Return first common successor (could be multiple in complex graphs)
        return list(common_successors)[0]

    def _check_branch_dependencies(
        self,
        branches: List[List[str]],
        graph_introspector: GraphIntrospector
    ) -> tuple[bool, Dict[str, Any]]:
        """Check if branches have dependencies preventing parallelization.

        Args:
            branches: List of branch node sequences
            graph_introspector: Graph introspector

        Returns:
            Tuple of (has_dependencies, dependency_details)
        """
        # For now, use simple heuristic:
        # - Check if branches modify shared state
        # - Check for data dependencies between branches

        has_dependencies = False
        dependency_details = {
            "shared_state_conflicts": [],
            "data_dependencies": [],
            "reason": "No dependencies detected (heuristic analysis)"
        }

        # Analyze shared state
        state_keys = self._get_state_keys_accessed(branches, graph_introspector)

        # Check for write conflicts
        written_keys = state_keys.get("written", {})
        for branch_idx, keys in written_keys.items():
            for other_idx, other_keys in written_keys.items():
                if branch_idx >= other_idx:
                    continue

                # Check for shared write keys
                shared = keys & other_keys
                if shared:
                    has_dependencies = True
                    dependency_details["shared_state_conflicts"].append({
                        "branches": [branch_idx, other_idx],
                        "conflicting_keys": list(shared)
                    })

        # Check for read-after-write dependencies
        read_keys = state_keys.get("read", {})
        for branch_idx, read_set in read_keys.items():
            for other_idx, write_set in written_keys.items():
                if branch_idx == other_idx:
                    continue

                shared = read_set & write_set
                if shared:
                    has_dependencies = True
                    dependency_details["data_dependencies"].append({
                        "reader_branch": branch_idx,
                        "writer_branch": other_idx,
                        "shared_keys": list(shared)
                    })

        if has_dependencies:
            dependency_details["reason"] = "Shared state or data dependencies detected"

        return has_dependencies, dependency_details

    def _get_state_keys_accessed(
        self,
        branches: List[List[str]],
        graph_introspector: GraphIntrospector
    ) -> Dict[str, Dict[int, Set[str]]]:
        """Get state keys accessed by each branch.

        Args:
            branches: List of branch node sequences
            graph_introspector: Graph introspector

        Returns:
            Dict with 'read' and 'written' keys accessed per branch
        """
        result = {
            "read": {},
            "written": {}
        }

        for branch_idx, branch in enumerate(branches):
            read_keys = set()
            written_keys = set()

            for node_id in branch:
                # Get node config to infer state access
                # This is a simplified heuristic
                node_spec = graph_introspector.get_node_spec(node_id)
                if not node_spec:
                    continue

                node_config = node_spec.config or {}

                # Check for state-related config
                if node_config.get("uses_graph_state"):
                    # Assume both read and write for simplicity
                    read_keys.add(f"{node_id}_state")
                    written_keys.add(f"{node_id}_state")

            result["read"][branch_idx] = read_keys
            result["written"][branch_idx] = written_keys

        return result

    def _estimate_speedup(
        self,
        branches: List[List[str]],
        graph_introspector: GraphIntrospector
    ) -> float:
        """Estimate speedup from parallelizing branches.

        Args:
            branches: List of branch node sequences
            graph_introspector: Graph introspector

        Returns:
            Estimated speedup multiplier
        """
        if not branches:
            return 1.0

        # Calculate total sequential time (sum of all branches)
        branch_durations = []
        for branch in branches:
            branch_duration = 0.0
            for node_id in branch:
                # Get complexity as proxy for duration
                complexity = graph_introspector.get_node_complexity(node_id)
                if complexity:
                    score = complexity.get("complexity_score", 2)
                    duration = score * 0.1  # 0.1s per complexity point
                    branch_duration += duration
                else:
                    branch_duration += 0.2  # Default 0.2s per node

            branch_durations.append(branch_duration)

        # Sequential time: sum of all branches
        sequential_time = sum(branch_durations)

        # Parallel time: max of all branches (slowest branch)
        parallel_time = max(branch_durations) if branch_durations else 1.0

        # Speedup
        if parallel_time > 0:
            speedup = sequential_time / parallel_time
        else:
            speedup = 1.0

        # Account for parallelization overhead (reduce by 10%)
        speedup *= 0.9

        return speedup

    def _calculate_confidence(
        self,
        branches: List[List[str]],
        estimated_speedup: float
    ) -> float:
        """Calculate confidence in parallelization suggestion.

        Args:
            branches: List of branch node sequences
            estimated_speedup: Estimated speedup multiplier

        Returns:
            Confidence score from 0.0 to 1.0
        """
        confidence = 0.0

        # Number of branches contribution (max 0.3)
        num_branches = len(branches)
        if num_branches >= 4:
            confidence += 0.3
        elif num_branches >= 3:
            confidence += 0.2
        elif num_branches >= 2:
            confidence += 0.1

        # Speedup contribution (max 0.4)
        if estimated_speedup >= 3.0:
            confidence += 0.4
        elif estimated_speedup >= 2.0:
            confidence += 0.3
        elif estimated_speedup >= 1.5:
            confidence += 0.2

        # Branch balance contribution (max 0.3)
        # More balanced branches = higher confidence
        branch_lengths = [len(branch) for branch in branches]
        if branch_lengths:
            avg_length = sum(branch_lengths) / len(branch_lengths)
            max_deviation = max(abs(l - avg_length) for l in branch_lengths)
            if max_deviation <= 1:
                confidence += 0.3  # Very balanced
            elif max_deviation <= 2:
                confidence += 0.2  # Somewhat balanced
            else:
                confidence += 0.1  # Unbalanced

        return min(confidence, 1.0)

    async def estimate_parallelization_benefit(
        self,
        sequence: ParallelizableSequence,
        historical_latency: Dict[str, float]
    ) -> ParallelizationBenefit:
        """Estimate benefit from parallelizing a sequence.

        Args:
            sequence: Parallelizable sequence
            historical_latency: Historical latency data per node

        Returns:
            Estimated benefits
        """
        if self.enable_mock_mode:
            return self._generate_mock_parallelization_benefit()

        # Calculate latency reduction
        # TODO: Use historical data more effectively
        estimated_speedup = sequence.estimated_speedup

        # Assume average latency per node
        avg_node_latency = 0.5  # 0.5s default
        num_nodes = len(sequence.sequential_nodes)

        sequential_latency = num_nodes * avg_node_latency
        parallel_latency = sequential_latency / estimated_speedup
        latency_reduction = sequential_latency - parallel_latency

        # Resource increase (running nodes in parallel uses more resources)
        # Assume linear resource scaling
        num_parallel_branches = estimated_speedup  # Rough estimate
        resource_increase = (num_parallel_branches - 1) * 100.0  # Percentage

        # Complexity increase (adding parallel execution adds complexity)
        complexity_increase = len(sequence.sequential_nodes) * 2  # Rough estimate

        return ParallelizationBenefit(
            latency_reduction=latency_reduction,
            speedup_multiplier=estimated_speedup,
            resource_increase=resource_increase,
            complexity_increase=complexity_increase,
            confidence=sequence.confidence
        )

    async def generate_parallel_structure(
        self,
        sequence: ParallelizableSequence
    ) -> ParallelGraphStructure:
        """Generate parallel graph structure for a sequence.

        Args:
            sequence: Parallelizable sequence

        Returns:
            Parallel graph structure specification
        """
        if self.enable_mock_mode:
            return self._generate_mock_parallel_structure()

        # Extract branches from sequence
        # This is simplified - in reality would need more sophisticated analysis

        # For now, create a simple two-branch structure
        mid_point = len(sequence.sequential_nodes) // 2
        branch1 = sequence.sequential_nodes[:mid_point]
        branch2 = sequence.sequential_nodes[mid_point:]

        parallel_branches = [branch1, branch2]

        # Determine if merge is needed
        requires_merge = True
        merge_node_id = f"{sequence.exit_node}_merge" if sequence.exit_node else None

        return ParallelGraphStructure(
            parallel_branches=parallel_branches,
            merge_node_id=merge_node_id,
            requires_merge=requires_merge,
            merge_strategy="wait_all"
        )

    # ========================================================================
    # Mock Mode Helpers
    # ========================================================================

    def _generate_mock_parallelizable_sequences(self) -> List[ParallelizableSequence]:
        """Generate mock parallelizable sequences for testing."""
        return [
            ParallelizableSequence(
                sequential_nodes=["entry", "branch_a1", "branch_a2", "branch_b1", "branch_b2", "merge"],
                entry_node="entry",
                exit_node="merge",
                has_dependencies=False,
                dependency_details={"reason": "Mock: No dependencies"},
                estimated_speedup=2.3,
                confidence=0.80
            ),
            ParallelizableSequence(
                sequential_nodes=["start", "task1", "task2", "task3", "end"],
                entry_node="start",
                exit_node="end",
                has_dependencies=False,
                dependency_details={"reason": "Mock: Independent tasks"},
                estimated_speedup=1.8,
                confidence=0.65
            )
        ]

    def _generate_mock_parallelization_benefit(self) -> ParallelizationBenefit:
        """Generate mock parallelization benefit for testing."""
        return ParallelizationBenefit(
            latency_reduction=1.2,
            speedup_multiplier=2.1,
            resource_increase=100.0,
            complexity_increase=4,
            confidence=0.75
        )

    def _generate_mock_parallel_structure(self) -> ParallelGraphStructure:
        """Generate mock parallel structure for testing."""
        return ParallelGraphStructure(
            parallel_branches=[
                ["branch_a_node1", "branch_a_node2"],
                ["branch_b_node1", "branch_b_node2"]
            ],
            merge_node_id="merge_node",
            requires_merge=True,
            merge_strategy="wait_all"
        )
