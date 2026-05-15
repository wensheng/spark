from typing import Any
from uuid import uuid4

from spark.core.exceptions import ActorNotStartedError
from spark.core.message import Message
from spark.graph.graph_state import GraphState
from spark.node.base import BaseNode, Edge
from spark.system import get_global_syndicate


class Graph:
    def __init__(self, *edges: Edge, **kwargs) -> None:
        self.id = kwargs.get("id", str(uuid4()))
        self.edges: list[Edge] = list(edges)
        self.nodes: set[BaseNode] = set()
        for node in self.get_nodes_from_edges(self.edges):
            self.nodes.add(node)
            # Track whether an explicit end node was provided so inference doesn't override it later.
        self._end_node_explicit: bool = kwargs.get("end") is not None
        self.end_node: BaseNode | None = kwargs.get("end") if self._end_node_explicit else None

        start_node = None
        if self.edges:
            start_node = self.edges[0].from_node
        if kwargs.get("start") and isinstance(kwargs["start"], BaseNode):
            start_node = kwargs["start"]
        self.start_node: BaseNode | None = start_node
        # Auto-discover nodes and edges if start_node is provided but edges are empty
        if self.start_node and not self.edges:
            self._discover_graph_from_start_node()
        self._infer_end_node()
        state_backend = kwargs.pop("state_backend", None)
        state_schema = kwargs.pop("state_schema", None)
        # Initialize graph state
        initial_state = kwargs.get("initial_state")
        self._state_schema = state_schema
        self.state = GraphState(initial_state, backend=state_backend, schema_model=state_schema)

        # syn = kwargs.get("syndicate")
        # if syn is not None and isinstance(syn, Syndicate):
        #     self.syndicate = syn
        # else:
        #     syn = get_existing_global_syndicate()
        #     if syn is not None:
        #         self.syndicate = syn
        #     else:
        #         self.syndicate = get_global_syndicate()
        # TODO: check there is no stray nodes, and end_node is final sink

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
        if not self.start_node:
            return

        discovered_nodes: set[BaseNode] = set()
        discovered_edges: list[Edge] = []
        queue: list[BaseNode] = [self.start_node]

        while queue:
            current_node = queue.pop(0)

            # Skip if already discovered
            if current_node in discovered_nodes:
                continue

            discovered_nodes.add(current_node)

            # Collect edges from this node
            node_edges = getattr(current_node, "edges", [])
            for edge in node_edges:
                if edge not in discovered_edges:
                    discovered_edges.append(edge)
                    # Add to_node to queue for further exploration
                    if edge.to_node and edge.to_node not in discovered_nodes:
                        queue.append(edge.to_node)

        self.nodes = discovered_nodes
        self.edges = discovered_edges

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

    def set_start_node(self, node: BaseNode) -> None:
        """Set the start node of the graph."""
        self.start_node = node
        self._discover_graph_from_start_node()
        self._infer_end_node()

    def add_node(self, node: BaseNode) -> None:
        """Add a node to the graph."""
        self.nodes.add(node)

        event_bus = getattr(self, "event_bus", None)
        if event_bus:
            attach = getattr(node, "attach_event_bus", None)
            if callable(attach):
                attach(event_bus)

        # state = getattr(self, "state", None)
        # if state:
        #    node._graph_state = state

    def add_edge(self, *edges: Edge) -> None:
        """Add edges to the graph."""
        if not edges:
            return
        self.edges.extend(edges)
        for node in self.get_nodes_from_edges(list(edges)):
            self.add_node(node)
        self._infer_end_node()

    def create_node(self, node_class: type[BaseNode], **kwargs) -> BaseNode:
        node = node_class(**kwargs)
        self.add_node(node)
        return node

    async def run(self, data: Any = None, timeout: float | None = None) -> Any:
        """Run the graph starting from the start node."""
        if not self.start_node:
            raise ValueError("Cannot run graph without a start node.")
        start_address = self.start_node.address
        if start_address is None:
            raise ActorNotStartedError(self.start_node.__class__.__name__)
        # Placeholder for actual execution logic, which would depend on the specific use case.
        print(f"Running graph {self.id} starting from node {self.start_node}")
        syn = get_global_syndicate()
        message = Message(content=data)
        return await syn.ask(start_address, message, timeout=timeout)
