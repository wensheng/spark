"""Tools for introspecting and analyzing Spark graphs."""

from typing import Dict, List, Any, Optional, Set
from spark.graphs import BaseGraph
import logging

logger = logging.getLogger(__name__)

# from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec
from spark.nodes.serde import graph_to_spec


class GraphIntrospector:
    """Provides tools for analyzing graph structure and configuration.

    Usage:
        introspector = GraphIntrospector(graph)
        node_ids = introspector.get_node_ids()
        depth = introspector.get_graph_depth()
        cycles = introspector.find_cycles()
    """

    def __init__(self, graph: BaseGraph):
        """Initialize GraphIntrospector.

        Args:
            graph: Graph to introspect
        """
        self.graph = graph
        self.spec: Optional[Any] = None  # GraphSpec

    def load_spec(self) -> Optional[Any]:
        """Load graph specification.

        Returns:
            GraphSpec if available, None otherwise
        """
        if self.spec is None:
            try:
                self.spec = graph_to_spec(self.graph)
            except Exception as e:
                logger.error(f"Error loading graph spec: {e}")
                return None

        return self.spec

    def get_node_ids(self) -> List[str]:
        """Get list of all node IDs in graph.

        Returns:
            List of node IDs
        """
        spec = self.load_spec()
        if spec is None:
            # Fallback: use graph's nodes dict if available
            if hasattr(self.graph, '_nodes') and self.graph._nodes:
                return list(self.graph._nodes.keys())
            logger.warning("Cannot get node IDs - spec not available")
            return []

        return [node.id for node in spec.nodes]

    def get_node_spec(self, node_id: str) -> Optional[Any]:
        """Get specification for a specific node.

        Args:
            node_id: Node ID to retrieve

        Returns:
            NodeSpec if found, None otherwise
        """
        spec = self.load_spec()
        if spec is None:
            return None

        for node in spec.nodes:
            if node.id == node_id:
                return node
        return None

    def get_node_config(self, node_id: str) -> Dict[str, Any]:
        """Get configuration for a specific node.

        Args:
            node_id: Node ID

        Returns:
            Dict of configuration parameters
        """
        node_spec = self.get_node_spec(node_id)
        if node_spec is None:
            return {}
        return node_spec.config or {}

    def get_edges_from_node(self, node_id: str) -> List[Any]:
        """Get all edges originating from a node.

        Args:
            node_id: Source node ID

        Returns:
            List of EdgeSpec objects
        """
        spec = self.load_spec()
        if spec is None:
            return []

        return [edge for edge in spec.edges if edge.from_node == node_id]

    def get_edges_to_node(self, node_id: str) -> List[Any]:
        """Get all edges leading to a node.

        Args:
            node_id: Target node ID

        Returns:
            List of EdgeSpec objects
        """
        spec = self.load_spec()
        if spec is None:
            return []

        return [edge for edge in spec.edges if edge.to_node == node_id]

    def get_graph_depth(self) -> int:
        """Calculate maximum depth of graph (longest path from start).

        Returns:
            Maximum depth (number of nodes in longest path)
        """
        spec = self.load_spec()
        if spec is None:
            return 0

        # Build adjacency list
        adj = {node.id: [] for node in spec.nodes}
        for edge in spec.edges:
            adj[edge.from_node].append(edge.to_node)

        # BFS to find longest path
        max_depth = 0
        visited = set()
        queue = [(spec.start, 0)]

        while queue:
            node_id, depth = queue.pop(0)
            if node_id in visited:
                continue

            visited.add(node_id)
            max_depth = max(max_depth, depth)

            for next_node in adj.get(node_id, []):
                if next_node not in visited:
                    queue.append((next_node, depth + 1))

        return max_depth

    def get_node_complexity(self, node_id: str) -> Dict[str, Any]:
        """Analyze complexity of a node.

        Args:
            node_id: Node ID to analyze

        Returns:
            Dict with complexity metrics
        """
        node_spec = self.get_node_spec(node_id)
        if node_spec is None:
            return {}

        config = node_spec.config or {}
        outgoing_edges = self.get_edges_from_node(node_id)
        incoming_edges = self.get_edges_to_node(node_id)

        # Calculate branching factor (number of possible next nodes)
        branching_factor = len(set(edge.to_node for edge in outgoing_edges))

        # Check for conditional logic
        has_conditions = any(edge.condition is not None for edge in outgoing_edges)

        return {
            'node_type': node_spec.type,
            'config_keys': list(config.keys()),
            'config_complexity': len(str(config)),
            'incoming_edges': len(incoming_edges),
            'outgoing_edges': len(outgoing_edges),
            'branching_factor': branching_factor,
            'has_conditional_logic': has_conditions,
        }

    def find_cycles(self) -> List[List[str]]:
        """Find cycles in graph (useful for detecting infinite loops).

        Returns:
            List of cycles, each cycle is a list of node IDs
        """
        spec = self.load_spec()
        if spec is None:
            return []

        # Build adjacency list
        adj = {node.id: [] for node in spec.nodes}
        for edge in spec.edges:
            adj[edge.from_node].append(edge.to_node)

        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found cycle
                    try:
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:]
                        if cycle not in cycles:  # Avoid duplicates
                            cycles.append(cycle)
                    except ValueError:
                        pass

            path.pop() if path else None
            rec_stack.discard(node)

        # Start DFS from each node
        for node in adj.keys():
            if node not in visited:
                dfs(node, [])

        return cycles

    def get_critical_path(self) -> List[str]:
        """Identify critical path (longest execution path from start).

        Returns:
            List of node IDs in critical path
        """
        spec = self.load_spec()
        if spec is None:
            return []

        # Build adjacency list
        adj = {node.id: [] for node in spec.nodes}
        for edge in spec.edges:
            adj[edge.from_node].append(edge.to_node)

        # Find longest path using DFS
        longest_path = []

        def dfs(node: str, path: List[str], visited: Set[str]):
            nonlocal longest_path

            path.append(node)
            visited.add(node)

            # Update longest path if current is longer
            if len(path) > len(longest_path):
                longest_path = path.copy()

            # Explore neighbors
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy(), visited.copy())

        dfs(spec.start, [], set())
        return longest_path

    def get_node_stats(self) -> Dict[str, Any]:
        """Get overall statistics about the graph structure.

        Returns:
            Dict with graph statistics
        """
        spec = self.load_spec()
        if spec is None:
            return {}

        # Count node types
        node_types = {}
        for node in spec.nodes:
            node_type = node.type
            node_types[node_type] = node_types.get(node_type, 0) + 1

        # Analyze edges
        total_edges = len(spec.edges)
        conditional_edges = sum(1 for e in spec.edges if e.condition is not None)

        # Find leaf nodes (no outgoing edges)
        nodes_with_outgoing = set(e.from_node for e in spec.edges)
        all_nodes = set(n.id for n in spec.nodes)
        leaf_nodes = all_nodes - nodes_with_outgoing

        # Find entry nodes (no incoming edges)
        nodes_with_incoming = set(e.to_node for e in spec.edges)
        entry_nodes = all_nodes - nodes_with_incoming

        return {
            'total_nodes': len(spec.nodes),
            'total_edges': total_edges,
            'conditional_edges': conditional_edges,
            'max_depth': self.get_graph_depth(),
            'node_types': node_types,
            'leaf_nodes': list(leaf_nodes),
            'entry_nodes': list(entry_nodes),
            'has_cycles': len(self.find_cycles()) > 0,
        }

    def visualize_structure(self) -> str:
        """Generate a simple text visualization of graph structure.

        Returns:
            String representation of graph structure
        """
        spec = self.load_spec()
        if spec is None:
            return "Graph structure unavailable"

        lines = []
        lines.append(f"Graph: {spec.id or 'unnamed'}")
        lines.append(f"Start Node: {spec.start}")
        lines.append(f"Total Nodes: {len(spec.nodes)}")
        lines.append(f"Total Edges: {len(spec.edges)}")
        lines.append("")

        # Show nodes
        lines.append("Nodes:")
        for node in spec.nodes[:10]:  # Limit to first 10
            lines.append(f"  - {node.id} ({node.type})")
        if len(spec.nodes) > 10:
            lines.append(f"  ... and {len(spec.nodes) - 10} more")

        lines.append("")

        # Show edges
        lines.append("Edges:")
        for edge in spec.edges[:10]:  # Limit to first 10
            condition = " [conditional]" if edge.condition else ""
            lines.append(f"  {edge.from_node} -> {edge.to_node}{condition}")
        if len(spec.edges) > 10:
            lines.append(f"  ... and {len(spec.edges) - 10} more")

        return "\n".join(lines)
