"""In-process backend facade."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.actor_spec import ActorSpec
from ..core.identity import Envelope
from ..core.messages import DeadLetter
from ..runtime.diagnostics import RuntimeDiagnostics
from ..runtime.external import ExternalInbox
from ..runtime.kernel import Kernel
from ..runtime.results import DeliveryResult


@dataclass(slots=True)
class InProcessBackend:
    """Marker facade for the deterministic in-process kernel backend."""

    kernel: Kernel
    inbox: ExternalInbox

    @property
    def address(self) -> ActorAddress:
        """Return the external system inbox address."""
        return self.inbox.address

    def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a top-level actor."""
        address = self.kernel.create_actor(actor_class, *args, **kwargs)
        self.kernel.run_until_idle()
        return address

    def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        """Create a top-level actor from an actor specification."""
        address = self.kernel.create_actor_from_spec(spec)
        self.kernel.run_until_idle()
        return address

    def start_actor(self, actor: Actor) -> ActorAddress:
        """Start an existing top-level actor."""
        address = self.kernel.start_actor(actor)
        self.kernel.run_until_idle()
        return address

    def tell(self, message: Any, target: ActorAddress) -> None:
        """Send a message and drain runnable work."""
        self.kernel.tell(target, message, sender=self.inbox.actor_id)
        self.kernel.run_until_idle()

    def deliver_envelope(self, envelope: Envelope) -> DeliveryResult:
        """Deliver an already-formed envelope."""
        return self.kernel.deliver(envelope)

    def set_remote_sender(self, sender: Callable[[Envelope], DeliveryResult] | None) -> None:
        """Install or clear the system-level remote sender."""
        self.kernel.remote_sender = sender

    def set_drain_logger(self, logger: logging.Logger | None) -> None:
        """Install or clear the drain logger on the system's external inbox."""
        self.inbox._drain_logger = logger

    def ask(self, message: Any, target: ActorAddress, timeout: float | None = 5.0) -> Any:
        """Ask an actor for a reply."""
        return self.kernel.ask(target, message, timeout=timeout)

    def listen(self, timeout: float | None = None) -> Any:
        """Return the next external inbox message, if any."""
        return self.kernel.listen(self.inbox, timeout=timeout)

    def run_until_idle(self) -> None:
        """Drain immediately runnable work."""
        self.kernel.run_until_idle()

    def stop(self, target: ActorAddress) -> None:
        """Stop an actor."""
        self.kernel.stop_actor(target.actor_id)
        self.kernel.run_until_idle()

    def shutdown(self) -> None:
        """Shut down the backend."""
        self.kernel.shutdown()

    def diagnostics(self) -> RuntimeDiagnostics:
        """Return a read-only diagnostics snapshot."""
        return self.kernel.diagnostics("inprocess")

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        """Return recorded dead letters."""
        return self.kernel.dead_letters.letters
