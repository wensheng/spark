"""Transport protocol boundaries."""

from __future__ import annotations

from typing import Protocol

from ..core.identity import Envelope, SyndicateId
from ..runtime.results import DeliveryResult


class Transport(Protocol):
    """System-level transport for routing envelopes by SyndicateId."""

    @property
    def address(self) -> tuple[str, int] | None:
        """Return this transport's bound address after startup."""
        ...

    def connect(self, syndicate_id: SyndicateId, host: str, port: int) -> None:
        """Add or replace a route to another actor system."""
        ...

    async def send(self, envelope: Envelope) -> DeliveryResult:
        """Send envelope to its target system."""
        ...

    async def send_to(self, envelope: Envelope, host: str, port: int) -> DeliveryResult:
        """Send envelope to an explicit host:port, bypassing the route table."""
        ...

    async def close(self) -> None:
        """Close the transport."""
        ...
