"""Tests for remote transport (async version)."""

import pytest

from spark import Actor, ActorAddress, Syndicate
from spark.core.exceptions import ActorTimeout, MessageDeliveryError, UnsupportedBackendError
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message


class RemoteEchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(f"remote:{message.content}", message.sender)


async def connect_systems(left: Syndicate, right: Syndicate) -> None:
    left_address = left.remote_address
    right_address = right.remote_address
    assert left_address is not None
    assert right_address is not None
    await left.connect(right.syndicate_id, *right_address)
    await right.connect(left.syndicate_id, *left_address)


class TestRemoteTransport:
    @pytest.mark.asyncio
    async def test_remote_tell_routes_envelope_between_systems(self) -> None:
        async with (
            Syndicate("async-remote-left-tell", remote=True, transport_codec="trusted-pickle") as left,
            Syndicate("async-remote-right-tell", remote=True, transport_codec="trusted-pickle") as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            await left.tell("hello", remote_actor)

            assert await left.receive(timeout=2.0) == "remote:hello"

    @pytest.mark.asyncio
    async def test_remote_ask_uses_external_inbox_reply_route(self) -> None:
        async with (
            Syndicate("async-remote-left-ask", remote=True, transport_codec="trusted-pickle") as left,
            Syndicate("async-remote-right-ask", remote=True, transport_codec="trusted-pickle") as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            assert await left.ask("question", remote_actor, timeout=2.0) == "remote:question"

    @pytest.mark.asyncio
    async def test_remote_ask_uses_cbor2_codec(self) -> None:
        pytest.importorskip("cbor2")
        async with (
            Syndicate("async-remote-left-cbor", remote=True, transport_codec="cbor2") as left,
            Syndicate("async-remote-right-cbor", remote=True, transport_codec="cbor2") as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            assert (
                await left.ask({"question": ["hello", 1]}, remote_actor, timeout=2.0)
                == "remote:{'question': ['hello', 1]}"
            )

    @pytest.mark.asyncio
    async def test_mismatched_codecs_fail_cleanly(self) -> None:
        pytest.importorskip("cbor2")
        async with (
            Syndicate("async-remote-left-cbor-mismatch", remote=True, transport_codec="cbor2") as left,
            Syndicate("async-remote-right-pickle-mismatch", remote=True, transport_codec="trusted-pickle") as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            with pytest.raises((ActorTimeout, MessageDeliveryError)):
                await left.ask("question", remote_actor, timeout=0.1)

    @pytest.mark.asyncio
    async def test_authenticated_tcp_route_uses_shared_secret(self) -> None:
        async with (
            Syndicate(
                "async-remote-left-auth",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="shared",
            ) as left,
            Syndicate(
                "async-remote-right-auth",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="shared",
            ) as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            assert await left.ask("secret", remote_actor, timeout=2.0) == "remote:secret"

            route = left.transport_health[right.syndicate_id.uuid]
            assert route["state"] == "connected"
            assert route["frames_sent"] == 1
            assert route["connections_opened"] == 1

    @pytest.mark.asyncio
    async def test_authenticated_tcp_route_rejects_bad_secret(self) -> None:
        async with (
            Syndicate(
                "async-remote-left-bad-auth",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="left",
                transport_frame_timeout=0.2,
            ) as left,
            Syndicate(
                "async-remote-right-bad-auth",
                remote=True,
                transport_codec="trusted-pickle",
                transport_secret="right",
                transport_frame_timeout=0.2,
            ) as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            with pytest.raises(MessageDeliveryError):
                await left.ask("secret", remote_actor, timeout=0.5)

            route = left.transport_health[right.syndicate_id.uuid]
            assert route["state"] == "degraded"
            assert route["last_failure"]

    @pytest.mark.asyncio
    async def test_tcp_transport_reuses_persistent_connection(self) -> None:
        async with (
            Syndicate("async-remote-left-persistent", remote=True, transport_codec="trusted-pickle") as left,
            Syndicate("async-remote-right-persistent", remote=True, transport_codec="trusted-pickle") as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            assert await left.ask("one", remote_actor, timeout=2.0) == "remote:one"
            assert await left.ask("two", remote_actor, timeout=2.0) == "remote:two"

            route = left.transport_health[right.syndicate_id.uuid]
            assert route["state"] == "connected"
            assert route["connections_opened"] == 1
            assert route["frames_sent"] == 2

    @pytest.mark.asyncio
    async def test_tcp_route_health_reports_failure(self) -> None:
        async with Syndicate("async-remote-health-fail", remote=True, transport_codec="trusted-pickle") as system:
            missing_id = SyndicateId.from_name("async-remote-health-missing")
            missing = ActorAddress(ActorId(missing_id))
            await system.connect(missing_id, "127.0.0.1", 1)

            await system.tell("lost", missing)

            route = system.transport_health[missing_id.uuid]
            assert route["state"] == "disconnected"
            assert route["last_failure"]

    @pytest.mark.asyncio
    async def test_missing_remote_route_records_dead_letter(self) -> None:
        async with Syndicate("async-remote-missing", remote=True, transport_codec="trusted-pickle") as system:
            missing = ActorAddress(ActorId(SyndicateId.from_name("missing-system")))

            await system.tell("lost", missing)

            assert len(system.dead_letters) == 1
            assert system.dead_letters[0].reason == "remote route not found"
            assert system.dead_letters[0].original_envelope.payload == "lost"

    @pytest.mark.asyncio
    async def test_connect_requires_enabled_remote_transport(self) -> None:
        async with Syndicate("async-remote-no-transport") as system:
            assert system.remote_address is None
            with pytest.raises(UnsupportedBackendError):
                await system.connect(SyndicateId(), "127.0.0.1", 1)

    def test_pickle_codec_name_is_rejected(self) -> None:
        with pytest.raises(UnsupportedBackendError, match="trusted-pickle"):
            Syndicate("async-remote-old-pickle", remote=True, transport_codec="pickle")

    def test_unknown_codec_name_is_rejected_without_remote(self) -> None:
        with pytest.raises(UnsupportedBackendError, match="unsupported transport_codec"):
            Syndicate("async-remote-bad-codec", transport_codec="msgpack")

    def test_trusted_pickle_requires_explicit_non_loopback_opt_in(self) -> None:
        with pytest.raises(UnsupportedBackendError, match="unsafe"):
            Syndicate(
                "async-remote-unsafe-pickle",
                remote=True,
                remote_host="0.0.0.0",
                transport_codec="trusted-pickle",
            )
