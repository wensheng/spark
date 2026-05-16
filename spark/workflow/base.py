"""Workflow orchestration built on explicit Syndicate instances."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from spark.actor import ActorAddress
from spark.core.exceptions import ActorNotStartedError
from spark.workflow.graph_state import GraphState
from spark.node.base import Chain, Edge, Node
from spark.system.syndicate import Syndicate


class Workflow:
    """A directed workflow of actor-backed nodes.

    Workflows are explicit lifecycle owners: construct one with nodes/edges,
    call ``await workflow.start(system)``, then ``await workflow.run(...)``.
    They never create or use the process-wide global Syndicate.
    """

    def __init__(
        self,
        *edges: Edge,
        id: str | None = None,
        start: Node | None = None,
        end: Node | None = None,
        initial_state: dict[str, Any] | None = None,
        state_backend: Any = None,
        state_schema: type | Any | None = None,
    ) -> None:
        self.id = id or str(uuid4())
        self.edges: list[Edge] = list(edges)
        self.nodes: set[Node] = set()
        self._end_node_explicit = end is not None
        self.end_node: Node | None = end
        self.start_node: Node | None = start or (self.edges[0].from_node if self.edges else None)
        self._state_schema = state_schema
        self.state = GraphState(initial_state, backend=state_backend, schema_model=state_schema)
        self._system: Syndicate | None = None
        self._started = False
        self._owned_addresses: dict[Node, ActorAddress] = {}

        for node in self.get_nodes_from_edges(self.edges):
            self.nodes.add(node)
        if self.start_node is not None:
            self._discover_workflow_from_start_node()
        self._infer_end_node()

    @property
    def started(self) -> bool:
        """Return whether this workflow has been started."""
        return self._started

    @classmethod
    def from_chain(cls, chain: Chain, **kwargs: Any) -> Workflow:
        """Create a workflow from an existing Chain."""
        workflow = cls(start=chain.nodes[0], **kwargs)
        workflow._discover_workflow_from_start_node()
        return workflow

    def get_nodes_from_edges(self, edges: Iterable[Edge]) -> set[Node]:
        """Extract all nodes from edges."""
        nodes: set[Node] = set()
        for edge in edges:
            nodes.add(edge.from_node)
            if edge.to_node is not None:
                nodes.add(edge.to_node)
        return nodes

    def _discover_workflow_from_start_node(self) -> None:
        """Traverse reachable nodes and edges from ``start_node``."""
        if self.start_node is None:
            return

        discovered_nodes: set[Node] = set()
        discovered_edges: list[Edge] = []
        queue: deque[Node] = deque([self.start_node])

        while queue:
            current_node = queue.popleft()
            if current_node in discovered_nodes:
                continue
            discovered_nodes.add(current_node)
            for edge in current_node.edges:
                if edge not in discovered_edges:
                    discovered_edges.append(edge)
                if edge.to_node is not None and edge.to_node not in discovered_nodes:
                    queue.append(edge.to_node)

        self.nodes = discovered_nodes
        self.edges = discovered_edges

    def _infer_end_node(self) -> None:
        """Infer a single sink node when end was not provided."""
        if self._end_node_explicit:
            return
        if not self.nodes:
            self.end_node = None
            return
        sink_candidates: list[Node] = []
        for node in self.nodes:
            has_outgoing = any(
                edge.to_node is not None and edge.to_node in self.nodes for edge in self.edges if edge.from_node is node
            )
            if not has_outgoing:
                sink_candidates.append(node)
        self.end_node = sink_candidates[0] if len(sink_candidates) == 1 else None

    def set_start_node(self, node: Node) -> None:
        """Set the start node and rediscover reachable workflow structure."""
        self._ensure_not_started()
        self.start_node = node
        self._discover_workflow_from_start_node()
        self._infer_end_node()

    def add_node(self, node: Node) -> None:
        """Add a node to the workflow."""
        self._ensure_not_started()
        if not isinstance(node, Node):
            raise TypeError("workflow nodes must be Node instances")
        self.nodes.add(node)

    def add_edge(self, *edges: Edge) -> None:
        """Add one or more edges to the workflow."""
        self._ensure_not_started()
        if not edges:
            return
        self.edges.extend(edges)
        for node in self.get_nodes_from_edges(edges):
            self.nodes.add(node)
        if self.start_node is None:
            self.start_node = edges[0].from_node
        self._infer_end_node()

    def create_node(self, node_class: type[Node], **kwargs: Any) -> Node:
        """Construct and add a node instance."""
        self._ensure_not_started()
        node = node_class(**kwargs)
        self.add_node(node)
        return node

    async def start(self, system: Syndicate) -> None:
        """Initialize state and start all workflow nodes in ``system``."""
        if self._started:
            if system is not self._system:
                raise RuntimeError("workflow is already started with a different Syndicate")
            return
        if not isinstance(system, Syndicate):
            raise TypeError("Workflow.start() requires an explicit Syndicate")
        if self.start_node is None:
            raise ValueError("Cannot start workflow without a start node.")
        self._discover_workflow_from_start_node()
        self._validate()
        await self.state.initialize()
        await system.start()
        for node in self.nodes:
            if node.address is not None and node.address.actor_id.syndicate_id != system.syndicate_id:
                raise RuntimeError("workflow node is already started in a different Syndicate")
        for node in self.nodes:
            if node.address is None:
                self._owned_addresses[node] = await system.start_actor(node)
        self._system = system
        self._started = True

    async def run(self, data: Any = None, *, system: Syndicate | None = None, timeout: float | None = None) -> Any:
        """Run the workflow from its start node."""
        if system is not None:
            await self.start(system)
        if not self._started or self._system is None:
            raise RuntimeError("workflow must be started with an explicit Syndicate before run()")
        if self.start_node is None:
            raise ValueError("Cannot run workflow without a start node.")
        start_address = self.start_node.address
        if start_address is None:
            raise ActorNotStartedError(self.start_node.__class__.__name__)
        return await self._system.ask(data, start_address, timeout=timeout)

    async def shutdown(self) -> None:
        """Stop nodes that this workflow started."""
        if self._system is None:
            self._started = False
            return
        for node, address in reversed(tuple(self._owned_addresses.items())):
            if node.address is not None:
                await self._system.stop(address)
                node._context = None
        self._owned_addresses.clear()
        self._system = None
        self._started = False

    def _validate(self) -> None:
        if self.start_node is None:
            raise ValueError("workflow requires a start node")
        if self.start_node not in self.nodes:
            raise ValueError("workflow start node is not reachable")
        dangling = [edge for edge in self.edges if edge.to_node is None]
        if dangling:
            raise ValueError("workflow contains dangling edges without a target node")
        missing = [
            edge
            for edge in self.edges
            if edge.from_node not in self.nodes or (edge.to_node is not None and edge.to_node not in self.nodes)
        ]
        if missing:
            raise ValueError("workflow contains edges whose nodes are not part of the workflow")

    def _ensure_not_started(self) -> None:
        if self._started:
            raise RuntimeError("workflow structure cannot be changed after start()")


Graph = Workflow
