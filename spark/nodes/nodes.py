"""
Nodes for the Spark framework.
"""

from abc import abstractmethod
import sys
import asyncio

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import copy
from collections import deque
import inspect
import logging
import pickle
import time
from typing import Any, Callable, Mapping, Optional, final
from uuid import uuid4

from spark.nodes.base import (
    BaseNode,
    Edge,
    ExecutionContext,
    SparkError,
    wrap_sync_method,
)
from spark.nodes.config import NodeConfig
# Removed: from spark.nodes.capabilities import CapabilitySuite
from spark.nodes.policies import ( # Import all policy classes
    RetryPolicy,
    TimeoutPolicy,
    RateLimiterPolicy,
    CircuitBreakerPolicy,
    IdempotencyPolicy,
)
from spark.nodes.exceptions import ContextValidationError, NodeExecutionError, NodeTimeoutError
from spark.nodes.types import EventSink, NodeMessage, NullEventSink
from spark.nodes.channels import ChannelMessage

try:  # Optional telemetry instrumentation
    from spark.telemetry.instrumentation import instrument_edge_transition
except ImportError:  # pragma: no cover - optional dependency
    instrument_edge_transition = None

_BATCH_FAILURE_STRATEGIES = {'all_or_nothing', 'skip_failed', 'collect_errors'}


async def _maybe_await(x):
    if inspect.isawaitable(x):
        return await x
    return x


