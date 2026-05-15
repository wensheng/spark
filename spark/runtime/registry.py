"""Actor registry for the in-process kernel."""

from dataclasses import dataclass, field

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.exceptions import ActorAlreadyExists, ActorNotFound
from ..core.identity import ActorId, ActorIncarnation


@dataclass(slots=True)
class ActorRecord:
    """Runtime state tracked for one actor."""

    actor: Actor
    address: ActorAddress
    incarnation: ActorIncarnation
    parent_id: ActorId | None = None
    children: set[ActorId] = field(default_factory=set)


class ActorRegistry:
    """Maps actor ids to running actor records."""

    def __init__(self) -> None:
        self._records: dict[ActorId, ActorRecord] = {}

    def register(self, actor_id: ActorId, record: ActorRecord) -> None:
        """Register an actor record."""
        if actor_id in self._records:
            raise ActorAlreadyExists(actor_id)
        self._records[actor_id] = record
        if record.parent_id is not None and record.parent_id in self._records:
            self._records[record.parent_id].children.add(actor_id)

    def get(self, actor_id: ActorId) -> ActorRecord:
        """Return the actor record for actor_id."""
        try:
            return self._records[actor_id]
        except KeyError as exc:
            raise ActorNotFound(actor_id) from exc

    def exists(self, actor_id: ActorId) -> bool:
        """Return whether actor_id is registered."""
        return actor_id in self._records

    def remove(self, actor_id: ActorId) -> ActorRecord:
        """Remove and return an actor record."""
        record = self.get(actor_id)
        if record.parent_id is not None and record.parent_id in self._records:
            self._records[record.parent_id].children.discard(actor_id)
        del self._records[actor_id]
        return record

    def children_of(self, parent_id: ActorId) -> list[ActorId]:
        """Return a stable snapshot of child ids for parent_id."""
        return list(self.get(parent_id).children)

    def parent_of(self, actor_id: ActorId) -> ActorId | None:
        """Return the parent id for actor_id."""
        return self.get(actor_id).parent_id

    def all_ids(self) -> list[ActorId]:
        """Return a stable snapshot of all registered actor ids."""
        return list(self._records)

    def __len__(self) -> int:
        return len(self._records)
