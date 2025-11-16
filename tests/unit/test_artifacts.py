"""Tests for artifact schema."""

import pytest

from spark.graphs import GraphState
from spark.graphs.artifacts import ArtifactRecord, ArtifactStatus, ArtifactManager, ArtifactPolicy
from spark.graphs.shared_memory import (
    MemoryReference,
    MemoryAccessPolicy,
    AccessVisibility,
    MemoryPolicyViolation,
)


def test_artifact_record_defaults():
    record = ArtifactRecord(name='Diff')
    assert record.artifact_type == 'generic'
    assert record.status == ArtifactStatus.DRAFT
    assert record.access_policy.visibility == AccessVisibility.MISSION
    assert record.references == []


def test_artifact_record_with_metadata():
    record = ArtifactRecord(
        artifact_type='report',
        name='Release Notes',
        description='Summary of release',
        node_id='node_a',
        task_id='task-1',
        campaign_id='campaign-99',
        blob_id='blob-123',
        external_uri='s3://bucket/object',
        tags=['release', 'report'],
        metadata={'format': 'md'},
        references=[MemoryReference(entity_id='repo:spark')],
        access_policy=MemoryAccessPolicy(visibility=AccessVisibility.PUBLIC),
        status=ArtifactStatus.FINAL,
    )
    assert record.status == ArtifactStatus.FINAL
    assert record.access_policy.visibility == AccessVisibility.PUBLIC
    assert record.references[0].entity_id == 'repo:spark'


@pytest.mark.asyncio
async def test_artifact_manager_register_and_list():
    state = GraphState(initial_state={})
    await state.initialize()
    manager = ArtifactManager(state)

    record = await manager.register_artifact(
        artifact_type='diff',
        name='PR Diff',
        node_id='node_a',
        references=[MemoryReference(entity_id='repo:spark')],
        tags=['diff'],
    )

    artifacts = await manager.list_artifacts(kinds=['diff'])
    assert len(artifacts) == 1
    assert artifacts[0].id == record.id


@pytest.mark.asyncio
async def test_artifact_manager_enforces_access():
    state = GraphState(initial_state={})
    await state.initialize()

    def enforcer(record, context, action):
        if action == 'read':
            return record.access_policy.visibility is AccessVisibility.PUBLIC
        return context.agent_id == record.node_id

    manager = ArtifactManager(state, policy_enforcer=enforcer)

    record = await manager.register_artifact(
        artifact_type='log',
        name='Sensitive Log',
        node_id='node1',
        access_context={'agent_id': 'node1'},
    )

    with pytest.raises(MemoryPolicyViolation):
        await manager.register_artifact(
            artifact_type='log',
            name='Unauthorized',
            node_id='node2',
            access_context={'agent_id': 'nodeA'},
        )

    filtered = await manager.list_artifacts(enforce_access=True, access_context={'agent_id': 'node2'})
    assert filtered == []

    allowed = await manager.list_artifacts(enforce_access=True, access_context={'agent_id': 'any'})
    assert allowed == []

    await manager.delete_artifact(record.id, access_context={'agent_id': 'node1'})


@pytest.mark.asyncio
async def test_artifact_policy_cleanup(tmp_path):
    state = GraphState(initial_state={})
    await state.initialize()
    policy = ArtifactPolicy(cleanup_on_success=True)
    manager = ArtifactManager(state, policy=policy)
    await manager.register_artifact(artifact_type='report', name='Report')
    await manager.finalize(run_error=None)
    assert await manager.list_artifacts() == []


@pytest.mark.asyncio
async def test_artifact_policy_retain(tmp_path):
    state = GraphState(initial_state={})
    await state.initialize()
    policy = ArtifactPolicy(retain_per_type=1)
    manager = ArtifactManager(state, policy=policy)
    await manager.register_artifact(artifact_type='report', name='One')
    await manager.register_artifact(artifact_type='report', name='Two')
    await manager.finalize(run_error=Exception("failed"))
    artifacts = await manager.list_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].name == 'Two'