class Node(BaseNode):
    """
    a Node is an actor in the Actor Model.
    The differences between Node and BaseNode are:
      1. Node can have a config object.
      2. Node have capabilities.
      3. Node have a go method that run continuously
    """

    def __init__(self, config: Optional[NodeConfig] = None, **kwargs):
        """Initialize the BasicNode with configuration."""
        super().__init__(**kwargs)
        self.config = config if config is not None else self._get_default_config()

        # Assign config attributes to self, with kwargs overriding config values
        self._assign_config_attributes(**kwargs)

        # Apply policies (this modifies self._process)
        self._apply_policies()

        # keep_in_state hook should run before other pre_process_hooks
        self.pre_process_hooks.insert(0, self.process_keep_in_state)

        self._event_sink: EventSink = NullEventSink()
        self._active_run_id: str | None = None
        self._redact_keys: set[str] = set()
        self.parents: list['Node'] = []
        self._stop_flag: bool = False
        self._last_process_attempts = 0

    def _get_default_config(self) -> NodeConfig:
        """
        Get the default config instance for this node type.
        Subclasses such as Agent should override this method to return a config
        instance with the correct type.
        """
        return NodeConfig()

    def _assign_config_attributes(self, **kwargs) -> None:
        """
        Assign config attributes to self, with kwargs overriding config values.

        This helper method iterates through all config attributes and assigns them
        to self. If a key exists in kwargs, it will override the config value.
        """
        config_dict = self.config.model_dump()

        # Assign config attributes to self
        for key in config_dict.keys():
            setattr(self, key, getattr(self.config, key))

        # Override with kwargs values if they exist
        for key, value in kwargs.items():
            if hasattr(self.config, key):  # Only override if the key exists in config
                setattr(self, key, value)

        # Handle special cases that need default values
        self.id = kwargs.get('id', getattr(self, 'id', uuid4().hex))
        self.name = kwargs.get('name', getattr(self, 'name', None))
        self.type = kwargs.get('type', getattr(self, 'type', self.__class__.__name__))
        self.description = kwargs.get('description', getattr(self, 'description', ''))

    def _apply_policies(self) -> None:
        """
        Apply configured policies to wrap the node's _process method.
        Policies are applied in a specific order:
        Idempotency -> RateLimiter -> CircuitBreaker -> Timeout -> Retry
        This order ensures that idempotency is checked first, then rate limits,
        then circuit breakers, then timeouts, and finally retries.
        """
        # Apply policies in a sensible order (e.g., idempotency -> rate_limit -> circuit_breaker -> timeout -> retry)
        # Each policy's __call__ method returns the node with its _process method wrapped.
        
        # Idempotency is typically very early to avoid unnecessary work.
        if self.config.idempotency:
            self.config.idempotency(self)
        
        # Rate Limiting should happen before trying to execute (and potentially timeout/retry)
        if self.config.rate_limiter:
            self.config.rate_limiter(self)
            
        # Circuit Breaker should check before execution
        if self.config.circuit_breaker:
            self.config.circuit_breaker(self)
            
        # Timeout wraps the execution
        if self.config.timeout:
            self.config.timeout(self)
            
        # Retry wraps the outermost execution attempt logic
        if self.config.retry:
            self.config.retry(self)

    def process_keep_in_state(self, context: ExecutionContext) -> None:
        """Process the keep in state."""
        for key in self.config.keep_in_state:
            if key in context.inputs.content:
                if key in self._state:
                    self._state[key] = context.inputs.content[key]  # type: ignore[literal-required]
            else:
                context.inputs.content[key] = self._state.get(key)

    async def go(self):
        """Run continuously, processing messages from the mailbox."""
        node_name = getattr(self, 'name', None) or self.__class__.__name__
        while not self._stop_flag:
            message = await self.mailbox.receive()

            # If we receive a shutdown signal, honor it once processing finishes.
            if message.is_shutdown:
                print(f"[Debug] {node_name}: Received shutdown sentinel, exiting")
                break

            payload = message.payload

            # Legacy behaviour: treat None as empty payload when not stopping.
            if payload is None and not self._stop_flag:
                payload = {}

            if self._stop_flag:
                print(f"[Debug] {node_name}: stop_flag set, exiting go() loop")
                break

            self._state['processing'] = True
            try:
                node_message = payload if isinstance(payload, NodeMessage) else NodeMessage(content=payload)
                context = self._prepare_context(node_message)
                result = await self._process(context) # This _process is now the wrapped version
                result = await self._maybe_collect_human_input(context, result)

                context.outputs = result

                # Store outputs and snapshot
                self.outputs = self._post_process(context)
                self._record_snapshot(context)

                # Forward outputs to successor nodes
                if not self._stop_flag:
                    await self._forward_to_successors(self.outputs, message)

                if message.ack:
                    await _maybe_await(message.ack())
            finally:
                self._state['processing'] = False

        print(f"[Debug] {node_name}: go() loop exited")

    async def _forward_to_successors(self, outputs: NodeMessage, source_message: ChannelMessage) -> None:
        """Forward node outputs to qualified successor nodes."""
        metadata_base = {
            'source_node_id': self.id,
            'source_node_name': getattr(self, 'name', None),
        }
        parent_metadata = source_message.metadata or {}
        for edge in self.iter_active_edges():
            target = edge.to_node
            if target is None:
                continue
            channel = edge.channel or getattr(target, 'mailbox', None)
            if channel is None:
                continue
            payload = outputs
            merged_metadata = {
                **metadata_base,
                'edge_id': str(edge.id),
                'target_node_id': getattr(target, 'id', None),
                'parent_metadata': parent_metadata,
            }
            outgoing = ChannelMessage(payload=payload, metadata=merged_metadata)
            await channel.send(outgoing)
            manager = getattr(self, '_telemetry_manager', None)
            if instrument_edge_transition and manager:
                try:
                    await instrument_edge_transition(self, target, edge.condition, manager)
                except Exception:
                    logging.getLogger(__name__).exception('Telemetry edge instrumentation failed')

    def stop(self) -> None:
        """Signal the node to stop processing after completing the current message."""
        self._stop_flag = True

    def _resolve_node_name(self) -> str:
        """Resolve the node name for event logging."""
        if self.name:
            return self.name
        return self.id or self.__class__.__name__

    def _build_event(self, event_type: str, run_id: str | None) -> dict:
        event: dict[str, Any] = {
            'type': event_type,
            'node_name': self._resolve_node_name(),
            'node_class': self.__class__.__name__,
            'timestamp': time.time(),
        }
        if run_id is not None:
            event['run_id'] = run_id
        return event

    async def _emit_event(self, event_type: str, payload: dict | None = None, *, run_id: str | None = None) -> None:
        sink = self._event_sink
        if isinstance(sink, NullEventSink):
            return
        run_id = run_id or self._active_run_id
        event = self._build_event(event_type, run_id)
        if payload:
            event.update(payload)
        try:
            redacted = self._apply_redaction(event)
        except Exception:  # pragma: no cover - defensive, should not happen
            logging.getLogger(__name__).exception('Failed to redact event payload')
            redacted = event
        try:
            await _maybe_await(sink.emit(redacted))
        except Exception:  # pragma: no cover - observability must not break execution
            logging.getLogger(__name__).exception('Event sink emit failed')

    def _apply_redaction(self, value: Any) -> Any:
        if not self._redact_keys:
            return value
        if isinstance(value, dict):
            return {
                key: '***' if key in self._redact_keys else self._apply_redaction(val) for key, val in value.items()
            }
        if isinstance(value, list):
            return [self._apply_redaction(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._apply_redaction(item) for item in value)
        if isinstance(value, set):
            return {self._apply_redaction(item) for item in value}
        return value

    def _summarize_value(self, value: Any) -> dict[str, Any]:
        summary: dict[str, Any] = {'type': type(value).__name__}
        try:
            if isinstance(value, dict):
                summary['size'] = len(value)
                summary['keys'] = sorted(map(str, value.keys()))[:10]
            elif isinstance(value, (list, tuple, set)):
                summary['length'] = len(value)
            elif isinstance(value, (str, bytes, bytearray)):
                summary['length'] = len(value)
            elif value is None:
                summary['value'] = None
            else:
                summary['repr'] = self._truncate(repr(value))
        except Exception:
            summary['repr'] = '<unavailable>'
        return summary

    async def _emit_stage_done(
        self,
        run_id: str,
        stage: str,
        duration: float,
        *,
        result: Any = None,
        metadata: dict | None = None,
    ) -> None:
        payload: dict[str, Any] = {'stage': stage, 'duration': duration}
        if result is not None:
            payload['result_summary'] = self._summarize_value(result)
        if metadata:
            payload.update(metadata)
        await self._emit_event('stage_done', payload, run_id=run_id)

    async def _emit_node_error(
        self,
        run_id: str,
        stage: str,
        exc: BaseException,
        decision: str,
        *,
        duration: float | None = None,
        attempts: int | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            'stage': stage,
            'decision': decision,
            'error_type': exc.__class__.__name__,
            'error_message': self._truncate(str(exc)),
            'error_kind': 'timeout' if isinstance(exc, NodeTimeoutError) else 'exception',
        }
        if duration is not None:
            payload['duration'] = duration
        if attempts is not None:
            payload['attempts'] = attempts
        await self._emit_event('node_error', payload, run_id=run_id)

    @staticmethod
    def _truncate(text: str, max_length: int = 200) -> str:
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + '...'

    def _await_stage(self, coro, stage: str):
        """Await a stage coroutine - placeholder for actual implementation."""
        # TODO: Implement proper stage awaiting with timeout/monitoring
        return coro

    def _refresh_observability_state(self) -> None:
        """Sync per-run observability controls from dynamic attributes."""
        sink = getattr(self, 'event_sink', None)
        self._event_sink = sink if sink is not None else NullEventSink()
        redact_keys = getattr(self, 'redact_keys', None)
        if redact_keys:
            self._redact_keys = set(redact_keys)
        else:
            self._redact_keys = set()

    def _validate_context_contract(self, context: ExecutionContext) -> None:
        """Run configured validators against the incoming payload."""
        validators = getattr(self.config, 'validators', ())
        if not validators:
            return
        payload = context.inputs.content
        if not isinstance(payload, Mapping):
            raise ContextValidationError(self, 'inputs must be a mapping for configured validators')
        for validator in validators:
            message = validator(payload)
            if message:
                raise ContextValidationError(self, message)

    def _derive_run_id(self, context: ExecutionContext) -> str:
        """Resolve the active run identifier for observability streams."""
        metadata = getattr(context.inputs, 'metadata', {}) or {}
        run_id = metadata.get('run_id')
        if isinstance(run_id, str) and run_id:
            return run_id
        return uuid4().hex

    # Simplified _process method
    async def _process(self, context: ExecutionContext) -> Any:  # type: ignore[override]
        """
        Execute the node's core processing logic.
        Policy orchestration (retry, timeout, etc.) is now handled by wrappers
        applied during node initialization. This method now primarily performs
        observability state refreshing, context validation, and then delegates
        to the BaseNode's _process (which calls the user's process method).
        """
        self._refresh_observability_state()
        self._validate_context_contract(context)
        
        # The actual policy logic is now in the wrappers that mutated self._process
        # So we just call the base class's _process, which will eventually call Node.process()
        # The run_id logic and error emission are left in the wrapped _process
        # but the core resilience logic is outside in the policy wrappers.
        
        run_id = self._derive_run_id(context)
        previous_run_id = self._active_run_id
        self._active_run_id = run_id
        
        try:
            # Call the next layer down, which might be another policy wrapper
            # or BaseNode._process if all policies have been applied.
            result = await super()._process(context)
            # Emit success event if no policy wrapper already did (e.g., for idempotency replay)
            await self._emit_stage_done(
                run_id,
                'process',
                (time.time() - context.metadata.started_at) if context.metadata.started_at else 0.0,
                result=result,
                metadata={'attempt': 1, 'attempts': 1, 'reused': False}, # Default, can be overridden by policy
            )
            return result
        except Exception as exc:
            # Emit error if no policy wrapper already did (e.g., retry exhaustion)
            await self._emit_node_error(
                run_id,
                'process',
                exc,
                'abort', # Default decision, can be overridden by policy
                duration=(time.time() - context.metadata.started_at) if context.metadata.started_at else None,
                attempts=1,
            )
            raise
        finally:
            self._active_run_id = previous_run_id


class JoinNode(Node):
    """Barrier node that waits for multiple parents before executing.
    """
    def __init__(
        self,
        *,
        mode: str = 'all',
        keys: list[str] | tuple[str, ...] | None = None,
        reducer: Callable[[list[dict]], dict] | None = None,
        trace_keys: tuple[str, ...] = ('trace_id', '__trace_id__'),
        config: Optional[NodeConfig] = None, # Added config parameter
        **kwargs,
    ) -> None:
        super().__init__(config=config, **kwargs) # Pass config to super
        if mode not in {'all', 'any'}:
            raise ValueError("JoinNode mode must be 'all' or 'any'")
        self._mode = mode
        self._configured_keys = tuple(keys) if keys else None
        self._reducer = reducer or self._default_reducer
        self._trace_keys = trace_keys
        self._buffers: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()
        self._ready_trace_ids: deque[str] = deque()
        self._any_ready_traces: set[str] = set()

    @staticmethod
    def _default_reducer(items: list[dict]) -> dict:
        merged: dict[str, Any] = {}
        for item in items:
            merged.update(item)
        return merged

    async def receive_from_parent(  # type: ignore[override]
        self,
        parent: 'Node',
        payload: Any = None,
        parent_ctx: dict | None = None,
    ) -> bool:
        data = self._extract_payload(payload, parent_ctx)
        trace_id = self._derive_trace_id(payload, parent_ctx)
        key = self._resolve_parent_key(parent)

        async with self._lock:
            if self._mode == 'any':
                if trace_id in self._any_ready_traces:
                    return False
                self._any_ready_traces.add(trace_id)
                self._stage_trace_payload(trace_id, [data])
                return True

            expected_keys = self._expected_keys()
            if expected_keys and self._configured_keys and key not in expected_keys:
                raise ValueError(
                    f"JoinNode received contribution from unexpected parent key {key!r}; "
                    f"expected one of {sorted(expected_keys)}"
                )

            state = self._buffers.setdefault(trace_id, {})
            state[key] = data

            if expected_keys:
                ready = expected_keys.issubset(state.keys())
            else:
                # Fallback: wait for all currently known parents
                ready = len(state) >= len(self.parents)

            if ready:
                contributions = self._collect_contributions(state)
                self._buffers.pop(trace_id, None)
                self._stage_trace_payload(trace_id, contributions)
                return True

            return False

    def pop_ready_input(self) -> Any | None:
        payload = super().pop_ready_input()
        if payload is None:
            return None
        self._ready_trace_ids.popleft()
        return payload

    def _stage_trace_payload(self, trace_id: str, contributions: list[dict]) -> None:
        merged = self._reducer([self._safe_deepcopy(item) for item in contributions])
        if not isinstance(merged, dict):
            raise TypeError('JoinNode reducer must return a dict to merge contexts.')
        # self._stage_ready_input(merged)
        self._ready_trace_ids.append(trace_id)

    def _collect_contributions(self, state: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        if self._configured_keys is not None:
            return [state[key] for key in self._configured_keys if key in state]
        return list(state.values())

    def _expected_keys(self) -> set[str]:
        if self._configured_keys is not None:
            return set(self._configured_keys)
        return {self._resolve_parent_key(parent) for parent in self.parents}

    def _resolve_parent_key(self, parent: 'Node') -> str:
        if self._configured_keys is not None:
            if isinstance(getattr(parent, 'name', None), str) and parent.name:
                return parent.name
            return parent.__class__.__name__
        name = getattr(parent, 'name', None)
        if isinstance(name, str) and name:
            return name
        return f"{parent.__class__.__name__}:{id(parent)}"

    def _derive_trace_id(self, payload: Any, parent_ctx: dict | None) -> str:
        for container in (payload, parent_ctx):
            if isinstance(container, dict):
                for key in self._trace_keys:
                    value = container.get(key)
                    if value is not None:
                        return str(value)
        return 'default'

    def _extract_payload(self, payload: Any, parent_ctx: dict | None) -> dict[str, Any]:
        if isinstance(payload, dict):
            return self._safe_deepcopy(payload)
        if isinstance(parent_ctx, dict):
            return self._safe_deepcopy(parent_ctx)
        return {'value': self._safe_deepcopy(payload)}

    def _safe_deepcopy(self, value: Any) -> Any:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    def get_next_nodes(self) -> list[BaseNode]:  # type: ignore[override]
        nodes = super().get_next_nodes()
        if not nodes:
            return nodes

        # Stage the merged output for downstream consumers so they receive the
        # aggregated context as their input regardless of scheduler defaults.
        # Note: self.ctx should be self._state
        staged_payload = self._safe_deepcopy(self._state)
        for index, node in enumerate(nodes):
            payload = staged_payload if index == 0 else self._safe_deepcopy(self._state)
            # _stage_ready_input is not a method, should use _pending_inputs
            if isinstance(node, Node):
                node._state['pending_inputs'].append(payload)
        return nodes


class BatchProcessNode(Node):
    """
    Base class for all batch processing nodes: SequentialNode, ParallelNode, MultipleThreadNode, MultipleProcessNode
    A BatchProcessNode works on a list of data, each item of the list is processed by process_item(self, item)
    """

    def __init__(
        self,
        edges: Optional[list[Edge]] = None,
        *,
        failure_strategy: str = 'all_or_nothing',
        config: Optional[NodeConfig] = None, # Pass config to super
        **kwargs,
    ) -> None:
        # Pass config to super, ensuring it's handled by Node.__init__
        super().__init__(config=config, **kwargs)
        self._set_failure_strategy(failure_strategy)

    @property
    def failure_strategy(self) -> str:
        """Get the failure strategy."""
        return self._failure_strategy

    def set_failure_strategy(self, strategy: str) -> None:
        """Set the failure strategy."""
        self._set_failure_strategy(strategy)

    def _set_failure_strategy(self, strategy: str) -> None:
        """Set the failure strategy."""
        if strategy not in _BATCH_FAILURE_STRATEGIES:
            raise ValueError(f"failure_strategy must be one of {_BATCH_FAILURE_STRATEGIES}, got {strategy!r}")
        self._failure_strategy = strategy

    def _empty_batch_result(self) -> Any:
        """Get the empty batch result."""
        if self._failure_strategy == 'collect_errors':
            return {'data': [], 'errors': []}
        return []

    @abstractmethod
    async def process_item(self, item: Any) -> Any:
        """
        Process an item from the batch.
        """

    async def _finalize_batch_results(
        self,
        items: list[Any],
        outcomes: list[Any],
    ) -> Any:
        """Finalize the batch results."""
        if not items:
            return self._empty_batch_result()

        successes: list[Any] = []
        collected_errors: list[dict[str, Any]] = []

        for index, (item, outcome) in enumerate(zip(items, outcomes)):
            if isinstance(outcome, BaseException):
                if isinstance(outcome, asyncio.CancelledError):  # propagate cancellations
                    raise outcome

                action = self._failure_strategy
                await self._emit_event(
                    'batch_item_error',
                    {
                        'index': index,
                        'strategy': action,
                        'item_summary': self._summarize_value(item),
                        'error_type': outcome.__class__.__name__,
                        'error_message': self._truncate(str(outcome)),
                    },
                )

                if action == 'all_or_nothing':
                    raise outcome

                if action == 'collect_errors':
                    collected_errors.append({
                        'index': index,
                        'item': item,
                        'exception': outcome,
                        'error_type': outcome.__class__.__name__,
                        'error_message': self._truncate(str(outcome)),
                        'item_summary': self._summarize_value(item),
                    })
                # skip_failed simply omits the item
                continue

            successes.append(outcome)

        if self._failure_strategy == 'collect_errors':
            return {'data': successes, 'errors': collected_errors}
        return successes

    async def _get_fn_and_items(self, context: ExecutionContext) -> tuple[Callable[..., Any], list[Mapping[str, Any]]]:
        """get the process function and the items to process"""

        process_fn = wrap_sync_method(self.process)
        if self._process_no_arg:
            await process_fn()
        else:
            await process_fn(context)
        process_item_fn = wrap_sync_method(self.process_item)
        if self._process_item_no_arg:
            raise SparkError("process_item method cannot be called without arguments")

        items = context.inputs.content
        if not isinstance(items, list):
            raise SparkError("inputs must be a list")
        return process_item_fn, items


class SequentialNode(BatchProcessNode):
    """
    Node that works on a list of data sequentially
    It is discouraged to use this class.  Use parallel nodes instead.
    if you need to process data sequentially, simply call node in a for-loop.
    """

    @final
    async def _process(self, context: ExecutionContext) -> Any:
        """call the process_item method to process the items in the context.inputs"""
        fn, items = await self._get_fn_and_items(context)
        if not items:
            return self._empty_batch_result()

        outcomes: list[Any] = []
        for item in items:
            try:
                outcomes.append(await fn(item))
            except Exception as exc:  # noqa: PERF203 - intentional broad catch for retry semantics
                if isinstance(exc, asyncio.CancelledError):
                    raise
                outcomes.append(exc)
                if self._failure_strategy == 'all_or_nothing':
                    break
        processed_items = items[: len(outcomes)]
        return await self._finalize_batch_results(processed_items, list(outcomes))


class BaseParallelNode(BatchProcessNode):
    """
    Base class for parallel node classes: ParallelNode, MultipleThreadNode, MultipleProcessNode
    """

    def __init__(self, max_workers: Optional[int] = None, **kwargs):
        super().__init__(max_workers=max_workers, **kwargs) # Ensure config is passed up from here too


class ParallelNode(BaseParallelNode):
    """
    Node that works on a list of data in parallel within the same thread,
    limiting concurrency based on max_workers.
    """

    @final
    async def _process(self, context: ExecutionContext) -> Any:
        """call the process_item method to process the items in the context.inputs"""
        fn, items = await self._get_fn_and_items(context)
        if not items:
            return self._empty_batch_result()

        if self.max_workers and self.max_workers > 0:
            semaphore = asyncio.Semaphore(self.max_workers)

            async def process_with_semaphore(item):
                async with semaphore:
                    return await fn(item)

            tasks = [process_with_semaphore(item) for item in items]
            outcomes_tuple = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # No limit or invalid limit, run all concurrently
            outcomes_tuple = await asyncio.gather(*(fn(i) for i in items), return_exceptions=True)

        return await self._finalize_batch_results(items, list(outcomes_tuple))


class MultipleThreadNode(BaseParallelNode):
    """
    Node that processes data using multiple threads
    """

    @final
    async def _process(self, context: ExecutionContext) -> Any:
        fn, items = await self._get_fn_and_items(context)
        if not items:
            return self._empty_batch_result()

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create a list of futures for each data item
            # Note: mypy cannot infer lambda type properly - adding type ignore
            futures = [
                loop.run_in_executor(executor, lambda item=item: asyncio.run(fn(item)))  # type: ignore[misc]
                for item in items
            ]
            # Wait for all futures to complete
            outcomes_tuple = await asyncio.gather(*futures, return_exceptions=True)
        return await self._finalize_batch_results(items, list(outcomes_tuple))


def _run_process_item_async(instance_pickle, item):
    """
    Top-level helper function for process pool worker ProcessPoolExecutor.
    Unpickles the Node instance and runs its async process method for the given item.
    """
    try:
        instance = pickle.loads(instance_pickle)
        # Run the async method in a new event loop in this process
        return asyncio.run(instance.process_item(item))
    except Exception as e:
        # Log or handle error appropriately
        # For now, just re-raise to propagate it back via the future
        # Consider more robust error handling/logging if needed
        print(f"Error in worker process processing item {item}: {e}")
        raise


class MultipleProcessNode(BaseParallelNode):
    """
    Node that processes data using multiple processes.
    Its load method must return a list of data.
    Requires the Node instance and its relevant state to be picklable.
    """

    @final
    async def _process(self, context: ExecutionContext) -> Any:
        if not inspect.iscoroutinefunction(self.process_item):
            raise SparkError("process_item method must be async")

        _, items = await self._get_fn_and_items(context)
        if not items:
            return self._empty_batch_result()

        # Ensure the instance is picklable before proceeding
        try:
            instance_pickle = pickle.dumps(self)
        except Exception as e:
            # Provide a more informative error if pickling fails
            raise TypeError(
                f"Node instance {self.__class__.__name__} is not picklable, "
                f"cannot use MultipleProcessNode. Underlying error: {e}"
            ) from e

        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Create a list of futures for each data item using the top-level wrapper
            futures = [
                loop.run_in_executor(
                    executor,
                    _run_process_item_async,  # Use the picklable top-level function
                    instance_pickle,  # Pass the pickled instance state
                    item,  # Pass the specific item for this task
                )
                for item in items
            ]
            # Wait for all futures to complete and gather results
            # Important: return exceptions to allow failure strategy handling
            results_tuple = await asyncio.gather(*futures, return_exceptions=True)

        return await self._finalize_batch_results(items, list(results_tuple))


class MultipleInterpreterNode(BaseParallelNode):
    """
    Node that processes data using multiple interpreters.
    Its load method must return a list of data.
    Requires the Node instance and its relevant state to be picklable.
    """

    @final
    async def _process(self, context: ExecutionContext) -> Any:
        if sys.version_info < (3, 14):
            raise SparkError("MultipleInterpreterNode requires Python 3.14 or later")

        # TODO: Implement MultipleInterpreterNode
        pass