"""
Graphs are the top-level construct in Spark, defining the complete blueprint of an agentic workflow.
"""

import asyncio
from asyncio import QueueEmpty
import copy
import logging
import time
from collections.abc import Iterable
from typing import Any, Callable, Coroutine, Optional, final
from types import SimpleNamespace

from pydantic import BaseModel

from spark.nodes.base import BaseNode, Edge, EdgeCondition
from spark.nodes.nodes import Node
from spark.graphs.base import BaseGraph
from spark.graphs.tasks import Task, TaskType
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.nodes.channels import ChannelMessage, ForwardingChannel, BaseChannel
from spark.graphs.event_bus import GraphEventBus
from spark.graphs.graph_state import GraphState
from spark.graphs.checkpoint import GraphCheckpoint, GraphCheckpointConfig
from spark.graphs.hooks import GraphLifecycleContext, GraphLifecycleEvent, HookFn, ensure_coroutine

# Import telemetry (optional)
try:
    from spark.telemetry import TelemetryManager, TelemetryConfig, EventType, SpanKind, SpanStatus
    from spark.telemetry.instrumentation import attach_telemetry_to_node
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    TelemetryManager = None  # type: ignore
    TelemetryConfig = None  # type: ignore
    SpanStatus = None  # type: ignore

logger = logging.getLogger(__name__)


