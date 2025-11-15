"""Integration tests for Graph task scheduling and metadata."""

from __future__ import annotations

import pytest

from spark.graphs import (
    Budget,
    CampaignBudgetError,
    CampaignInfo,
    Graph,
    Task,
    TaskScheduler,
)
from spark.nodes.nodes import Node
from spark.nodes.types import NodeMessage


class RecordingNode(Node):
    """Node that records labels into graph state for assertions."""

    async def process(self, context):  # type: ignore[override]
        payload = context.inputs.content or {}
        label = payload.get('label')
        runs = await context.graph_state.get('runs', []) if context.graph_state else []
        runs = list(runs)
        runs.append(label)
        if context.graph_state:
            await context.graph_state.set('runs', runs)
        return NodeMessage(content={'label': label})


class MaybeFailNode(Node):
    """Node that raises when the payload asks it to."""

    async def process(self, context):  # type: ignore[override]
        payload = context.inputs.content or {}
        if payload.get('fail'):
            raise RuntimeError('boom')
        return NodeMessage(content=payload)


@pytest.mark.asyncio
async def test_run_tasks_respects_dependencies():
    node = RecordingNode()
    graph = Graph(start=node, initial_state={'runs': []})

    collect = Task(task_id='collect', inputs=NodeMessage(content={'label': 'collect'}))
    analyze = Task(
        task_id='analyze',
        depends_on=['collect'],
        inputs=NodeMessage(content={'label': 'analyze'}),
    )

    scheduler = TaskScheduler([collect, analyze])
    batch = await graph.run_tasks(scheduler)

    assert list(batch.completed.keys()) == ['collect', 'analyze']
    assert batch.failed == {}
    assert await graph.state.get('runs') == ['collect', 'analyze']


@pytest.mark.asyncio
async def test_run_tasks_enforces_campaign_budget():
    node = RecordingNode()
    graph = Graph(start=node)

    campaign = CampaignInfo(campaign_id='mission', budget=Budget(max_tokens=5))
    t1 = Task(task_id='t1', inputs=NodeMessage(content={'label': 't1'}), campaign=campaign)
    t2 = Task(task_id='t2', inputs=NodeMessage(content={'label': 't2'}), campaign=campaign)
    scheduler = TaskScheduler([t1, t2])

    async def usage_provider(task, _result):  # noqa: ANN001
        return {'tokens': 3}

    with pytest.raises(CampaignBudgetError):
        await graph.run_tasks(scheduler, usage_provider=usage_provider)


@pytest.mark.asyncio
async def test_run_tasks_continue_on_error():
    node = MaybeFailNode()
    graph = Graph(start=node)

    failing = Task(task_id='first', inputs=NodeMessage(content={'fail': True}))
    succeeding = Task(task_id='second', inputs=NodeMessage(content={'label': 'ok'}))
    scheduler = TaskScheduler([failing, succeeding])

    batch = await graph.run_tasks(scheduler, continue_on_error=True)

    assert 'first' in batch.failed
    assert 'second' in batch.completed


@pytest.mark.asyncio
async def test_task_metadata_persisted_in_state():
    node = RecordingNode()
    graph = Graph(start=node)

    campaign = CampaignInfo(campaign_id='camp-1', name='Demo')
    task = Task(task_id='meta', inputs=NodeMessage(content={'label': 'meta'}), campaign=campaign)

    await graph.run(task)
    metadata = await graph.state.get('task_metadata')

    assert metadata['task_id'] == 'meta'
    assert metadata['status'] == 'completed'
    assert metadata['campaign']['campaign_id'] == 'camp-1'
    assert metadata['duration_seconds'] >= 0
