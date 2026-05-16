"""Structured runtime event records."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..core.identity import ActorId, SyndicateId


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """One structured runtime event emitted by a backend."""

    kind: str
    syndicate_id: SyndicateId
    timestamp: float = field(default_factory=time.time)
    actor_id: ActorId | None = None
    message_id: str | None = None
    reason: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
