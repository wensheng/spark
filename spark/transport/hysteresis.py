"""
Hysteresis delay sender for federation message rate limiting.

Prevents a misbehaving member from flooding the federation by growing a
blackout period with each send attempt. The delay decays when no sends
are queued.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..core.identity import Envelope
from ..runtime.results import DeliveryResult

HYSTERESIS_MIN_PERIOD: float = 0.25
HYSTERESIS_MAX_PERIOD: float = 45.0
HYSTERESIS_RATE: float = 1.2


@dataclass(slots=True)
class _QueuedSend:
    """A send queued behind hysteresis."""

    envelope: Envelope
    target_key: str  # dedup key (target + message type name)
    callbacks: list[Callable[[DeliveryResult], None]] = field(default_factory=list)


class HysteresisDelaySender:
    """Rate-limiting sender for federation protocol messages.

    Each send attempt extends a blackout period. During the blackout,
    sends are queued and deduplicated by (target, message type). When
    the blackout expires, all queued sends are flushed.
    """

    def __init__(
        self,
        actual_sender: Callable[[Envelope], DeliveryResult],
        hysteresis_min_period: float = HYSTERESIS_MIN_PERIOD,
        hysteresis_max_period: float = HYSTERESIS_MAX_PERIOD,
        hysteresis_rate: float = HYSTERESIS_RATE,
    ) -> None:
        self._sender = actual_sender
        self._min_period = hysteresis_min_period
        self._max_period = hysteresis_max_period
        self._rate = hysteresis_rate
        self._queue: list[_QueuedSend] = []
        self._current_hysteresis: float | None = None
        self._hysteresis_until: float = 0.0

    @property
    def delay(self) -> float:
        """Seconds remaining in the current blackout period."""
        remaining = self._hysteresis_until - time.monotonic()
        return max(0.0, remaining)

    def pending_count(self) -> int:
        """Number of queued sends."""
        return len(self._queue)

    def send_with_hysteresis(self, envelope: Envelope) -> None:
        """Queue *envelope*, deduplicating prior sends to the same target+type."""
        msg_type = type(envelope.payload).__name__
        target_key = str(envelope.target) + ":" + msg_type

        # Deduplicate: replace any existing queued send with the same key
        kept: list[_QueuedSend] = []
        for qs in self._queue:
            if qs.target_key != target_key:
                kept.append(qs)
        self._queue = kept

        # If no blackout is active, send immediately and start one
        if self._hysteresis_until <= time.monotonic():
            self._increase_hysteresis()
            self._update_deadline()
            self._sender(envelope)
            return

        qs = _QueuedSend(envelope=envelope, target_key=target_key, callbacks=[])
        self._queue.append(qs)
        self._increase_hysteresis()
        self._update_deadline()

    def check_sends(self) -> None:
        """Flush queued sends if the blackout period has expired."""
        if self._hysteresis_until <= time.monotonic():
            self._decrease_hysteresis()
            self._update_deadline(reset=True)
            for qs in self._queue:
                result = self._sender(qs.envelope)
                for cb in qs.callbacks:
                    cb(result)
            self._queue.clear()

    def cancel_sends(self, actor_id: str) -> None:
        """Cancel all pending sends targeting *actor_id*."""
        removed: list[_QueuedSend] = []
        kept: list[_QueuedSend] = []
        for qs in self._queue:
            if str(qs.envelope.target) == actor_id:
                removed.append(qs)
            else:
                kept.append(qs)
        self._queue = kept

    def _increase_hysteresis(self) -> None:
        if self._current_hysteresis is not None and self._current_hysteresis >= self._min_period:
            self._current_hysteresis = min(
                self._current_hysteresis * self._rate,
                self._max_period,
            )
        else:
            self._current_hysteresis = self._min_period

    def _decrease_hysteresis(self) -> None:
        if self._has_hysteresis():
            reduced = self._current_hysteresis / self._rate  # type: ignore[operator]
            self._current_hysteresis = reduced if reduced >= self._min_period else None
        else:
            self._current_hysteresis = None

    def _has_hysteresis(self) -> bool:
        return self._current_hysteresis is not None and self._current_hysteresis >= self._min_period

    def _update_deadline(self, *, reset: bool = False) -> None:
        if not self._current_hysteresis:
            self._hysteresis_until = 0.0
        elif reset:
            self._hysteresis_until = time.monotonic() + self._current_hysteresis
        else:
            remaining = max(0.0, self._hysteresis_until - time.monotonic())
            self._hysteresis_until = time.monotonic() + max(
                self._current_hysteresis - remaining,
                0.0,
            )
