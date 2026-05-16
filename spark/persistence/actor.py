"""Persistent actor helper base class."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from typing import Any

from ..actor.base import Actor


class PersistentActor(Actor):
    """Actor base class for opt-in event-sourced persistence."""

    def __init__(self, persistence_id: str) -> None:
        super().__init__()
        normalized = persistence_id.strip()
        if not normalized:
            raise ValueError("persistence_id must not be empty")
        self.persistence_id = normalized

    async def persist(self, event: Any) -> None:
        """Append an event and apply it to in-memory state."""
        await self.persist_event(event)
        result = self.apply_event(event)
        if inspect.isawaitable(result):
            await result

    async def persist_event(self, event: Any) -> None:
        """Append an event without applying it."""
        context = self._require_context()
        persist_event = getattr(context, "persist_event", None)
        if persist_event is None:
            raise RuntimeError("persistent actors require an async runtime with a journal")
        await persist_event(event)

    def apply_event(self, event: Any) -> Any | Awaitable[Any]:
        """Apply a recovered or newly persisted event to actor state."""
        return None

    def apply_snapshot(self, state: Any) -> Any | Awaitable[Any]:
        """Restore actor state from a snapshot."""
        return None

    def snapshot_state(self) -> Any:
        """Return actor state suitable for a snapshot."""
        return None

    async def save_snapshot(self, state: Any = None, *, sequence: int | None = None) -> None:
        """Persist a snapshot of current actor state."""
        context = self._require_context()
        save_snapshot = getattr(context, "save_snapshot", None)
        if save_snapshot is None:
            raise RuntimeError("persistent actors require an async runtime with a journal")
        await save_snapshot(self.snapshot_state() if state is None else state, sequence=sequence)
