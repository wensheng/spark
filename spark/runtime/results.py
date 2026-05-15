"""Runtime operation result types."""

from dataclasses import dataclass

from ..actor.address import ActorAddress


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Result of attempting to deliver one envelope."""

    success: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SpawnResult:
    """Result of creating one actor."""

    address: ActorAddress
