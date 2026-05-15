"""Federation membership provider for multi-system federation.

Implements the ``MembershipProvider`` protocol with a dynamic discovery
mechanism based on the Spark Federation protocol.  Systems
periodically exchange ``FederationRegister`` messages to maintain
federation, and a leader runs expiry checks on inactive members.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from ..actor.address import ActorAddress
from ..core.federation_messages import (
    FederationDeRegister,
    FederationInvite,
    FederationMessage,
    FederationRegister,
    NotifyOnSystemRegistration,
    SyndicateFederationUpdate,
)
from ..core.identity import ActorId, Envelope, SyndicateId
from ..core.messages import SystemShutdown
from ..runtime.results import DeliveryResult
from ..transport.hysteresis import HysteresisDelaySender
from .membership import SystemDescriptor, SystemEvent

_logger = logging.getLogger("spark.federation")

# ---------------------------------------------------------------------------
# Configuration defaults (seconds)
# ---------------------------------------------------------------------------
REREGISTRATION_PERIOD: float = 442.0  # 7m22s
RESTART_PERIOD: float = 202.0  # 3m22s
REGISTRATION_MISS_MAX: int = 3
REINVITE_ADJUSTMENT: float = 1.1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _FederationTimer:
    """Monotonic expiration timer."""

    def __init__(self, duration: float | None = None) -> None:
        self._deadline: float | None = None if duration is None else time.monotonic() + duration

    @property
    def expired(self) -> bool:
        if self._deadline is None:
            return False
        return time.monotonic() >= self._deadline

    @property
    def remaining(self) -> float:
        if self._deadline is None:
            return float("inf")
        return max(0.0, self._deadline - time.monotonic())

    def reset(self, duration: float | None = None) -> None:
        self._deadline = None if duration is None else time.monotonic() + duration


class _PreRegistration:
    """Tracks pre-registration ping state."""

    def __init__(self) -> None:
        self.ping_valid = _FederationTimer(0.0)
        self.ping_pending = False

    def refresh(self) -> None:
        self.ping_valid.reset(REREGISTRATION_PERIOD)


class _FederationMemberData:
    """State for one remote federation member."""

    __slots__ = (
        "remote_address",
        "remote_capabilities",
        "has_remote_actors",
        "pre_reg_only",
        "pre_registered",
        "registry_valid",
    )

    def __init__(
        self,
        remote_address: ActorAddress,
        remote_capabilities: dict,
        pre_reg_only: bool = False,
    ) -> None:
        self.remote_address = remote_address
        self.remote_capabilities = remote_capabilities
        self.has_remote_actors: list[tuple[ActorAddress, ActorAddress]] = []
        self.pre_reg_only = pre_reg_only
        self.pre_registered: _PreRegistration | None = None
        self.registry_valid = _FederationTimer(
            REREGISTRATION_PERIOD * REGISTRATION_MISS_MAX,
        )

    def refresh(self, capabilities: dict, pre_reg: bool = False) -> None:
        self.remote_capabilities = capabilities
        self.registry_valid.reset(
            REREGISTRATION_PERIOD * REGISTRATION_MISS_MAX,
        )
        if self.pre_registered is not None:
            self.pre_registered.refresh()

    @property
    def permanent_entry(self) -> bool:
        return self.pre_reg_only or self.pre_registered is not None


# ---------------------------------------------------------------------------
# FederationMembershipProvider
# ---------------------------------------------------------------------------


class FederationMembershipProvider:
    """Dynamic membership provider using the Federation protocol.

    Replaces `StaticMembershipProvider` when `federation=True` on
    `Syndicate`.  Maintains federation with remote systems via
    periodic registration exchanges and pre-registration pinging.

    Parameters
    ----------
    syndicate_id:
        This system's identity.
    federation_actor_id:
        Well-known ``ActorId`` for routing federation envelopes to this
        provider (actor_id string ``"__spark_federation__"``).
    address:
        ``ActorAddress`` wrapping *federation_actor_id*.
    capabilities:
        This system's capabilities dict.  Must include
        ``"Federation Address.IPv4"`` when TCP transport is in use.
    send_message:
        Callable routing an envelope via the transport route table
        (``transport.send``).
    send_to_address:
        Callable sending an envelope to an explicit host:port,
        bypassing the route table.  Used for initial bootstrap.
    federation_addresses:
        List of ``(host, port)`` tuples for potential federation leaders.
        The lowest-index reachable leader becomes the active leader.
    """

    def __init__(
        self,
        syndicate_id: SyndicateId,
        federation_actor_id: ActorId,
        address: ActorAddress,
        capabilities: dict,
        send_message: Callable[[Envelope], DeliveryResult],
        send_to_address: Callable[[Envelope, str, int], DeliveryResult],
        federation_addresses: list[tuple[str, int]] | None = None,
        *,
        reregistration_period: float = REREGISTRATION_PERIOD,
        restart_period: float = RESTART_PERIOD,
        registration_miss_max: int = REGISTRATION_MISS_MAX,
        reinvite_adjustment: float = REINVITE_ADJUSTMENT,
    ) -> None:
        self._syndicate_id = syndicate_id
        self._federation_actor_id = federation_actor_id
        self._address = address
        self._capabilities = dict(capabilities)
        self._send_message = send_message
        self._send_to_address = send_to_address
        self._federation_addresses: list[tuple[str, int] | None] = (
            list(federation_addresses) if federation_addresses else []
        )
        self._reregistration_period = reregistration_period
        self._restart_period = restart_period
        self._registration_miss_max = registration_miss_max
        self._reinvite_adjustment = reinvite_adjustment

        # Internal state
        self._lock = threading.RLock()
        self._members: dict[str, _FederationMemberData] = {}  # keyed by admin address str
        self._systems: dict[SyndicateId, SystemDescriptor] = {}
        self._watchers: list[Callable[[SystemEvent], None]] = []
        self._notification_handlers: list[ActorAddress] = []
        self._shutdown = False
        self._activated = False
        self._invited = False
        self._federation_leader_idx = 0
        self._federation_registration_timer = _FederationTimer()
        self._leader_miss_count = 0

        # Hysteresis sender for outbound federation messages
        self._hysteresis = HysteresisDelaySender(self._send_hysteresis_envelope)

        # Timer thread
        self._timer_thread = threading.Thread(
            target=self._timer_loop,
            name=f"spark-federation-timer-{id(self)}",
            daemon=True,
        )

    # ------------------------------------------------------------------
    # MembershipProvider protocol
    # ------------------------------------------------------------------

    def list_systems(self) -> list[SystemDescriptor]:
        with self._lock:
            return list(self._systems.values())

    def watch(
        self,
        callback: Callable[[SystemEvent], None],
    ) -> Callable[[], None]:
        with self._lock:
            self._watchers.append(callback)
            descriptors = list(self._systems.values())
        for d in descriptors:
            callback(SystemEvent("joined", d))

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._watchers:
                    self._watchers.remove(callback)

        return unsubscribe

    # ------------------------------------------------------------------
    # Lifecycle — called by Syndicate
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Start the federation: register with leaders and begin the timer loop."""
        with self._lock:
            if self._activated:
                return
            self._activated = True
        self._setup_federation(activation=True)
        if not self._timer_thread.is_alive():
            self._timer_thread.start()

    def exit_federation(self) -> None:
        """Gracefully leave the federation."""
        with self._lock:
            self._shutdown = True
            members = list(self._members.items())
        for key, member in members:
            self._hysteresis.cancel_sends(key)
            self._send_federation_message(
                FederationDeRegister(
                    admin_address=self._address,
                    pre_registered=member.pre_registered is not None,
                ),
                member.remote_address.actor_id,
            )
        with self._lock:
            self._members.clear()
            self._systems.clear()

    # ------------------------------------------------------------------
    # Incoming message dispatch — called from transport receive callback
    # ------------------------------------------------------------------

    def handle_envelope(self, envelope: Envelope) -> None:
        """Dispatch an incoming federation envelope."""
        msg = envelope.payload
        sender_addr = ActorAddress(envelope.sender) if envelope.sender else None

        if isinstance(msg, FederationRegister):
            self._handle_federation_register(msg, sender_addr)
        elif isinstance(msg, FederationDeRegister):
            self._handle_federation_deregister(msg, sender_addr)
        elif isinstance(msg, FederationInvite):
            self._handle_federation_invite(sender_addr)
        elif isinstance(msg, NotifyOnSystemRegistration):
            self._handle_notify_on_system_registration(msg, sender_addr)
        elif isinstance(msg, SystemShutdown):
            self._handle_system_shutdown(sender_addr)

    # ------------------------------------------------------------------
    # Periodic check — called from timer loop
    # ------------------------------------------------------------------

    def check_federation(self) -> None:
        with self._lock:
            if not self._activated:
                return
            time.monotonic()

            # Leader checks
            if self._is_federation_leader():
                expired_members = [
                    (key, m) for key, m in self._members.items() if m.registry_valid.expired and not m.permanent_entry
                ]
                for key, member in expired_members:
                    _logger.warning(
                        "Federation member %s missed check-in; cleaning up",
                        key,
                    )
                    self._remote_system_cleanup_locked(key, member)

            # Member checks
            if not self._is_federation_leader():
                if self._federation_registration_timer.expired:
                    leader = self._current_leader()
                    if leader is not None:
                        self._leader_miss_count += 1
                        if self._leader_miss_count >= self._registration_miss_max:
                            _logger.warning(
                                "Federation leader unreachable after %d misses; cleaning up leader",
                                self._leader_miss_count,
                            )
                            self._cleanup_leader_locked()
                            self._leader_miss_count = 0
                        else:
                            self._setup_federation()
                    else:
                        self._setup_federation()

            # Pre-registration pinging
            for member in list(self._members.values()):
                if (
                    member.pre_registered is not None
                    and member.pre_registered.ping_valid.expired
                    and not member.pre_registered.ping_pending
                ):
                    member.pre_registered.ping_pending = True
                    period = self._restart_period if member.registry_valid.expired else self._reregistration_period
                    member.pre_registered.ping_valid.reset(
                        period * self._reinvite_adjustment,
                    )
                    self._hysteresis.send_with_hysteresis(
                        _federation_envelope(
                            FederationInvite(),
                            self._federation_actor_id,
                            member.remote_address.actor_id,
                        ),
                    )

    # ------------------------------------------------------------------
    # Private: message handlers
    # ------------------------------------------------------------------

    def _handle_federation_register(
        self,
        msg: FederationRegister,
        sender: ActorAddress | None,
    ) -> None:
        if sender is None:
            return
        sender_key = str(sender.actor_id)

        # Self-registration guard
        if sender.actor_id == self._federation_actor_id:
            return

        with self._lock:
            if sender_key in self._members:
                existing = self._members[sender_key]
                if msg.first_time:
                    # Full refresh
                    self._remote_system_cleanup_locked(sender_key, existing)
                    existing = None
                elif msg.pre_register and existing.pre_registered is None:
                    existing.pre_registered = _PreRegistration()
                    existing.pre_registered.refresh()
            else:
                existing = None

            if existing is None:
                member = _FederationMemberData(
                    msg.admin_address,
                    msg.capabilities,
                    pre_reg_only=msg.pre_register,
                )
                if msg.pre_register:
                    member.pre_registered = _PreRegistration()
                    member.pre_registered.refresh()
                self._members[sender_key] = member
                self._update_system_descriptor_locked(member)
                _logger.info(
                    "Federation member registered: %s (first_time=%s)",
                    sender_key,
                    msg.first_time,
                )
            else:
                member = existing
                member.refresh(msg.capabilities, pre_reg=msg.pre_register)

            # Notification to handlers
            self._notify_handlers_locked(sender, member.remote_capabilities, added=True)

            # Respond if pre-register
            if msg.pre_register:
                self._send_federation_message(
                    FederationInvite(),
                    sender.actor_id,
                )

            # Respond if leader, or if first_time
            if self._is_federation_leader() or msg.first_time:
                self._send_federation_message(
                    FederationRegister(
                        admin_address=self._address,
                        capabilities=self._capabilities,
                    ),
                    sender.actor_id,
                )

    def _handle_federation_deregister(
        self,
        msg: FederationDeRegister,
        sender: ActorAddress | None,
    ) -> None:
        if sender is None:
            return
        sender_key = str(sender.actor_id)
        with self._lock:
            if sender_key not in self._members:
                return
            member = self._members[sender_key]
            if msg.pre_registered:
                member.pre_registered = None
            self._remote_system_cleanup_locked(sender_key, member)

    def _handle_federation_invite(
        self,
        sender: ActorAddress | None,
    ) -> None:
        if sender is None:
            return
        with self._lock:
            if not self._invited:
                self._invited = True
                # Set the inviter as the sole federation address
                self._federation_addresses = [None]
            # Register back to the inviter
            self._send_federation_message(
                FederationRegister(
                    admin_address=self._address,
                    capabilities=self._capabilities,
                    first_time=True,
                ),
                sender.actor_id,
            )

    def _handle_notify_on_system_registration(
        self,
        msg: NotifyOnSystemRegistration,
        sender: ActorAddress | None,
    ) -> None:
        del sender  # not used
        handler = msg.handler_address
        with self._lock:
            if msg.enable_notification:
                if handler not in self._notification_handlers:
                    self._notification_handlers.append(handler)
                # Replay current members
                for _key, member in self._members.items():
                    self._send_federation_message(
                        SyndicateFederationUpdate(
                            remote_admin_address=member.remote_address,
                            remote_capabilities=member.remote_capabilities,
                            added=True,
                        ),
                        handler.actor_id,
                    )
            else:
                if handler in self._notification_handlers:
                    self._notification_handlers.remove(handler)

    def _handle_system_shutdown(self, sender: ActorAddress | None) -> None:
        del sender
        self.exit_federation()

    # ------------------------------------------------------------------
    # Private: setup / teardown
    # ------------------------------------------------------------------

    def _setup_federation(self, activation: bool = False) -> None:
        """Send ``FederationRegister`` to all potential leaders."""
        with self._lock:
            addresses = list(self._federation_addresses)
        for addr in addresses:
            if addr is None:
                continue
            # Skip self
            cap_addr = self._capabilities.get("Federation Address.IPv4")
            if cap_addr is not None and addr == tuple(cap_addr):
                continue
            envelope = _federation_envelope(
                FederationRegister(
                    admin_address=self._address,
                    capabilities=self._capabilities,
                    first_time=activation,
                ),
                self._federation_actor_id,
                self._federation_actor_id,  # Will be overwritten when route known
            )
            self._send_to_address(envelope, addr[0], addr[1])
        with self._lock:
            self._federation_registration_timer.reset(self._reregistration_period)

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _is_federation_leader(self) -> bool:
        """Return True if this system is the current federation leader."""
        if self._invited:
            return False
        cap_addr = self._capabilities.get("Federation Address.IPv4")
        if cap_addr is None:
            return not self._federation_addresses
        my_addr = tuple(cap_addr)
        for idx, addr in enumerate(self._federation_addresses):
            if addr is not None and addr < my_addr:
                self._federation_leader_idx = idx
                return False
        self._federation_leader_idx = 0
        return True

    def _current_leader(self) -> tuple[str, int] | None:
        """Return the current leader's (host, port) or None."""
        if self._invited:
            return None
        if not self._federation_addresses:
            return None
        idx = self._federation_leader_idx % len(self._federation_addresses)
        return self._federation_addresses[idx]

    def _send_federation_message(
        self,
        msg: FederationMessage,
        target: ActorId,
    ) -> None:
        """Send a federation message to *target* via the hysteresis sender."""
        envelope = _federation_envelope(msg, self._federation_actor_id, target)
        self._hysteresis.send_with_hysteresis(envelope)

    def _send_hysteresis_envelope(self, envelope: Envelope) -> DeliveryResult:
        """Callback used by HysteresisDelaySender to actually transmit."""
        return self._send_message(envelope)

    def _remote_system_cleanup_locked(
        self,
        key: str,
        member: _FederationMemberData,
    ) -> None:
        """Remove a federation member (caller holds ``_lock``)."""
        if member.pre_reg_only:
            return

        # Notify handlers
        self._notify_handlers_locked(
            member.remote_address,
            member.remote_capabilities,
            added=False,
        )

        # Notify parents of remote child actors
        for _local_parent, _remote_child in member.has_remote_actors:
            # Dispatch ChildActorExited to parent via local delivery
            pass  # Parent notification is handled externally

        # Remove from members
        self._members.pop(key, None)

        # Remove from systems and notify watchers
        for sid, desc in list(self._systems.items()):
            if desc.remote_address in (
                member.remote_address,
                None,
            ):
                del self._systems[sid]
                for w in self._watchers:
                    w(SystemEvent("left", desc))
                break

        # Cancel hysteresis sends
        self._hysteresis.cancel_sends(key)

        # If leader was removed, trigger leader re-evaluation
        cap_addr = self._capabilities.get("Federation Address.IPv4")
        if cap_addr is not None and key == str(ActorAddress(ActorId(SyndicateId(), "__spark_federation__")).actor_id):
            pass  # Leader cleanup is handled in check_federation

    def _cleanup_leader_locked(self) -> None:
        """Remove the current leader from federation addresses."""
        if self._federation_leader_idx < len(self._federation_addresses):
            self._federation_addresses[self._federation_leader_idx] = None
        self._leader_miss_count = 0
        self._setup_federation()

    def _notify_handlers_locked(
        self,
        remote_addr: ActorAddress,
        capabilities: dict,
        *,
        added: bool,
    ) -> None:
        """Send ``SyndicateFederationUpdate`` to all registered handlers."""
        update = SyndicateFederationUpdate(
            remote_admin_address=remote_addr,
            remote_capabilities=capabilities,
            added=added,
        )
        for handler in self._notification_handlers:
            self._send_federation_message(update, handler.actor_id)

    def _update_system_descriptor_locked(
        self,
        member: _FederationMemberData,
    ) -> None:
        """Create a ``SystemDescriptor`` for *member* and notify watchers."""
        from ..core.identity import SyndicateId

        # Use a synthetic SyndicateId for remote systems
        sid = SyndicateId()
        remote_addr = None
        cap = member.remote_capabilities
        addr = cap.get("Federation Address.IPv4")
        if addr is not None:
            remote_addr = tuple(addr)
        desc = SystemDescriptor(
            syndicate_id=sid,
            address=member.remote_address,
            remote_address=remote_addr,
            capabilities=member.remote_capabilities,
        )
        self._systems[sid] = desc
        for w in self._watchers:
            w(SystemEvent("joined", desc))

    # ------------------------------------------------------------------
    # Timer loop
    # ------------------------------------------------------------------

    def _timer_loop(self) -> None:
        while not self._shutdown:
            try:
                self.check_federation()
                self._hysteresis.check_sends()
            except Exception:
                _logger.exception("Error in federation timer loop")

            # Compute sleep time
            delays: list[float] = [
                self._reregistration_period,
            ]
            with self._lock:
                if self._federation_registration_timer.remaining < float("inf"):
                    delays.append(self._federation_registration_timer.remaining)
                for member in self._members.values():
                    delays.append(member.registry_valid.remaining)
                    if member.pre_registered is not None:
                        delays.append(member.pre_registered.ping_valid.remaining)
                delays.append(self._hysteresis.delay)

            sleep_time = max(0.05, min(min(delays), 10.0))
            time.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _federation_envelope(
    msg: FederationMessage,
    sender: ActorId,
    target: ActorId,
) -> Envelope:
    """Build an envelope for a federation protocol message."""
    return Envelope(target=target, sender=sender, payload=msg)
