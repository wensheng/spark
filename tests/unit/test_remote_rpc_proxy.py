import asyncio

import pytest

from spark.graphs.event_bus import GraphEventBus
from spark.nodes.exceptions import ContextValidationError
from spark.nodes.rpc_client import RemoteRpcProxyConfig, RemoteRpcProxyNode


class DummyTransport:
    def __init__(self):
        self.last_request = None
        self.last_notify = None

    async def connect(self):
        return None

    async def close(self):
        return None

    async def request(self, payload, *, timeout=None):
        self.last_request = (payload, timeout)
        return {"jsonrpc": "2.0", "result": {"echo": payload}, "id": payload.get("id")}

    async def notify(self, payload):
        self.last_notify = payload

    def register_notification_handler(self, handler):
        self._handler = handler
        return lambda: None


@pytest.mark.asyncio
async def test_remote_rpc_proxy_builds_jsonrpc_request():
    node = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(endpoint="http://remote"))
    node._transport = DummyTransport()  # type: ignore[attr-defined]

    result = await node.do({"method": "add", "params": {"a": 2, "b": 3}})

    payload, timeout = node._transport.last_request  # type: ignore[attr-defined]
    assert payload["method"] == "add"
    assert payload["params"] == {"a": 2, "b": 3}
    assert timeout is None
    assert result.content["result"]["echo"]["params"]["a"] == 2


@pytest.mark.asyncio
async def test_remote_rpc_proxy_notification_mode():
    node = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(endpoint="http://remote"))
    node._transport = DummyTransport()  # type: ignore[attr-defined]

    result = await node.do({"method": "log", "params": {"message": "hi"}, "notify": True})

    assert node._transport.last_notify["method"] == "log"  # type: ignore[attr-defined]
    assert result.content["status"] == "sent"
    assert result.metadata["rpc_expect_response"] is False


@pytest.mark.asyncio
async def test_remote_rpc_proxy_requires_method():
    node = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(endpoint="http://remote"))
    node._transport = DummyTransport()  # type: ignore[attr-defined]

    with pytest.raises(ContextValidationError):
        await node.do({"params": {"value": 1}})


@pytest.mark.asyncio
async def test_remote_rpc_proxy_event_bus_bridge():
    node = RemoteRpcProxyNode(
        config=RemoteRpcProxyConfig(endpoint="http://remote", transport="websocket"),
    )
    event_bus = GraphEventBus()
    node.attach_event_bus(event_bus)
    subscription = await event_bus.subscribe("graph.topic")

    await node._handle_remote_notification(  # type: ignore[attr-defined]
        {
            "jsonrpc": "2.0",
            "method": "event.remote",
            "params": {"topic": "graph.topic", "payload": {"value": 42}},
        }
    )

    message = await asyncio.wait_for(subscription.receive(), timeout=1.0)
    assert message.payload["value"] == 42