class Graph(BaseGraph):
    """
    A flow is a graph based workflow.
    Its run method is just a simple loop that runs the nodes in the flow one by one.
    The return value of run() is the return value of last node
    """

    def __init__(self, *edges: Edge, **kwargs) -> None:
        """Initialize the Graph with edges and optional parameters."""
        lifecycle_hooks = kwargs.pop('lifecycle_hooks', None)
        state_backend = kwargs.pop('state_backend', None)
        mission_control = kwargs.pop('mission_control', None)
        state_schema: type[BaseModel] | BaseModel | None = kwargs.pop('state_schema', None)
        checkpoint_config: GraphCheckpointConfig | None = kwargs.pop('checkpoint_config', None)
        super().__init__(*edges, **kwargs)
        self._running_nodes: set[BaseNode] | None = None
        self._auto_shutdown_enabled: bool = kwargs.get('auto_shutdown', True)
        self._idle_timeout: float = kwargs.get('idle_timeout', 2.0)
        self.event_bus: GraphEventBus = kwargs.get('event_bus', GraphEventBus())
        self._channel_factory: Callable[[Edge, BaseChannel], BaseChannel] | None = kwargs.get('channel_factory')
        self._channels_configured: bool = False

        # Initialize graph state
        initial_state = kwargs.get('initial_state')
        self._state_schema = state_schema
        self.state = GraphState(initial_state, backend=state_backend, schema_model=state_schema)
        self._state_enabled: bool = kwargs.get('enable_graph_state', True)
        self._checkpoint_config: GraphCheckpointConfig | None = None
        self._checkpoint_history: list[GraphCheckpoint] = []
        self._last_checkpoint_at: float | None = None
        if checkpoint_config:
            self.configure_checkpoints(checkpoint_config)

        # Initialize telemetry
        self._telemetry_config: Optional[Any] = kwargs.get('telemetry_config')
        self._telemetry_manager: Optional[Any] = None
        self._telemetry_enabled = False
        if TELEMETRY_AVAILABLE and self._telemetry_config is not None:
            self._telemetry_manager = TelemetryManager.get_instance(self._telemetry_config)
            self._telemetry_enabled = self._telemetry_config.enabled

        self._attach_event_bus_to_nodes()
        self._lifecycle_hooks: dict[GraphLifecycleEvent, list[HookFn]] = {event: [] for event in GraphLifecycleEvent}
        if lifecycle_hooks:
            for event, handlers in lifecycle_hooks.items():
                handler_list = handlers if isinstance(handlers, Iterable) else [handlers]
                for handler in handler_list:
                    self.register_hook(event, handler)
        if mission_control:
            mission_control.attach(self)
        self._event_edges_configured: bool = False
        self._delayed_ready: asyncio.Queue[BaseNode] = asyncio.Queue()
        self._delay_tasks: list[asyncio.Task] = []
        self._event_tasks: list[asyncio.Task] = []
        self._event_subscriptions: list[Any] = []

    def register_hook(self, event: GraphLifecycleEvent | str, hook: HookFn) -> None:
        """Register a lifecycle hook handler for the graph runtime."""
        normalized = event if isinstance(event, GraphLifecycleEvent) else GraphLifecycleEvent(event)
        self._lifecycle_hooks.setdefault(normalized, []).append(hook)

    async def _emit_lifecycle_event(
        self,
        event: GraphLifecycleEvent,
        task: Task,
        iteration_index: int = -1,
        last_output: NodeMessage | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit lifecycle events to registered hooks."""
        handlers = self._lifecycle_hooks.get(event)
        if not handlers:
            return
        context = GraphLifecycleContext(
            graph=self,
            task=task,
            iteration_index=iteration_index,
            last_output=last_output,
            metadata=dict(metadata or {}),
        )
        context.metadata.setdefault('event', event.value)
        for handler in handlers:
            try:
                await ensure_coroutine(handler, context)
            except Exception:
                logger.exception("Lifecycle hook failed for event=%s handler=%s", event, handler)
                raise

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
        run_metadata = {
            'task_type': task.type.value if hasattr(task.type, 'value') else str(task.type),
            'graph_id': self.id,
        }
        await self._emit_lifecycle_event(GraphLifecycleEvent.BEFORE_RUN, task, metadata=run_metadata)

        final_result: Any = None
        run_error: Exception | None = None
        try:
            if timeout_seconds:
                # Run with timeout
                final_result = await asyncio.wait_for(self._run_internal(task), timeout=timeout_seconds)
            else:
                # Run without timeout
                final_result = await self._run_internal(task)
            return final_result
        except asyncio.TimeoutError as e:
            # Timeout exceeded, stop all nodes gracefully
            self.stop_all_nodes()
            new_exc = TimeoutError(f"Graph execution exceeded max_seconds budget of {timeout_seconds} seconds")
            run_error = new_exc
            raise new_exc from e
        except Exception as exc:
            run_error = exc
            raise
        finally:
            after_metadata = dict(run_metadata)
            after_metadata['timeout_configured'] = bool(timeout_seconds)
            if run_error:
                after_metadata['error'] = str(run_error)
                after_metadata['error_type'] = type(run_error).__name__
            if final_result is not None:
                after_metadata['result'] = final_result
            last_output = final_result if isinstance(final_result, NodeMessage) else None
            await self._emit_lifecycle_event(
                GraphLifecycleEvent.AFTER_RUN,
                task,
                last_output=last_output,
                metadata=after_metadata,
            )

    async def _run_internal(self, task: Task) -> Any:
        """Internal run implementation without timeout handling."""
        inputs = task.inputs
        self._last_checkpoint_at = None
        self._delayed_ready = asyncio.Queue()
        self._delay_tasks = []
        self._event_tasks = []
        self._event_subscriptions = []
        self._event_edges_configured = False

        # Ensure nodes are discovered for timeout handling
        if not self.nodes:
            self._discover_graph_from_start_node()
            self._channels_configured = False

        self._prepare_runtime()
        await self.state.initialize()
        await self._configure_event_edges()
        # Persist campaign metadata for downstream nodes/telemetry
        campaign_info = getattr(task, 'campaign', None)
        if campaign_info and self._state_enabled:
            await self.state.set('campaign', campaign_info.model_dump())

        # Start telemetry trace if enabled
        trace = None
        if self._telemetry_enabled and self._telemetry_manager:
            trace = self._telemetry_manager.start_trace(
                name="graph_run",
                attributes={
                    'graph.type': self.__class__.__name__,
                    'graph.nodes_count': len(self.nodes),
                    'task.type': task.type.value if hasattr(task.type, 'value') else str(task.type),
                }
            )
            # Record graph started event
            self._telemetry_manager.record_event(
                type=EventType.GRAPH_STARTED,
                name="Graph execution started",
                trace_id=trace.trace_id,
                attributes={'graph_type': self.__class__.__name__}
            )
            # Attach telemetry context to all nodes
            telemetry_context = self._telemetry_manager.create_context(trace.trace_id)
            for node in self.nodes:
                setattr(node, '_telemetry_context', telemetry_context)
                if self._telemetry_config.auto_instrument_nodes:
                    attach_telemetry_to_node(node, self._telemetry_manager)

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

            # End telemetry trace for LONG_RUNNING
            if trace and self._telemetry_manager:
                self._telemetry_manager.record_event(
                    type=EventType.GRAPH_FINISHED,
                    name="Graph execution finished",
                    trace_id=trace.trace_id,
                    attributes={'task_type': 'LONG_RUNNING'}
                )
                self._telemetry_manager.end_trace(trace.trace_id)

            await self._cleanup_async_helpers()
            return self.end_node.outputs if self.end_node else None

        # For regular tasks, track nodes for timeout handling
        self._running_nodes = self.nodes
        try:
            active_nodes: set[BaseNode] = {self.start}
            initial_run = True
            iteration_index = 0

            while active_nodes:
                processed_nodes = list(active_nodes)
                active_nodes = set()
                jobs = []
                current_data = inputs if initial_run else NodeMessage(content='', metadata={})
                before_metadata = {
                    'active_nodes': len(processed_nodes),
                    'initial_run': initial_run,
                }
                await self._emit_lifecycle_event(
                    GraphLifecycleEvent.BEFORE_ITERATION,
                    task,
                    iteration_index=iteration_index,
                    last_output=last_output,
                    metadata=before_metadata,
                )

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
                    active_edges = node.iter_active_edges()
                    for edge in active_edges:
                        if edge.is_event_driven:
                            continue
                        successor_node = edge.to_node
                        if successor_node is None:
                            continue
                        if edge.delay_seconds and edge.delay_seconds > 0:
                            payload = copy.deepcopy(node.outputs)
                            self._schedule_delayed_activation(edge, payload)
                            continue
                        should_schedule = await successor_node.receive_from_parent(node)
                        if should_schedule:
                            active_nodes.add(successor_node)

                while not active_nodes and self._delayed_ready.empty():
                    if not self._has_pending_delay_tasks():
                        break
                    try:
                        successor = await self._delayed_ready.get()
                    except asyncio.CancelledError:
                        break
                    active_nodes.add(successor)

                delayed_ready = self._drain_delayed_successors()
                active_nodes.update(delayed_ready)
                after_metadata = {
                    'active_nodes': len(processed_nodes),
                    'initial_run': before_metadata['initial_run'],
                    'jobs_run': len(jobs),
                    'scheduled_successors': len(active_nodes),
                }
                await self._emit_lifecycle_event(
                    GraphLifecycleEvent.AFTER_ITERATION,
                    task,
                    iteration_index=iteration_index,
                    last_output=last_output,
                    metadata=after_metadata,
                )
                await self._emit_lifecycle_event(
                    GraphLifecycleEvent.ITERATION_COMPLETE,
                    task,
                    iteration_index=iteration_index,
                    last_output=last_output,
                    metadata=after_metadata,
                )
                await self._maybe_checkpoint(iteration_index + 1, task)
                iteration_index += 1

            if last_output is None:
                if self.end_node and isinstance(self.end_node.outputs, NodeMessage):
                    last_output = self.end_node.outputs
                elif isinstance(self.start.outputs, NodeMessage):
                    last_output = self.start.outputs

            # End telemetry trace for regular tasks
            if trace and self._telemetry_manager:
                self._telemetry_manager.record_event(
                    type=EventType.GRAPH_FINISHED,
                    name="Graph execution finished",
                    trace_id=trace.trace_id,
                    attributes={'task_type': 'REGULAR'}
                )
                self._telemetry_manager.end_trace(trace.trace_id)

            return last_output
        except Exception as e:
            # Record graph failure
            if trace and self._telemetry_manager:
                self._telemetry_manager.record_event(
                    type=EventType.GRAPH_FAILED,
                    name="Graph execution failed",
                    trace_id=trace.trace_id,
                    attributes={
                        'error': str(e),
                        'error_type': type(e).__name__
                    }
                )
                self._telemetry_manager.end_trace(trace.trace_id, status=SpanStatus.ERROR)
            raise
        finally:
            self._running_nodes = None  # Clear after completion
            await self._cleanup_async_helpers()

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

    async def _configure_event_edges(self) -> None:
        if self._event_edges_configured:
            return
        self._event_edges_configured = True
        for edge in self.edges:
            if not edge.event_topic or edge.to_node is None:
                continue
            subscription = await self.event_bus.subscribe(edge.event_topic)
            self._event_subscriptions.append(subscription)
            task = asyncio.create_task(self._event_edge_worker(edge, subscription))
            self._event_tasks.append(task)

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

    def reset_state(self, new_state: dict[str, Any] | None = None, *, preserve_backend: bool = True) -> None:
        """Reset graph state (useful between runs).

        Args:
            new_state: Optional new state dictionary. If None, state is cleared.
            preserve_backend: Whether to re-use the existing state backend.
        """
        backend = getattr(self.state, '_backend', None) if preserve_backend else None
        if backend and preserve_backend:
            try:
                backend.clear()
            except Exception:
                logger.debug("State backend does not support clear(); continuing with existing data.")
        self.state = GraphState(new_state, backend=backend, schema_model=self._state_schema)

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get a snapshot of current state.

        Returns:
            A shallow copy of the state dictionary.
        """
        return self.state.get_snapshot()

    def configure_checkpoints(self, config: GraphCheckpointConfig | dict[str, Any] | None) -> None:
        """Configure auto-checkpointing behavior."""
        if config is None:
            self._checkpoint_config = None
            return
        if isinstance(config, GraphCheckpointConfig):
            self._checkpoint_config = config.clone()
        else:
            self._checkpoint_config = GraphCheckpointConfig.from_dict(dict(config))

    def get_checkpoint_config(self) -> GraphCheckpointConfig | None:
        """Return current checkpointing configuration."""
        return self._checkpoint_config.clone() if self._checkpoint_config else None

    def get_checkpoint_history(self) -> list[GraphCheckpoint]:
        """List recent checkpoints created by auto-checkpointing."""
        return list(self._checkpoint_history)

    async def checkpoint_state(
        self,
        *,
        iteration: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GraphCheckpoint:
        """Create a checkpoint containing the graph state."""
        checkpoint = GraphCheckpoint.create(
            graph_id=self.id or 'graph',
            state=self.state.get_snapshot(),
            iteration=iteration,
            schema=self.state.describe_schema(),
            metadata=metadata,
        )
        checkpoint.metadata.setdefault('backend', self.state.describe_backend())
        return checkpoint

    async def restore_state(self, snapshot: GraphCheckpoint | dict[str, Any]) -> None:
        """Restore state from a checkpoint snapshot."""
        checkpoint = GraphCheckpoint.ensure(snapshot)
        await self.state.reset(dict(checkpoint.state))

    async def resume_from(
        self,
        checkpoint: GraphCheckpoint | dict[str, Any],
        *,
        overrides: dict[str, Any] | None = None,
        task: Task | None = None,
    ) -> Any:
        """Resume execution from a checkpoint."""
        checkpoint_obj = GraphCheckpoint.ensure(checkpoint)
        await self.state.reset(dict(checkpoint_obj.state))
        if overrides:
            await self.state.update(dict(overrides))
        resume_task = task.model_copy(deep=True) if task is not None else Task()
        resume_task.type = TaskType.RESUMABLE
        resume_task.metadata = dict(resume_task.metadata or {})
        resume_task.metadata.setdefault('checkpoint_id', checkpoint_obj.checkpoint_id)
        if hasattr(resume_task, 'resume_from'):
            resume_task.resume_from = checkpoint_obj.checkpoint_id  # type: ignore[attr-defined]
        return await self.run(resume_task)

    async def _maybe_checkpoint(self, iteration_index: int, task: Task) -> None:
        """Emit auto-checkpoints when configured."""
        if not self._checkpoint_config:
            return
        now = time.time()
        if not self._checkpoint_config.should_checkpoint(
            iteration_index,
            now=now,
            last_checkpoint_at=self._last_checkpoint_at,
        ):
            return
        metadata = dict(self._checkpoint_config.metadata)
        metadata.setdefault('task_type', task.type.value if hasattr(task.type, 'value') else str(task.type))
        checkpoint = await self.checkpoint_state(iteration=iteration_index, metadata=metadata)
        self._checkpoint_history.append(checkpoint)
        retain = self._checkpoint_config.retain_last
        if retain and retain > 0 and len(self._checkpoint_history) > retain:
            self._checkpoint_history = self._checkpoint_history[-retain:]
        self._last_checkpoint_at = checkpoint.created_at
        if self._checkpoint_config.handler:
            await ensure_coroutine(self._checkpoint_config.handler, checkpoint)

    async def _event_edge_worker(self, edge: Edge, subscription: Any) -> None:
        try:
            async for message in subscription:
                successor = edge.to_node
                if successor is None:
                    continue
                payload = getattr(message, 'payload', message)
                if edge.event_filter and not self._event_filter_matches(edge.event_filter, payload):
                    continue
                node_message = payload if isinstance(payload, NodeMessage) else NodeMessage(content=payload, metadata={})
                successor.enqueue_input(node_message)
                await self._delayed_ready.put(successor)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Event edge worker failed for topic=%s", edge.event_topic)
        finally:
            await subscription.close()

    def _event_filter_matches(self, condition: EdgeCondition, payload: Any) -> bool:
        dummy = SimpleNamespace()
        dummy.outputs = NodeMessage(content=payload, metadata={})
        return condition.check(dummy)  # type: ignore[arg-type]

    def _drain_delayed_successors(self) -> set[BaseNode]:
        ready: set[BaseNode] = set()
        while True:
            try:
                successor = self._delayed_ready.get_nowait()
            except QueueEmpty:
                break
            ready.add(successor)
        return ready

    def _schedule_delayed_activation(
        self,
        edge: Edge,
        payload: NodeMessage | dict[str, Any] | list[dict[str, Any]] | None,
    ) -> None:
        task = asyncio.create_task(self._delayed_activation(edge, payload))
        self._delay_tasks.append(task)

    async def _delayed_activation(self, edge: Edge, payload: Any) -> None:
        try:
            await asyncio.sleep(edge.delay_seconds or 0)
            successor = edge.to_node
            if successor is None:
                return
            successor.enqueue_input(payload)
            await self._delayed_ready.put(successor)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Delayed activation failed for edge=%s", edge.id)

    def _has_pending_delay_tasks(self) -> bool:
        return any(not task.done() for task in self._delay_tasks)

    async def _cancel_tasks(self, tasks: list[asyncio.Task]) -> None:
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Helper task failed during shutdown", exc_info=True)
        tasks.clear()

    async def _cleanup_async_helpers(self) -> None:
        await self._cancel_tasks(self._delay_tasks)
        await self._cancel_tasks(self._event_tasks)
        for subscription in self._event_subscriptions:
            try:
                await subscription.close()
            except Exception:
                logger.debug("Failed to close event subscription", exc_info=True)
        self._event_subscriptions.clear()
        self._event_edges_configured = False
        while True:
            try:
                self._delayed_ready.get_nowait()
            except QueueEmpty:
                break
        self._delayed_ready = asyncio.Queue()


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
