"""Tests for SharedMemoryManager and KnowledgeGraph."""

from __future__ import annotations

import pytest

from spark.graphs import (
    GraphState,
    SharedMemoryManager,
    KnowledgeGraph,
    AccessVisibility,
)
from spark.graphs.shared_memory import MemoryAccessContext, MemoryPolicyViolation


@pytest.mark.asyncio
async def test_shared_memory_add_and_query():
    state = GraphState(initial_state={})
    await state.initialize()
    manager = SharedMemoryManager(state)

    record1 = await manager.add_record(
        kind='fact',
        payload={'text': 'Upgraded database'},
        agent_id='agent-1',
        tags=['infra'],
        references=[{'entity_id': 'repo:spark', 'relation': 'touches'}],
        access_policy={'visibility': 'mission', 'allowed_agents': ['agent-1']},
    )
    record2 = await manager.add_record(
        kind='task',
        payload={'title': 'Ship release'},
        agent_id='agent-2',
        tags=['release'],
        access_policy={'visibility': 'public'},
    )

    recent = await manager.list_records(limit=1)
    assert recent[-1].id == record2.id

    infra_records = await manager.list_records(tags=['infra'])
    assert len(infra_records) == 1 and infra_records[0].id == record1.id

    referenced = await manager.list_records(reference_entity_id='repo:spark')
    assert len(referenced) == 1
    assert referenced[0].references[0].entity_id == 'repo:spark'

    mission_visible = await manager.list_records(visibility=AccessVisibility.MISSION)
    assert all(rec.access_policy.visibility is AccessVisibility.MISSION for rec in mission_visible)

    await manager.delete_record(record1.id)
    remaining = await manager.list_records()
    assert all(rec.id != record1.id for rec in remaining)


@pytest.mark.asyncio
async def test_shared_memory_enforces_access():
    state = GraphState(initial_state={})
    await state.initialize()

    def enforcer(record, context, action):
        # allow if agent owns record or action is read on public records
        if action == 'read' and record.access_policy.visibility is AccessVisibility.PUBLIC:
            return True
        return context.agent_id == record.agent_id

    manager = SharedMemoryManager(state, policy_enforcer=enforcer)

    record = await manager.add_record(
        kind='fact',
        payload={'text': 'Secret'},
        agent_id='agent-1',
        access_context={'agent_id': 'agent-1'},
    )

    with pytest.raises(MemoryPolicyViolation):
        await manager.add_record(
            kind='fact',
            payload={'text': 'Fail'},
            agent_id='agent-2',
            access_context=MemoryAccessContext(agent_id='agent-3'),
        )

    # unauthorized read filtered
    unauthorized = await manager.list_records(access_context={'agent_id': 'agent-2'}, enforce_access=True)
    assert unauthorized == []

    authorized = await manager.list_records(access_context={'agent_id': 'agent-1'}, enforce_access=True)
    assert len(authorized) == 1 and authorized[0].id == record.id


@pytest.mark.asyncio
async def test_knowledge_graph_entities_and_edges():
    state = GraphState(initial_state={})
    await state.initialize()
    kg = KnowledgeGraph(state)

    await kg.upsert_entity(
        'repo:spark',
        kind='repository',
        attributes={'path': '/spark'},
        references=[{'entity_id': 'workspace:core', 'relation': 'contains'}],
        access_policy={'visibility': 'public'},
    )
    await kg.upsert_entity('ticket:42', kind='ticket')
    await kg.link(
        'ticket:42',
        'repo:spark',
        relation='touches',
        attributes={'status': 'open'},
        references=[{'entity_id': 'repo:spark', 'relation': 'impacts'}],
        access_policy={'visibility': 'mission'},
    )

    entity = await kg.get_entity('repo:spark')
    assert entity['kind'] == 'repository'
    assert entity['references'][0]['entity_id'] == 'workspace:core'
    assert entity['access_policy']['visibility'] == 'public'

    edges = await kg.neighbors('ticket:42')
    assert len(edges) == 1
    assert edges[0]['relation'] == 'touches'
    assert edges[0]['references'][0]['entity_id'] == 'repo:spark'
    assert edges[0]['access_policy']['visibility'] == 'mission'
