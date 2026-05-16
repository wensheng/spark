"""Federation service and protocol messages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..actor.address import ActorAddress
from ..core.actor_spec import ActorExecution, ActorSpec
from ..core.identity import FrozenHeaders, SyndicateId
from ..core.mailbox_policy import MailboxPolicy
from ..core.supervision import SupervisorStrategy
from .artifact import ArtifactProvider, ArtifactRef
from .membership import StaticMembershipProvider, SystemDescriptor


class FederationError(ValueError):
    """Raised when a federation operation fails."""


class FederationAuthError(FederationError):
    """Raised when a federation message fails authentication."""


class RemoteSpawnError(FederationError):
    """Raised when a remote actor spawn request fails."""


@dataclass(frozen=True, slots=True)
class RemoteActorSpec:
    """Serializable actor specification for remote spawn requests."""

    artifact: ArtifactRef
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    requirements: Mapping[str, Any] = field(default_factory=FrozenHeaders)
    execution: ActorExecution = "system"
    stateless: bool = False
    supervisor_strategy: SupervisorStrategy = field(default_factory=SupervisorStrategy.stop)
    mailbox_policy: MailboxPolicy = field(default_factory=MailboxPolicy.unbounded)

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "kwargs", FrozenHeaders(self.kwargs))
        object.__setattr__(self, "requirements", FrozenHeaders(self.requirements))

    @classmethod
    def from_actor_spec(cls, spec: ActorSpec, artifact: ArtifactRef | None = None) -> RemoteActorSpec:
        """Build a remote spawn spec from a local ActorSpec."""
        return cls(
            artifact=artifact or ArtifactRef.from_actor_class(spec.actor_class),
            args=tuple(spec.args),
            kwargs=dict(spec.kwargs),
            requirements=dict(spec.requirements),
            execution=spec.execution,
            stateless=spec.stateless,
            supervisor_strategy=spec.supervisor_strategy,
            mailbox_policy=spec.mailbox_policy,
        )

    def to_actor_spec(self, actor_class: type[Any]) -> ActorSpec:
        """Resolve this remote spec into a local ActorSpec."""
        return ActorSpec(
            actor_class=actor_class,
            args=self.args,
            kwargs=dict(self.kwargs),
            requirements=dict(self.requirements),
            execution=self.execution,
            stateless=self.stateless,
            supervisor_strategy=self.supervisor_strategy,
            mailbox_policy=self.mailbox_policy,
        )


@dataclass(frozen=True, slots=True)
class FederationJoinRequest:
    """Request to join a peer's federation membership view."""

    descriptor: SystemDescriptor
    token: str | None = None


@dataclass(frozen=True, slots=True)
class FederationJoinAccepted:
    """Successful federation join response."""

    descriptor: SystemDescriptor
    members: tuple[SystemDescriptor, ...]


@dataclass(frozen=True, slots=True)
class FederationJoinRejected:
    """Rejected federation join response."""

    reason: str


@dataclass(frozen=True, slots=True)
class FederationAck:
    """Successful federation control response."""

    ok: bool = True


@dataclass(frozen=True, slots=True)
class FederationHeartbeat:
    """Lease refresh and health update from one member."""

    descriptor: SystemDescriptor
    health: str = "healthy"
    token: str | None = None


@dataclass(frozen=True, slots=True)
class FederationLeave:
    """Graceful federation leave message."""

    syndicate_id: SyndicateId
    token: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteSpawnRequest:
    """Request a peer to create an actor from an importable artifact."""

    spec: RemoteActorSpec
    token: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteSpawnAccepted:
    """Successful remote actor spawn response."""

    address: ActorAddress


@dataclass(frozen=True, slots=True)
class RemoteSpawnRejected:
    """Rejected remote actor spawn response."""

    reason: str


RouteConnector = Callable[[SystemDescriptor], Awaitable[None]]
LocalSpawner = Callable[[ActorSpec], Awaitable[ActorAddress]]


