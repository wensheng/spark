"""Supervision policy types for actor failure handling."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

SupervisionDecision = Literal["restart", "stop", "resume", "escalate"]


@dataclass(frozen=True, slots=True)
class SupervisorStrategy:
    """Policy applied when an actor fails while processing a message."""

    decision: SupervisionDecision = "stop"
    max_restarts: int = 0
    period_seconds: float = 60.0
    backoff_seconds: float = 0.0
    backoff_factor: float = 2.0
    max_backoff_seconds: float = 30.0
    jitter_ratio: float = 0.0

    def __post_init__(self) -> None:
        if self.decision not in {"restart", "stop", "resume", "escalate"}:
            raise ValueError(f"unsupported supervision decision: {self.decision!r}")
        if self.max_restarts < 0:
            raise ValueError("max_restarts must be >= 0")
        if self.period_seconds <= 0:
            raise ValueError("period_seconds must be > 0")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")
        if self.backoff_factor < 1:
            raise ValueError("backoff_factor must be >= 1")
        if self.max_backoff_seconds < 0:
            raise ValueError("max_backoff_seconds must be >= 0")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be >= 0")

    @classmethod
    def stop(cls) -> SupervisorStrategy:
        """Stop the actor on failure."""
        return cls(decision="stop")

    @classmethod
    def resume(cls) -> SupervisorStrategy:
        """Keep the actor running after recording the failed message."""
        return cls(decision="resume")

    @classmethod
    def escalate(cls) -> SupervisorStrategy:
        """Escalate failure to the parent by stopping this actor."""
        return cls(decision="escalate")

    @classmethod
    def restart(
        cls,
        *,
        max_restarts: int = 1,
        period_seconds: float = 60.0,
        backoff_seconds: float = 0.0,
        backoff_factor: float = 2.0,
        max_backoff_seconds: float = 30.0,
        jitter_ratio: float = 0.0,
    ) -> SupervisorStrategy:
        """Restart the actor up to ``max_restarts`` times in ``period_seconds``."""
        return cls(
            decision="restart",
            max_restarts=max_restarts,
            period_seconds=period_seconds,
            backoff_seconds=backoff_seconds,
            backoff_factor=backoff_factor,
            max_backoff_seconds=max_backoff_seconds,
            jitter_ratio=jitter_ratio,
        )

    def restart_delay(self, prior_restart_count: int) -> float:
        """Return the delay before the next restart attempt."""
        if self.backoff_seconds <= 0:
            return 0.0
        delay = self.backoff_seconds * (self.backoff_factor ** max(0, prior_restart_count))
        delay = min(delay, self.max_backoff_seconds)
        if self.jitter_ratio:
            jitter = delay * self.jitter_ratio
            delay += random.uniform(-jitter, jitter)
        return max(0.0, delay)
