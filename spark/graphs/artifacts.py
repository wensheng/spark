"""Artifact registry schemas."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from spark.graphs.graph_state import GraphState
from spark.graphs.shared_memory import (
    MemoryReference,
    MemoryAccessPolicy,
    AccessVisibility,
    MemoryAccessContext,
    MemoryPolicyViolation,
)


class ArtifactStatus(str, Enum):
    """Lifecycle states for artifacts."""

    DRAFT = "draft"
    FINAL = "final"
    DELETED = "deleted"


@dataclass(slots=True)
class ArtifactPolicy:
    """Lifecycle rules for stored artifacts."""

    cleanup_on_success: bool = False
    cleanup_on_failure: bool = False
    retain_per_type: int | None = None


class ArtifactRecord(BaseModel):
    """Metadata describing a mission artifact."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    artifact_type: str = Field(default='generic', description='Type of artifact (diff, report, dataset, etc.)')
    name: str = Field(default='artifact', description='Human-readable label.')
    description: str | None = Field(default=None, description='Optional description or summary.')
    created_at: _dt.datetime = Field(
        default_factory=lambda: _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc)
    )
    node_id: str | None = Field(default=None, description='Producer node identifier.')
    task_id: str | None = Field(default=None, description='Scheduler task identifier.')
    campaign_id: str | None = Field(default=None, description='Campaign identifier if applicable.')
    blob_id: str | None = Field(default=None, description='Identifier returned by GraphState.open_blob_writer().')
    external_uri: str | None = Field(default=None, description='Optional link to remote storage.')
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    references: list[MemoryReference] = Field(default_factory=list)
    access_policy: MemoryAccessPolicy = Field(default_factory=MemoryAccessPolicy)
    status: ArtifactStatus = Field(default=ArtifactStatus.DRAFT)

    model_config = dict(use_enum_values=True)


