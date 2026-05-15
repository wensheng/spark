"""Local actor name registry service."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Protocol

from ..actor.address import ActorAddress


class NameRegistry(Protocol):
    """Maps stable local names to actor addresses."""

    def register(self, name: str, address: ActorAddress) -> None:
        """Register or replace a name."""
        ...

    def resolve(self, name: str) -> ActorAddress | None:
        """Resolve a name to an actor address."""
        ...


class LocalNameRegistry:
    """Thread-safe in-memory name registry."""

    def __init__(self) -> None:
        self._addresses: dict[str, ActorAddress] = {}
        self._lock = threading.RLock()

    def register(self, name: str, address: ActorAddress) -> None:
        """Register or replace a local name."""
        normalized = self._normalize(name)
        with self._lock:
            self._addresses[normalized] = address

    def resolve(self, name: str) -> ActorAddress | None:
        """Resolve a local name, returning None when absent."""
        normalized = self._normalize(name)
        with self._lock:
            return self._addresses.get(normalized)

    def unregister(self, name: str) -> ActorAddress | None:
        """Remove and return a local name mapping, if present."""
        normalized = self._normalize(name)
        with self._lock:
            return self._addresses.pop(normalized, None)

    def snapshot(self) -> Mapping[str, ActorAddress]:
        """Return a stable snapshot of all name mappings."""
        with self._lock:
            return dict(self._addresses)

    def _normalize(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("actor name must not be empty")
        return normalized
