import asyncio
import json
from collections import deque

import pytest

from spark.nodes.rpc_transport import (
    HttpJsonRpcTransport,
    JsonRpcTimeoutError,
    WebSocketJsonRpcTransport,
)


class DummyResponse:
    def __init__(self, data=None, *, status=200):
        self._data = data
        self.status = status
        self.read_called = False
        self.kwargs = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._data

    async def read(self):
        self.read_called = True

    async def text(self):
        if self._data is None:
            return ""
        return json.dumps(self._data)


class DummySession:
    def __init__(self, responses):
        self._responses = deque(responses)
        self.closed = False

    def post(self, *args, **kwargs):
        if not self._responses:
            raise AssertionError("No more responses configured")
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        response.kwargs = kwargs
        return response

    async def close(self):
        self.closed = True


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def send(self, data: str):
        self.sent.append(json.loads(data))

    async def close(self):
        self.closed = True
        await self._queue.put(None)

    def queue_json(self, payload):
        self._queue.put_nowait(json.dumps(payload))

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self._queue.get()
        if message is None:
            raise StopAsyncIteration
        return message


@pytest.mark.asyncio
async def test_http_transport_request():
    response = DummyResponse({"jsonrpc": "2.0", "result": {"sum": 5}, "id": 10})
    session = DummySession([response])
    transport = HttpJsonRpcTransport("http://service", session=session)

    payload = {"jsonrpc": "2.0", "method": "add", "params": {"a": 2, "b": 3}, "id": 10}
    result = await transport.request(payload)

    assert result["result"]["sum"] == 5
    assert response.kwargs["json"] == payload
    await transport.close()


@pytest.mark.asyncio
async def test_http_transport_notify_reads_response():
    response = DummyResponse(status=204)
    session = DummySession([response])
    transport = HttpJsonRpcTransport("http://service", session=session)

    await transport.notify({"jsonrpc": "2.0", "method": "notify"})
    assert response.read_called is True

    await transport.close()


@pytest.mark.asyncio
async def test_http_transport_timeout():
    session = DummySession([asyncio.TimeoutError()])
    transport = HttpJsonRpcTransport("http://service", session=session)

    with pytest.raises(JsonRpcTimeoutError):
        await transport.request({"jsonrpc": "2.0", "method": "slow"})

    await transport.close()


@pytest.fixture
def fake_websocket(monkeypatch):
    socket = FakeWebSocket()

    async def fake_connect(*args, **kwargs):
        return socket

    monkeypatch.setattr("spark.nodes.rpc_transport.websockets.connect", fake_connect)
    return socket


@pytest.mark.asyncio
async def test_websocket_transport_request(fake_websocket):
    transport = WebSocketJsonRpcTransport("ws://service", request_timeout=1.0)

    task = asyncio.create_task(
        transport.request({"jsonrpc": "2.0", "method": "echo", "params": {"value": 7}})
    )
    await asyncio.sleep(0)
    fake_websocket.queue_json({"jsonrpc": "2.0", "id": 1, "result": {"value": 7}})

    response = await task
    assert response["result"]["value"] == 7
    assert fake_websocket.sent[0]["method"] == "echo"

    await transport.close()


@pytest.mark.asyncio
async def test_websocket_notification_handler(fake_websocket):
    transport = WebSocketJsonRpcTransport("ws://service", request_timeout=1.0)
    received = asyncio.Event()
    events = []

    async def handler(message):
        events.append(message)
        received.set()

    transport.register_notification_handler(handler)
    await transport.notify({"jsonrpc": "2.0", "method": "fire_event", "params": {"value": 42}})
    await asyncio.sleep(0)
    fake_websocket.queue_json({"jsonrpc": "2.0", "method": "event.remote", "params": {"value": 42}})

    await asyncio.wait_for(received.wait(), timeout=1.0)
    assert events[0]["params"]["value"] == 42

    await transport.close()
