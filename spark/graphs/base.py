"""
Graphs are the top-level construct in Spark, defining the complete blueprint of an agentic workflow.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import uuid4

from spark.nodes.base import BaseNode, Edge


class BaseGraph(ABC):
    """
    Abstract Base class for all graphs.
    A graph must have a start node to be runnable.
    Use add() to add edges to the graph.
    How the nodes are connected are actually defined outside of the graph.
    """

    start: BaseNode

    def __init__(self, *edges: Edge, **kwargs) -> None:
        """Initialize the graph with edges and optional parameters.

        Either edges or start node must be provided.

        If start node is provided but no edges, automatically traverses the graph
        from start_node to discover all reachable nodes and their edges.
        """
        self.id = kwargs.get('id', uuid4().hex)
        self.edges: list[Edge] = list(edges)
        self.nodes: set[BaseNode] = self.get_nodes_from_edges(self.edges)
        # Track whether an explicit end node was provided so inference doesn't override it later.
        self._end_node_explicit: bool = kwargs.get('end') is not None
        self.end_node: BaseNode | None = kwargs.get('end') if self._end_node_explicit else None

        start_node = None
        # Set start node/agent from edges or kwargs
        if self.edges:
            start_node = self.edges[0].from_node

        if kwargs.get('start') and isinstance(kwargs.get('start'), BaseNode):
            # this can override the start node from *edges
            start_node = kwargs.get('start')

        if not start_node:
            raise ValueError("Graph has no start node")

        self.start = start_node

        # Auto-discover nodes and edges if start_node is provided but edges are empty
        if self.start and not self.edges:
            self._discover_graph_from_start_node()
        self._infer_end_node()

    def get_nodes_from_edges(self, edges: list[Edge]) -> set[BaseNode]:
        """Extract all nodes from the given edges."""
        nodes = set()
        for edge in edges:
            nodes.add(edge.from_node)
            if edge.to_node:
                nodes.add(edge.to_node)
        return nodes

    def _discover_graph_from_start_node(self) -> None:
        """Traverse the graph from start_node to discover all nodes and edges.

        Uses breadth-first traversal to find all reachable nodes and collect
        their edges into self.edges and self.nodes.
        """
        if not self.start:
            return

        discovered_nodes: set[BaseNode] = set()
        discovered_edges: list[Edge] = []
        queue: list[BaseNode] = [self.start]

        while queue:
            current_node = queue.pop(0)

            # Skip if already discovered
            if current_node in discovered_nodes:
                continue

            discovered_nodes.add(current_node)

            # Collect edges from this node
            node_edges = getattr(current_node, 'edges', [])
            for edge in node_edges:
                if edge not in discovered_edges:
                    discovered_edges.append(edge)
                    # Add to_node to queue for further exploration
                    if edge.to_node and edge.to_node not in discovered_nodes:
                        queue.append(edge.to_node)

        self.nodes = discovered_nodes
        self.edges = discovered_edges
        self._infer_end_node()

    def add(self, *edges: Edge) -> None:
        """Add edges to the graph."""
        if not edges:
            return
        self.edges.extend(edges)
        self.nodes = self.get_nodes_from_edges(self.edges)
        self._infer_end_node()

    @abstractmethod
    async def run(self, arg: Any = None) -> Any:
        """
        Run the graph.
        """
        pass

    def _infer_end_node(self) -> None:
        """Infer the end node when it isn't explicitly provided."""
        if self._end_node_explicit:
            return
        if not self.nodes:
            self.end_node = None
            return

        sink_candidates: list[BaseNode] = []
        for node in self.nodes:
            has_outgoing = any(
                edge.to_node is not None and edge.to_node in self.nodes for edge in self.edges if edge.from_node is node
            )
            if not has_outgoing:
                sink_candidates.append(node)

        if len(sink_candidates) == 1:
            self.end_node = sink_candidates[0]
        else:
            # Ambiguous or cyclical graphs don't have an obvious end node; leave unset.
            self.end_node = None
