"""Optional services for Spark actor framework."""

from .artifact import (
    ArtifactError,
    ArtifactProvider,
    ArtifactRef,
    ArtifactVerificationError,
    PackageArtifactProvider,
    SignatureVerifier,
)
from .diagnostics import DiagnosticsService, SystemDiagnosticsSnapshot
from .federation import (
    FederationAck,
    FederationAuthError,
    FederationError,
    FederationHeartbeat,
    FederationJoinAccepted,
    FederationJoinRejected,
    FederationJoinRequest,
    FederationLeave,
    FederationManager,
    RemoteActorSpec,
    RemoteSpawnAccepted,
    RemoteSpawnError,
    RemoteSpawnRejected,
    RemoteSpawnRequest,
)
from .membership import MembershipProvider, StaticMembershipProvider, SystemDescriptor, SystemEvent
from .name_registry import LocalNameRegistry, NameRegistry, NameScope
from .placement import LocalFirstPlacementStrategy, PlacementError, PlacementStrategy

__all__ = [
    "ArtifactError",
    "ArtifactProvider",
    "ArtifactRef",
    "ArtifactVerificationError",
    "DiagnosticsService",
    "FederationAck",
    "FederationAuthError",
    "FederationError",
    "FederationHeartbeat",
    "FederationJoinAccepted",
    "FederationJoinRejected",
    "FederationJoinRequest",
    "FederationLeave",
    "FederationManager",
    "LocalFirstPlacementStrategy",
    "LocalNameRegistry",
    "MembershipProvider",
    "NameRegistry",
    "NameScope",
    "PackageArtifactProvider",
    "PlacementError",
    "PlacementStrategy",
    "RemoteActorSpec",
    "RemoteSpawnAccepted",
    "RemoteSpawnError",
    "RemoteSpawnRejected",
    "RemoteSpawnRequest",
    "SignatureVerifier",
    "StaticMembershipProvider",
    "SystemDescriptor",
    "SystemDiagnosticsSnapshot",
    "SystemEvent",
]
