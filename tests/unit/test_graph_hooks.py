"""Tests for Graph lifecycle hooks."""

import pytest

from spark.graphs.graph import Graph
from spark.graphs.hooks import GraphLifecycleEvent
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext, NodeMessage


class IncrementNode(Node):
    """Simple node that increments a numeric value."""

    async def process(self, context: ExecutionContext) -> dict:
        payload = context.inputs.content or {}
        value = payload.get('value', 0)
        return {'value': value + 1}


class FailingNode(Node):
    """Node that raises to test failure hooks."""

    async def process(self, context: ExecutionContext) -> dict:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_graph_lifecycle_hook_sequence():
    """Hooks should fire around run/iteration boundaries."""
    graph = Graph(start=IncrementNode())
    events: list[tuple[str, int]] = []
    after_run_meta: dict[str, object] = {}

    def make_hook(name: str):
        async def _hook(ctx):
            events.append((name, ctx.iteration_index))
        return _hook

    graph.register_hook(GraphLifecycleEvent.BEFORE_RUN, make_hook('before_run'))
    graph.register_hook(GraphLifecycleEvent.BEFORE_ITERATION, make_hook('before_iter'))
    graph.register_hook(GraphLifecycleEvent.AFTER_ITERATION, make_hook('after_iter'))
    graph.register_hook(GraphLifecycleEvent.ITERATION_COMPLETE, make_hook('iteration_complete'))

    async def after_run(ctx):
        events.append(('after_run', ctx.iteration_index))
        after_run_meta['error'] = ctx.metadata.get('error')
        after_run_meta['result'] = ctx.metadata.get('result')

    graph.register_hook(GraphLifecycleEvent.AFTER_RUN, after_run)

    result = await graph.run({'value': 3})

    assert isinstance(result, NodeMessage)
    assert [name for name, _ in events] == [
        'before_run',
        'before_iter',
        'after_iter',
        'iteration_complete',
        'after_run',
    ]
    assert events[1][1] == 0  # iteration index for iteration events
    assert events[-1][1] == -1  # after_run uses -1
    assert after_run_meta['error'] is None
    assert isinstance(after_run_meta['result'], NodeMessage)


@pytest.mark.asyncio
async def test_after_run_hook_receives_errors():
    """AFTER_RUN should fire even when the graph fails."""
    graph = Graph(start=FailingNode())
    captured: dict[str, object] = {}

    async def after_run(ctx):
        captured['error'] = ctx.metadata.get('error')
        captured['error_type'] = ctx.metadata.get('error_type')

    graph.register_hook(GraphLifecycleEvent.AFTER_RUN, after_run)

    with pytest.raises(RuntimeError):
        await graph.run()

    assert 'RuntimeError' in str(captured['error_type'])
    assert isinstance(captured['error'], str) and captured['error']
