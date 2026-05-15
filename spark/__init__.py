"""Spark - A modern actor framework for concurrent and distributed applications.

Spark provides a clean, intuitive implementation of the actor model with:
- Simple yet powerful actor API
- Unified runtime kernel supporting multiple execution backends
- Optional services for distributed systems
- Modern Python features and type safety
- Excellent performance and observability
"""

__version__ = "0.1.0"
__author__ = "Wensheng Wang"
__email__ = "wenshengwang@gmail.com"

from spark.node.base import Node

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
from .core.message import Message
from .core.messages import (
    ActorExitRequest,
    ActorStatus,
    ChildActorExited,
    CommonStatusFields,
    FederationAttendee,
    LoadedSourceInfo,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
    WakeupMessage,
    WatchMessage,
)
from .core.status import format_status
from .graph import Graph
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
from .services import (
    ArtifactRef,
    DiagnosticsService,
    LocalFirstPlacementStrategy,
    LocalNameRegistry,
    PackageArtifactProvider,
    StaticMembershipProvider,
    SystemDescriptor,
)
from .system import Syndicate, get_existing_global_syndicate, get_global_syndicate, shutdown_global_syndicate

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
    "SparkException",
    "ActorNotFound",
    "ActorAlreadyExists",
    "ActorNotStartedError",
    "ActorAlreadyStartedError",
    "ActorTimeout",
    "MessageDeliveryError",
    "ActorStatus",
    "ChildActorExited",
    "ActorExitRequest",
    "CommonStatusFields",
    "FederationAttendee",
    "LoadedSourceInfo",
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
    "format_status",
    "get_existing_global_syndicate",
    "get_global_syndicate",
    "shutdown_global_syndicate",
    "ArtifactRef",
    "DiagnosticsService",
    "LocalFirstPlacementStrategy",
    "LocalNameRegistry",
    "PackageArtifactProvider",
    "StaticMembershipProvider",
    "SystemDescriptor",
    "Node",
    "Graph",
]
