"""
Graphs are the top-level construct in Spark, defining the complete blueprint of an agentic workflow.
"""

import asyncio
from asyncio import QueueEmpty
import copy
import inspect
import logging
import time
from collections.abc import Iterable
from typing import Any, Awaitable, Callable, Coroutine, Optional, final
from types import SimpleNamespace

from pydantic import BaseModel

from spark.nodes.base import BaseNode, Edge, EdgeCondition
from spark.nodes.nodes import Node
from spark.graphs.base import BaseGraph
from spark.graphs.tasks import (
    CampaignBudgetError,
    Task,
    TaskBatchResult,
    TaskDependencyError,
    TaskScheduler,
    TaskType,
)
from spark.graphs.mailbox import MailboxPersistenceManager
from spark.graphs.artifacts import ArtifactManager, ArtifactPolicy
from spark.utils.logging_utils import structured_log_context, get_structured_logger
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.nodes.channels import ChannelMessage, ForwardingChannel, BaseChannel
from spark.graphs.event_bus import GraphEventBus
from spark.graphs.graph_state import GraphState
from spark.graphs.workspace import Workspace
from spark.graphs.checkpoint import GraphCheckpoint, GraphCheckpointConfig
from spark.graphs.hooks import GraphLifecycleContext, GraphLifecycleEvent, HookFn, ensure_coroutine
from spark.governance.approval import ApprovalGateManager, ApprovalPendingError
from spark.governance.policy import (
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    PolicyRule,
    PolicySet,
    PolicySubject,
    PolicyViolationError,
)

# Import telemetry (optional)
try:
    from spark.telemetry import TelemetryManager, TelemetryConfig, EventType, SpanKind, SpanStatus
    from spark.telemetry.instrumentation import attach_telemetry_to_node, instrument_edge_transition
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    TelemetryManager = None  # type: ignore
    TelemetryConfig = None  # type: ignore
    SpanStatus = None  # type: ignore

logger = logging.getLogger(__name__)


