"""Tests for optional websocket remote transport."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("websockets")

from websockets.asyncio.client import connect as websocket_connect

from spark import Actor, ActorAddress, Syndicate
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message
from spark.transport.websocket import WebSocketRelay


class WebSocketEchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(f"remote:{message.content}", message.sender)


async def _wait_for_connected(relay: WebSocketRelay, count: int) -> None:
    for _ in range(100):
        if len(relay.connected_systems) == count:
            return
        await asyncio.sleep(0.01)
    assert len(relay.connected_systems) == count


class TestWebSocketTransport:
    @pytest.mark.asyncio
    async def test_direct_websocket_tell_routes_between_systems(self) -> None:
        async with (
            Syndicate(
                "ws-left-tell",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as left,
            Syndicate(
                "ws-right-tell",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as right,
        ):
            assert right.remote_uri is not None
            await left.connect_uri(right.syndicate_id, right.remote_uri)
            remote_actor = await right.create_actor(WebSocketEchoActor)

            await left.tell("hello", remote_actor)

            assert await left.receive(timeout=2.0) == "remote:hello"

    @pytest.mark.asyncio
    async def test_direct_websocket_ask_replies_over_single_outbound_connection(self) -> None:
        async with (
            Syndicate(
                "ws-left-ask",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as left,
            Syndicate(
                "ws-right-ask",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as right,
        ):
            assert right.remote_uri is not None
            await left.connect_uri(right.syndicate_id, right.remote_uri)
            remote_actor = await right.create_actor(WebSocketEchoActor)

            assert await left.ask("question", remote_actor, timeout=2.0) == "remote:question"

    @pytest.mark.asyncio
    async def test_direct_websocket_ask_uses_cbor2_codec(self) -> None:
        pytest.importorskip("cbor2")
        async with (
            Syndicate(
                "ws-left-cbor",
                remote=True,
                remote_transport="websocket",
                transport_codec="cbor2",
            ) as left,
            Syndicate(
                "ws-right-cbor",
                remote=True,
                remote_transport="websocket",
                transport_codec="cbor2",
            ) as right,
        ):
            assert right.remote_uri is not None
            await left.connect_uri(right.syndicate_id, right.remote_uri)
            remote_actor = await right.create_actor(WebSocketEchoActor)

            assert (
                await left.ask({"question": ["hello", 1]}, remote_actor, timeout=2.0)
                == "remote:{'question': ['hello', 1]}"
            )

    @pytest.mark.asyncio
    async def test_missing_websocket_route_records_dead_letter(self) -> None:
        async with Syndicate(
            "ws-missing",
            remote=True,
            remote_transport="websocket",
            transport_codec="trusted-pickle",
        ) as system:
            missing = ActorAddress(ActorId(SyndicateId.from_name("missing-ws-system")))

            await system.tell("lost", missing)

            assert len(system.dead_letters) == 1
            assert system.dead_letters[0].reason == "remote route not found"
            assert system.dead_letters[0].original_envelope.payload == "lost"

    @pytest.mark.asyncio
    async def test_bad_websocket_frame_does_not_crash_transport(self) -> None:
        async with Syndicate(
            "ws-bad-frame",
            remote=True,
            remote_transport="websocket",
            transport_codec="trusted-pickle",
        ) as system:
            assert system.remote_uri is not None
            async with websocket_connect(system.remote_uri, max_size=64 * 1024 * 1024) as websocket:
                await websocket.send(b"not-a-spark-frame")
            await asyncio.sleep(0.05)

            actor = await system.create_actor(WebSocketEchoActor)
            await system.tell("still-running", actor)

            assert await system.receive(timeout=2.0) == "remote:still-running"


class TestWebSocketRelay:
    @pytest.mark.asyncio
    async def test_relay_routes_between_systems(self) -> None:
        async with WebSocketRelay() as relay:
            assert relay.uri is not None
            async with (
                Syndicate(
                    "ws-relay-left",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="trusted-pickle",
                ) as left,
                Syndicate(
                    "ws-relay-right",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="trusted-pickle",
                ) as right,
            ):
                await left.connect_relay(relay.uri)
                await right.connect_relay(relay.uri)
                await _wait_for_connected(relay, 2)
                remote_actor = await right.create_actor(WebSocketEchoActor)

                assert await left.ask("relay", remote_actor, timeout=2.0) == "remote:relay"

    @pytest.mark.asyncio
    async def test_relay_routes_cbor2_payloads(self) -> None:
        pytest.importorskip("cbor2")
        async with WebSocketRelay() as relay:
            assert relay.uri is not None
            async with (
                Syndicate(
                    "ws-relay-left-cbor",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="cbor2",
                ) as left,
                Syndicate(
                    "ws-relay-right-cbor",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="cbor2",
                ) as right,
            ):
                await left.connect_relay(relay.uri)
                await right.connect_relay(relay.uri)
                await _wait_for_connected(relay, 2)
                remote_actor = await right.create_actor(WebSocketEchoActor)

                assert (
                    await left.ask({"relay": ["hello", 1]}, remote_actor, timeout=2.0)
                    == "remote:{'relay': ['hello', 1]}"
                )

    @pytest.mark.asyncio
    async def test_authenticated_relay_routes_between_systems(self) -> None:
        async with WebSocketRelay(auth_secret="shared") as relay:
            assert relay.uri is not None
            async with (
                Syndicate(
                    "ws-relay-auth-left",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="trusted-pickle",
                ) as left,
                Syndicate(
                    "ws-relay-auth-right",
                    remote=True,
                    remote_transport="websocket",
                    transport_codec="trusted-pickle",
                ) as right,
            ):
                await left.connect_relay(relay.uri, secret="shared")
                await right.connect_relay(relay.uri, secret="shared")
                await _wait_for_connected(relay, 2)
                remote_actor = await right.create_actor(WebSocketEchoActor)

                assert await left.ask("relay", remote_actor, timeout=2.0) == "remote:relay"

    @pytest.mark.asyncio
    async def test_authenticated_relay_rejects_missing_secret(self) -> None:
        async with WebSocketRelay(auth_secret="shared") as relay:
            assert relay.uri is not None
            async with Syndicate(
                "ws-relay-auth-missing",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as system:
                with pytest.raises(OSError, match="authentication"):
                    await system.connect_relay(relay.uri)
                await _wait_for_connected(relay, 0)

    @pytest.mark.asyncio
    async def test_authenticated_relay_rejects_bad_secret(self) -> None:
        async with WebSocketRelay(auth_secret="shared") as relay:
            assert relay.uri is not None
            async with Syndicate(
                "ws-relay-auth-bad",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as system:
                with pytest.raises(OSError, match="authentication"):
                    await system.connect_relay(relay.uri, secret="wrong")
                await _wait_for_connected(relay, 0)

    @pytest.mark.asyncio
    async def test_relay_reports_missing_target_as_dead_letter(self) -> None:
        async with WebSocketRelay() as relay:
            assert relay.uri is not None
            async with Syndicate(
                "ws-relay-missing",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            ) as system:
                await system.connect_relay(relay.uri)
                await _wait_for_connected(relay, 1)
                missing = ActorAddress(ActorId(SyndicateId.from_name("relay-missing-system")))

                await system.tell("lost", missing)

                assert len(system.dead_letters) == 1
                assert system.dead_letters[0].reason == "relay route not found"
                assert system.dead_letters[0].original_envelope.payload == "lost"

    @pytest.mark.asyncio
    async def test_relay_removes_disconnected_systems(self) -> None:
        async with WebSocketRelay() as relay:
            assert relay.uri is not None
            system = Syndicate(
                "ws-relay-disconnect",
                remote=True,
                remote_transport="websocket",
                transport_codec="trusted-pickle",
            )
            try:
                await system.connect_relay(relay.uri)
                await _wait_for_connected(relay, 1)
            finally:
                await system.shutdown()

            await _wait_for_connected(relay, 0)
