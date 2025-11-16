"""Shared mission memory and workspace knowledge graph utilities."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from spark.graphs.graph_state import GraphState


class AccessVisibility(str, Enum):
    """Visibility levels for mission data."""

    PUBLIC = 'public'
    MISSION = 'mission'
    PRIVATE = 'private'


class MemoryReference(BaseModel):
    """Link from shared memory to a knowledge-graph entity."""

    entity_id: str = Field(..., description='Knowledge graph entity identifier.')
    entity_kind: str | None = Field(default=None, description='Optional entity type.')
    relation: str | None = Field(default=None, description='Relationship between the record and entity.')
    note: str | None = Field(default=None, description='Human-readable description of the reference.')


class MemoryAccessPolicy(BaseModel):
    """Access control metadata associated with shared memory."""

    visibility: AccessVisibility = Field(default=AccessVisibility.MISSION)
    allowed_agents: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)

    def allows(self, *, agent_id: str | None = None, roles: Sequence[str] | None = None) -> bool:
        """Return True if the provided identity matches this policy."""

        if self.visibility is AccessVisibility.PUBLIC:
            return True
        if self.visibility is AccessVisibility.PRIVATE:
            if agent_id:
                return agent_id in self.allowed_agents
            return False
        # Mission visibility optionally restricts via allowlists.
        if agent_id and self.allowed_agents and agent_id in self.allowed_agents:
            return True
        if roles and self.allowed_roles and set(roles).intersection(self.allowed_roles):
            return True
        return not (self.allowed_agents or self.allowed_roles)


class MemoryRecord(BaseModel):
    """Single shared-memory entry persisted in GraphState."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = Field(default='note', description='Record category (fact, task, reflection, etc.)')
    agent_id: str | None = Field(default=None, description='Originating agent identifier.')
    tags: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    references: list[MemoryReference] = Field(default_factory=list)
    access_policy: MemoryAccessPolicy = Field(default_factory=MemoryAccessPolicy)
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc))


def _normalize_references(references: Iterable[MemoryReference | dict[str, Any]] | None) -> list[MemoryReference]:
    if not references:
        return []
    normalized: list[MemoryReference] = []
    for ref in references:
        if isinstance(ref, MemoryReference):
            normalized.append(ref)
        elif isinstance(ref, dict):
            normalized.append(MemoryReference.model_validate(ref))
        else:
            raise TypeError(f'Unsupported reference payload: {ref!r}')
    return normalized


def _normalize_access_policy(policy: MemoryAccessPolicy | dict[str, Any] | None) -> MemoryAccessPolicy:
    if policy is None:
        return MemoryAccessPolicy()
    if isinstance(policy, MemoryAccessPolicy):
        return policy
    if isinstance(policy, dict):
        return MemoryAccessPolicy.model_validate(policy)
    raise TypeError(f'Unsupported access policy payload: {policy!r}')


@dataclass(slots=True)
class MemoryAccessContext:
    """Context provided when evaluating access policies."""

    agent_id: str | None = None
    roles: Sequence[str] | None = None
    stage: str | None = None


def _normalize_access_context(
    context: MemoryAccessContext | dict[str, Any] | None,
) -> MemoryAccessContext | None:
    if context is None:
        return None
    if isinstance(context, MemoryAccessContext):
        return context
    if isinstance(context, dict):
        return MemoryAccessContext(**context)
    raise TypeError(f'Unsupported access context payload: {context!r}')


class MemoryPolicyViolation(RuntimeError):
    """Raised when a memory policy check fails."""


