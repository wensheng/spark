"""Runtime-backed actor context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.identity import ActorId, Envelope

if TYPE_CHECKING:
    from .kernel import Kernel


@dataclass(slots=True)
class RuntimeActorContext:
    """ActorContext implementation backed by a Kernel."""

    kernel: Kernel
    actor_id: ActorId
    address: ActorAddress
    syndicate_address: ActorAddress
    parent: ActorAddress | None = None

    def tell(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Send a message from this actor."""
        if ttl is not None or deadline is not None or headers is not None or trace_id is not None:
            raise RuntimeError("ttl/deadline/trace sends are only supported by the async runtime")
        self.kernel.tell(target, message, sender=self.actor_id)

    async def tell_async(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Send a message from async actor code."""
        self.tell(message, target, ttl=ttl, deadline=deadline, headers=headers, trace_id=trace_id)

    def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        """Ask another actor and wait for its reply."""
        if ttl is not None or deadline is not None:
            raise RuntimeError("ttl/deadline asks are only supported by the async runtime")
        return self.kernel.ask(target, message, timeout=timeout)

    async def ask_async(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        """Ask another actor from async actor code."""
        return self.ask(message, target, timeout=timeout, ttl=ttl, deadline=deadline)

    def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a child actor."""
        return self.kernel.create_actor(
            actor_class,
            *args,
            parent_id=self.actor_id,
            **kwargs,
        )

    def wakeupAfter(
        self,
        timeout: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        """Schedule a wakeup for this actor."""
        if durable or timer_id is not None:
            raise RuntimeError("durable timers are only supported by the async runtime")
        self.kernel.wakeup_after(self.actor_id, timeout, payload)

    def schedule_after(
        self,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        """Schedule a wakeup for this actor."""
        self.wakeupAfter(delay, payload, durable=durable, timer_id=timer_id)

    async def persist_event(self, event: Any) -> None:
        """Persistence is only supported by the async runtime."""
        raise RuntimeError("persistent actors are only supported by the async runtime")

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        """Persistence is only supported by the async runtime."""
        raise RuntimeError("persistent actors are only supported by the async runtime")

    def set_watch(
        self,
        *,
        read: tuple[int, ...] = (),
        write: tuple[int, ...] = (),
    ) -> None:
        """Replace this actor's fd watch list."""
        self.kernel.set_watch(self.actor_id, read=read, write=write)

    async def link(self, target: ActorAddress) -> None:
        """Linking is only supported by the async runtime."""
        raise RuntimeError("link is only supported by the async runtime")

    async def monitor(self, target: ActorAddress) -> None:
        """Monitoring is only supported by the async runtime."""
        raise RuntimeError("monitor is only supported by the async runtime")

    def stop(self) -> None:
        """Stop this actor."""
        self.kernel.stop_actor(self.actor_id)

    # ------------------------------------------------------------------
    # Federation APIs
    # ------------------------------------------------------------------

    def notify_on_system_registration_changes(self, enable: bool = True) -> None:
        """Register or unregister for `SyndicateFederationUpdate` messages."""
        if self.kernel.federation_handler is not None and self.kernel._federation_actor_id is not None:
            from ..core.federation_messages import NotifyOnSystemRegistration

            self.kernel.deliver(
                Envelope(
                    target=self.kernel._federation_actor_id,
                    payload=NotifyOnSystemRegistration(
                        handler_address=self.address,
                        enable_notification=enable,
                    ),
                    sender=self.actor_id,
                )
            )

    def pre_register_remote_system(self, remote_address: ActorAddress, remote_capabilities: dict) -> None:
        """Pre-register a remote system for federation membership."""
        if self.kernel.federation_handler is not None and self.kernel._federation_actor_id is not None:
            from ..core.federation_messages import FederationRegister

            self.kernel.deliver(
                Envelope(
                    target=self.kernel._federation_actor_id,
                    payload=FederationRegister(
                        admin_address=remote_address,
                        capabilities=remote_capabilities,
                        pre_register=True,
                    ),
                    sender=self.actor_id,
                )
            )

    def de_register_remote_system(self, remote_address: ActorAddress) -> None:
        """Remove a pre-registered remote system from federation tracking."""
        if self.kernel.federation_handler is not None and self.kernel._federation_actor_id is not None:
            from ..core.federation_messages import FederationDeRegister

            self.kernel.deliver(
                Envelope(
                    target=self.kernel._federation_actor_id,
                    payload=FederationDeRegister(
                        admin_address=remote_address,
                        pre_registered=True,
                    ),
                    sender=self.actor_id,
                )
            )

    def syndicate_shutdown(self) -> None:
        """Request shutdown of the entire actor system."""
        if self.kernel._federation_actor_id is not None:
            from ..core.messages import SystemShutdown

            self.kernel.deliver(
                Envelope(
                    target=self.kernel._federation_actor_id,
                    payload=SystemShutdown(sender=self.actor_id),
                )
            )
