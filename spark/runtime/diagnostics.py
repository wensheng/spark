"""Read-only runtime diagnostics snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.identity import ActorId, SyndicateId


@dataclass(frozen=True, slots=True)
class ActorDiagnostics:
    """Read-only runtime state for one actor."""

    actor_id: ActorId
    parent_id: ActorId | None = None
    child_count: int = 0
    mailbox_depth: int | None = None
    oldest_message_age: float | None = None
    running: bool | None = None
    stopped: bool | None = None
    active: bool | None = None
    processed_count: int = 0
    failure_count: int = 0
    restart_count: int = 0
    average_processing_latency: float = 0.0


@dataclass(frozen=True, slots=True)
class RuntimeDiagnostics:
    """Read-only runtime state for one backend."""

    syndicate_id: SyndicateId
    backend_type: str
    actor_count: int
    external_inbox_count: int
    dead_letter_count: int
    lifecycle_failure_count: int = 0
    late_reply_count: int = 0
    event_count: int = 0
    uptime_seconds: float = 0.0
    dead_letter_summary: dict[str, int] | None = None
    actors: tuple[ActorDiagnostics, ...] = ()
