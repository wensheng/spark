"""Membership provider services."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..actor.address import ActorAddress
from ..core.identity import FrozenHeaders, SyndicateId

SystemEventKind = Literal["joined", "left", "updated"]


@dataclass(frozen=True, slots=True)
class SystemDescriptor:
    """Read-only description of one actor system."""

    syndicate_id: SyndicateId
    address: ActorAddress | None = None
    remote_address: tuple[str, int] | None = None
    federation_address: ActorAddress | None = None
    endpoints: Mapping[str, str] = field(default_factory=FrozenHeaders)
    auth_identity: str | None = None
    health: str = "healthy"
    lease_expires_at: float | None = None
    capabilities: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoints", FrozenHeaders(self.endpoints))
        object.__setattr__(self, "capabilities", FrozenHeaders(self.capabilities))
        object.__setattr__(self, "tags", frozenset(self.tags))

    @property
    def expired(self) -> bool:
        """Return whether this descriptor's lease has expired."""
        return self.lease_expires_at is not None and self.lease_expires_at <= time.time()

    def with_lease(self, lease_seconds: float | None) -> SystemDescriptor:
        """Return a descriptor with a refreshed lease."""
        return SystemDescriptor(
            syndicate_id=self.syndicate_id,
            address=self.address,
            remote_address=self.remote_address,
            federation_address=self.federation_address,
            endpoints=self.endpoints,
            auth_identity=self.auth_identity,
            health=self.health,
            lease_expires_at=None if lease_seconds is None else time.time() + max(0.0, lease_seconds),
            capabilities=self.capabilities,
            tags=self.tags,
        )

    def with_health(self, health: str, lease_seconds: float | None = None) -> SystemDescriptor:
        """Return a descriptor with updated health and optional lease."""
        return SystemDescriptor(
            syndicate_id=self.syndicate_id,
            address=self.address,
            remote_address=self.remote_address,
            federation_address=self.federation_address,
            endpoints=self.endpoints,
            auth_identity=self.auth_identity,
            health=health,
            lease_expires_at=self.lease_expires_at if lease_seconds is None else time.time() + max(0.0, lease_seconds),
            capabilities=self.capabilities,
            tags=self.tags,
        )


@dataclass(frozen=True, slots=True)
class SystemEvent:
    """Membership event for one actor system."""

    kind: SystemEventKind
    descriptor: SystemDescriptor


class MembershipProvider(Protocol):
    """Provides a view of known actor systems."""

    def list_systems(self) -> list[SystemDescriptor]:
        """Return known actor systems."""
        ...

    def watch(self, callback: Callable[[SystemEvent], None]) -> Callable[[], None]:
        """Watch membership events and return an unsubscribe callback."""
        ...


class StaticMembershipProvider:
    """In-memory membership provider for configured systems."""

    def __init__(self, systems: Iterable[SystemDescriptor] = ()) -> None:
        self._systems: dict[SyndicateId, SystemDescriptor] = {system.syndicate_id: system for system in systems}
        self._watchers: list[Callable[[SystemEvent], None]] = []
        self._lock = threading.RLock()

    def list_systems(self) -> list[SystemDescriptor]:
        """Return a stable list of known systems."""
        with self._lock:
            return list(self._systems.values())

    def get_system(self, syndicate_id: SyndicateId) -> SystemDescriptor | None:
        """Return one system descriptor by id."""
        with self._lock:
            return self._systems.get(syndicate_id)

    def watch(self, callback: Callable[[SystemEvent], None]) -> Callable[[], None]:
        """Register a watcher and replay current systems as joined events."""
        with self._lock:
            self._watchers.append(callback)
            systems = list(self._systems.values())
        for system in systems:
            callback(SystemEvent("joined", system))

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._watchers:
                    self._watchers.remove(callback)

        return unsubscribe

    def add_system(self, descriptor: SystemDescriptor) -> None:
        """Add or update a system descriptor."""
        with self._lock:
            kind: SystemEventKind = "updated" if descriptor.syndicate_id in self._systems else "joined"
            self._systems[descriptor.syndicate_id] = descriptor
            watchers = tuple(self._watchers)
        self._notify(watchers, SystemEvent(kind, descriptor))

    def remove_system(self, syndicate_id: SyndicateId) -> SystemDescriptor | None:
        """Remove a system descriptor."""
        with self._lock:
            descriptor = self._systems.pop(syndicate_id, None)
            watchers = tuple(self._watchers)
        if descriptor is not None:
            self._notify(watchers, SystemEvent("left", descriptor))
        return descriptor

    def prune_expired(self, now: float | None = None) -> list[SystemDescriptor]:
        """Remove expired leased systems and return removed descriptors."""
        timestamp = time.time() if now is None else now
        with self._lock:
            expired = [
                descriptor
                for descriptor in self._systems.values()
                if descriptor.lease_expires_at is not None and descriptor.lease_expires_at <= timestamp
            ]
            for descriptor in expired:
                self._systems.pop(descriptor.syndicate_id, None)
            watchers = tuple(self._watchers)
        for descriptor in expired:
            self._notify(watchers, SystemEvent("left", descriptor))
        return expired

    def _notify(self, watchers: tuple[Callable[[SystemEvent], None], ...], event: SystemEvent) -> None:
        for watcher in watchers:
            watcher(event)
