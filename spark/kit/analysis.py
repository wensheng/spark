"""
Graph analysis and introspection tools.

Provides comprehensive analysis of GraphSpec including:
- Complexity metrics (node count, depth, branching factor)
- Cycle detection and topology analysis
- Bottleneck identification
- Optimization suggestions
- Semantic validation beyond schema
- Detailed metrics reporting
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque

from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec, ConditionSpec


# ============================================================================
# Graph Analysis
# ============================================================================

class GraphAnalyzer:
    """Analyze graph structure and properties."""

    def __init__(self, spec: GraphSpec):
        """Initialize analyzer with a GraphSpec.

        Args:
            spec: The GraphSpec to analyze
        """
        self.spec = spec
        self._adjacency: Dict[str, List[str]] = {}
        self._reverse_adjacency: Dict[str, List[str]] = {}
        self._node_map: Dict[str, NodeSpec] = {}
        self._edge_map: Dict[Tuple[str, str], List[EdgeSpec]] = defaultdict(list)
        self._build_graph()

    def _build_graph(self):
        """Build internal graph representation from spec."""
        # Build node map
        for node in self.spec.nodes:
            self._node_map[node.id] = node

        # Build adjacency lists
        for node_id in self._node_map:
            self._adjacency[node_id] = []
            self._reverse_adjacency[node_id] = []

        # Build edge maps
        for edge in self.spec.edges:
            self._adjacency[edge.from_node].append(edge.to_node)
            self._reverse_adjacency[edge.to_node].append(edge.from_node)
            self._edge_map[(edge.from_node, edge.to_node)].append(edge)

    def analyze_complexity(self) -> Dict[str, Any]:
        """Compute complexity metrics.

        Returns:
            Dictionary containing:
                - node_count: Total number of nodes
                - edge_count: Total number of edges
                - max_depth: Maximum path length from start node
                - avg_depth: Average path length from start node
                - branching_factor: Average number of outgoing edges per node
                - cyclic: Whether graph contains cycles
                - cycle_count: Number of cycles detected
                - connected_components: Number of disconnected components
                - unreachable_nodes: List of nodes not reachable from start
        """
        node_count = len(self.spec.nodes)
        edge_count = len(self.spec.edges)

        # Compute depths
        max_depth, avg_depth, depths = self._compute_depths()

        # Compute branching factor
        branching_factor = self._compute_branching_factor()

        # Check for cycles
        cyclic, cycle_count, cycles = self._detect_cycles()

        # Count connected components
        connected_components = self._count_components()

        # Find unreachable nodes
        unreachable = self._find_unreachable_nodes()

        return {
            'node_count': node_count,
            'edge_count': edge_count,
            'max_depth': max_depth,
            'avg_depth': avg_depth,
            'branching_factor': branching_factor,
            'cyclic': cyclic,
            'cycle_count': cycle_count,
            'cycles': cycles,
            'connected_components': connected_components,
            'unreachable_nodes': unreachable,
        }

    def _compute_depths(self) -> Tuple[int, float, Dict[str, int]]:
        """Compute max and average depth from start node.

        Returns:
            (max_depth, avg_depth, node_depths)
        """
        if not self.spec.start or self.spec.start not in self._node_map:
            return 0, 0.0, {}

        depths: Dict[str, int] = {}
        queue = deque([(self.spec.start, 0)])
        visited = set()

        while queue:
            node_id, depth = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            depths[node_id] = depth

            for successor in self._adjacency.get(node_id, []):
                if successor not in visited:
                    queue.append((successor, depth + 1))

        if not depths:
            return 0, 0.0, {}

        max_depth = max(depths.values())
        avg_depth = sum(depths.values()) / len(depths)

        return max_depth, avg_depth, depths

    def _compute_branching_factor(self) -> float:
        """Compute average branching factor (outgoing edges per node)."""
        if not self._adjacency:
            return 0.0

        total_edges = sum(len(successors) for successors in self._adjacency.values())
        nodes_with_edges = sum(1 for successors in self._adjacency.values() if successors)

        if nodes_with_edges == 0:
            return 0.0

        return total_edges / nodes_with_edges

    def _detect_cycles(self) -> Tuple[bool, int, List[List[str]]]:
        """Detect cycles using DFS.

        Returns:
            (has_cycles, cycle_count, list_of_cycles)
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in self._node_map}
        parent = {node_id: None for node_id in self._node_map}
        cycles = []

        def dfs(node: str, path: List[str]):
            """DFS with cycle detection."""
            color[node] = GRAY
            path.append(node)

            for successor in self._adjacency.get(node, []):
                if color[successor] == GRAY:
                    # Found a cycle
                    cycle_start = path.index(successor)
                    cycle = path[cycle_start:] + [successor]
                    cycles.append(cycle)
                elif color[successor] == WHITE:
                    parent[successor] = node
                    dfs(successor, path[:])

            color[node] = BLACK

        for node_id in self._node_map:
            if color[node_id] == WHITE:
                dfs(node_id, [])

        return len(cycles) > 0, len(cycles), cycles

    def _count_components(self) -> int:
        """Count connected components using BFS."""
        visited = set()
        components = 0

        for node_id in self._node_map:
            if node_id not in visited:
                components += 1
                # BFS to mark all reachable nodes
                queue = deque([node_id])
                while queue:
                    current = queue.popleft()
                    if current in visited:
                        continue
                    visited.add(current)
                    # Add both successors and predecessors
                    queue.extend(self._adjacency.get(current, []))
                    queue.extend(self._reverse_adjacency.get(current, []))

        return components

    def _find_unreachable_nodes(self) -> List[str]:
        """Find nodes not reachable from start node."""
        if not self.spec.start or self.spec.start not in self._node_map:
            return list(self._node_map.keys())

        visited = set()
        queue = deque([self.spec.start])

        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            queue.extend(self._adjacency.get(node_id, []))

        return [node_id for node_id in self._node_map if node_id not in visited]

    def identify_bottlenecks(self) -> List[Dict[str, Any]]:
        """Find potential performance bottlenecks.

        Returns:
            List of bottleneck descriptions with:
                - type: 'high_fan_in' | 'sequential_chain' | 'complex_condition'
                - node_id: Node identifier
                - severity: 'low' | 'medium' | 'high'
                - description: Human-readable description
                - suggestion: Optimization suggestion
        """
        bottlenecks = []

        # Detect high fan-in nodes
        for node_id, predecessors in self._reverse_adjacency.items():
            if len(predecessors) > 5:
                bottlenecks.append({
                    'type': 'high_fan_in',
                    'node_id': node_id,
                    'fan_in_count': len(predecessors),
                    'severity': 'high' if len(predecessors) > 10 else 'medium',
                    'description': f"Node '{node_id}' has {len(predecessors)} incoming edges",
                    'suggestion': 'Consider using a JoinNode or refactoring to reduce fan-in'
                })

        # Detect long sequential chains
        chains = self._find_sequential_chains()
        for chain in chains:
            if len(chain) > 3:
                bottlenecks.append({
                    'type': 'sequential_chain',
                    'node_ids': chain,
                    'chain_length': len(chain),
                    'severity': 'medium' if len(chain) > 3 else 'low',
                    'description': f"Sequential chain of {len(chain)} nodes: {' -> '.join(chain[:3])}...",
                    'suggestion': 'Consider if any nodes could be parallelized'
                })

        # Detect complex edge conditions
        for (from_node, to_node), edges in self._edge_map.items():
            for edge in edges:
                if edge.condition and self._is_complex_condition(edge.condition):
                    bottlenecks.append({
                        'type': 'complex_condition',
                        'edge_id': edge.id,
                        'from_node': from_node,
                        'to_node': to_node,
                        'severity': 'low',
                        'description': f"Complex condition on edge from '{from_node}' to '{to_node}'",
                        'suggestion': 'Consider simplifying condition or caching results'
                    })

        return bottlenecks

    def _find_sequential_chains(self) -> List[List[str]]:
        """Find sequential chains (nodes with single in/out edge)."""
        chains = []
        visited = set()

        for node_id in self._node_map:
            if node_id in visited:
                continue

            # Start a chain only from the head of a sequence.
            # A head is a node that doesn't have a single predecessor.
            if len(self._reverse_adjacency.get(node_id, [])) != 1:
                # Follow the chain from this head
                if len(self._adjacency.get(node_id, [])) == 1:
                    chain = [node_id]
                    visited.add(node_id)
                    current = self._adjacency[node_id][0]

                    # Traverse nodes with exactly one predecessor and one successor
                    while (current not in visited and
                           len(self._reverse_adjacency.get(current, [])) == 1):
                        chain.append(current)
                        visited.add(current)
                        
                        successors = self._adjacency.get(current, [])
                        if len(successors) == 1:
                            current = successors[0]
                        else:
                            break  # End of chain

                    if len(chain) > 1:
                        chains.append(chain)

        return chains

    def _is_complex_condition(self, condition: ConditionSpec) -> bool:
        """Determine if a condition is complex."""
        if condition.kind == 'expr' and condition.expr:
            # Consider expressions with multiple operators as complex
            return condition.expr.count(' and ') + condition.expr.count(' or ') >= 2
        elif condition.kind == 'lambda':
            return True  # Lambda conditions are always considered complex
        return False

    def suggest_optimizations(self) -> List[str]:
        """Suggest graph optimizations.

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Check for parallelization opportunities
        chains = self._find_sequential_chains()
        independent_chains = self._find_independent_chains(chains)
        if independent_chains:
            suggestions.append(
                f"Found {len(independent_chains)} sequential chains that could be parallelized using ParallelNode"
            )

        # Check for redundant nodes
        redundant = self._find_redundant_nodes()
        if redundant:
            suggestions.append(
                f"Found {len(redundant)} potentially redundant nodes: {', '.join(redundant[:3])}"
            )

        # Check for inefficient routing
        bottlenecks = self.identify_bottlenecks()
        high_fan_in = [b for b in bottlenecks if b['type'] == 'high_fan_in']
        if high_fan_in:
            suggestions.append(
                f"Found {len(high_fan_in)} nodes with high fan-in - consider using JoinNode"
            )

        # Check for multiple edges between same nodes
        duplicate_edges = self._find_duplicate_edges()
        if duplicate_edges:
            suggestions.append(
                f"Found {len(duplicate_edges)} node pairs with multiple edges - consider consolidating conditions"
            )

        # Check for unreachable nodes
        complexity = self.analyze_complexity()
        if complexity['unreachable_nodes']:
            suggestions.append(
                f"Remove {len(complexity['unreachable_nodes'])} unreachable nodes: {', '.join(complexity['unreachable_nodes'][:3])}"
            )

        if not suggestions:
            suggestions.append("No obvious optimizations detected - graph structure looks good")

        return suggestions

    def _find_independent_chains(self, chains: List[List[str]]) -> List[List[str]]:
        """Find chains that are independent and could be parallelized."""
        independent = []

        for i, chain1 in enumerate(chains):
            for chain2 in chains[i+1:]:
                # Check if chains don't depend on each other
                chain1_set = set(chain1)
                chain2_set = set(chain2)

                # No overlap and no dependencies
                if not chain1_set.intersection(chain2_set):
                    # Check if there's no path between them
                    if not self._has_path(chain1[0], chain2[0]) and not self._has_path(chain2[0], chain1[0]):
                        independent.append([chain1, chain2])

        return independent

    def _has_path(self, start: str, end: str) -> bool:
        """Check if there's a path from start to end."""
        if start == end:
            return True

        visited = set()
        queue = deque([start])

        while queue:
            current = queue.popleft()
            if current == end:
                return True
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self._adjacency.get(current, []))

        return False

    def _find_redundant_nodes(self) -> List[str]:
        """Find potentially redundant nodes (pass-through nodes with no logic)."""
        redundant = []

        for node_id, node in self._node_map.items():
            # Check if node is a simple pass-through
            in_edges = len(self._reverse_adjacency.get(node_id, []))
            out_edges = len(self._adjacency.get(node_id, []))

            # Node with single in/out and no special config might be redundant
            if (in_edges == 1 and out_edges == 1 and
                node.type == 'Node' and
                not node.config):
                redundant.append(node_id)

        return redundant

    def _find_duplicate_edges(self) -> List[Tuple[str, str]]:
        """Find node pairs with multiple edges."""
        return [(from_node, to_node)
                for (from_node, to_node), edges in self._edge_map.items()
                if len(edges) > 1]

    def validate_semantics(self) -> List[str]:
        """Semantic validation beyond schema.

        Returns:
            List of validation issues
        """
        issues = []

        # Check for unreachable nodes
        unreachable = self._find_unreachable_nodes()
        if unreachable:
            issues.append(f"Unreachable nodes: {', '.join(unreachable)}")

        # Detect infinite loops
        cyclic, cycle_count, cycles = self._detect_cycles()
        if cyclic:
            issues.append(f"Graph contains {cycle_count} cycle(s)")
            for i, cycle in enumerate(cycles[:3]):  # Show first 3 cycles
                issues.append(f"  Cycle {i+1}: {' -> '.join(cycle)}")

        # Validate start node exists
        if not self.spec.start:
            issues.append("No start node specified")
        elif self.spec.start not in self._node_map:
            issues.append(f"Start node '{self.spec.start}' not found in nodes")

        # Check for orphan nodes
        orphans = []
        for node_id in self._node_map:
            if (not self._adjacency.get(node_id) and
                not self._reverse_adjacency.get(node_id) and
                node_id != self.spec.start):
                orphans.append(node_id)
        if orphans:
            issues.append(f"Orphan nodes (no edges): {', '.join(orphans)}")

        # Validate edge references
        for edge in self.spec.edges:
            if edge.from_node not in self._node_map:
                issues.append(f"Edge '{edge.id}' references non-existent from_node '{edge.from_node}'")
            if edge.to_node not in self._node_map:
                issues.append(f"Edge '{edge.id}' references non-existent to_node '{edge.to_node}'")

        # Check for tool dependencies in agents
        for node in self.spec.nodes:
            if node.type == 'Agent' and node.config:
                tools = node.config.get('tools', [])
                if tools and not self.spec.tools:
                    issues.append(f"Agent '{node.id}' references tools but no tools are defined in spec")

        # Check for conflicting edge conditions
        for (from_node, to_node), edges in self._edge_map.items():
            if len(edges) > 1:
                # Check if multiple edges have no conditions (all would fire)
                unconditional = [e for e in edges if not e.condition]
                if len(unconditional) > 1:
                    issues.append(
                        f"Multiple unconditional edges from '{from_node}' to '{to_node}' (all will fire)"
                    )

        return issues

    def generate_metrics_report(self) -> str:
        """Generate comprehensive analysis report.

        Returns:
            Formatted text report
        """
        lines = []
        lines.append("=" * 70)
        lines.append("GRAPH ANALYSIS REPORT")
        lines.append("=" * 70)
        lines.append("")

        # Complexity metrics
        lines.append("COMPLEXITY METRICS")
        lines.append("-" * 70)
        complexity = self.analyze_complexity()
        lines.append(f"  Nodes: {complexity['node_count']}")
        lines.append(f"  Edges: {complexity['edge_count']}")
        lines.append(f"  Max Depth: {complexity['max_depth']}")
        lines.append(f"  Avg Depth: {complexity['avg_depth']:.2f}")
        lines.append(f"  Branching Factor: {complexity['branching_factor']:.2f}")
        lines.append(f"  Cyclic: {'Yes' if complexity['cyclic'] else 'No'}")
        if complexity['cyclic']:
            lines.append(f"  Cycle Count: {complexity['cycle_count']}")
        lines.append(f"  Connected Components: {complexity['connected_components']}")
        if complexity['unreachable_nodes']:
            lines.append(f"  Unreachable Nodes: {len(complexity['unreachable_nodes'])}")
        lines.append("")

        # Bottlenecks
        lines.append("BOTTLENECKS")
        lines.append("-" * 70)
        bottlenecks = self.identify_bottlenecks()
        if bottlenecks:
            for bottleneck in bottlenecks:
                lines.append(f"  [{bottleneck['severity'].upper()}] {bottleneck['description']}")
                lines.append(f"    → {bottleneck['suggestion']}")
        else:
            lines.append("  No bottlenecks detected")
        lines.append("")

        # Optimization suggestions
        lines.append("OPTIMIZATION SUGGESTIONS")
        lines.append("-" * 70)
        suggestions = self.suggest_optimizations()
        for suggestion in suggestions:
            lines.append(f"  • {suggestion}")
        lines.append("")

        # Semantic validation
        lines.append("SEMANTIC VALIDATION")
        lines.append("-" * 70)
        issues = self.validate_semantics()
        if issues:
            for issue in issues:
                lines.append(f"  ⚠ {issue}")
        else:
            lines.append("  ✓ No semantic issues detected")
        lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)
