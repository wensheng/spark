"""
Tests for RpcNode (JSON-RPC 2.0 server).
"""

import pytest
import pytest_asyncio
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from spark.nodes.rpc import RpcNode, MethodNotFoundError, InvalidParamsError, JsonRpcError
from spark.nodes.types import ExecutionContext
from spark.nodes.channels import ChannelMessage


class TestRpcNode(RpcNode):
    """Test RPC node with sample methods."""

    async def rpc_add(self, params, context):
        """Add two numbers."""
        return {"sum": params["a"] + params["b"]}

    async def rpc_echo(self, params, context):
        """Echo back the params."""
        return {"echo": params}

    async def rpc_error(self, params, context):
        """Raise an error."""
        raise ValueError("Intentional error")

    async def rpc_invalid_params(self, params, context):
        """Method that expects specific params."""
        # This will raise KeyError if 'required_field' is missing
        return {"value": params["required_field"]}


@pytest_asyncio.fixture
async def rpc_node():
    """Create test RPC node with processing loop running."""
    node = TestRpcNode(host="127.0.0.1", port=8888)

    # Start the node's processing loop in background
    node_task = asyncio.create_task(node.go())

    yield node

    # Cleanup: shutdown the node
    try:
        # Send shutdown signal
        await node.mailbox.send(ChannelMessage(payload={}, is_shutdown=True))
        # Wait briefly for graceful shutdown
        await asyncio.wait_for(node_task, timeout=1.0)
    except asyncio.TimeoutError:
        node_task.cancel()
        try:
            await node_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# JSON-RPC Message Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_valid_request(rpc_node):
    """Test handling valid JSON-RPC request."""
    request = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"a": 5, "b": 3},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert response["jsonrpc"] == "2.0"
    assert response["result"] == {"sum": 8}
    assert response["id"] == 1


@pytest.mark.asyncio
async def test_notification(rpc_node):
    """Test notification (no id, no response)."""
    notification = {
        "jsonrpc": "2.0",
        "method": "echo",
        "params": {"message": "hello"}
    }

    response = await rpc_node._handle_single_request(notification)

    # Notifications should return None (no response)
    assert response is None