async def _call_optional(
    fn: Callable[..., Any] | None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Invoke optional callbacks that may be async or sync."""

    if fn is None:
        return None
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class Graph(BaseGraph):
    """
    A flow is a graph based workflow.
    Its run method is just a simple loop that runs the nodes in the flow one by one.
    The return value of run() is the return value of last node
    """

    def __init__(self, *edges: Edge, **kwargs) -> None:
        """Initialize the Graph with edges and optional parameters."""
        policy_engine = kwargs.pop('policy_engine', None)
        policy_set = kwargs.pop('policy_set', None)
        policy_rules = kwargs.pop('policy_rules', None)
        policy_state_key = kwargs.pop('policy_state_key', 'policy_events')
        approval_state_key = kwargs.pop('approval_state_key', 'approval_requests')
        lifecycle_hooks = kwargs.pop('lifecycle_hooks', None)
        state_backend = kwargs.pop('state_backend', None)
        mission_control = kwargs.pop('mission_control', None)
        workspace: Workspace | None = kwargs.pop('workspace', None)
        artifact_manager: ArtifactManager | None = kwargs.pop('artifact_manager', None)
        artifact_policy: ArtifactPolicy | None = kwargs.pop('artifact_policy', None)
        state_schema: type[BaseModel] | BaseModel | None = kwargs.pop('state_schema', None)
        checkpoint_config: GraphCheckpointConfig | None = kwargs.pop('checkpoint_config', None)
        super().__init__(*edges, **kwargs)
        self._policy_state_key = policy_state_key
        self._policy_engine: PolicyEngine | None = self._initialize_policy_engine(
            policy_engine,
            policy_set,
            policy_rules,
        )
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
        self._mailbox_manager: MailboxPersistenceManager | None = None
        self.workspace: Workspace | None = workspace
        self.artifacts: ArtifactManager | None = artifact_manager or (
            ArtifactManager(self.state, policy=artifact_policy) if artifact_policy else None
        )
        approval_state = self.state if self._state_enabled else None
        self._approval_manager = ApprovalGateManager(approval_state, storage_key=approval_state_key)
        self._attach_policy_engine_to_nodes()

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

    def _build_task_metadata_payload(self, task: Task) -> dict[str, Any]:
        """Construct a serializable snapshot of task metadata."""

        if not task.task_id:
            return {}
        metadata: dict[str, Any] = {
            'task_id': task.task_id,
            'type': task.type.value if hasattr(task.type, 'value') else str(task.type),
            'depends_on': list(task.depends_on),
            'priority': task.priority,
            'resume_from': task.resume_from,
        }
        if task.budget:
            metadata['budget'] = task.budget.model_dump()
        if task.campaign:
            metadata['campaign'] = task.campaign.model_dump()
        if task.metadata:
            metadata['metadata'] = dict(task.metadata)
        return metadata

    async def _persist_task_metadata(
        self,
        task: Task,
        status: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Store task metadata in graph state for observability."""

        if not self._state_enabled or not task.task_id:
            return
        payload = self._build_task_metadata_payload(task)
        if not payload:
            return
        existing = await self.state.get('task_metadata', {})
        if isinstance(existing, dict) and existing.get('task_id') == task.task_id:
            for key in ('started_at', 'campaign', 'budget', 'metadata'):
                if key in existing and key not in payload:
                    payload[key] = existing[key]
        payload['status'] = status
        payload['updated_at'] = time.time()
        if extra:
            payload.update(extra)
        await self.state.set('task_metadata', payload)

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
        run_started_at = time.perf_counter()
        await self._emit_lifecycle_event(GraphLifecycleEvent.BEFORE_RUN, task, metadata=run_metadata)

        final_result: Any = None
        run_error: Exception | None = None
        structured_logger = get_structured_logger()
        context_fields = {
            'graph_id': self.id,
            'graph_class': self.__class__.__name__,
            'task_id': task.task_id,
            'task_type': task.type.value if hasattr(task.type, 'value') else str(task.type),
        }
        campaign_info = getattr(task, 'campaign', None)
        if campaign_info:
            context_fields['campaign_id'] = getattr(campaign_info, 'campaign_id', None)

        with structured_log_context(**context_fields):
            structured_logger.info('graph.run.start')
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
                await self._disable_mailbox_persistence()
                after_metadata = dict(run_metadata)
                after_metadata['timeout_configured'] = bool(timeout_seconds)
                if run_error:
                    after_metadata['error'] = str(run_error)
                    after_metadata['error_type'] = type(run_error).__name__
                if final_result is not None:
                    after_metadata['result'] = final_result
                duration = time.perf_counter() - run_started_at
                task_status = 'failed' if run_error else 'completed'
                status_extra = {'duration_seconds': duration}
                if run_error:
                    status_extra['error'] = str(run_error)
                    status_extra['error_type'] = type(run_error).__name__
                await self._persist_task_metadata(task, task_status, extra=status_extra)
                last_output = final_result if isinstance(final_result, NodeMessage) else None
                await self._emit_lifecycle_event(
                    GraphLifecycleEvent.AFTER_RUN,
                    task,
                    last_output=last_output,
                    metadata=after_metadata,
                )
                structured_logger.info(
                    'graph.run.finish',
                    status=task_status,
                    duration_seconds=duration,
                    error=str(run_error) if run_error else None,
                )
                await self._finalize_workspace(run_error)
                await self._finalize_artifacts(run_error)

    async def _run_internal(self, task: Task) -> Any:
        """Internal run implementation without timeout handling."""
        inputs = task.inputs
        self._last_checkpoint_at = None
        self._delayed_ready = asyncio.Queue()
        self._delay_tasks = []
        self._event_tasks = []
        self._event_subscriptions = []
        self._event_edges_configured = False
        is_long_lived_task = task.type in (TaskType.LONG_RUNNING, TaskType.RESUMABLE)

        # Ensure nodes are discovered for timeout handling
        if not self.nodes:
            self._discover_graph_from_start_node()
            self._attach_policy_engine_to_nodes()
            self._channels_configured = False

        await self.state.initialize()
        await self._enforce_policy_for_task(task)
        if self.workspace:
            await self.workspace.ensure_directories()
            if self._state_enabled:
                await self.state.set('workspace', self.workspace.describe())
        if is_long_lived_task:
            await self._enable_mailbox_persistence()
        self._prepare_runtime()
        await self._configure_event_edges()
        await self._persist_task_metadata(task, 'running', extra={'started_at': time.time()})
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
                setattr(node, '_telemetry_manager', self._telemetry_manager)
                if self._telemetry_config.auto_instrument_nodes:
                    attach_telemetry_to_node(node, self._telemetry_manager)

        # Configure state mode based on task type
        if is_long_lived_task:
            self.state.enable_concurrent_mode()
        else:
            self.state.disable_concurrent_mode()

        jobs: list[Coroutine[Any, Any, Optional[NodeMessage]]]
        last_output: NodeMessage | None = None

        if is_long_lived_task:
            # For long-running tasks, discover all nodes and start them as continuous workers
            all_nodes = self.nodes
            self._running_nodes = all_nodes  # Store for later stopping

            # Send initial inputs to the start node's queue
            await self.start.mailbox.send(
                ChannelMessage(payload=inputs, metadata={'source': 'graph', 'kind': 'initial'})
            )

            # Create jobs for all nodes' go() methods
            for node in all_nodes:
                await self._enforce_policy_for_node(node, task)
            jobs = [node.go() for node in all_nodes]

            # Add idle monitor if auto_shutdown is enabled
            if self._auto_shutdown_enabled:
                jobs.append(self._monitor_idle_and_shutdown())

            # Start all nodes concurrently as long-running workers
            await asyncio.gather(*jobs)
            self._running_nodes = None  # Clear after completion

            # End telemetry trace for long-lived runs
            if trace and self._telemetry_manager:
                self._telemetry_manager.record_event(
                    type=EventType.GRAPH_FINISHED,
                    name="Graph execution finished",
                    trace_id=trace.trace_id,
                    attributes={'task_type': task.type.value if hasattr(task.type, 'value') else str(task.type)}
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

            while (
                active_nodes
                or not self._delayed_ready.empty()
                or self._has_pending_delay_tasks()
                or self._has_pending_event_messages()
            ):
                if not active_nodes:
                    if not self._delayed_ready.empty():
                        active_nodes.update(self._drain_delayed_successors())
                        continue
                    if self._has_pending_delay_tasks():
                        try:
                            successor = await self._delayed_ready.get()
                        except asyncio.CancelledError:
                            break
                        active_nodes.add(successor)
                        continue
                    if self._has_pending_event_messages():
                        await asyncio.sleep(0)
                        continue
                    break
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
                    await self._enforce_policy_for_node(node, task)
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
                        if (
                            TELEMETRY_AVAILABLE
                            and self._telemetry_manager
                            and instrument_edge_transition is not None
                        ):
                            try:
                                await instrument_edge_transition(
                                    node,
                                    successor_node,
                                    edge.condition,
                                    self._telemetry_manager,
                                )
                            except Exception:
                                logger.exception('Telemetry edge instrumentation failed')

                for node in processed_nodes:
                    pending = getattr(node, '_state', {}).get('pending_inputs')
                    if pending and len(pending) > 0:
                        active_nodes.add(node)

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

    async def run_tasks(
        self,
        scheduler: TaskScheduler,
        *,
        continue_on_error: bool = False,
        on_task_completed: Callable[[Task, Any], Awaitable[None] | None] | None = None,
        on_task_failed: Callable[[Task, Exception], Awaitable[None] | None] | None = None,
        usage_provider: Callable[[Task, Any], Awaitable[dict[str, float] | None] | dict[str, float] | None] | None = None,
    ) -> TaskBatchResult:
        """Execute tasks defined in a scheduler respecting dependencies and budgets."""

        results = TaskBatchResult()
        while True:
            task = scheduler.acquire_next_task()
            if task is None:
                break
            if not task.task_id:
                raise ValueError("Scheduled tasks must define task_id")
            task_id = task.task_id
            start_time = time.perf_counter()
            try:
                outcome = await self.run(task)
            except Exception as exc:
                scheduler.mark_failed(task_id)
                results.failed[task_id] = exc
                await _call_optional(on_task_failed, task, exc)
                if not continue_on_error:
                    raise
                continue

            duration = time.perf_counter() - start_time
            usage = {'seconds': duration, 'tokens': 0, 'cost': 0.0}
            if usage_provider:
                user_usage = await _call_optional(usage_provider, task, outcome) or {}
                if isinstance(user_usage, dict):
                    usage.update({k: user_usage[k] for k in ('tokens', 'seconds', 'cost') if k in user_usage})
            try:
                scheduler.record_campaign_usage(
                    task,
                    tokens=int(usage.get('tokens') or 0),
                    seconds=float(usage.get('seconds') or 0.0),
                    cost=float(usage.get('cost') or 0.0),
                )
            except CampaignBudgetError as budget_err:
                scheduler.mark_failed(task_id)
                results.failed[task_id] = budget_err
                await _call_optional(on_task_failed, task, budget_err)
                if not continue_on_error:
                    raise
                continue

            scheduler.mark_completed(task_id)
            results.completed[task_id] = outcome
            await _call_optional(on_task_completed, task, outcome)

        pending = [task_id for task_id in scheduler.pending if task_id not in results.failed]
        if pending:
            error = TaskDependencyError(
                "Unresolved task dependencies prevented execution: " + ", ".join(sorted(pending))
            )
            for task_id in pending:
                results.failed.setdefault(task_id, error)
            if not continue_on_error:
                raise error

        return results

    def _initialize_policy_engine(
        self,
        policy_engine: PolicyEngine | None,
        policy_set: PolicySet | None,
        policy_rules: Iterable[PolicyRule] | None,
    ) -> PolicyEngine | None:
        """Normalize various policy configuration inputs into an engine instance."""

        if policy_engine is not None:
            if not isinstance(policy_engine, PolicyEngine):
                raise TypeError("policy_engine must be an instance of PolicyEngine")
            return policy_engine
        if policy_set is not None:
            if not isinstance(policy_set, PolicySet):
                raise TypeError("policy_set must be an instance of PolicySet")
            return PolicyEngine(policy_set)
        if policy_rules:
            rules: list[PolicyRule] = []
            for rule in policy_rules:
                if isinstance(rule, PolicyRule):
                    rules.append(rule)
                elif isinstance(rule, dict):
                    rules.append(PolicyRule.model_validate(rule))
                else:
                    raise TypeError("policy_rules entries must be PolicyRule instances or dictionaries")
            return PolicyEngine(PolicySet(name=f'graph:{self.id}', rules=rules))
        return None

    def _attach_policy_engine_to_nodes(self) -> None:
        """Propagate the current policy engine to all nodes."""

        if not self._policy_engine:
            return
        for node in getattr(self, 'nodes', []):
            setattr(node, 'policy_engine', self._policy_engine)

    async def _enforce_policy_for_task(self, task: Task) -> None:
        """Run governance checks before executing a task."""

        if not self._policy_engine:
            return
        subject = self._build_task_subject(task)
        context = {
            'graph': {'id': self.id, 'type': self.__class__.__name__},
            'task': {
                'task_id': task.task_id,
                'type': task.type.value if hasattr(task.type, 'value') else str(task.type),
                'metadata': dict(task.metadata),
            },
        }
        if task.campaign:
            context['task']['campaign'] = task.campaign.model_dump()
        if isinstance(task.inputs, NodeMessage):
            context['task']['input_metadata'] = dict(task.inputs.metadata)
        request = PolicyRequest(
            subject=subject,
            action='graph:execute_task',
            resource=f"graph://{self.id}/tasks/{task.task_id or 'anonymous'}",
            context=context,
        )
        decision = self._policy_engine.evaluate(request)
        await self._handle_policy_decision(decision, request)

    async def _enforce_policy_for_node(self, node: BaseNode, task: Task) -> None:
        """Evaluate node-level policies before executing."""

        if not self._policy_engine:
            return
        subject = self._build_node_subject(node)
        context = {
            'graph': {'id': self.id, 'type': self.__class__.__name__},
            'node': {
                'id': node.id,
                'name': getattr(node, 'name', None),
                'type': node.__class__.__name__,
            },
            'task': {
                'task_id': task.task_id,
                'type': task.type.value if hasattr(task.type, 'value') else str(task.type),
            },
        }
        request = PolicyRequest(
            subject=subject,
            action='node:execute',
            resource=f"graph://{self.id}/nodes/{node.id}",
            context=context,
        )
        decision = self._policy_engine.evaluate(request)
        await self._handle_policy_decision(decision, request)

    def _build_task_subject(self, task: Task) -> PolicySubject:
        """Construct a policy subject representing the current task owner."""

        metadata = dict(task.metadata or {})
        subject_id = metadata.get('subject_id') or metadata.get('run_as') or self.id
        roles = metadata.get('roles') or []
        if isinstance(roles, str):
            roles = [roles]
        tags: dict[str, str] = {}
        if task.campaign and task.campaign.campaign_id:
            tags['campaign'] = task.campaign.campaign_id
        return PolicySubject(
            identifier=str(subject_id),
            roles=[str(role) for role in roles],
            tags=tags,
            attributes={
                'graph_id': self.id,
                'task_type': task.type.value if hasattr(task.type, 'value') else str(task.type),
            },
        )

    def _build_node_subject(self, node: BaseNode) -> PolicySubject:
        """Construct a policy subject representing a node/agent."""

        identifier = getattr(node, 'name', None) or node.id
        return PolicySubject(
            identifier=str(identifier),
            roles=['node', node.__class__.__name__.lower()],
            tags={'graph_id': self.id},
            attributes={
                'node_id': node.id,
                'node_type': node.__class__.__name__,
            },
        )

    async def _record_policy_decision(self, decision: PolicyDecision, request: PolicyRequest) -> None:
        """Persist policy decisions for auditing."""

        if not self._state_enabled:
            return
        events = await self.state.get(self._policy_state_key, [])
        timeline = list(events) if isinstance(events, list) else []
        timeline.append(
            {
                'timestamp': time.time(),
                'decision': decision.effect.value,
                'rule': decision.rule,
                'reason': decision.reason,
                'action': request.action,
                'resource': request.resource,
                'subject': request.subject.model_dump(),
                'metadata': dict(decision.metadata),
            }
        )
        await self.state.set(self._policy_state_key, timeline)

    async def _handle_policy_decision(self, decision: PolicyDecision, request: PolicyRequest) -> None:
        """Record decision and raise when policies block or require approvals."""

        await self._record_policy_decision(decision, request)
        if decision.effect == PolicyEffect.ALLOW:
            return
        if decision.effect == PolicyEffect.DENY:
            raise PolicyViolationError(
                f"Policy denied '{request.action}' on '{request.resource}'",
                decision=decision,
                request=request,
            )
        if decision.effect == PolicyEffect.REQUIRE_APPROVAL:
            approval = await self._create_approval_request(decision, request)
            raise ApprovalPendingError(approval)

    async def _create_approval_request(self, decision: PolicyDecision, request: PolicyRequest):
        """Create an approval request entry for governance workflows."""

        manager = self._approval_manager or ApprovalGateManager(None)
        approval = await manager.submit_request(
            action=request.action,
            resource=request.resource,
            subject=request.subject.model_dump(),
            reason=decision.reason or 'Approval required by policy',
            metadata={
                'rule': decision.rule,
                'policy_metadata': dict(decision.metadata),
                'context': dict(request.context),
            },
        )
        return approval

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
        self._attach_policy_engine_to_nodes()

    def _prepare_runtime(self) -> None:
        """Ensure runtime services (event bus, channels, state) are configured."""
        self._reset_node_stop_flags()
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

    async def _finalize_workspace(self, run_error: Exception | None) -> None:
        if not self.workspace:
            return
        policy = getattr(self.workspace, 'policy', None)
        if not policy:
            return
        should_cleanup = False
        if run_error and policy.cleanup_on_failure:
            should_cleanup = True
        elif not run_error and policy.cleanup_on_success:
            should_cleanup = True
        if should_cleanup:
            try:
                await self.workspace.cleanup()
            except Exception:
                logger.exception("Workspace cleanup failed for %s", self.workspace.root)

    async def _finalize_artifacts(self, run_error: Exception | None) -> None:
        if not self.artifacts:
            return
        try:
            await self.artifacts.finalize(run_error)
        except Exception:
            logger.exception("Artifact lifecycle policy failed")

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

    async def _enable_mailbox_persistence(self) -> None:
        """Swap node mailboxes with persistent channels for long-lived runs."""
        if self._mailbox_manager:
            return
        manager = MailboxPersistenceManager(self.state, self.nodes, graph_id=self.id)
        await manager.enable()
        self._mailbox_manager = manager
        self._channels_configured = False

    async def _disable_mailbox_persistence(self) -> None:
        """Restore original mailboxes if persistence was enabled."""
        if not self._mailbox_manager:
            return
        await self._mailbox_manager.disable()
        self._mailbox_manager = None
        self._channels_configured = False

    def _reset_node_stop_flags(self) -> None:
        """Clear stop flags so nodes can be reused across runs."""
        for node in self.nodes:
            if hasattr(node, '_stop_flag'):
                node._stop_flag = False

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
        mailboxes = await self.state.mailbox_snapshot()
        if mailboxes:
            checkpoint.metadata['mailboxes'] = mailboxes
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
        mailboxes = checkpoint_obj.metadata.get('mailboxes')
        if mailboxes:
            await self.state.restore_mailboxes(mailboxes)
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
                metadata = dict(getattr(message, 'metadata', {}) or {})
                metadata.setdefault('topic', edge.event_topic)
                if edge.event_filter and not self._event_filter_matches(edge.event_filter, payload, metadata):
                    continue
                node_message = self._wrap_event_message(payload, metadata)
                successor.enqueue_input(node_message)
                await self._delayed_ready.put(successor)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Event edge worker failed for topic=%s", edge.event_topic)
        finally:
            await subscription.close()

    def _wrap_event_message(self, payload: Any, metadata: dict[str, Any]) -> NodeMessage:
        event_info = dict(metadata)
        if isinstance(payload, NodeMessage):
            cloned = payload.model_copy(deep=True)
            current_metadata = dict(cloned.metadata or {})
            current_metadata.setdefault('event', event_info)
            cloned.metadata = current_metadata
            return cloned
        return NodeMessage(content=payload, metadata={'event': event_info})

    def _event_filter_matches(self, condition: EdgeCondition, payload: Any, metadata: dict[str, Any]) -> bool:
        value = payload.content if isinstance(payload, NodeMessage) else payload
        envelope: dict[str, Any]
        if isinstance(value, dict):
            envelope = dict(value)
            envelope.setdefault('_event', metadata)
        else:
            envelope = {'value': value, '_event': metadata}
        dummy = SimpleNamespace()
        dummy.outputs = NodeMessage(content=envelope, metadata={})
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

    def _has_pending_event_messages(self) -> bool:
        for subscription in self._event_subscriptions:
            channel = getattr(subscription, '_channel', None)
            if channel is None:
                continue
            empty_fn = getattr(channel, 'empty', None)
            if callable(empty_fn) and not empty_fn():
                return True
        return False


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
    """Wrap a `Graph` so it can execute as a single node inside another graph."""

    def __init__(
        self,
        *,
        graph: BaseGraph | None = None,
        graph_factory: Callable[[], BaseGraph] | None = None,
        graph_spec: Any | None = None,
        graph_source: str | None = None,
        input_mapping: dict[str, str] | None = None,
        output_mapping: dict[str, str] | None = None,
        share_state: bool = True,
        share_event_bus: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if graph is None and graph_factory is None:
            raise ValueError("SubgraphNode requires a graph instance or graph_factory.")
        if graph is not None and not isinstance(graph, BaseGraph):
            raise TypeError("graph must be a BaseGraph instance.")

        self._graph_template = graph
        self._graph_factory = graph_factory
        self._graph_spec_payload = self._normalize_graph_spec(graph_spec)
        self._graph_source_ref = graph_source

        self.input_mapping = dict(input_mapping or {})
        self.output_mapping = dict(output_mapping or {})
        self.share_state = share_state
        self.share_event_bus = share_event_bus

    async def process(self, context: ExecutionContext) -> Any:
        runtime_graph = self._create_runtime_graph()
        self._prepare_runtime_graph(runtime_graph, context)
        sub_inputs = self._map_inputs(context.inputs)
        result = await runtime_graph.run(sub_inputs)
        mapped = self._map_outputs(result)
        return mapped

    @property
    def graph_source(self) -> str | None:
        return self._graph_source_ref

    @property
    def graph_spec_payload(self) -> Any | None:
        return self._graph_spec_payload

    def attach_graph_spec(self, spec: Any) -> None:
        """Attach a graph spec payload for future serialization."""
        self._graph_spec_payload = self._normalize_graph_spec(spec)

    def _create_runtime_graph(self) -> BaseGraph:
        if self._graph_factory is not None:
            graph = self._graph_factory()
        elif self._graph_template is not None:
            graph = self._clone_graph(self._graph_template)
        else:
            raise RuntimeError("SubgraphNode is misconfigured without a graph factory.")
        if not isinstance(graph, BaseGraph):
            raise TypeError("graph_factory must return a BaseGraph instance.")
        return graph

    def _prepare_runtime_graph(self, graph: BaseGraph, context: ExecutionContext) -> None:
        if self.share_state and context.graph_state is not None:
            graph.state = context.graph_state  # type: ignore[assignment]
        if self.share_event_bus and self.event_bus is not None:
            graph.event_bus = self.event_bus

    def _map_inputs(self, payload: NodeMessage | dict[str, Any] | list[dict[str, Any]] | None) -> NodeMessage:
        message = self._ensure_node_message(payload)
        if not isinstance(message.content, dict):
            return message
        data = copy.deepcopy(message.content)
        for outer_key, inner_key in self.input_mapping.items():
            if outer_key in data:
                data[inner_key] = data.pop(outer_key)
        message.content = data
        return message

    def _map_outputs(self, result: Any) -> NodeMessage:
        message = self._ensure_node_message(result)
        if isinstance(message.content, dict) and self.output_mapping:
            data = copy.deepcopy(message.content)
            for inner_key, outer_key in self.output_mapping.items():
                if inner_key in data:
                    data[outer_key] = data.pop(inner_key)
            message.content = data
        return message

    def _clone_graph(self, template: BaseGraph) -> BaseGraph:
        clone_method = getattr(template, 'copy', None)
        if callable(clone_method):
            return clone_method()  # type: ignore[return-value]
        return copy.deepcopy(template)

    def _normalize_graph_spec(self, spec_payload: Any | None) -> Any | None:
        if spec_payload is None:
            return None
        dump = getattr(spec_payload, 'model_dump', None)
        if callable(dump):
            try:
                return dump()
            except Exception:
                return spec_payload
        return spec_payload

    def _ensure_node_message(self, payload: Any) -> NodeMessage:
        if isinstance(payload, NodeMessage):
            return payload
        return NodeMessage(content=copy.deepcopy(payload), metadata={})
