"""Unified user-level message type for actors, nodes, and graph systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..actor.address import ActorAddress


@dataclass(slots=True)
class Message:
    """Unified message passed to ``Actor.process``.

    Carried as the payload of an ``Envelope`` on the wire. The runtime sets
    ``sender`` immediately before dispatch; user code reads it but should
    not mutate it.
    """

    content: Any = None
    sender: ActorAddress | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    state: dict[str, Any] | None = None
