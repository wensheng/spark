"""Core control message types for Spark."""

import time
from dataclasses import dataclass, field
from typing import Any

from .actor_spec import ActorSpec
from .identity import ActorId, ActorIncarnation, Envelope, SyndicateId


class SyndicateMessage:
    """Base class for all actor system messages.

    These messages are handled internally by the actor system and
    are not typically used directly by user actors.
    """

    ...


@dataclass(frozen=True, slots=True)
class SystemShutdown(SyndicateMessage):
    """Request to shut down the entire actor system."""

    sender: ActorId | None = None


@dataclass(frozen=True, slots=True)
class ActorExitRequest(SyndicateMessage):
    """Request an actor to exit gracefully.

    This message should be sent to an actor to request it to stop.
    The actor should clean up resources and exit.
    """

    reason: str = "actor requested to exit"


@dataclass(frozen=True, slots=True)
class CancellationRequest(SyndicateMessage):
    """Best-effort request to cancel work associated with a correlation id."""

    correlation_id: str
    reason: str = "request cancelled"


@dataclass(frozen=True, slots=True)
class ActorExited(SyndicateMessage):
    """Notification that an actor has exited.

    This message is sent by the actor system to notify monitor watchers when
    an actor exits.
    """

    actor_id: ActorId
    incarnation: ActorIncarnation | None = None
    exit_code: int = 0
    reason: str = "actor exited"


@dataclass(frozen=True, slots=True)
class ChildActorExited(SyndicateMessage):
    """Notification about child actor exit.

    This is sent to the parent of an actor when a child actor exits.
    """

    child_id: ActorId
    parent_id: ActorId
    child_incarnation: ActorIncarnation | None = None
    exit_code: int = 0
    reason: str = "child actor exited"


@dataclass(frozen=True, slots=True)
class ChildActorRestarted(SyndicateMessage):
    """Notification that a child actor restarted after failure."""

    child_id: ActorId
    parent_id: ActorId
    old_incarnation: ActorIncarnation
    new_incarnation: ActorIncarnation
    reason: str = "child actor restarted"


@dataclass(frozen=True, slots=True)
class ActorCreateRequest(SyndicateMessage):
    """Request to create a new actor."""

    actor_spec: ActorSpec
    parent_id: ActorId | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActorCreateResponse(SyndicateMessage):
    """Response to an actor creation request."""

    actor_id: ActorId | None = None
    success: bool = True
    error: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class WakeupRequest(SyndicateMessage):
    """Request to wake up an actor after a delay."""

    actor_id: ActorId
    payload: Any = None


@dataclass(frozen=True, slots=True)
class WakeupMessage(SyndicateMessage):
    """Message delivered to an actor when a scheduled wakeup fires."""

    delay: float
    payload: Any = None


@dataclass(frozen=True, slots=True)
class StatusRequest(SyndicateMessage):
    """Request system or actor status.

    Send to an Syndicate's external inbox for ``SystemStatus``,
    or to an individual actor for `Syndicate`.
    """

    sender_id: ActorId | None = None


# ---------------------------------------------------------------------------
# Status response supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PendingMessage:
    """A message queued for delivery (from, to, message-string)."""

    from_addr: str
    to_addr: str
    message: str


@dataclass(frozen=True, slots=True)
class PendingWakeup:
    """A scheduled wakeup (target, delay-seconds, payload-string)."""

    target: str
    delay: float
    payload: str


@dataclass(frozen=True, slots=True)
class FederationAttendee:
    """One federation member (address, valid-until-string)."""

    address: str
    valid_until: str


@dataclass(frozen=True, slots=True)
class CommonStatusFields:
    """Fields shared between SystemStatus and ActorStatus."""

    pending_messages: tuple[PendingMessage, ...] = ()
    pending_wakeups: tuple[PendingWakeup, ...] = ()
    received_messages: tuple[PendingMessage, ...] = ()
    child_actors: tuple[str, ...] = ()
    governor: str | None = None
    messages_sent: int = 0
    send_failures: int = 0
    messages_received: int = 0
    misc: dict[str, str] = field(default_factory=dict)
    pending_addr_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# System-level status response
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SystemStatus(SyndicateMessage):
    """Comprehensive system-level status response."""

    syndicate_id: SyndicateId
    admin_address: str
    actor_count: int
    uptime_seconds: float
    backend_type: str
    common: CommonStatusFields = field(default_factory=CommonStatusFields)
    capabilities: dict[str, Any] = field(default_factory=dict)
    federation_leader: str | None = None
    federation_register_time: str | None = None
    federation_attendees: tuple[FederationAttendee, ...] = ()
    dead_letter_handler: str | None = None
    dead_letter_addresses: tuple[str, ...] = ()
    notify_addresses: tuple[str, ...] = ()
    global_actors: dict[str, str] = field(default_factory=dict)
    in_shutdown: bool = False


# ---------------------------------------------------------------------------
# Actor-level status response
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActorStatus(SyndicateMessage):
    """Comprehensive actor-level status response."""

    actor_address: str
    actor_class: str
    admin_address: str
    common: CommonStatusFields = field(default_factory=CommonStatusFields)
    parent_address: str | None = None
    exiting: str | None = None


@dataclass(frozen=True, slots=True)
class DeadLetter(SyndicateMessage):
    """A message that could not be delivered to its target.

    This message is sent to the dead letter handler when a message
    cannot be delivered to its target actor.
    """

    original_envelope: Envelope
    reason: str
    timestamp: float | None = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Normalize timestamps supplied as None by compatibility callers."""
        if self.timestamp is None:
            object.__setattr__(self, "timestamp", time.time())


@dataclass(frozen=True, slots=True)
class WatchMessage(SyndicateMessage):
    """Delivered when one or more watched fds become ready or fail.

    The kernel removes any fds in ``failed`` from the watch list before
    delivery, so the actor's view stays consistent.
    """

    ready_read: tuple[int, ...] = ()
    ready_write: tuple[int, ...] = ()
    failed: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "ready_read", tuple(self.ready_read))
        object.__setattr__(self, "ready_write", tuple(self.ready_write))
        object.__setattr__(self, "failed", tuple(self.failed))