@dataclass
class SharedMemoryManager:
    """Manages mission-level shared memories stored in GraphState."""

    state: GraphState
    state_key: str = 'shared_memory'
    policy_enforcer: Callable[[MemoryRecord, MemoryAccessContext | None, str], bool] | None = None

    async def add_record(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        tags: Iterable[str] | None = None,
        references: Iterable[MemoryReference | dict[str, Any]] | None = None,
        access_policy: MemoryAccessPolicy | dict[str, Any] | None = None,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            kind=kind,
            payload=payload,
            agent_id=agent_id,
            tags=list(tags or []),
            references=_normalize_references(references),
            access_policy=_normalize_access_policy(access_policy),
        )
        self._authorize(record, _normalize_access_context(access_context), action='write')
        async with self.state.lock(self.state_key):
            bucket = await self.state.get(self.state_key, {'records': []})
            records: list[dict[str, Any]] = bucket.get('records', [])
            records.append(record.model_dump())
            bucket['records'] = records[-1000:]
            await self.state.set(self.state_key, bucket)
        return record

    async def list_records(
        self,
        *,
        limit: int | None = None,
        kinds: Sequence[str] | None = None,
        tags: Sequence[str] | None = None,
        agent_id: str | None = None,
        reference_entity_id: str | None = None,
        visibility: AccessVisibility | None = None,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
        enforce_access: bool = False,
    ) -> list[MemoryRecord]:
        bucket = await self.state.get(self.state_key, {'records': []})
        results: list[MemoryRecord] = []
        context = _normalize_access_context(access_context)
        for raw in reversed(bucket.get('records', [])):
            candidate = MemoryRecord.model_validate(raw)
            if kinds and candidate.kind not in kinds:
                continue
            if agent_id and candidate.agent_id != agent_id:
                continue
            if tags and not set(tags).issubset(set(candidate.tags)):
                continue
            if visibility and candidate.access_policy.visibility is not visibility:
                continue
            if reference_entity_id and not any(ref.entity_id == reference_entity_id for ref in candidate.references):
                continue
            if enforce_access and not self._is_allowed(candidate, context, action='read'):
                continue
            results.append(candidate)
            if limit and len(results) >= limit:
                break
        return list(reversed(results)) if limit else list(reversed(results))

    async def delete_record(
        self,
        record_id: str,
        *,
        access_context: MemoryAccessContext | dict[str, Any] | None = None,
        enforce_access: bool = False,
    ) -> bool:
        async with self.state.lock(self.state_key):
            bucket = await self.state.get(self.state_key, {'records': []})
            records = bucket.get('records', [])
            new_records = [rec for rec in records if rec.get('id') != record_id]
            if len(new_records) == len(records):
                return False
            if enforce_access:
                context = _normalize_access_context(access_context)
                for rec in records:
                    if rec.get('id') == record_id:
                        candidate = MemoryRecord.model_validate(rec)
                        self._authorize(candidate, context, action='delete')
                        break
            bucket['records'] = new_records
            await self.state.set(self.state_key, bucket)
            return True

    def _authorize(
        self,
        record: MemoryRecord,
        context: MemoryAccessContext | None,
        *,
        action: str,
    ) -> None:
        if context is None:
            return
        allowed = self._is_allowed(record, context, action=action)
        if not allowed:
            raise MemoryPolicyViolation(
                f"Memory access denied for agent={context.agent_id!r} action={action} visibility={record.access_policy.visibility}"
            )

    def _is_allowed(
        self,
        record: MemoryRecord,
        context: MemoryAccessContext | None,
        *,
        action: str,
    ) -> bool:
        if context is None:
            return True
        if self.policy_enforcer:
            return bool(self.policy_enforcer(record, context, action))
        return record.access_policy.allows(agent_id=context.agent_id, roles=context.roles)


@dataclass
class KnowledgeGraph:
    """Lightweight knowledge graph built atop GraphState."""

    state: GraphState
    state_key: str = 'knowledge_graph'

    async def upsert_entity(
        self,
        entity_id: str,
        *,
        kind: str,
        attributes: dict[str, Any] | None = None,
        references: Iterable[MemoryReference | dict[str, Any]] | None = None,
        access_policy: MemoryAccessPolicy | dict[str, Any] | None = None,
    ) -> None:
        async with self.state.lock(self.state_key):
            graph = await self.state.get(self.state_key, {'entities': {}, 'edges': []})
            entities: dict[str, dict[str, Any]] = graph.get('entities', {})
            entities[entity_id] = {
                'kind': kind,
                'attributes': dict(attributes or {}),
                'references': [ref.model_dump() for ref in _normalize_references(references)],
                'access_policy': _normalize_access_policy(access_policy).model_dump(),
            }
            graph['entities'] = entities
            await self.state.set(self.state_key, graph)

    async def link(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        attributes: dict[str, Any] | None = None,
        references: Iterable[MemoryReference | dict[str, Any]] | None = None,
        access_policy: MemoryAccessPolicy | dict[str, Any] | None = None,
    ) -> None:
        async with self.state.lock(self.state_key):
            graph = await self.state.get(self.state_key, {'entities': {}, 'edges': []})
            edges: list[dict[str, Any]] = graph.get('edges', [])
            edges.append(
                {
                    'id': uuid4().hex,
                    'source': source_id,
                    'target': target_id,
                    'relation': relation,
                    'attributes': dict(attributes or {}),
                    'references': [ref.model_dump() for ref in _normalize_references(references)],
                    'access_policy': _normalize_access_policy(access_policy).model_dump(),
                }
            )
            graph['edges'] = edges[-2000:]
            await self.state.set(self.state_key, graph)

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        graph = await self.state.get(self.state_key, {'entities': {}, 'edges': []})
        return graph.get('entities', {}).get(entity_id)

    async def neighbors(self, entity_id: str, *, relation: str | None = None) -> list[dict[str, Any]]:
        graph = await self.state.get(self.state_key, {'entities': {}, 'edges': []})
        neighbors: list[dict[str, Any]] = []
        for edge in graph.get('edges', []):
            if edge.get('source') != entity_id and edge.get('target') != entity_id:
                continue
            if relation and edge.get('relation') != relation:
                continue
            neighbors.append(edge)
        return neighbors
