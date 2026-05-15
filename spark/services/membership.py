"""Membership provider services."""

from __future__ import annotations

import threading
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
    capabilities: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", FrozenHeaders(self.capabilities))
        object.__setattr__(self, "tags", frozenset(self.tags))


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

    def _notify(self, watchers: tuple[Callable[[SystemEvent], None], ...], event: SystemEvent) -> None:
        for watcher in watchers:
            watcher(event)