class FederationManager:
    """Small authenticated membership and remote-spawn coordinator."""

    def __init__(
        self,
        local_syndicate_id: SyndicateId,
        membership: StaticMembershipProvider,
        artifact_provider: ArtifactProvider,
        *,
        auth_secret: str | None = None,
        lease_seconds: float = 30.0,
    ) -> None:
        self.local_syndicate_id = local_syndicate_id
        self.membership = membership
        self.artifact_provider = artifact_provider
        self.auth_secret = auth_secret
        self.lease_seconds = lease_seconds
        self._local_descriptor: SystemDescriptor | None = None
        self._route_connector: RouteConnector | None = None
        self._local_spawner: LocalSpawner | None = None

    def configure(
        self,
        *,
        local_descriptor: SystemDescriptor,
        route_connector: RouteConnector,
        local_spawner: LocalSpawner,
    ) -> None:
        """Install runtime callbacks after the owning Syndicate starts."""
        self._local_descriptor = local_descriptor
        self._route_connector = route_connector
        self._local_spawner = local_spawner
        self.membership.add_system(local_descriptor)

    def local_descriptor(self) -> SystemDescriptor:
        """Return this system's current descriptor."""
        if self._local_descriptor is None:
            raise FederationError("federation manager is not configured")
        return self._local_descriptor

    async def accept_join(self, request: FederationJoinRequest) -> FederationJoinAccepted | FederationJoinRejected:
        """Authenticate and add a joining member."""
        if not self._authenticated(request.token):
            return FederationJoinRejected("federation authentication failed")
        descriptor = request.descriptor.with_lease(self.lease_seconds)
        await self.add_member(descriptor)
        return FederationJoinAccepted(
            descriptor=self.local_descriptor(),
            members=tuple(self.membership.list_systems()),
        )

    async def accept_heartbeat(self, heartbeat: FederationHeartbeat) -> FederationAck | FederationJoinRejected:
        """Authenticate and refresh a member lease."""
        if not self._authenticated(heartbeat.token):
            return FederationJoinRejected("federation authentication failed")
        descriptor = heartbeat.descriptor.with_health(heartbeat.health, self.lease_seconds)
        await self.add_member(descriptor)
        return FederationAck()

    async def accept_leave(self, leave: FederationLeave) -> FederationAck | FederationJoinRejected:
        """Authenticate and remove a member."""
        if not self._authenticated(leave.token):
            return FederationJoinRejected("federation authentication failed")
        self.membership.remove_system(leave.syndicate_id)
        return FederationAck()

    async def accept_spawn(self, request: RemoteSpawnRequest) -> RemoteSpawnAccepted | RemoteSpawnRejected:
        """Authenticate and create an actor for a remote requester."""
        if not self._authenticated(request.token):
            return RemoteSpawnRejected("federation authentication failed")
        if self._local_spawner is None:
            return RemoteSpawnRejected("federation manager is not configured")
        try:
            actor_class = self.artifact_provider.resolve(request.spec.artifact)
            address = await self._local_spawner(request.spec.to_actor_spec(actor_class))
        except Exception as exc:
            return RemoteSpawnRejected(str(exc))
        return RemoteSpawnAccepted(address)

    async def add_member(self, descriptor: SystemDescriptor) -> None:
        """Add or update a member and connect its transport route when possible."""
        self.membership.add_system(descriptor)
        if descriptor.syndicate_id == self.local_syndicate_id:
            return
        if self._route_connector is not None:
            await self._route_connector(descriptor)

    def remove_member(self, syndicate_id: SyndicateId) -> SystemDescriptor | None:
        """Remove a member by system id."""
        return self.membership.remove_system(syndicate_id)

    def prune_expired(self, now: float | None = None) -> list[SystemDescriptor]:
        """Remove expired members from membership."""
        return [
            descriptor
            for descriptor in self.membership.prune_expired(now)
            if descriptor.syndicate_id != self.local_syndicate_id
        ]

    def _authenticated(self, token: str | None) -> bool:
        return self.auth_secret is None or token == self.auth_secret
