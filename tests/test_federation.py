"""Tests for federation membership and remote placement."""

import time

import pytest

from spark import Actor, ActorSpec, FederationAuthError, RemoteSpawnError, Syndicate
from spark.core.identity import SyndicateId
from spark.core.message import Message
from spark.services import PlacementError, SystemEvent


class FederationEchoActor(Actor):
    async def process(self, message: Message) -> str:
        return f"remote:{message.content}"


class TestFederation:
    @pytest.mark.asyncio
    async def test_authenticated_join_adds_membership_and_routes(self) -> None:
        async with (
            Syndicate(
                "fed-left-join",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="transport",
                federation=True,
                federation_secret="cluster",
            ) as left,
            Syndicate(
                "fed-right-join",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="transport",
                federation=True,
                federation_secret="cluster",
            ) as right,
        ):
            events: list[SystemEvent] = []
            unsubscribe = left.membership.watch(events.append)
            events.clear()

            joined = await left.join_federation(right.local_descriptor, token="cluster")

            unsubscribe()
            assert joined.syndicate_id == right.syndicate_id
            assert left.membership.get_system(right.syndicate_id) is not None
            assert right.membership.get_system(left.syndicate_id) is not None
            assert right.syndicate_id.uuid in left.transport_health
            assert left.syndicate_id.uuid in right.transport_health
            assert any(
                event.kind == "joined" and event.descriptor.syndicate_id == right.syndicate_id for event in events
            )

    @pytest.mark.asyncio
    async def test_join_rejects_bad_federation_token(self) -> None:
        async with (
            Syndicate(
                "fed-left-bad-auth",
                remote=True,
                transport_codec="trusted-pickle",
                federation=True,
                federation_secret="cluster",
            ) as left,
            Syndicate(
                "fed-right-bad-auth",
                remote=True,
                transport_codec="trusted-pickle",
                federation=True,
                federation_secret="cluster",
            ) as right,
        ):
            with pytest.raises(FederationAuthError):
                await left.join_federation(right.local_descriptor, token="wrong")

            assert left.membership.get_system(right.syndicate_id) is None

    @pytest.mark.asyncio
    async def test_heartbeat_refreshes_lease_and_prune_removes_expired_members(self) -> None:
        async with (
            Syndicate(
                "fed-left-heartbeat",
                remote=True,
                transport_codec="trusted-pickle",
                federation=True,
                federation_secret="cluster",
                federation_lease_seconds=0.05,
            ) as left,
            Syndicate(
                "fed-right-heartbeat",
                remote=True,
                transport_codec="trusted-pickle",
                federation=True,
                federation_secret="cluster",
                federation_lease_seconds=0.05,
            ) as right,
        ):
            await left.join_federation(right.local_descriptor, token="cluster")
            before = right.membership.get_system(left.syndicate_id)
            assert before is not None

            await left.heartbeat_federation(right.syndicate_id, token="cluster")
            refreshed = right.membership.get_system(left.syndicate_id)

            assert refreshed is not None
            assert refreshed.lease_expires_at is not None
            assert before.lease_expires_at is not None
            assert refreshed.lease_expires_at >= before.lease_expires_at

            removed = right.federation.prune_expired(time.time() + 1.0)
            assert [descriptor.syndicate_id for descriptor in removed] == [left.syndicate_id]
            assert right.membership.get_system(left.syndicate_id) is None

    @pytest.mark.asyncio
    async def test_auto_placement_spawns_actor_on_matching_remote_system(self) -> None:
        async with (
            Syndicate(
                "fed-left-placement",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="transport",
                federation=True,
                federation_secret="cluster",
                system_capabilities={"gpu": False},
            ) as left,
            Syndicate(
                "fed-right-placement",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="transport",
                federation=True,
                federation_secret="cluster",
                system_capabilities={"gpu": True},
            ) as right,
        ):
            await left.join_federation(right.local_descriptor, token="cluster")

            actor = await left.create_actor_from_spec(
                ActorSpec(FederationEchoActor, requirements={"gpu": True}),
                placement="auto",
            )

            assert actor.actor_id.syndicate_id == right.syndicate_id
            assert await left.ask("hello", actor, timeout=2.0) == "remote:hello"

    @pytest.mark.asyncio
    async def test_auto_placement_reports_no_matching_system(self) -> None:
        async with Syndicate("fed-left-no-placement", federation=True, system_capabilities={"gpu": False}) as system:
            with pytest.raises(PlacementError):
                await system.create_actor_from_spec(
                    ActorSpec(FederationEchoActor, requirements={"gpu": True}),
                    placement="auto",
                )

    @pytest.mark.asyncio
    async def test_remote_spawn_requires_federation_address(self) -> None:
        async with Syndicate("fed-left-no-address", federation=True, system_capabilities={"gpu": False}) as system:
            descriptor = system.local_descriptor
            descriptor = type(descriptor)(
                syndicate_id=SyndicateId.from_name("fed-right-no-address"),
                capabilities={"gpu": True},
            )

            with pytest.raises(RemoteSpawnError):
                await system.create_actor_from_spec(
                    ActorSpec(FederationEchoActor, requirements={"gpu": True}),
                    placement=descriptor,
                )

    def test_scoped_name_registry_keeps_federation_names_separate(self) -> None:
        system = Syndicate("fed-names")
        local = system.address

        system.register_name("workers", local)
        system.register_name("workers", local, scope="federation")

        assert system.resolve_name("workers") == local
        assert system.resolve_name("workers", scope="federation") == local
        assert system.name_registry.snapshot() == {"workers": local}
        assert system.name_registry.snapshot(scope=None) == {"local:workers": local, "federation:workers": local}
