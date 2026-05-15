"""Per-actor FIFO mailbox."""

from collections import deque
from dataclasses import dataclass, field

from ..core.identity import ActorId, Envelope


@dataclass(slots=True)
class Mailbox:
    """FIFO queue for one actor."""

    actor_id: ActorId
    _queue: deque[Envelope] = field(default_factory=deque)

    def enqueue(self, envelope: Envelope) -> None:
        """Append an envelope to the mailbox."""
        self._queue.append(envelope)

    def dequeue(self) -> Envelope | None:
        """Return the next envelope, if one exists."""
        if not self._queue:
            return None
        return self._queue.popleft()

    def has_pending(self) -> bool:
        """Return whether this mailbox has messages waiting."""
        return bool(self._queue)

    def size(self) -> int:
        """Return the current queue depth."""
        return len(self._queue)
