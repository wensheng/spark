"""External inboxes used by Syndicate.ask and Syndicate.listen."""

import logging
from collections import deque
from dataclasses import dataclass, field

from ..actor.address import ActorAddress
from ..core.identity import ActorId, Envelope, SyndicateId


@dataclass(slots=True)
class ExternalInbox:
    """Mailbox for code outside the actor registry."""

    actor_id: ActorId
    address: ActorAddress
    _queue: deque[Envelope] = field(default_factory=deque)
    _drain_logger: logging.Logger | None = None

    def enqueue(self, envelope: Envelope) -> None:
        """Append an envelope to this external inbox.

        When ``_drain_logger`` is set, the envelope is logged and discarded
        instead of queued.
        """
        if self._drain_logger is not None:
            self._drain_logger.info(
                "global Syndicate drained message: payload=%r sender=%s",
                envelope.payload,
                envelope.sender,
            )
            return
        self._queue.append(envelope)

    def dequeue(self) -> Envelope | None:
        """Return the next envelope, if any."""
        if not self._queue:
            return None
        return self._queue.popleft()

    def has_pending(self) -> bool:
        """Return whether the inbox has queued envelopes."""
        return bool(self._queue)


class ExternalInboxRegistry:
    """Tracks external inboxes by actor id."""

    def __init__(self, syndicate_id: SyndicateId) -> None:
        self._syndicate_id = syndicate_id
        self._inboxes: dict[ActorId, ExternalInbox] = {}

    def create(self) -> ExternalInbox:
        """Create and register a new external inbox."""
        actor_id = ActorId(syndicate_id=self._syndicate_id)
        inbox = ExternalInbox(actor_id=actor_id, address=ActorAddress(actor_id))
        self._inboxes[actor_id] = inbox
        return inbox

    def get(self, actor_id: ActorId) -> ExternalInbox | None:
        """Return an inbox by actor id, if it exists."""
        return self._inboxes.get(actor_id)

    def remove(self, actor_id: ActorId) -> None:
        """Remove an inbox if present."""
        self._inboxes.pop(actor_id, None)

    def __len__(self) -> int:
        return len(self._inboxes)
