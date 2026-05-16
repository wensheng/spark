"""Actor creation specification."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .mailbox_policy import MailboxPolicy
from .supervision import SupervisorStrategy

ActorExecution = Literal["inprocess", "thread", "process", "system"]


@dataclass(frozen=True, slots=True)
class ActorSpec:
    """Describes an actor the runtime should create."""

    actor_class: type[Any]
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    requirements: Mapping[str, Any] = field(default_factory=dict)
    execution: ActorExecution = "inprocess"
    stateless: bool = False
    supervisor_strategy: SupervisorStrategy = field(default_factory=SupervisorStrategy.stop)
    mailbox_policy: MailboxPolicy = field(default_factory=MailboxPolicy.unbounded)
