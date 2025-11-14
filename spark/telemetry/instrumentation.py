"""
Instrumentation utilities for automatic telemetry collection.

This module provides decorators, context managers, and hooks for
integrating telemetry with Spark nodes and graphs without requiring
manual instrumentation in user code.
"""

from __future__ import annotations

import functools
import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional, TypeVar

from spark.telemetry.manager import TelemetryManager
from spark.telemetry.types import EventType, SpanKind, SpanStatus

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def instrument_node_method(
    method_name: str = "process",
    span_kind: SpanKind = SpanKind.NODE_EXECUTION
) -> Callable[[F], F]:
    """Decorator to instrument a node method with telemetry.

    Args:
        method_name: Name of the method being instrumented
        span_kind: Type of span to create

    Returns:
        Decorated method that automatically creates spans

    Usage:
        class MyNode(Node):
            @instrument_node_method()
            async def process(self, context):
                # Telemetry automatically collected
                return {'result': 'done'}
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            manager = TelemetryManager.get_instance()
            if not manager.config.enabled:
                return await func(self, *args, **kwargs)

            # Get telemetry context from node
            telemetry_context = getattr(self, '_telemetry_context', None)
            if telemetry_context is None:
                # No context available, execute without telemetry
                return await func(self, *args, **kwargs)

            # Extract node information
            node_id = getattr(self, 'id', 'unknown')
            node_name = self.__class__.__name__

            span_name = f"{node_name}.{method_name}"

            async with manager.start_span(
                name=span_name,
                trace_id=telemetry_context.trace_id,
                kind=span_kind,
                parent_span_id=telemetry_context.span_id,
                attributes={
                    'node.id': node_id,
                    'node.name': node_name,
                    'node.method': method_name,
                }
            ) as span:
                # Update context with new span
                setattr(self, '_telemetry_context', telemetry_context.create_child_context(span.span_id))

                try:
                    # Record node started event
                    manager.record_event(
                        type=EventType.NODE_STARTED,
                        name=f"{node_name} started",
                        trace_id=telemetry_context.trace_id,
                        span_id=span.span_id,
                        attributes={'node_id': node_id}
                    )

                    # Execute method
                    result = await func(self, *args, **kwargs)

                    # Record node finished event
                    manager.record_event(
                        type=EventType.NODE_FINISHED,
                        name=f"{node_name} finished",
                        trace_id=telemetry_context.trace_id,
                        span_id=span.span_id,
                        attributes={'node_id': node_id}
                    )

                    return result

                except Exception as e:
                    # Record node failed event
                    manager.record_event(
                        type=EventType.NODE_FAILED,
                        name=f"{node_name} failed",
                        trace_id=telemetry_context.trace_id,
                        span_id=span.span_id,
                        attributes={
                            'node_id': node_id,
                            'error': str(e),
                            'error_type': type(e).__name__
                        }
                    )
                    raise

        # Handle sync functions by wrapping
        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(self, *args, **kwargs):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                return loop.run_until_complete(async_wrapper(self, *args, **kwargs))
            return sync_wrapper  # type: ignore

    return decorator


async def instrument_node_do(node: Any, inputs: Any, manager: TelemetryManager) -> Any:
    """Instrument a node's do() method execution.

    This function wraps node execution with telemetry spans and events.

    Args:
        node: Node instance
        inputs: Node inputs
        manager: TelemetryManager instance

    Returns:
        Node outputs
    """
    if not manager.config.enabled:
        return await node._original_do(inputs)

    # Get telemetry context
    telemetry_context = getattr(node, '_telemetry_context', None)
    if telemetry_context is None:
        return await node._original_do(inputs)

    # Extract node information
    node_id = getattr(node, 'id', 'unknown')
    node_name = node.__class__.__name__

    async with manager.start_span(
        name=f"{node_name}.do",
        trace_id=telemetry_context.trace_id,
        kind=SpanKind.NODE_EXECUTION,
        parent_span_id=telemetry_context.span_id,
        attributes={
            'node.id': node_id,
            'node.name': node_name,
            'node.type': type(node).__name__,
        }
    ) as span:
        # Update context
        child_context = telemetry_context.create_child_context(span.span_id)
        setattr(node, '_telemetry_context', child_context)

        try:
            # Record started event
            manager.record_event(
                type=EventType.NODE_STARTED,
                name=f"{node_name} execution started",
                trace_id=telemetry_context.trace_id,
                span_id=span.span_id,
                attributes={'node_id': node_id}
            )

            # Execute node
            result = await node._original_do(inputs)

            # Record finished event
            manager.record_event(
                type=EventType.NODE_FINISHED,
                name=f"{node_name} execution finished",
                trace_id=telemetry_context.trace_id,
                span_id=span.span_id,
                attributes={'node_id': node_id}
            )

            return result

        except Exception as e:
            # Record failed event
            manager.record_event(
                type=EventType.NODE_FAILED,
                name=f"{node_name} execution failed",
                trace_id=telemetry_context.trace_id,
                span_id=span.span_id,
                attributes={
                    'node_id': node_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
            raise


async def instrument_edge_transition(
    from_node: Any,
    to_node: Any,
    condition: Any,
    manager: TelemetryManager
) -> None:
    """Instrument an edge transition with telemetry.

    Args:
        from_node: Source node
        to_node: Target node
        condition: Edge condition
        manager: TelemetryManager instance
    """
    if not manager.config.enabled:
        return

    telemetry_context = getattr(from_node, '_telemetry_context', None)
    if telemetry_context is None:
        return

    from_node_id = getattr(from_node, 'id', 'unknown')
    to_node_id = getattr(to_node, 'id', 'unknown')

    # Record edge evaluated event
    manager.record_event(
        type=EventType.EDGE_EVALUATED,
        name=f"Edge {from_node_id} -> {to_node_id} evaluated",
        trace_id=telemetry_context.trace_id,
        span_id=telemetry_context.span_id,
        attributes={
            'from_node_id': from_node_id,
            'to_node_id': to_node_id,
            'condition': str(condition),
        }
    )

    # Record edge taken event
    manager.record_event(
        type=EventType.EDGE_TAKEN,
        name=f"Edge {from_node_id} -> {to_node_id} taken",
        trace_id=telemetry_context.trace_id,
        span_id=telemetry_context.span_id,
        attributes={
            'from_node_id': from_node_id,
            'to_node_id': to_node_id,
        }
    )

    # Propagate telemetry context to next node
    setattr(to_node, '_telemetry_context', telemetry_context)


async def instrument_state_change(
    key: str,
    old_value: Any,
    new_value: Any,
    scope: str,
    manager: TelemetryManager,
    telemetry_context: Optional[Any] = None
) -> None:
    """Instrument a state change with telemetry.

    Args:
        key: State key
        old_value: Previous value
        new_value: New value
        scope: State scope (node or graph)
        manager: TelemetryManager instance
        telemetry_context: Optional telemetry context
    """
    if not manager.config.enabled or telemetry_context is None:
        return

    manager.record_event(
        type=EventType.STATE_UPDATED,
        name=f"State updated: {key}",
        trace_id=telemetry_context.trace_id,
        span_id=telemetry_context.span_id,
        attributes={
            'key': key,
            'scope': scope,
            'has_old_value': old_value is not None,
            'has_new_value': new_value is not None,
        }
    )


def attach_telemetry_to_node(node: Any, manager: TelemetryManager) -> None:
    """Attach telemetry instrumentation to a node.

    This function wraps the node's do() method to automatically collect telemetry.

    Args:
        node: Node instance to instrument
        manager: TelemetryManager instance
    """
    if not manager.config.enabled:
        return

    # Store original do method
    if not hasattr(node, '_original_do'):
        node._original_do = node.do

        # Create instrumented do method
        async def instrumented_do(inputs: Any) -> Any:
            return await instrument_node_do(node, inputs, manager)

        # Replace do method
        node.do = instrumented_do


def attach_telemetry_to_graph(graph: Any, manager: TelemetryManager) -> None:
    """Attach telemetry instrumentation to a graph and all its nodes.

    This function instruments the graph's run() method and all node do() methods.

    Args:
        graph: Graph instance to instrument
        manager: TelemetryManager instance
    """
    if not manager.config.enabled:
        return

    # Attach to all nodes
    for node in graph.nodes:
        attach_telemetry_to_node(node, manager)

    logger.debug(f"Attached telemetry to graph with {len(graph.nodes)} nodes")


@asynccontextmanager
async def telemetry_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[dict] = None
):
    """Create a telemetry span as a context manager.

    Args:
        name: Span name
        kind: Span kind
        attributes: Optional attributes

    Yields:
        Span object

    Usage:
        async with telemetry_span("my_operation") as span:
            span.set_attribute("key", "value")
            # Do work
    """
    manager = TelemetryManager.get_instance()

    if not manager.config.enabled:
        # No-op context manager
        from contextlib import nullcontext
        yield None
        return

    # Create a temporary trace if none exists
    trace = manager.start_trace(name)

    async with manager.start_span(
        name=name,
        trace_id=trace.trace_id,
        kind=kind,
        attributes=attributes or {}
    ) as span:
        yield span

    manager.end_trace(trace.trace_id)