class ArtifactManager:
    """Registers mission artifacts and handles blob bookkeeping."""

    def __init__(
        self,
        state: GraphState,
        *,
        state_key: str = 'artifacts',
        policy_enforcer: Any | None = None,
        policy: ArtifactPolicy | None = None,
    ) -> None:
        self._state = state
        self._state_key = state_key
        self._policy_enforcer = policy_enforcer
        self._policy = policy or ArtifactPolicy()

    async def register_artifact(
        self,
        *,
        artifact_type: str,
        name: str,
        description: str | None = None,
        node_id: str | None = None,
        task_id: str | None = None,
        campaign_id: str | None = None,
        blob_writer: Any | None = None,
        external_uri: str | None = None,
        tags: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
        references: Iterable[MemoryReference | dict[str, Any]] | None = None,
        access_policy: MemoryAccessPolicy | dict[str, Any] | None = None,
        status: ArtifactStatus = ArtifactStatus.DRAFT,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            artifact_type=artifact_type,
            name=name,
            description=description,
            node_id=node_id,
            task_id=task_id,
            campaign_id=campaign_id,
            tags=list(tags or []),
            metadata=dict(metadata or {}),
            references=[MemoryReference.model_validate(ref) for ref in references or []],
            access_policy=self._normalize_policy(access_policy),
            status=status,
        )
        if blob_writer is not None:
            record.blob_id = getattr(blob_writer, 'blob_id', None)
        if external_uri:
            record.external_uri = external_uri
        self._authorize(record, access_context, action='write')
        await self._persist(record)
        return record

    async def update_status(
        self,
        artifact_id: str,
        status: ArtifactStatus,
        *,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
    ) -> ArtifactRecord | None:
        async with self._state.lock(self._state_key):
            bucket = await self._state.get(self._state_key, {'records': []})
            records = bucket.get('records', [])
            for idx, raw in enumerate(records):
                if raw.get('id') != artifact_id:
                    continue
                record = ArtifactRecord.model_validate(raw)
                self._authorize(record, access_context, action='update')
                record.status = status
                records[idx] = record.model_dump()
                await self._state.set(self._state_key, bucket)
                return record
        return None

    async def list_artifacts(
        self,
        *,
        kinds: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        node_id: str | None = None,
        task_id: str | None = None,
        status: ArtifactStatus | None = None,
        reference_entity_id: str | None = None,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
        enforce_access: bool = False,
    ) -> list[ArtifactRecord]:
        bucket = await self._state.get(self._state_key, {'records': []})
        results: list[ArtifactRecord] = []
        for raw in bucket.get('records', []):
            record = ArtifactRecord.model_validate(raw)
            if kinds and record.artifact_type not in kinds:
                continue
            if tags and not set(tags).issubset(set(record.tags)):
                continue
            if node_id and record.node_id != node_id:
                continue
            if task_id and record.task_id != task_id:
                continue
            if status and record.status is not status:
                continue
            if reference_entity_id and not any(ref.entity_id == reference_entity_id for ref in record.references):
                continue
            if enforce_access and not self._is_allowed(record, access_context, action='read'):
                continue
            results.append(record)
        return results

    async def delete_artifact(
        self,
        artifact_id: str,
        *,
        delete_blob: bool = False,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
    ) -> bool:
        async with self._state.lock(self._state_key):
            bucket = await self._state.get(self._state_key, {'records': []})
            records = bucket.get('records', [])
            new_records = []
            target_blob = None
            deleted = False
            for raw in records:
                if raw.get('id') == artifact_id:
                    record = ArtifactRecord.model_validate(raw)
                    self._authorize(record, access_context, action='delete')
                    target_blob = record.blob_id
                    deleted = True
                else:
                    new_records.append(raw)
            if not deleted:
                return False
            bucket['records'] = new_records
            await self._state.set(self._state_key, bucket)
        if delete_blob and target_blob:
            try:
                await self._state.delete_blob(target_blob)
            except RuntimeError:
                # Backend may not support blobs; ignore.
                pass
        return True

    async def finalize(self, run_error: Exception | None = None) -> None:
        """Apply lifecycle policies after a mission finishes."""
        if not self._policy:
            return
        cleanup = False
        if run_error and self._policy.cleanup_on_failure:
            cleanup = True
        elif not run_error and self._policy.cleanup_on_success:
            cleanup = True
        if cleanup:
            artifacts = await self.list_artifacts()
            for record in artifacts:
                await self.delete_artifact(record.id, delete_blob=bool(record.blob_id))
            return
        if self._policy.retain_per_type:
            await self._enforce_retention(self._policy.retain_per_type)

    def _normalize_policy(self, policy: MemoryAccessPolicy | dict[str, Any] | None) -> MemoryAccessPolicy:
        if policy is None:
            return MemoryAccessPolicy()
        if isinstance(policy, MemoryAccessPolicy):
            return policy
        if isinstance(policy, dict):
            return MemoryAccessPolicy.model_validate(policy)
        raise TypeError(f'Unsupported policy payload: {policy!r}')

    async def _persist(self, record: ArtifactRecord) -> None:
        async with self._state.lock(self._state_key):
            bucket = await self._state.get(self._state_key, {'records': []})
            records = bucket.setdefault('records', [])
            records.append(record.model_dump())
            bucket['records'] = records[-1000:]
            await self._state.set(self._state_key, bucket)

    def _authorize(
        self,
        record: ArtifactRecord,
        context: MemoryAccessContext | dict[str, Any] | None,
        *,
        action: str,
    ) -> None:
        if context is None:
            return
        ctx = context if isinstance(context, MemoryAccessContext) else MemoryAccessContext(**context)
        if self._policy_enforcer:
            allowed = bool(self._policy_enforcer(record, ctx, action))
        else:
            allowed = record.access_policy.allows(agent_id=ctx.agent_id, roles=ctx.roles)
        if not allowed:
            raise MemoryPolicyViolation(
                f"Artifact access denied for agent={ctx.agent_id!r} action={action} visibility={record.access_policy.visibility}"
            )

    def _is_allowed(
        self,
        record: ArtifactRecord,
        context: MemoryAccessContext | dict[str, Any] | None,
        *,
        action: str,
    ) -> bool:
        if context is None:
            return True
        ctx = context if isinstance(context, MemoryAccessContext) else MemoryAccessContext(**context)
        if self._policy_enforcer:
            return bool(self._policy_enforcer(record, ctx, action))
        return record.access_policy.allows(agent_id=ctx.agent_id, roles=ctx.roles)

    async def _enforce_retention(self, retain_per_type: int) -> None:
        artifacts = await self.list_artifacts()
        to_delete: list[str] = []
        by_type: dict[str, list[ArtifactRecord]] = {}
        for record in artifacts:
            by_type.setdefault(record.artifact_type, []).append(record)
        for artifact_type, records in by_type.items():
            sorted_records = sorted(records, key=lambda r: r.created_at)
            if len(sorted_records) > retain_per_type:
                for record in sorted_records[:-retain_per_type]:
                    to_delete.append(record.id)
        for artifact_id in to_delete:
            await self.delete_artifact(artifact_id, delete_blob=True)
