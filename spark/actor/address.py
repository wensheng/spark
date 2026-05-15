"""Stable public reference to an actor."""

from dataclasses import dataclass

from ..core.identity import ActorId


@dataclass(frozen=True, slots=True)
class ActorAddress:
    """Address used to reference an actor.

    ActorAddresses are stable references that can be used to send messages
    to actors regardless of their location.
    """

    actor_id: ActorId

    @property
    def address_string(self) -> str:
        """Get a string representation of the address."""
        return str(self.actor_id)

    def __str__(self) -> str:
        """String representation of the address."""
        return f"ActorAddr-{self.address_string}"

    def __repr__(self) -> str:
        """Detailed string representation of the address."""
        return f"ActorAddress(actor_id={self.actor_id!r})"
