"""
Graphs are the top-level construct in Spark, defining the complete blueprint of an agentic workflow.
"""

import asyncio
import copy
from typing import Any, Callable, Coroutine, Optional, final

from spark.nodes.base import BaseNode, Edge
from spark.nodes.nodes import Node
from spark.graphs.base import BaseGraph
from spark.graphs.tasks import Task, TaskType
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.nodes.channels import ChannelMessage, ForwardingChannel, BaseChannel
from spark.graphs.event_bus import GraphEventBus
from spark.graphs.graph_state import GraphState


class Graph(BaseGraph):
    """
    A flow is a graph based workflow.
    Its run method is just a simple loop that runs the nodes in the flow one by one.
    The return value of run() is the return value of last node
    """

    def __init__(self, *edges: Edge, **kwargs) -> None:
        """Initialize the Graph with edges and optional parameters."""
        super().__init__(*edges, **kwargs)
        self._running_nodes: set[BaseNode] | None = None
        self._auto_shutdown_enabled: bool = kwargs.get('auto_shutdown', True)
        self._idle_timeout: float = kwargs.get('idle_timeout', 2.0)
        self.event_bus: GraphEventBus = kwargs.get('event_bus', GraphEventBus())
        self._channel_factory: Callable[[Edge, BaseChannel], BaseChannel] | None = kwargs.get('channel_factory')
        self._channels_configured: bool = False

        # Initialize graph state
        initial_state = kwargs.get('initial_state')
        self.state = GraphState(initial_state)
        self._state_enabled: bool = kwargs.get('enable_graph_state', True)

        self._attach_event_bus_to_nodes()

    @final
    async def run(self, arg: Any = None) -> Any:
        """
        Runs the graph starting from the start node.
        Allows concurrent execution if a node branches to multiple next nodes.
        How it works:
        When a node finishes processing, call receive_from_parent() on each successor node,
        passing the parent's outputs. The successor node stores this in its _pending_inputs queue
        On the next iteration, when the successor runs, pop_ready_input() retrieves this input
        This input is then passed to the node's do() method, making it available in the context.inputs

        If task.budget.max_seconds is set, the graph will automatically stop after that duration.
        """
        if arg:
            if isinstance(arg, Task):
                task = arg
            elif isinstance(arg, NodeMessage):
                task = Task(inputs=arg)
            elif isinstance(arg, dict):
                task = Task(inputs=NodeMessage(content=arg, metadata={}))
            else:
                task = Task(inputs=NodeMessage(content=str(arg), metadata={}))
        else:
            task = Task(inputs=NodeMessage(content='', metadata={}))

        # Check if timeout is configured
        timeout_seconds = task.budget.max_seconds if task.budget.max_seconds > 0 else None

        try:
            if timeout_seconds:
                # Run with timeout
                return await asyncio.wait_for(self._run_internal(task), timeout=timeout_seconds)
            else:
                # Run without timeout
                return await self._run_internal(task)
        except asyncio.TimeoutError as e:
            # Timeout exceeded, stop all nodes gracefully
            self.stop_all_nodes()
            raise TimeoutError(f"Graph execution exceeded max_seconds budget of {timeout_seconds} seconds") from e

    async def _run_internal(self, task: Task) -> Any:
        """Internal run implementation without timeout handling."""
        inputs = task.inputs

        # Ensure nodes are discovered for timeout handling
        if not self.nodes:
            self._discover_graph_from_start_node()
            self._channels_configured = False

        self._prepare_runtime()

        # Configure state mode based on task type
        if task.type == TaskType.LONG_RUNNING:
            self.state.enable_concurrent_mode()
        else:
            self.state.disable_concurrent_mode()

        jobs: list[Coroutine[Any, Any, Optional[NodeMessage]]]
        last_output: NodeMessage | None = None

        if task.type == TaskType.LONG_RUNNING:
            # For long-running tasks, discover all nodes and start them as continuous workers
            all_nodes = self.nodes
            self._running_nodes = all_nodes  # Store for later stopping

            # Send initial inputs to the start node's queue
            await self.start.mailbox.send(
                ChannelMessage(payload=inputs, metadata={'source': 'graph', 'kind': 'initial'})
            )

            # Create jobs for all nodes' go() methods
            jobs = [node.go() for node in all_nodes]

            # Add idle monitor if auto_shutdown is enabled
            if self._auto_shutdown_enabled:
                jobs.append(self._monitor_idle_and_shutdown())

            # Start all nodes concurrently as long-running workers
            await asyncio.gather(*jobs)
            self._running_nodes = None  # Clear after completion
            return self.end_node.outputs if self.end_node else None

        # For regular tasks, track nodes for timeout handling
        self._running_nodes = self.nodes
        try:
            active_nodes: set[BaseNode] = {self.start}
            initial_run = True

            while active_nodes:
                processed_nodes = list(active_nodes)
                active_nodes = set()
                jobs = []
                current_data = inputs if initial_run else NodeMessage(content='', metadata={})

                for node in processed_nodes:
                    run_input = node.pop_ready_input()
                    if run_input is None:
                        if node is self.start and initial_run:
                            run_input = current_data
                        else:
                            run_input = (
                                node.outputs if node.outputs is not None else NodeMessage(content='', metadata={})
                            )
                    jobs.append(node.do(run_input))

                if jobs:
                    results = await asyncio.gather(*jobs)
                    for node, result in zip(processed_nodes, results):
                        # Prefer sink node outputs but fall back to last processed node.
                        if not node.get_next_nodes():
                            last_output = result
                        elif last_output is None:
                            last_output = result
                    initial_run = False

                for node in processed_nodes:
                    successors = node.get_next_nodes()
                    for successor_node in successors:
                        if successor_node is None:
                            continue
                        should_schedule = await successor_node.receive_from_parent(node)
                        if should_schedule:
                            active_nodes.add(successor_node)

            if last_output is None:
                if self.end_node and isinstance(self.end_node.outputs, NodeMessage):
                    return self.end_node.outputs
                if isinstance(self.start.outputs, NodeMessage):
                    return self.start.outputs
            return last_output
        finally:
            self._running_nodes = None  # Clear after completion

    async def _monitor_idle_and_shutdown(self) -> None:
        """Monitor nodes for idle state and automatically shutdown when all nodes are idle.

        A node is considered idle when:
        1. Its mailbox is empty
        2. It's not currently processing (not actively waiting on mailbox.receive())

        When all nodes have been idle for idle_timeout seconds, automatically stop all nodes.
        """
        if self._running_nodes is None:
            return

        while True:
            await asyncio.sleep(self._idle_timeout)

            # Check if all nodes are stopped
            all_stopped = all(
                getattr(node, '_stop_flag', False) for node in self._running_nodes if hasattr(node, '_stop_flag')
            )
            if all_stopped:
                break

            # Check if all mailboxes are empty and nodes are idle
            all_idle = True
            for node in self._running_nodes:
                mailbox = getattr(node, 'mailbox', None)
                if mailbox is None:
                    continue
                if not mailbox.empty():
                    all_idle = False
                    break
                if node._state['processing']:
                    all_idle = False
                    break

            if all_idle:
                # All nodes are idle, trigger shutdown
                print("[System] All nodes idle, triggering automatic shutdown...")
                await self._stop_all_nodes_async()
                break

    async def _stop_all_nodes_async(self) -> None:
        """Stop all running nodes asynchronously.

        This method sets the stop flag on all currently running nodes and
        sends a shutdown sentinel to unblock any nodes waiting on queue.get().
        """
        if self._running_nodes is None:
            return

        # First, set all stop flags
        for node in self._running_nodes:
            if hasattr(node, 'stop'):
                node.stop()

        # Then send shutdown sentinels to all mailboxes to unblock waiting nodes
        for node in self._running_nodes:
            mailbox = getattr(node, 'mailbox', None)
            if mailbox is None:
                continue
            try:
                await mailbox.send(
                    ChannelMessage(payload=None, is_shutdown=True, metadata={'reason': 'graph_shutdown'})
                )
            except Exception as e:
                print(f"[Debug] Failed to send sentinel to node: {e}")

        # Give nodes a moment to process the sentinels
        await asyncio.sleep(0.1)

    def stop_all_nodes(self) -> None:
        """Stop all running nodes in the graph gracefully.

        This method sets the stop flag on all currently running nodes and
        sends a shutdown sentinel to unblock any nodes waiting on queue.get().
        Nodes will finish processing their current message before stopping.
        Only applicable for long-running tasks.

        Note: This is a synchronous wrapper. For async contexts, nodes may not
        immediately unblock. Consider using the async monitor instead.
        """
        if self._running_nodes is None:
            return

        for node in self._running_nodes:
            if hasattr(node, 'stop'):
                node.stop()
            mailbox = getattr(node, 'mailbox', None)
            if mailbox is None:
                continue
            try:
                mailbox.send_nowait(
                    ChannelMessage(payload=None, is_shutdown=True, metadata={'reason': 'graph_shutdown'})
                )
            except Exception:
                pass  # Mailbox might be full or closed, that's okay

    def add(self, *edges: Edge) -> None:
        """Add edges to the graph and refresh runtime wiring."""
        super().add(*edges)
        self._channels_configured = False
        self._attach_event_bus_to_nodes()

    def _prepare_runtime(self) -> None:
        """Ensure runtime services (event bus, channels, state) are configured."""
        self._attach_event_bus_to_nodes()
        self._attach_graph_state_to_nodes()
        if not self._channels_configured:
            self._configure_edge_channels()

    def _attach_event_bus_to_nodes(self) -> None:
        for node in self.nodes:
            attach = getattr(node, 'attach_event_bus', None)
            if callable(attach):
                attach(self.event_bus)

    def _attach_graph_state_to_nodes(self) -> None:
        """Inject graph state reference into all nodes."""
        if not self._state_enabled:
            return
        for node in self.nodes:
            setattr(node, '_graph_state', self.state)

    def _configure_edge_channels(self) -> None:
        for edge in self.edges:
            target = edge.to_node
            if target is None:
                continue
            downstream = getattr(target, 'mailbox', None)
            if downstream is None:
                continue
            if self._channel_factory:
                edge.channel = self._channel_factory(edge, downstream)
            else:
                metadata_defaults = {
                    'edge_id': str(edge.id),
                    'from_node_id': getattr(edge.from_node, 'id', None),
                    'to_node_id': getattr(target, 'id', None),
                }
                edge.channel = ForwardingChannel(
                    downstream,
                    metadata_defaults=metadata_defaults,
                    name=f'edge:{edge.id}',
                )
        self._channels_configured = True

    # Graph state helper methods

    async def get_state(self, key: str, default: Any = None) -> Any:
        """Get value from graph state.

        Args:
            key: The key to retrieve.
            default: Default value if key doesn't exist.

        Returns:
            The value associated with the key, or default if not found.
        """
        return await self.state.get(key, default)

    async def set_state(self, key: str, value: Any) -> None:
        """Set value in graph state.

        Args:
            key: The key to set.
            value: The value to associate with the key.
        """
        await self.state.set(key, value)

    async def update_state(self, updates: dict[str, Any]) -> None:
        """Batch update graph state.

        Args:
            updates: Dictionary of key-value pairs to update.
        """
        await self.state.update(updates)

    def reset_state(self, new_state: dict[str, Any] | None = None) -> None:
        """Reset graph state (useful between runs).

        Args:
            new_state: Optional new state dictionary. If None, state is cleared.
        """
        self.state = GraphState(new_state)

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get a snapshot of current state.

        Returns:
            A shallow copy of the state dictionary.
        """
        return self.state.get_snapshot()


class SubgraphNode(Node):
    """Wrap a graph so it can execute as a single node within another flow."""

    def __init__(
        self,
        graph: 'BaseGraph',
        io_map: dict[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if not isinstance(graph, BaseNode):
            raise TypeError('SubgraphNode requires a graph derived from Node.')
        self._graph_template: 'BaseGraph' = graph
        self._io_map = dict(io_map or {})
        self._previous_output_keys: set[str] = set()

    async def process(self, context: ExecutionContext) -> Any:
        runtime_flow = self._clone_flow()
        self._apply_event_sink(runtime_flow)
        initial_keys: set[str] = set(context.state.__dict__.keys())
        baseline_keys = initial_keys - self._previous_output_keys
        sub_input = self._prepare_subgraph_input()
        result = await runtime_flow.run(sub_input)
        output = self._prepare_subgraph_output(result, runtime_flow)

        if isinstance(output, dict):
            for key, value in output.items():
                setattr(context.state, key, self._safe_copy(value))
            self._previous_output_keys = {key for key in output if key not in baseline_keys}
        else:
            setattr(context.state, 'subgraph_output', self._safe_copy(output))
            self._previous_output_keys = set()

        return output

    def _clone_flow(self) -> 'BaseGraph':
        clone_method = getattr(self._graph_template, 'copy', None)
        if callable(clone_method):
            return clone_method()  # type: ignore[return-value]
        return copy.deepcopy(self._graph_template)

    def _apply_event_sink(self, flow: 'BaseGraph') -> None:
        # Note: event_sink is not defined on SubgraphNode in the type system
        # This is a runtime attribute that may be set dynamically
        sink = getattr(self, 'event_sink', None)  # type: ignore[attr-defined]
        if sink is None:
            return
        setattr(flow, 'event_sink', sink)  # type: ignore[attr-defined]
        for node in self._iterate_nodes(flow):
            setattr(node, 'event_sink', sink)  # type: ignore[attr-defined]

    def _iterate_nodes(self, flow: 'BaseGraph') -> list[BaseNode]:
        start = getattr(flow, 'start', None)
        if not isinstance(start, BaseNode):
            return []
        seen: set[BaseNode] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(child for child in node.get_next_nodes() if isinstance(child, BaseNode) and child not in seen)
        return list(seen)

    def _prepare_subgraph_input(self) -> NodeMessage:
        # Note: self.context is not defined on SubgraphNode - should use self._state
        snapshot = self._safe_copy(getattr(self, 'context', {}).get('state', self._state))  # type: ignore[attr-defined]
        if not isinstance(snapshot, dict):
            snapshot = NodeMessage(content=snapshot, metadata={})
        for key in self._previous_output_keys:
            snapshot.content.pop(key, None)
        if self._io_map:
            for outer_key, inner_key in self._io_map.items():
                if outer_key in snapshot and inner_key != outer_key:
                    snapshot.content[inner_key] = snapshot.content.pop(outer_key)
        return NodeMessage(content=snapshot, metadata={})

    def _prepare_subgraph_output(self, result: Any, flow: 'BaseGraph') -> Any:
        flow_ctx = getattr(flow, 'context.state', None)
        base_ctx = self._safe_copy(flow_ctx) if isinstance(flow_ctx, dict) else NodeMessage(content='', metadata={})

        if isinstance(result, dict):
            payload = base_ctx
            payload.content.update(self._safe_copy(result))
        elif base_ctx:
            payload = base_ctx.content
        else:
            return self._safe_copy(result)

        if self._io_map:
            for outer_key, inner_key in self._io_map.items():
                if inner_key in payload and inner_key != outer_key:
                    value = payload.content.pop(inner_key)
                    payload.content[outer_key] = value
        return payload

    def _safe_copy(self, value: Any) -> Any:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value
