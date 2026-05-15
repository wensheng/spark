"""Tests for the direct websocket remote agent spawn example."""

from __future__ import annotations

import pytest

pytest.importorskip("websockets")

from examples.remote_agent_spawn import (  # noqa: E402
    AGENT_ERROR,
    AGENT_STARTED,
    SPAWN_REQUEST,
    AgentSpawner,
    RequesterNode,
)
from spark import ActorAddress, Syndicate  # noqa: E402


async def _connect_left_to_right(left: Syndicate, right: Syndicate) -> ActorAddress:
    assert right.remote_uri is not None
    await left.connect_uri(right.syndicate_id, right.remote_uri)
    return await right.create_actor(AgentSpawner)


class TestRemoteAgentSpawnExample:
    @pytest.mark.asyncio
    async def test_requester_node_starts_remote_abc_agent_and_gets_reply(self) -> None:
        async with (
            Syndicate("remote-agent-left-success", remote=True, remote_transport="websocket") as left,
            Syndicate("remote-agent-right-success", remote=True, remote_transport="websocket") as right,
        ):
            spawner = await _connect_left_to_right(left, right)
            requester = await left.create_actor(RequesterNode, spawner)

            reply = await left.ask(requester, "start agent AbcAgent", timeout=2.0)

            assert isinstance(reply, dict)
            assert reply["type"] == AGENT_STARTED
            assert reply["agent_type"] == "AbcAgent"
            assert "AbcAgent started" in reply["message"]
            assert isinstance(reply["agent_address"], ActorAddress)
            assert reply["agent_address"].actor_id.syndicate_id == right.syndicate_id
            assert right.diagnostics().actor_count == 2

    @pytest.mark.asyncio
    async def test_unknown_command_returns_local_error_without_remote_spawn(self) -> None:
        async with (
            Syndicate("remote-agent-left-unknown-command", remote=True, remote_transport="websocket") as left,
            Syndicate("remote-agent-right-unknown-command", remote=True, remote_transport="websocket") as right,
        ):
            spawner = await _connect_left_to_right(left, right)
            requester = await left.create_actor(RequesterNode, spawner)

            reply = await left.ask(requester, "stop agent AbcAgent", timeout=2.0)

            assert reply == "unsupported command: stop agent AbcAgent"
            assert right.diagnostics().actor_count == 1

    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_remote_error(self) -> None:
        async with (
            Syndicate("remote-agent-left-unknown-agent", remote=True, remote_transport="websocket") as left,
            Syndicate("remote-agent-right-unknown-agent", remote=True, remote_transport="websocket") as right,
        ):
            spawner = await _connect_left_to_right(left, right)
            requester = await left.create_actor(RequesterNode, spawner)

            reply = await left.ask(requester, "start agent MissingAgent", timeout=2.0)

            assert isinstance(reply, dict)
            assert reply["type"] == AGENT_ERROR
            assert reply["error"] == "unknown agent type: MissingAgent"
            assert right.diagnostics().actor_count == 1

    @pytest.mark.asyncio
    async def test_malformed_remote_spawn_request_returns_error(self) -> None:
        async with (
            Syndicate("remote-agent-left-malformed", remote=True, remote_transport="websocket") as left,
            Syndicate("remote-agent-right-malformed", remote=True, remote_transport="websocket") as right,
        ):
            spawner = await _connect_left_to_right(left, right)

            reply = await left.ask(spawner, {"type": SPAWN_REQUEST, "request_id": "bad"}, timeout=2.0)

            assert isinstance(reply, dict)
            assert reply["type"] == AGENT_ERROR
            assert reply["request_id"] == "bad"
            assert reply["error"] == "agent_type must be a string"

    @pytest.mark.asyncio
    async def test_remote_spawn_flow_works_with_cbor2_codec(self) -> None:
        pytest.importorskip("cbor2")
        async with (
            Syndicate(
                "remote-agent-left-cbor",
                remote=True,
                remote_transport="websocket",
                transport_codec="cbor2",
            ) as left,
            Syndicate(
                "remote-agent-right-cbor",
                remote=True,
                remote_transport="websocket",
                transport_codec="cbor2",
            ) as right,
        ):
            spawner = await _connect_left_to_right(left, right)
            requester = await left.create_actor(RequesterNode, spawner)

            reply = await left.ask(requester, "start agent AbcAgent", timeout=2.0)

            assert isinstance(reply, dict)
            assert reply["type"] == AGENT_STARTED
            assert isinstance(reply["agent_address"], ActorAddress)
