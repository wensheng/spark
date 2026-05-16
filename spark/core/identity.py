"""Core identity and envelope types for Spark."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any


class FrozenHeaders(Mapping[str, Any]):
    """Small immutable mapping used for envelope metadata."""

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data = dict(data or {})

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return repr(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False


@dataclass(frozen=True, slots=True)
class SyndicateId:
    """Unique identifier for an syndicate.

    A SyndicateId identifies a single Spark instance, whether it's running
    in-process, across multiple processes, or distributed across multiple nodes.
    """

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def from_name(cls, name: str) -> SyndicateId:
        """Create a SyndicateId from a human-readable name."""
        return cls(uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, name)))

    def __str__(self) -> str:
        return f"System({self.uuid[:8]})"

    def __repr__(self) -> str:
        return f"SyndicateId(uuid='{self.uuid}')"


@dataclass(frozen=True, slots=True)
class ActorId:
    """Unique identifier for an actor.

    An ActorId is stable and doesn't change regardless of where the actor
    is running (in-process, remote system, etc.). This enables true
    location transparency.
    """

    syndicate_id: SyndicateId
    actor_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __str__(self) -> str:
        return f"Actor({self.syndicate_id.uuid[:8]}:{self.actor_id[:8]})"

    def __repr__(self) -> str:
        return f"ActorId(syndicate_id={self.syndicate_id!r}, actor_id='{self.actor_id}')"


@dataclass(frozen=True, slots=True)
class ActorIncarnation:
    """Specific running generation of a logical actor."""

    actor_id: ActorId
    generation: int = 0

    def next_generation(self) -> ActorIncarnation:
        """Return the next running generation for the same logical actor."""
        return ActorIncarnation(actor_id=self.actor_id, generation=self.generation + 1)


@dataclass(frozen=True, slots=True)
class Envelope:
    """Message wrapper for all actor communication.

    All messages between actors are wrapped in an Envelope which provides
    metadata for routing, tracing, and error handling.
    """

    target: ActorId
    payload: Any
    target_incarnation: ActorIncarnation | None = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    headers: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    sender: ActorId | None = None
    deadline: datetime | None = None
    correlation_id: str | None = None
    trace_id: str | None = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        """Normalize immutable metadata defaults."""
        object.__setattr__(self, "headers", FrozenHeaders(self.headers))
        traceparent = self.headers.get("traceparent")
        if isinstance(traceparent, str):
            object.__setattr__(self, "trace_id", traceparent)
        if self.correlation_id is None:
            object.__setattr__(self, "correlation_id", self.message_id)
        if self.deadline is not None and self.deadline.tzinfo is None:
            msg = "Envelope deadlines must be timezone-aware"
            raise ValueError(msg)

    @property
    def is_expired(self) -> bool:
        """Check if the envelope has expired."""
        if self.deadline is None:
            return False
        return datetime.now(tz=UTC) > self.deadline

    def with_deadline(self, timeout: timedelta) -> Envelope:
        """Create a new envelope with a deadline based on timeout from now."""
        return Envelope(
            message_id=self.message_id,
            sender=self.sender,
            target=self.target,
            payload=self.payload,
            target_incarnation=self.target_incarnation,
            headers=self.headers,
            deadline=datetime.now(tz=UTC) + timeout,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
        )

    def with_sender(self, sender: ActorId) -> Envelope:
        """Create a new envelope with a different sender."""
        return Envelope(
            message_id=self.message_id,
            sender=sender,
            target=self.target,
            payload=self.payload,
            target_incarnation=self.target_incarnation,
            headers=self.headers,
            deadline=self.deadline,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
        )

    def __str__(self) -> str:
        return f"Envelope({self.message_id[:8]} -> {self.target})"
