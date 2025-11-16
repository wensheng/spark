"""Tests for GraphEventBus replay buffer."""

import pytest

from spark.graphs.event_bus import GraphEventBus


@pytest.mark.asyncio
async def test_event_bus_replay_buffer():
    bus = GraphEventBus(replay_buffer_size=3)
    await bus.publish('alpha', {'val': 1})
    await bus.publish('beta', {'val': 2})
    await bus.publish('alpha', {'val': 3})
    await bus.publish('gamma', {'val': 4})

    replay = await bus.replay()
    assert len(replay) == 3
    assert replay[0].metadata['topic'] == 'beta'
    alpha_events = await bus.replay('alpha')
    assert len(alpha_events) == 1
    assert alpha_events[0].payload == {'val': 3}
