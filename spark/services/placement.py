"""Actor placement strategies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from ..core.actor_spec import ActorSpec
from ..core.identity import SyndicateId
from .membership import SystemDescriptor


class PlacementError(ValueError):
    """Raised when no system can satisfy a placement request."""


class PlacementStrategy(Protocol):
    """Chooses a system for an actor specification."""

    def choose(self, spec: ActorSpec, candidates: Sequence[SystemDescriptor]) -> SystemDescriptor:
        """Choose a candidate system for the actor spec."""
        ...


class LocalFirstPlacementStrategy:
    """Choose the local system when it satisfies the actor requirements."""

    def __init__(self, local_syndicate_id: SyndicateId) -> None:
        self.local_syndicate_id = local_syndicate_id

    def choose(self, spec: ActorSpec, candidates: Sequence[SystemDescriptor]) -> SystemDescriptor:
        """Choose local first, then the first matching remote candidate."""
        matching = [candidate for candidate in candidates if self._matches(spec.requirements, candidate)]
        if not matching:
            raise PlacementError("no actor system satisfies placement requirements")
        for candidate in matching:
            if candidate.syndicate_id == self.local_syndicate_id:
                return candidate
        return matching[0]

    def _matches(self, requirements: Mapping[str, Any], candidate: SystemDescriptor) -> bool:
        return all(candidate.capabilities.get(key) == value for key, value in dict(requirements).items())
