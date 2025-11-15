"""Tests for SQLite state backend persistence."""

import asyncio
from pathlib import Path

import pytest

from spark.graphs.graph_state import GraphState
from spark.graphs.state_backend import SQLiteStateBackend


@pytest.mark.asyncio
async def test_sqlite_backend_persists_between_instances(tmp_path):
    """Values written via one GraphState should be visible to another."""
    db_path = tmp_path / "graph_state.db"

    backend = SQLiteStateBackend(db_path)
    state = GraphState(backend=backend)
    await state.initialize()
    await state.set('foo', 'bar')

    backend2 = SQLiteStateBackend(db_path)
    state2 = GraphState(backend=backend2)
    await state2.initialize()

    assert await state2.get('foo') == 'bar'


@pytest.mark.asyncio
async def test_sqlite_backend_transaction(tmp_path):
    """Transaction context should replace entire snapshot atomically."""
    backend = SQLiteStateBackend(tmp_path / "graph_state.db")
    state = GraphState(backend=backend)
    await state.initialize()
    await state.update({'a': 1, 'b': 2})

    async with state.transaction() as snapshot:
        snapshot['a'] = 5
        snapshot.pop('b')
        snapshot['c'] = 9

    assert await state.get('a') == 5
    assert await state.get('b') is None
    assert await state.get('c') == 9
