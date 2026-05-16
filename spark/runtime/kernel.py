"""Single-threaded in-process actor kernel."""

from __future__ import annotations

import selectors
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic, sleep
from time import time as wall_time
from typing import Any

from ..actor.address import ActorAddress
from ..actor.base import Actor, _disable_actor_auto_start
from ..core.actor_spec import ActorSpec
from ..core.exceptions import ActorNotFound, ActorTimeout, InvalidActorSpecError
from ..core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from ..core.messages import ActorExitRequest, ChildActorExited, StatusRequest, WakeupMessage
from .actor_context import RuntimeActorContext
from .dead_letters import DeadLetterHandler
from .diagnostics import ActorDiagnostics, RuntimeDiagnostics
from .external import ExternalInbox, ExternalInboxRegistry
from .mailbox import Mailbox
from .registry import ActorRecord, ActorRegistry
from .results import DeliveryResult
from .scheduler import Scheduler


@dataclass(frozen=True, slots=True)
class KernelConfig:
    """Configuration for a Kernel instance."""

    syndicate_id: SyndicateId


@dataclass(slots=True)
class _ActorWatch:
    """Per-actor fd watch state."""

    read: set[int] = field(default_factory=set)
    write: set[int] = field(default_factory=set)


class Kernel:
    """Deterministic, single-threaded actor runtime."""

    def __init__(self, config: KernelConfig) -> None:
        self.config = config
        self.registry = ActorRegistry()
        self.dead_letters = DeadLetterHandler()
        self.external_inboxes = ExternalInboxRegistry(config.syndicate_id)
        self._mailboxes: dict[ActorId, Mailbox] = {}
        self._scheduler = Scheduler()
        self._active_actor: ActorId | None = None
        self._shutdown = False
        self.remote_sender: Callable[[Envelope], DeliveryResult] | None = None
        self.federation_handler: Callable[[Envelope], None] | None = None
        self._federation_actor_id: ActorId | None = None
        self._federation_provider: Any = None
        self._start_time: float = wall_time()
        self._messages_sent: int = 0
        self._send_failures: int = 0
        self._messages_received: int = 0
        self._watches: dict[ActorId, _ActorWatch] = {}
        self._fd_owner: dict[int, ActorId] = {}
        self._watch_selector: selectors.DefaultSelector | None = None

    @property
    def syndicate_id(self) -> SyndicateId:
        """Return this kernel's actor-system id."""
        return self.config.syndicate_id

    def create_actor(
        self,
        actor_class: type[Actor],
        *args: Any,
        parent_id: ActorId | None = None,
        **kwargs: Any,
    ) -> ActorAddress:
        """Create an actor from a class and constructor arguments."""
        return self.create_actor_from_spec(
            ActorSpec(actor_class=actor_class, args=args, kwargs=kwargs),
            parent_id=parent_id,
        )

    def create_actor_from_spec(self, spec: ActorSpec, parent_id: ActorId | None = None) -> ActorAddress:
        """Create an actor from an ActorSpec."""
        actor_type = self._validate_actor_spec(spec)
        with _disable_actor_auto_start():
            actor = actor_type(*spec.args, **dict(spec.kwargs))
        return self.start_actor(actor, parent_id=parent_id)

    def start_actor(self, actor: Actor, parent_id: ActorId | None = None) -> ActorAddress:
        """Start an existing actor instance."""
        if not isinstance(actor, Actor):
            raise InvalidActorSpecError(f"actor must be an Actor instance, got {actor!r}")
        actor_id = ActorId(syndicate_id=self.syndicate_id)
        address = ActorAddress(actor_id)
        parent_address = ActorAddress(parent_id) if parent_id is not None else None
        mailbox = Mailbox(actor_id)
        context = RuntimeActorContext(
            kernel=self,
            actor_id=actor_id,
            address=address,
            syndicate_address=ActorAddress(ActorId(syndicate_id=self.syndicate_id)),
            parent=parent_address,
        )

        actor._bind_context(context)
        self._mailboxes[actor_id] = mailbox
        self.registry.register(
            actor_id,
            ActorRecord(
                actor=actor,
                address=address,
                incarnation=ActorIncarnation(actor_id),
                parent_id=parent_id,
            ),
        )

        try:
            actor.pre_start()
        except Exception:
            self.stop_actor(actor_id, reason="pre_start failed", notify_parent=False)
            raise

        return address

    def tell(self, target: ActorAddress, message: Any, sender: ActorId | None = None) -> DeliveryResult:
        """Enqueue a message for target."""
        envelope = Envelope(target=target.actor_id, payload=message, sender=sender)
        self._messages_sent += 1
        result = self.deliver(envelope)
        if not result.success:
            self._send_failures += 1
        return result

    def ask(self, target: ActorAddress, message: Any, timeout: float | None = None) -> Any:
        """Ask target for a reply using a temporary external inbox."""
        ask_timeout = 5.0 if timeout is None else timeout
        inbox = self.external_inboxes.create()
        try:
            self.deliver(
                Envelope(
                    target=target.actor_id,
                    payload=message,
                    sender=inbox.actor_id,
                )
            )
            if not self.run_until(inbox.has_pending, ask_timeout):
                raise ActorTimeout("ask", ask_timeout)
            reply = inbox.dequeue()
            if reply is None:
                raise ActorTimeout("ask", ask_timeout)
            return reply.payload
        finally:
            self.external_inboxes.remove(inbox.actor_id)

    def listen(self, inbox: ExternalInbox, timeout: float | None = None) -> Any:
        """Return the next message from an external inbox, if available."""
        if not inbox.has_pending():
            self.run_until(inbox.has_pending, timeout)
        envelope = inbox.dequeue()
        return None if envelope is None else envelope.payload

    def deliver(self, envelope: Envelope) -> DeliveryResult:
        """Deliver an envelope to an actor mailbox or external inbox."""
        # Federation routing — intercept before SyndicateId / mailbox checks
        if (
            self._federation_actor_id is not None
            and envelope.target == self._federation_actor_id
            and self.federation_handler is not None
        ):
            self.federation_handler(envelope)
            return DeliveryResult(success=True)

        if envelope.target.syndicate_id != self.syndicate_id:
            if self.remote_sender is None:
                self.dead_letters.handle(envelope, "remote route not found")
                return DeliveryResult(success=False, reason="remote route not found")
            result = self.remote_sender(envelope)
            if not result.success:
                self.dead_letters.handle(envelope, result.reason or "remote delivery failed")
            return result

        if envelope.is_expired:
            self.dead_letters.handle(envelope, "message expired")
            return DeliveryResult(success=False, reason="message expired")

        external = self.external_inboxes.get(envelope.target)
        if external is not None:
            # Auto-respond to StatusRequest with SystemStatus
            if isinstance(envelope.payload, StatusRequest):
                self._messages_received += 1
                self._handle_status_request(envelope.sender)
                return DeliveryResult(success=True)
            external.enqueue(envelope)
            return DeliveryResult(success=True)

        mailbox = self._mailboxes.get(envelope.target)
        if mailbox is None or not self.registry.exists(envelope.target):
            self.dead_letters.handle(envelope, "target not found")
            return DeliveryResult(success=False, reason="target not found")

        mailbox.enqueue(envelope)
        return DeliveryResult(success=True)

    def wakeup_after(self, actor_id: ActorId, delay: float, payload: Any = None) -> None:
        """Schedule a wakeup message for actor_id."""
        wakeup = WakeupMessage(delay=delay, payload=payload)
        self._scheduler.schedule(delay, Envelope(target=actor_id, payload=wakeup))

    def set_watch(
        self,
        actor_id: ActorId,
        *,
        read: tuple[int, ...] = (),
        write: tuple[int, ...] = (),
    ) -> None:
        """Replace ``actor_id``'s fd watch list.

        Atomic: validates ownership and fd validity first; on failure
        the prior watch list is unchanged. Each call replaces the
        previous registration entirely.
        """
        new_read = set(read)
        new_write = set(write)
        all_new = new_read | new_write

        prior = self._watches.get(actor_id)
        prior_owned = (prior.read | prior.write) if prior is not None else set()

        # Conflict check: any fd we're about to claim that's owned by
        # someone else?
        for fd in all_new:
            owner = self._fd_owner.get(fd)
            if owner is not None and owner != actor_id:
                raise ValueError(f"fd {fd} already watched by actor {owner}")

        # Empty target — clear and return early.
        if not all_new:
            self._clear_watch(actor_id)
            return

        # Build the new selector state in a sandbox first, so a bad fd
        # doesn't leave us partially registered.
        sel = self._watch_selector or selectors.DefaultSelector()
        # Unregister fds the actor previously owned that are not in the
        # new set.
        to_unregister = prior_owned - all_new
        # Compute the desired event mask per fd in the new set.
        desired: dict[int, int] = {}
        for fd in new_read:
            desired[fd] = desired.get(fd, 0) | selectors.EVENT_READ
        for fd in new_write:
            desired[fd] = desired.get(fd, 0) | selectors.EVENT_WRITE

        # Track changes for rollback.
        registered_now: list[int] = []
        modified_now: list[tuple[int, int]] = []  # (fd, old_events)
        try:
            for fd in to_unregister:
                if self._fd_selector_has(sel, fd):
                    sel.unregister(fd)
            for fd, events in desired.items():
                if self._fd_selector_has(sel, fd):
                    key = sel.get_key(fd)
                    if key.events != events:
                        modified_now.append((fd, key.events))
                        sel.modify(fd, events, data=actor_id)
                else:
                    sel.register(fd, events, data=actor_id)
                    registered_now.append(fd)
        except Exception:
            # Roll back: unregister anything we registered, restore
            # modifications, re-register removals.
            for fd in registered_now:
                try:
                    sel.unregister(fd)
                except Exception:
                    pass
            for fd, old_events in modified_now:
                try:
                    sel.modify(fd, old_events, data=actor_id)
                except Exception:
                    pass
            for fd in to_unregister:
                # Re-register what we removed using the prior masks.
                events = 0
                if prior is not None and fd in prior.read:
                    events |= selectors.EVENT_READ
                if prior is not None and fd in prior.write:
                    events |= selectors.EVENT_WRITE
                if events:
                    try:
                        sel.register(fd, events, data=actor_id)
                    except Exception:
                        pass
            raise

        # Commit.
        self._watch_selector = sel
        self._watches[actor_id] = _ActorWatch(read=new_read, write=new_write)
        # Update ownership map: drop fds we released, add fds we own.
        for fd in to_unregister:
            self._fd_owner.pop(fd, None)
        for fd in all_new:
            self._fd_owner[fd] = actor_id

    @staticmethod
    def _fd_selector_has(sel: selectors.BaseSelector, fd: int) -> bool:
        try:
            sel.get_key(fd)
            return True
        except KeyError:
            return False

    def _clear_watch(self, actor_id: ActorId) -> None:
        """Unregister all fds for ``actor_id`` and drop its watch entry."""
        watch = self._watches.pop(actor_id, None)
        if watch is None:
            return
        owned = watch.read | watch.write
        if self._watch_selector is not None:
            for fd in owned:
                try:
                    self._watch_selector.unregister(fd)
                except (KeyError, ValueError, OSError):
                    pass
            if not self._watch_selector.get_map():
                self._watch_selector.close()
                self._watch_selector = None
        for fd in owned:
            self._fd_owner.pop(fd, None)

    def stop_actor(
        self,
        actor_id: ActorId,
        reason: str = "actor stopped",
        exit_code: int = 0,
        notify_parent: bool = True,
    ) -> None:
        """Stop actor_id and its children."""
        if not self.registry.exists(actor_id):
            return

        for child_id in self.registry.children_of(actor_id):
            self.stop_actor(child_id, reason="parent stopped", notify_parent=False)

        record = self.registry.get(actor_id)
        try:
            record.actor.post_stop()
        finally:
            self._clear_watch(actor_id)
            self.registry.remove(actor_id)
            self._mailboxes.pop(actor_id, None)

        if notify_parent and record.parent_id is not None:
            self._notify_child_exited(record, reason, exit_code)

    def run_until_idle(self) -> None:
        """Process due wakeups and queued actor messages until no work is runnable."""
        while self._deliver_due_wakeups() or self._process_one_message():
            continue

    def run_until(self, predicate: Callable[[], bool], timeout: float | None = None) -> bool:
        """Run until predicate is true, timeout expires, or no progress is possible."""
        deadline = monotonic() + timeout if timeout is not None else None
        while not predicate():
            made_progress = self._deliver_due_wakeups() or self._process_one_message()
            if predicate():
                return True

            if not made_progress:
                next_due_at = self._scheduler.next_due_at()
                now = monotonic()
                if deadline is not None and now >= deadline:
                    return False
                if next_due_at is None:
                    if deadline is None and self._watch_selector is None:
                        return False
                    wait_budget = max(0.0, deadline - now) if deadline is not None else 0.05
                else:
                    wait_budget = max(0.0, next_due_at - now)
                    if deadline is not None:
                        wait_budget = min(wait_budget, max(0.0, deadline - now))
                self._wait_for_io_or_timeout(min(0.05, wait_budget))
        return True

    def _wait_for_io_or_timeout(self, timeout: float) -> None:
        """Either sleep or run the watch selector for ``timeout`` seconds.

        When watched fds become ready, deliver a WatchMessage per
        affected actor. Bad fds are unregistered and surfaced via
        WatchMessage.failed.
        """
        sel = self._watch_selector
        if sel is None or not sel.get_map():
            sleep(max(0.0, timeout))
            return

        try:
            events = sel.select(max(0.0, timeout))
        except OSError:
            self._dispatch_bad_fds()
            return

        if not events:
            # No events returned — some platforms (e.g. macOS/kqueue) silently
            # drop a closed fd rather than raising OSError, so we probe each
            # registered fd to surface stale entries. On a healthy idle kernel
            # this is one register/select(0)/close per fd per idle cycle (~20
            # cycles/s at the 50ms cap); cheap for small fd counts. A future
            # optimization could throttle the probe by tracking time since
            # last activity.
            self._dispatch_bad_fds()
            return
        self._dispatch_watch_events(events)

    def _dispatch_watch_events(
        self,
        events: list[tuple[selectors.SelectorKey, int]],
    ) -> None:
        from ..core.messages import WatchMessage

        per_actor: dict[ActorId, dict[str, set[int]]] = {}
        for key, mask in events:
            actor_id = key.data
            slot = per_actor.setdefault(actor_id, {"read": set(), "write": set()})
            if mask & selectors.EVENT_READ:
                slot["read"].add(key.fd)
            if mask & selectors.EVENT_WRITE:
                slot["write"].add(key.fd)

        for actor_id, slots in per_actor.items():
            self.deliver(
                Envelope(
                    target=actor_id,
                    payload=WatchMessage(
                        ready_read=tuple(sorted(slots["read"])),
                        ready_write=tuple(sorted(slots["write"])),
                    ),
                )
            )

    def _dispatch_bad_fds(self) -> None:
        """Probe all registered fds, unregister failures, deliver
        WatchMessage(failed=...) per affected actor."""
        from ..core.messages import WatchMessage

        sel = self._watch_selector
        if sel is None:
            return

        bad_per_actor: dict[ActorId, set[int]] = {}
        for fd, key in list(sel.get_map().items()):
            actor_id = key.data
            try:
                probe = selectors.DefaultSelector()
                try:
                    probe.register(fd, selectors.EVENT_READ)
                    probe.select(0)
                finally:
                    probe.close()
            except (OSError, ValueError):
                bad_per_actor.setdefault(actor_id, set()).add(fd)

        for actor_id, bad_fds in bad_per_actor.items():
            # Unregister and update bookkeeping.
            for fd in bad_fds:
                try:
                    sel.unregister(fd)
                except (KeyError, ValueError):
                    pass
                self._fd_owner.pop(fd, None)
            watch = self._watches.get(actor_id)
            if watch is not None:
                watch.read.difference_update(bad_fds)
                watch.write.difference_update(bad_fds)
            self.deliver(
                Envelope(
                    target=actor_id,
                    payload=WatchMessage(failed=tuple(sorted(bad_fds))),
                )
            )

        if not sel.get_map():
            sel.close()
            self._watch_selector = None

    @property
    def uptime_seconds(self) -> float:
        """Return wall-clock seconds since the kernel started."""
        return wall_time() - self._start_time

    def _handle_status_request(self, sender_id: ActorId | None) -> None:
        """Build and send a ``SystemStatus`` in response to a ``StatusRequest``."""
        from ..actor.address import ActorAddress
        from ..core.messages import (
            CommonStatusFields,
            FederationAttendee,
            PendingMessage,
            PendingWakeup,
            SystemStatus,
        )

        # --- Common fields ---
        admin_addr = str(ActorAddress(ActorId(syndicate_id=self.syndicate_id)))

        # Pending messages from all mailboxes
        pending_msgs: list[PendingMessage] = []
        for _aid, mb in list(self._mailboxes.items()):
            for env in mb._queue:
                pending_msgs.append(
                    PendingMessage(
                        from_addr=str(env.sender or ""),
                        to_addr=str(env.target),
                        message=str(env.payload),
                    )
                )

        # Pending wakeups from scheduler
        pending_wakeups: list[PendingWakeup] = []
        for se in self._scheduler.all_scheduled():
            pending_wakeups.append(
                PendingWakeup(
                    target=str(se.envelope.target),
                    delay=max(0.0, se.due_at - monotonic()),
                    payload=str(se.envelope.payload),
                )
            )

        # Child actors — top-level actors (no parent)
        child_actors: list[str] = []
        for aid in self.registry.all_ids():
            record = self.registry.get(aid)
            if record.parent_id is None:
                child_actors.append(str(record.address))

        # Received messages — same as pending for simplicity
        common = CommonStatusFields(
            pending_messages=tuple(pending_msgs),
            pending_wakeups=tuple(pending_wakeups),
            received_messages=(),  # tracked separately if needed
            child_actors=tuple(child_actors),
            governor=None,
            messages_sent=self._messages_sent,
            send_failures=self._send_failures,
            messages_received=self._messages_received,
            misc={},
            pending_addr_counts={},
        )

        # --- Federation fields ---
        federation_leader: str | None = None
        federation_register_time: str | None = None
        federation_attendees: list[FederationAttendee] = []
        notify_addrs: list[str] = []
        capabilities: dict[str, Any] = {}

        if self._federation_provider is not None:
            cp = self._federation_provider
            with cp._lock:
                # Leader address (lowest-index active address)
                if cp._federation_addresses and cp._members:
                    # Leader is the lowest-index federation address that's active
                    for _idx, addr in enumerate(cp._federation_addresses):
                        if addr is not None:
                            federation_leader = f"{addr[0]}:{addr[1]}"
                            break
                # Register time
                if cp._federation_registration_timer.valid():
                    federation_register_time = str(cp._federation_registration_timer._expiration)
                # Attendees
                for key, m in cp._members.items():
                    valid_str = (
                        str(m.registry_valid._expiration)
                        if m.registry_valid is not None and m.registry_valid.valid()
                        else "expired"
                    )
                    federation_attendees.append(FederationAttendee(address=key, valid_until=valid_str))
                # Notification handlers
                for addr in cp._notification_handlers:
                    notify_addrs.append(str(addr))
                # Capabilities
                capabilities = dict(cp._capabilities)

        # --- Dead letters ---
        dead_addrs: list[str] = []
        for dl in self.dead_letters.letters:
            dead_addrs.append(str(dl.original_envelope.target))

        status = SystemStatus(
            syndicate_id=self.syndicate_id,
            admin_address=admin_addr,
            actor_count=len(self.registry),
            uptime_seconds=self.uptime_seconds,
            backend_type="inprocess",
            common=common,
            capabilities=capabilities,
            federation_leader=federation_leader,
            federation_register_time=federation_register_time,
            federation_attendees=tuple(federation_attendees),
            dead_letter_handler=None,
            dead_letter_addresses=tuple(dead_addrs),
            notify_addresses=tuple(notify_addrs),
            global_actors={},
            in_shutdown=self._shutdown,
        )

        if sender_id is not None:
            self.deliver(Envelope(target=sender_id, payload=status, sender=None))

    def _handle_actor_status_request(self, actor_id: ActorId, sender_id: ActorId | None) -> None:
        """Build and send an ``ActorStatus`` for *actor_id*."""
        from ..actor.address import ActorAddress
        from ..core.messages import (
            ActorStatus,
            CommonStatusFields,
            PendingMessage,
            PendingWakeup,
        )

        record = self.registry.get(actor_id)
        actor = record.actor
        admin_addr = str(ActorAddress(ActorId(syndicate_id=self.syndicate_id)))

        # --- Common fields ---
        # Pending messages for this actor only
        pending_msgs: list[PendingMessage] = []
        mailbox = self._mailboxes.get(actor_id)
        if mailbox is not None:
            for env in mailbox._queue:
                pending_msgs.append(
                    PendingMessage(
                        from_addr=str(env.sender or ""),
                        to_addr=str(env.target),
                        message=str(env.payload),
                    )
                )

        # Pending wakeups for this actor
        pending_wakeups: list[PendingWakeup] = []
        for se in self._scheduler.all_scheduled():
            if se.envelope.target == actor_id:
                pending_wakeups.append(
                    PendingWakeup(
                        target=str(se.envelope.target),
                        delay=max(0.0, se.due_at - monotonic()),
                        payload=str(se.envelope.payload),
                    )
                )

        # Child actors
        child_actors = [str(self.registry.get(cid).address) for cid in self.registry.children_of(actor_id)]

        common = CommonStatusFields(
            pending_messages=tuple(pending_msgs),
            pending_wakeups=tuple(pending_wakeups),
            received_messages=(),
            child_actors=tuple(child_actors),
            governor=None,
            messages_sent=self._messages_sent,
            send_failures=self._send_failures,
            messages_received=self._messages_received,
            misc={},
            pending_addr_counts={},
        )

        parent_addr = str(record.parent_id) if record.parent_id else None

        status = ActorStatus(
            actor_address=str(record.address),
            actor_class=actor.__class__.__name__,
            admin_address=admin_addr,
            common=common,
            parent_address=parent_addr,
            exiting=None,
        )

        if sender_id is not None:
            self.deliver(Envelope(target=sender_id, payload=status, sender=None))

    def shutdown(self) -> None:
        """Stop all actors."""
        if self._shutdown:
            return
        self._shutdown = True
        for actor_id in reversed(self.registry.all_ids()):
            self.stop_actor(actor_id, reason="system shutdown", notify_parent=False)

    def diagnostics(self, backend_type: str = "inprocess") -> RuntimeDiagnostics:
        """Return a read-only snapshot of current runtime state."""
        actors = []
        for actor_id in self.registry.all_ids():
            record = self.registry.get(actor_id)
            mailbox = self._mailboxes.get(actor_id)
            actors.append(
                ActorDiagnostics(
                    actor_id=actor_id,
                    parent_id=record.parent_id,
                    child_count=len(record.children),
                    mailbox_depth=None if mailbox is None else mailbox.size(),
                    running=self._active_actor == actor_id,
                    stopped=False,
                    active=record.actor.active,
                )
            )
        return RuntimeDiagnostics(
            syndicate_id=self.syndicate_id,
            backend_type=backend_type,
            actor_count=len(self.registry),
            external_inbox_count=len(self.external_inboxes),
            dead_letter_count=len(self.dead_letters.letters),
            actors=tuple(actors),
        )

    def _deliver_due_wakeups(self) -> bool:
        due = self._scheduler.pop_due()
        for envelope in due:
            self.deliver(envelope)
        return bool(due)

    def _process_one_message(self) -> bool:
        for actor_id, mailbox in list(self._mailboxes.items()):
            if actor_id == self._active_actor or not mailbox.has_pending():
                continue

            envelope = mailbox.dequeue()
            if envelope is None:
                continue
            self._handle_envelope(actor_id, envelope)
            return True
        return False

    def _handle_envelope(self, actor_id: ActorId, envelope: Envelope) -> None:
        if isinstance(envelope.payload, StatusRequest):
            self._messages_received += 1
            self._handle_actor_status_request(actor_id, envelope.sender)
            return

        if envelope.is_expired:
            self.dead_letters.handle(envelope, "message expired")
            return
        try:
            record = self.registry.get(actor_id)
        except ActorNotFound:
            self.dead_letters.handle(envelope, "target not found")
            return

        if isinstance(envelope.payload, ActorExitRequest):
            self.stop_actor(actor_id, reason=envelope.payload.reason)
            return

        previous_active = self._active_actor
        self._active_actor = actor_id
        try:
            record.actor.receive_envelope(envelope)
        except Exception as exc:
            self.dead_letters.handle(envelope, f"handler failed: {exc}")
            self.stop_actor(actor_id, reason="handler failed")
        finally:
            self._active_actor = previous_active

    def _notify_child_exited(self, child_record: ActorRecord, reason: str, exit_code: int) -> None:
        parent_id = child_record.parent_id
        if parent_id is None or not self.registry.exists(parent_id):
            return
        notification = ChildActorExited(
            child_id=child_record.address.actor_id,
            parent_id=parent_id,
            child_incarnation=child_record.incarnation,
            exit_code=exit_code,
            reason=reason,
        )
        self.deliver(
            Envelope(
                target=parent_id,
                payload=notification,
                sender=child_record.address.actor_id,
            )
        )

    def _validate_actor_spec(self, spec: ActorSpec) -> type[Actor]:
        actor_class = spec.actor_class
        if not isinstance(actor_class, type) or not issubclass(actor_class, Actor):
            raise InvalidActorSpecError(f"actor_class must be an Actor subclass, got {actor_class!r}")
        return actor_class
