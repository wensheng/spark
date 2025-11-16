"""Tests for artifact schema."""

from spark.graphs.artifacts import ArtifactRecord, ArtifactStatus
from spark.graphs.shared_memory import MemoryReference, MemoryAccessPolicy, AccessVisibility


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
