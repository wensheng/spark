"""Diagnostics snapshot service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ..actor.address import ActorAddress
from ..core.identity import SyndicateId
from ..core.messages import DeadLetter
from ..runtime.diagnostics import RuntimeDiagnostics


class DiagnosableBackend(Protocol):
    def diagnostics(self) -> RuntimeDiagnostics:
        """Return backend diagnostics."""
        ...


class DiagnosableActorSystem(Protocol):
    """ActorSystem surface needed by diagnostics."""

    syndicate_id: SyndicateId
    address: ActorAddress
    backend: DiagnosableBackend

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        """Return runtime dead letters."""
        ...

    @property
    def remote_address(self) -> tuple[str, int] | None:
        """Return the remote transport address, if present."""
        ...

    @property
    def transport_health(self) -> Mapping[str, Mapping[str, object]]:
        """Return remote transport route health."""
        ...


@dataclass(frozen=True, slots=True)
class SystemDiagnosticsSnapshot:
    """Read-only actor-system diagnostics snapshot."""

    syndicate_id: SyndicateId
    address: ActorAddress
    remote_address: tuple[str, int] | None
    runtime: RuntimeDiagnostics
    dead_letters: tuple[DeadLetter, ...]
    transport_health: Mapping[str, Mapping[str, object]]


class DiagnosticsService:
    """Builds actor-system diagnostics snapshots."""

    def snapshot(self, system: DiagnosableActorSystem) -> SystemDiagnosticsSnapshot:
        """Return a read-only snapshot of one actor system."""
        return SystemDiagnosticsSnapshot(
            syndicate_id=system.syndicate_id,
            address=system.address,
            remote_address=system.remote_address,
            runtime=system.backend.diagnostics(),
            dead_letters=system.dead_letters,
            transport_health=system.transport_health,
        )
