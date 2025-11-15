"""Checkpoint abstractions for Graph runtimes."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

CheckpointHandler = Callable[['GraphCheckpoint'], Awaitable[None]] | Callable[['GraphCheckpoint'], None]


@dataclass
class GraphCheckpoint:
    """Serializable representation of a graph checkpoint."""

    checkpoint_id: str
    graph_id: str
    created_at: float
    iteration: int | None
    state: dict[str, Any]
    schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            'checkpoint_id': self.checkpoint_id,
            'graph_id': self.graph_id,
            'created_at': self.created_at,
            'iteration': self.iteration,
            'state': dict(self.state),
            'schema': dict(self.schema or {}),
            'metadata': dict(self.metadata),
        }

    @classmethod
    def create(
        cls,
        graph_id: str,
        state: dict[str, Any],
        *,
        iteration: int | None = None,
        schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> 'GraphCheckpoint':
        """Create a checkpoint with generated identifier and timestamp."""
        return cls(
            checkpoint_id=uuid.uuid4().hex,
            graph_id=graph_id,
            created_at=time.time(),
            iteration=iteration,
            state=dict(state),
            schema=dict(schema or {}),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'GraphCheckpoint':
        """Rehydrate a checkpoint from serialized payload."""
        return cls(
            checkpoint_id=payload['checkpoint_id'],
            graph_id=payload['graph_id'],
            created_at=payload['created_at'],
            iteration=payload.get('iteration'),
            state=dict(payload.get('state') or {}),
            schema=dict(payload.get('schema') or {}),
            metadata=dict(payload.get('metadata') or {}),
        )

    @classmethod
    def ensure(cls, payload: 'GraphCheckpoint | dict[str, Any]') -> 'GraphCheckpoint':
        """Normalize checkpoint inputs."""
        if isinstance(payload, GraphCheckpoint):
            return payload
        if isinstance(payload, dict):
            return cls.from_dict(payload)
        raise TypeError(f"Unsupported checkpoint payload: {type(payload)!r}")


@dataclass
class GraphCheckpointConfig:
    """Auto-checkpoint configuration for graphs."""

    enabled: bool = False
    every_n_iterations: int | None = None
    every_seconds: float | None = None
    retain_last: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    handler: CheckpointHandler | None = None

    def clone(self) -> 'GraphCheckpointConfig':
        """Create a shallow copy."""
        return GraphCheckpointConfig(
            enabled=self.enabled,
            every_n_iterations=self.every_n_iterations,
            every_seconds=self.every_seconds,
            retain_last=self.retain_last,
            metadata=dict(self.metadata),
            handler=self.handler,
        )

    def to_serializable(self) -> dict[str, Any]:
        """Convert to serializable dict (handler omitted)."""
        return {
            'enabled': self.enabled,
            'every_n_iterations': self.every_n_iterations,
            'every_seconds': self.every_seconds,
            'retain_last': self.retain_last,
            'metadata': dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'GraphCheckpointConfig':
        """Build config from serialized payload."""
        return cls(
            enabled=payload.get('enabled', False),
            every_n_iterations=payload.get('every_n_iterations'),
            every_seconds=payload.get('every_seconds'),
            retain_last=payload.get('retain_last', 5),
            metadata=dict(payload.get('metadata') or {}),
        )

    def should_checkpoint(self, iteration: int, *, now: float, last_checkpoint_at: float | None) -> bool:
        """Return True if checkpoint should fire."""
        if not self.enabled:
            return False
        due_iteration = (
            self.every_n_iterations is not None
            and self.every_n_iterations > 0
            and iteration > 0
            and iteration % self.every_n_iterations == 0
        )
        due_time = False
        if self.every_seconds and self.every_seconds > 0:
            if last_checkpoint_at is None:
                due_time = True
            else:
                due_time = (now - last_checkpoint_at) >= self.every_seconds
        return due_iteration or due_time
