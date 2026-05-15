"""Tests for optional Spark services (async version)."""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from spark import Actor, ActorAddress, Syndicate
from spark.core.actor_spec import ActorSpec
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message
from spark.services import (
    ArtifactRef,
    ArtifactVerificationError,
    LocalFirstPlacementStrategy,
    LocalNameRegistry,
    PackageArtifactProvider,
    PlacementError,
    StaticMembershipProvider,
    SystemDescriptor,
    SystemEvent,
)


class ServiceActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(message.content, message.sender)


class NotAnActor:
    pass


class AcceptingVerifier:
    def __init__(self) -> None:
        self.digest: str | None = None

    def verify(self, ref: ArtifactRef, digest: str) -> bool:
        self.digest = digest
        return ref.signature == "trusted"


class TestLocalNameRegistry:
    def test_register_resolve_snapshot_and_unregister(self) -> None:
        registry = LocalNameRegistry()
        address = ActorAddress(ActorId(SyndicateId()))

        registry.register(" workers ", address)

        assert registry.resolve("workers") == address
        assert registry.snapshot() == {"workers": address}
        assert registry.unregister("workers") == address
        assert registry.resolve("workers") is None

    def test_rejects_empty_names(self) -> None:
        registry = LocalNameRegistry()

        with pytest.raises(ValueError, match="must not be empty"):
            registry.register(" ", ActorAddress(ActorId(SyndicateId())))


class TestStaticMembershipProvider:
    def test_lists_systems_and_replays_initial_join_events(self) -> None:
        descriptor = SystemDescriptor(
            SyndicateId(),
            capabilities={"backend": "inprocess"},
            tags=frozenset({"local"}),
        )
        provider = StaticMembershipProvider([descriptor])
        events: list[SystemEvent] = []

        unsubscribe = provider.watch(events.append)

        assert provider.list_systems() == [descriptor]
        assert events == [SystemEvent("joined", descriptor)]
        unsubscribe()

    def test_add_update_and_remove_system_events(self) -> None:
        syndicate_id = SyndicateId()
        initial = SystemDescriptor(syndicate_id, capabilities={"zone": "a"})
        updated = SystemDescriptor(syndicate_id, capabilities={"zone": "b"})
        provider = StaticMembershipProvider()
        events: list[SystemEvent] = []
        unsubscribe = provider.watch(events.append)
        events.clear()

        provider.add_system(initial)
        provider.add_system(updated)
        removed = provider.remove_system(syndicate_id)
        unsubscribe()
        provider.add_system(SystemDescriptor(SyndicateId()))

        assert removed == updated
        assert events == [
            SystemEvent("joined", initial),
            SystemEvent("updated", updated),
            SystemEvent("left", updated),
        ]


class TestLocalFirstPlacement:
    def test_prefers_local_matching_candidate(self) -> None:
        local_id = SyndicateId()
        remote_id = SyndicateId()
        local = SystemDescriptor(local_id, capabilities={"backend": "inprocess"})
        remote = SystemDescriptor(remote_id, capabilities={"backend": "inprocess"})
        strategy = LocalFirstPlacementStrategy(local_id)

        choice = strategy.choose(
            ActorSpec(ServiceActor, requirements={"backend": "inprocess"}),
            [remote, local],
        )

        assert choice == local

    def test_falls_back_to_first_matching_remote_candidate(self) -> None:
        local_id = SyndicateId()
        remote = SystemDescriptor(SyndicateId(), capabilities={"gpu": True})
        strategy = LocalFirstPlacementStrategy(local_id)

        choice = strategy.choose(ActorSpec(ServiceActor, requirements={"gpu": True}), [remote])

        assert choice == remote

    def test_raises_when_no_candidate_matches(self) -> None:
        strategy = LocalFirstPlacementStrategy(SyndicateId())

        with pytest.raises(PlacementError, match="no actor system"):
            strategy.choose(
                ActorSpec(ServiceActor, requirements={"gpu": True}),
                [SystemDescriptor(SyndicateId(), capabilities={"gpu": False})],
            )


class TestPackageArtifactProvider:
    def test_resolves_importable_actor_class(self) -> None:
        provider = PackageArtifactProvider()
        ref = ArtifactRef.from_actor_class(ServiceActor)

        assert provider.resolve(ref) is ServiceActor

    def test_validates_module_sha256(self) -> None:
        provider = PackageArtifactProvider()
        digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

        ref = ArtifactRef.from_actor_class(ServiceActor, sha256=digest)
        bad_ref = ArtifactRef.from_actor_class(ServiceActor, sha256="0" * 64)

        assert provider.resolve(ref) is ServiceActor
        with pytest.raises(ArtifactVerificationError, match="sha256 mismatch"):
            provider.resolve(bad_ref)

    def test_signature_requires_verifier_and_can_be_verified(self) -> None:
        ref = ArtifactRef.from_actor_class(ServiceActor, signature="trusted")
        verifier = AcceptingVerifier()

        with pytest.raises(ArtifactVerificationError, match="verifier is required"):
            PackageArtifactProvider().resolve(ref)

        assert PackageArtifactProvider(verifier).resolve(ref) is ServiceActor
        assert verifier.digest is not None

    def test_rejects_non_actor_symbols(self) -> None:
        provider = PackageArtifactProvider()

        with pytest.raises(ValueError, match="not an Actor subclass"):
            provider.resolve(ArtifactRef(module=__name__, qualified_name="NotAnActor"))


class TestDiagnosticsService:
    @pytest.mark.asyncio
    async def test_syndicate_diagnostics_snapshot(self) -> None:
        async with Syndicate("async-diag-snap") as system:
            actor = await system.create_actor(ServiceActor)

            snapshot = system.diagnostics_snapshot()

            assert snapshot.syndicate_id == system.syndicate_id
            assert snapshot.address == system.address
            assert snapshot.runtime.backend_type == "async-inprocess"
            assert snapshot.runtime.actor_count == 1
            assert actor.actor_id in {a.actor_id for a in snapshot.runtime.actors}

    @pytest.mark.asyncio
    async def test_diagnostics_reports_dead_letters(self) -> None:
        async with Syndicate("async-diag-dead") as system:
            missing = ActorAddress(ActorId(system.syndicate_id))

            await system.tell(missing, "lost")
            snapshot = system.diagnostics_snapshot()

            assert snapshot.runtime.dead_letter_count == 1
            assert snapshot.dead_letters[0].reason == "target not found"

    @pytest.mark.asyncio
    async def test_syndicate_initializes_phase4_services(self) -> None:
        async with Syndicate("async-phase4-services", remote=True) as system:
            descriptor = system.membership.list_systems()[0]
            assert descriptor.syndicate_id == system.syndicate_id
            assert descriptor.address == system.address
            assert system.placement.choose(ActorSpec(ServiceActor), system.membership.list_systems()) == descriptor
            assert system.name_registry.resolve("missing") is None
            assert system.artifact_provider.resolve(ArtifactRef.from_actor_class(ServiceActor)) is ServiceActor
