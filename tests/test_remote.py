"""Tests for remote transport (async version)."""

import pytest

from spark import Actor, ActorAddress, Syndicate
from spark.core.exceptions import ActorTimeout, UnsupportedBackendError
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
            Syndicate("async-remote-left-tell", remote=True) as left,
            Syndicate("async-remote-right-tell", remote=True) as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            await left.tell(remote_actor, "hello")

            assert await left.receive(timeout=2.0) == "remote:hello"

    @pytest.mark.asyncio
    async def test_remote_ask_uses_external_inbox_reply_route(self) -> None:
        async with (
            Syndicate("async-remote-left-ask", remote=True) as left,
            Syndicate("async-remote-right-ask", remote=True) as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            assert await left.ask(remote_actor, "question", timeout=2.0) == "remote:question"

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
                await left.ask(remote_actor, {"question": ["hello", 1]}, timeout=2.0)
                == "remote:{'question': ['hello', 1]}"
            )

    @pytest.mark.asyncio
    async def test_mismatched_codecs_fail_cleanly(self) -> None:
        pytest.importorskip("cbor2")
        async with (
            Syndicate("async-remote-left-cbor-mismatch", remote=True, transport_codec="cbor2") as left,
            Syndicate("async-remote-right-pickle-mismatch", remote=True) as right,
        ):
            await connect_systems(left, right)
            remote_actor = await right.create_actor(RemoteEchoActor)

            with pytest.raises(ActorTimeout):
                await left.ask(remote_actor, "question", timeout=0.1)

    @pytest.mark.asyncio
    async def test_missing_remote_route_records_dead_letter(self) -> None:
        async with Syndicate("async-remote-missing", remote=True) as system:
            missing = ActorAddress(ActorId(SyndicateId.from_name("missing-system")))

            await system.tell(missing, "lost")

            assert len(system.dead_letters) == 1
            assert system.dead_letters[0].reason == "remote route not found"
            assert system.dead_letters[0].original_envelope.payload == "lost"

    @pytest.mark.asyncio
    async def test_connect_requires_enabled_remote_transport(self) -> None:
        async with Syndicate("async-remote-no-transport") as system:
            assert system.remote_address is None
            with pytest.raises(UnsupportedBackendError):
                await system.connect(SyndicateId(), "127.0.0.1", 1)
