"""Tests for SharedMemoryManager and KnowledgeGraph."""

from __future__ import annotations

import pytest

from spark.graphs import GraphState, SharedMemoryManager, KnowledgeGraph


@pytest.mark.asyncio
async def test_shared_memory_add_and_query():
    state = GraphState(initial_state={})
    await state.initialize()
    manager = SharedMemoryManager(state)

    record1 = await manager.add_record(kind='fact', payload={'text': 'Upgraded database'}, agent_id='agent-1', tags=['infra'])
    record2 = await manager.add_record(kind='task', payload={'title': 'Ship release'}, agent_id='agent-2', tags=['release'])

    recent = await manager.list_records(limit=1)
    assert recent[-1].id == record2.id

    infra_records = await manager.list_records(tags=['infra'])
    assert len(infra_records) == 1 and infra_records[0].id == record1.id

    await manager.delete_record(record1.id)
    remaining = await manager.list_records()
    assert all(rec.id != record1.id for rec in remaining)


@pytest.mark.asyncio
async def test_knowledge_graph_entities_and_edges():
    state = GraphState(initial_state={})
    await state.initialize()
    kg = KnowledgeGraph(state)

    await kg.upsert_entity('repo:spark', kind='repository', attributes={'path': '/spark'})
    await kg.upsert_entity('ticket:42', kind='ticket')
    await kg.link('ticket:42', 'repo:spark', relation='touches', attributes={'status': 'open'})

    entity = await kg.get_entity('repo:spark')
    assert entity['kind'] == 'repository'

    edges = await kg.neighbors('ticket:42')
    assert len(edges) == 1
    assert edges[0]['relation'] == 'touches'
