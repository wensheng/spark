"""Federation protocol messages for multi-system federation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..actor.address import ActorAddress

from .messages import SyndicateMessage

CONV_ADDR_IPV4_CAPABILITY = "Federation Address.IPv4"


class FederationMessage(SyndicateMessage):
    """Marker base class for all federation protocol messages.

    ``FederationMessage`` instances are reserved for federation membership
    runtimes and are not part of ordinary actor payload routing.
    """


@dataclass(frozen=True, slots=True)
class FederationRegister(FederationMessage):
    """Announce presence to federation members.

    Sent periodically to all potential federation leaders to maintain
    registration. Leaders reply with their own ``FederationRegister``
    as acknowledgment.
    """

    admin_address: ActorAddress
    capabilities: dict
    first_time: bool = False
    pre_register: bool = False


@dataclass(frozen=True, slots=True)
class FederationDeRegister(FederationMessage):
    """Gracefully leave the federation.

    Sent when a system shuts down or explicitly deregisters. Members
    receiving this message clean up all state associated with the sender.
    """

    admin_address: ActorAddress
    pre_registered: bool = False


@dataclass(frozen=True, slots=True)
class FederationInvite(FederationMessage):
    """Invite a pre-registered system to join the federation.

    Sent periodically to pre-registered remote systems to prompt them
    to send a ``FederationRegister``.
    """


@dataclass(frozen=True, slots=True)
class NotifyOnSystemRegistration(FederationMessage):
    """Register or unregister an actor for federation update notifications."""

    handler_address: ActorAddress
    enable_notification: bool = True


@dataclass(frozen=True, slots=True)
class SyndicateFederationUpdate(FederationMessage):
    """Delivered to registered notification handlers when members join or leave."""

    remote_admin_address: ActorAddress
    remote_capabilities: dict | None = None
    added: bool = True
