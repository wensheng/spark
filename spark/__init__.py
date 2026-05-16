"""Spark - A modern actor framework for concurrent and distributed applications.

Spark provides a clean, intuitive implementation of the actor model with:
- Simple yet powerful actor API
- Unified runtime kernel supporting multiple execution backends
- Optional services for distributed systems
- Modern Python features and type safety
- Excellent performance and observability
"""

__version__ = "0.4.0"
__author__ = "Wensheng Wang"
__email__ = "wenshengwang@gmail.com"

from .actor import Actor, ActorAddress
from .core.actor_spec import ActorExecution, ActorSpec
from .core.exceptions import (
    ActorAlreadyExists,
    ActorAlreadyStartedError,
    ActorNotFound,
    ActorNotStartedError,
    ActorTimeout,
    MessageDeliveryError,
    SparkException,
)
from .core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from .core.mailbox_policy import MailboxOverflow, MailboxPolicy
from .core.message import Message
from .core.messages import (
    ActorExited,
    ActorExitRequest,
    ActorStatus,
    CancellationRequest,
    ChildActorExited,
    ChildActorRestarted,
    CommonStatusFields,
    FederationAttendee,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
    WakeupMessage,
    WatchMessage,
)
from .core.status import format_status
from .core.supervision import SupervisionDecision, SupervisorStrategy
from .node.runcommand import (
    Command,
    CommandAbort,
    CommandError,
    CommandLog,
    CommandOutput,
    CommandResult,
    CommandStarted,
    RunCommand,
)
from .persistence import (
    DurableTimer,
    InMemoryJournal,
    Journal,
    JournalEvent,
    JournalSnapshot,
    PersistentActor,
    SQLiteJournal,
)
from .runtime.events import RuntimeEvent
from .services import (
    ArtifactRef,
    DiagnosticsService,
    FederationAck,
    FederationAuthError,
    FederationError,
    FederationManager,
    LocalFirstPlacementStrategy,
    LocalNameRegistry,
    PackageArtifactProvider,
    RemoteActorSpec,
    RemoteSpawnError,
    StaticMembershipProvider,
    SystemDescriptor,
)
from .system.syndicate import Syndicate, get_existing_global_syndicate, get_global_syndicate, shutdown_global_syndicate

__all__ = [
    "Actor",
    "Syndicate",
    "ActorAddress",
    "ActorId",
    "ActorIncarnation",
    "SyndicateId",
    "Envelope",
    "Message",
    "ActorSpec",
    "ActorExecution",
    "MailboxPolicy",
    "MailboxOverflow",
    "SupervisorStrategy",
    "SupervisionDecision",
    "SparkException",
    "ActorNotFound",
    "ActorAlreadyExists",
    "ActorNotStartedError",
    "ActorAlreadyStartedError",
    "ActorTimeout",
    "MessageDeliveryError",
    "ActorStatus",
    "ActorExited",
    "ChildActorExited",
    "ChildActorRestarted",
    "CancellationRequest",
    "ActorExitRequest",
    "CommonStatusFields",
    "FederationAttendee",
    "PendingMessage",
    "PendingWakeup",
    "StatusRequest",
    "SystemStatus",
    "WakeupMessage",
    "WatchMessage",
    "Command",
    "CommandAbort",
    "CommandError",
    "CommandLog",
    "CommandOutput",
    "CommandResult",
    "CommandStarted",
    "RunCommand",
    "RuntimeEvent",
    "PersistentActor",
    "DurableTimer",
    "InMemoryJournal",
    "Journal",
    "JournalEvent",
    "JournalSnapshot",
    "SQLiteJournal",
    "format_status",
    "get_existing_global_syndicate",
    "get_global_syndicate",
    "shutdown_global_syndicate",
    "ArtifactRef",
    "DiagnosticsService",
    "FederationAck",
    "FederationAuthError",
    "FederationError",
    "FederationManager",
    "LocalFirstPlacementStrategy",
    "LocalNameRegistry",
    "PackageArtifactProvider",
    "RemoteActorSpec",
    "RemoteSpawnError",
    "StaticMembershipProvider",
    "SystemDescriptor",
]
