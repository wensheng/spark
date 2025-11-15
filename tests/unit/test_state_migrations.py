"""Tests for MissionStateModel migrations and GraphState upgrade flow."""

from __future__ import annotations

import pytest

from spark.graphs import GraphState
from spark.graphs.state_backend import InMemoryStateBackend
from spark.graphs.state_schema import MissionStateModel


class LegacyState(MissionStateModel):
    schema_name = 'LegacyState'
    schema_version = '2.0'

    total: int
    owner: str


def _migrate_v1_to_v2(state: dict) -> dict:
    new_state = dict(state)
    new_state['total'] = new_state.pop('count', 0)
    new_state.setdefault('owner', 'unknown')
    return new_state


LegacyState.register_migration('1.0', '2.0', _migrate_v1_to_v2)


@pytest.mark.asyncio
async def test_graph_state_auto_migrates_backend():
    backend = InMemoryStateBackend(initial_state={'count': 5, 'owner': 'ops', '__schema_version__': '1.0'})
    state = GraphState(backend=backend, schema_model=LegacyState)
    await state.initialize()

    assert await state.get('total') == 5
    assert await state.get('owner') == 'ops'
    snapshot = backend.snapshot()
    assert snapshot['__schema_version__'] == '2.0'
    assert snapshot['total'] == 5
