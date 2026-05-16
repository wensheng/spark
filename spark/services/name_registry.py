"""Local actor name registry service."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Literal, Protocol

from ..actor.address import ActorAddress

NameScope = Literal["local", "federation", "tenant"]


class NameRegistry(Protocol):
    """Maps stable local names to actor addresses."""

    def register(self, name: str, address: ActorAddress, *, scope: NameScope = "local") -> None:
        """Register or replace a name."""
        ...

    def resolve(self, name: str, *, scope: NameScope = "local") -> ActorAddress | None:
        """Resolve a name to an actor address."""
        ...


class LocalNameRegistry:
    """Thread-safe in-memory name registry."""

    def __init__(self) -> None:
        self._addresses: dict[tuple[NameScope, str], ActorAddress] = {}
        self._lock = threading.RLock()

    def register(self, name: str, address: ActorAddress, *, scope: NameScope = "local") -> None:
        """Register or replace a local name."""
        normalized = (self._normalize_scope(scope), self._normalize(name))
        with self._lock:
            self._addresses[normalized] = address

    def resolve(self, name: str, *, scope: NameScope = "local") -> ActorAddress | None:
        """Resolve a local name, returning None when absent."""
        normalized = (self._normalize_scope(scope), self._normalize(name))
        with self._lock:
            return self._addresses.get(normalized)

    def unregister(self, name: str, *, scope: NameScope = "local") -> ActorAddress | None:
        """Remove and return a local name mapping, if present."""
        normalized = (self._normalize_scope(scope), self._normalize(name))
        with self._lock:
            return self._addresses.pop(normalized, None)

    def snapshot(self, *, scope: NameScope | None = "local") -> Mapping[str, ActorAddress]:
        """Return a stable snapshot of all name mappings."""
        with self._lock:
            if scope is None:
                return {f"{entry_scope}:{name}": address for (entry_scope, name), address in self._addresses.items()}
            normalized_scope = self._normalize_scope(scope)
            return {
                name: address
                for (entry_scope, name), address in self._addresses.items()
                if entry_scope == normalized_scope
            }

    def _normalize(self, name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise ValueError("actor name must not be empty")
        return normalized

    def _normalize_scope(self, scope: NameScope) -> NameScope:
        if scope not in {"local", "federation", "tenant"}:
            raise ValueError("name scope must be local, federation, or tenant")
        return scope
