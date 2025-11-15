"""Shared mission memory and workspace knowledge graph utilities."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from spark.graphs.graph_state import GraphState


class MemoryRecord(BaseModel):
    """Single shared-memory entry persisted in GraphState."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: str = Field(default='note', description='Record category (fact, task, reflection, etc.)')
    agent_id: str | None = Field(default=None, description='Originating agent identifier.')
    tags: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc))


@dataclass
class SharedMemoryManager:
    """Manages mission-level shared memories stored in GraphState."""

    state: GraphState
    state_key: str = 'shared_memory'

    async def add_record(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        agent_id: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> MemoryRecord:
        record = MemoryRecord(kind=kind, payload=payload, agent_id=agent_id, tags=list(tags or []))
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
    ) -> list[MemoryRecord]:
        bucket = await self.state.get(self.state_key, {'records': []})
        results: list[MemoryRecord] = []
        for raw in reversed(bucket.get('records', [])):
            candidate = MemoryRecord.model_validate(raw)
            if kinds and candidate.kind not in kinds:
                continue
            if agent_id and candidate.agent_id != agent_id:
                continue
            if tags and not set(tags).issubset(set(candidate.tags)):
                continue
            results.append(candidate)
            if limit and len(results) >= limit:
                break
        return list(reversed(results)) if limit else list(reversed(results))

    async def delete_record(self, record_id: str) -> bool:
        async with self.state.lock(self.state_key):
            bucket = await self.state.get(self.state_key, {'records': []})
            records = bucket.get('records', [])
            new_records = [rec for rec in records if rec.get('id') != record_id]
            if len(new_records) == len(records):
                return False
            bucket['records'] = new_records
            await self.state.set(self.state_key, bucket)
            return True


@dataclass
class KnowledgeGraph:
    """Lightweight knowledge graph built atop GraphState."""

    state: GraphState
    state_key: str = 'knowledge_graph'

    async def upsert_entity(self, entity_id: str, *, kind: str, attributes: dict[str, Any] | None = None) -> None:
        async with self.state.lock(self.state_key):
            graph = await self.state.get(self.state_key, {'entities': {}, 'edges': []})
            entities: dict[str, dict[str, Any]] = graph.get('entities', {})
            entities[entity_id] = {'kind': kind, 'attributes': dict(attributes or {})}
            graph['entities'] = entities
            await self.state.set(self.state_key, graph)

    async def link(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        *,
        attributes: dict[str, Any] | None = None,
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