@pytest.mark.asyncio
async def test_invalid_jsonrpc_version(rpc_node):
    """Test request with invalid jsonrpc version."""
    request = {
        "jsonrpc": "1.0",
        "method": "add",
        "params": {"a": 1, "b": 2},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert response["jsonrpc"] == "2.0"
    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.INVALID_REQUEST


@pytest.mark.asyncio
async def test_missing_method(rpc_node):
    """Test request with missing method."""
    request = {
        "jsonrpc": "2.0",
        "params": {"a": 1},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert response["jsonrpc"] == "2.0"
    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.INVALID_REQUEST


@pytest.mark.asyncio
async def test_invalid_params_type(rpc_node):
    """Test request with invalid params type."""
    request = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": "invalid",  # Should be dict or list
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.INVALID_REQUEST


@pytest.mark.asyncio
async def test_parse_error(rpc_node):
    """Test parse error handling."""
    # Simulate parse error by passing invalid dict
    response = await rpc_node._handle_single_request("not a dict")

    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.INVALID_REQUEST


# ============================================================================
# Method Dispatch Tests
# ============================================================================

@pytest.mark.asyncio
async def test_method_not_found(rpc_node):
    """Test calling non-existent method."""
    request = {
        "jsonrpc": "2.0",
        "method": "nonexistent",
        "params": {},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND


@pytest.mark.asyncio
async def test_method_with_error(rpc_node):
    """Test method that raises an error."""
    request = {
        "jsonrpc": "2.0",
        "method": "error",
        "params": {},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.INTERNAL_ERROR


@pytest.mark.asyncio
async def test_invalid_params_error(rpc_node):
    """Test method with invalid parameters."""
    request = {
        "jsonrpc": "2.0",
        "method": "invalid_params",
        "params": {},  # Missing required_field
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert "error" in response
    # Should be INVALID_PARAMS or INTERNAL_ERROR depending on error handling
    assert response["error"]["code"] in [JsonRpcError.INVALID_PARAMS, JsonRpcError.INTERNAL_ERROR]


# ============================================================================
# Batch Request Tests
# ============================================================================

@pytest.mark.asyncio
async def test_batch_request(rpc_node):
    """Test batch request handling."""
    batch = [
        {"jsonrpc": "2.0", "method": "add", "params": {"a": 1, "b": 2}, "id": 1},
        {"jsonrpc": "2.0", "method": "add", "params": {"a": 3, "b": 4}, "id": 2},
    ]

    responses = await rpc_node._handle_batch(batch)

    assert len(responses) == 2
    assert responses[0]["result"] == {"sum": 3}
    assert responses[1]["result"] == {"sum": 7}


@pytest.mark.asyncio
async def test_batch_with_notifications(rpc_node):
    """Test batch with mix of requests and notifications."""
    batch = [
        {"jsonrpc": "2.0", "method": "add", "params": {"a": 1, "b": 2}, "id": 1},
        {"jsonrpc": "2.0", "method": "echo", "params": {"x": "y"}},  # Notification
        {"jsonrpc": "2.0", "method": "add", "params": {"a": 5, "b": 5}, "id": 2},
    ]

    responses = await rpc_node._handle_batch(batch)

    # Filter out None (notifications)
    responses = [r for r in responses if r is not None]

    assert len(responses) == 2
    assert responses[0]["id"] == 1
    assert responses[1]["id"] == 2


@pytest.mark.asyncio
async def test_batch_with_errors(rpc_node):
    """Test batch with some errors."""
    batch = [
        {"jsonrpc": "2.0", "method": "add", "params": {"a": 1, "b": 2}, "id": 1},
        {"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 2},
        {"jsonrpc": "2.0", "method": "error", "params": {}, "id": 3},
    ]

    responses = await rpc_node._handle_batch(batch)

    assert len(responses) == 3
    assert "result" in responses[0]
    assert "error" in responses[1]
    assert responses[1]["error"]["code"] == JsonRpcError.METHOD_NOT_FOUND
    assert "error" in responses[2]
    assert responses[2]["error"]["code"] == JsonRpcError.INTERNAL_ERROR


# ============================================================================
# Method Dispatch Logic Tests
# ============================================================================

@pytest.mark.asyncio
async def test_dispatch_with_dict_params(rpc_node):
    """Test method dispatch with dict params."""
    context = ExecutionContext(inputs=MagicMock(), state={})

    result = await rpc_node._dispatch_rpc_method(
        "add",
        {"a": 10, "b": 20},
        context
    )

    assert result == {"sum": 30}


@pytest.mark.asyncio
async def test_dispatch_method_name_conversion(rpc_node):
    """Test that method names with dots/dashes are converted correctly."""
    # Add a method with dots in the name
    async def rpc_user_create(self, params, context):
        return {"created": True}

    rpc_node.rpc_user_create = rpc_user_create.__get__(rpc_node, TestRpcNode)

    context = ExecutionContext(inputs=MagicMock(), state={})

    result = await rpc_node._dispatch_rpc_method(
        "user.create",  # Should map to rpc_user_create
        {},
        context
    )

    assert result == {"created": True}


# ============================================================================
# Hooks Tests
# ============================================================================

@pytest.mark.asyncio
async def test_before_request_hook(rpc_node):
    """Test before_request hook is called."""
    called = False

    async def mock_before_request(method, params, request_id):
        nonlocal called
        called = True
        assert method == "add"
        assert params == {"a": 1, "b": 2}
        assert request_id == 1

    rpc_node.before_request = mock_before_request

    request = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"a": 1, "b": 2},
        "id": 1
    }

    await rpc_node._handle_single_request(request)
    assert called


@pytest.mark.asyncio
async def test_after_request_hook(rpc_node):
    """Test after_request hook is called."""
    called = False

    async def mock_after_request(method, params, request_id, result, error):
        nonlocal called
        called = True
        assert method == "add"
        assert result == {"sum": 3}
        assert error is None

    rpc_node.after_request = mock_after_request

    request = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"a": 1, "b": 2},
        "id": 1
    }

    await rpc_node._handle_single_request(request)
    assert called


# ============================================================================
# WebSocket Tests
# ============================================================================

@pytest.mark.asyncio
async def test_send_notification_to_client(rpc_node):
    """Test sending notification to specific WebSocket client."""
    # Mock WebSocket
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()

    # Add to clients
    client_id = "test_client"
    rpc_node.websocket_clients[client_id] = mock_ws

    # Send notification
    await rpc_node.send_notification_to_client(
        client_id,
        "test_method",
        {"data": "test"}
    )

    # Verify send_json was called with correct data
    mock_ws.send_json.assert_called_once()
    call_args = mock_ws.send_json.call_args[0][0]
    assert call_args["jsonrpc"] == "2.0"
    assert call_args["method"] == "test_method"
    assert call_args["params"] == {"data": "test"}
    assert "id" not in call_args  # Notifications don't have id


@pytest.mark.asyncio
async def test_broadcast_notification(rpc_node):
    """Test broadcasting notification to all WebSocket clients."""
    # Mock multiple WebSocket clients
    mock_ws1 = AsyncMock()
    mock_ws2 = AsyncMock()
    mock_ws1.send_json = AsyncMock()
    mock_ws2.send_json = AsyncMock()

    rpc_node.websocket_clients["client1"] = mock_ws1
    rpc_node.websocket_clients["client2"] = mock_ws2

    # Broadcast
    await rpc_node.broadcast_notification("broadcast_test", {"msg": "hello"})

    # Verify both clients received the notification
    assert mock_ws1.send_json.call_count == 1
    assert mock_ws2.send_json.call_count == 1


# ============================================================================
# Error Response Tests
# ============================================================================

def test_error_dict_format(rpc_node):
    """Test error dict formatting."""
    error = rpc_node._error_dict(
        request_id=123,
        code=-32600,
        message="Invalid Request",
        data={"extra": "info"}
    )

    assert error["jsonrpc"] == "2.0"
    assert error["error"]["code"] == -32600
    assert error["error"]["message"] == "Invalid Request"
    assert error["error"]["data"] == {"extra": "info"}
    assert error["id"] == 123


def test_error_dict_without_data(rpc_node):
    """Test error dict without data field."""
    error = rpc_node._error_dict(
        request_id=456,
        code=-32601,
        message="Method not found"
    )

    assert "data" not in error["error"]


# ============================================================================
# Request Timeout Tests
# ============================================================================

@pytest.mark.asyncio
async def test_request_timeout(rpc_node):
    """Test request timeout handling."""
    # Set very short timeout
    rpc_node.request_timeout = 0.1

    # Create a method that takes longer than timeout
    async def rpc_slow(self, params, context):
        await asyncio.sleep(1.0)
        return {"done": True}

    rpc_node.rpc_slow = rpc_slow.__get__(rpc_node, TestRpcNode)

    request = {
        "jsonrpc": "2.0",
        "method": "slow",
        "params": {},
        "id": 1
    }

    response = await rpc_node._handle_single_request(request)

    assert "error" in response
    assert response["error"]["code"] == JsonRpcError.TIMEOUT_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
