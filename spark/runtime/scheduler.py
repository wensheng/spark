"""Monotonic-time wakeup scheduler."""

from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from itertools import count
from time import monotonic

from ..core.identity import Envelope


@dataclass(order=True, slots=True)
class ScheduledEnvelope:
    """Envelope scheduled for future delivery."""

    due_at: float
    sequence: int
    envelope: Envelope = field(compare=False)


class Scheduler:
    """Schedules envelopes against monotonic time."""

    def __init__(self) -> None:
        self._queue: list[ScheduledEnvelope] = []
        self._counter = count()

    def schedule(self, delay: float, envelope: Envelope) -> None:
        """Schedule envelope after delay seconds."""
        due_at = monotonic() + max(0.0, delay)
        heappush(self._queue, ScheduledEnvelope(due_at, next(self._counter), envelope))

    def pop_due(self) -> list[Envelope]:
        """Pop all envelopes whose due time has arrived."""
        now = monotonic()
        due: list[Envelope] = []
        while self._queue and self._queue[0].due_at <= now:
            due.append(heappop(self._queue).envelope)
        return due

    def next_due_at(self) -> float | None:
        """Return the monotonic timestamp for the next scheduled envelope."""
        if not self._queue:
            return None
        return self._queue[0].due_at

    def has_due(self) -> bool:
        """Return whether at least one envelope is due now."""
        next_due_at = self.next_due_at()
        return next_due_at is not None and next_due_at <= monotonic()

    def all_scheduled(self) -> list[ScheduledEnvelope]:
        """Return all scheduled envelopes (for status reporting)."""
        return list(self._queue)
