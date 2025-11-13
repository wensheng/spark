"""
Example: Basic JSON-RPC Node Server

Demonstrates how to create a simple JSON-RPC 2.0 server using RpcNode.

Run this example:
    python -m examples.e008_rpc_node_basic

Test with curl (HTTP):
    # Request with response
    curl -X POST http://localhost:8000 \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"add","params":{"a":5,"b":3},"id":1}'

    # Notification (no response)
    curl -X POST http://localhost:8000 \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc":"2.0","method":"log","params":{"message":"Hello"}}'

    # Batch request
    curl -X POST http://localhost:8000 \
      -H "Content-Type: application/json" \
      -d '[
        {"jsonrpc":"2.0","method":"add","params":{"a":1,"b":2},"id":1},
        {"jsonrpc":"2.0","method":"multiply","params":{"a":3,"b":4},"id":2}
      ]'

    # Health check
    curl http://localhost:8000/health

Test with WebSocket (Python):
    import asyncio
    import websockets
    import json

    async def test_ws():
        uri = "ws://localhost:8000/ws"
        async with websockets.connect(uri) as websocket:
            # Send request
            await websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 10, "b": 20},
                "id": 1
            }))
            # Receive response
            response = await websocket.recv()
            print(f"Response: {response}")

    asyncio.run(test_ws())
"""

import asyncio
from spark.nodes.rpc import RpcNode
from spark.nodes.types import ExecutionContext


class CalculatorNode(RpcNode):
    """
    A simple calculator exposed as JSON-RPC 2.0 service.

    Implements basic arithmetic operations.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.operation_count = 0

    # ============================================================================
    # RPC Method Handlers
    # ============================================================================

    async def rpc_add(self, params: dict, context: ExecutionContext):
        """
        Add two numbers.

        Method: add
        Params:
            a (number): First number
            b (number): Second number
        Returns:
            object: {"sum": number}
        """
        a = params.get("a", 0)
        b = params.get("b", 0)

        self.operation_count += 1
        result = a + b

        print(f"[RPC] add({a}, {b}) = {result}")

        return {"sum": result, "operation": "add"}

    async def rpc_subtract(self, params: dict, context: ExecutionContext):
        """
        Subtract two numbers.

        Method: subtract
        Params:
            a (number): Minuend
            b (number): Subtrahend
        Returns:
            object: {"difference": number}
        """
        a = params.get("a", 0)
        b = params.get("b", 0)

        self.operation_count += 1
        result = a - b

        print(f"[RPC] subtract({a}, {b}) = {result}")

        return {"difference": result, "operation": "subtract"}

    async def rpc_multiply(self, params: dict, context: ExecutionContext):
        """
        Multiply two numbers.

        Method: multiply
        Params:
            a (number): First factor
            b (number): Second factor
        Returns:
            object: {"product": number}
        """
        a = params.get("a", 1)
        b = params.get("b", 1)

        self.operation_count += 1
        result = a * b

        print(f"[RPC] multiply({a}, {b}) = {result}")

        return {"product": result, "operation": "multiply"}

    async def rpc_divide(self, params: dict, context: ExecutionContext):
        """
        Divide two numbers.

        Method: divide
        Params:
            a (number): Dividend
            b (number): Divisor
        Returns:
            object: {"quotient": number}
        """
        a = params.get("a", 0)
        b = params.get("b", 1)

        if b == 0:
            from spark.nodes.rpc import InvalidParamsError
            raise InvalidParamsError("Cannot divide by zero")

        self.operation_count += 1
        result = a / b

        print(f"[RPC] divide({a}, {b}) = {result}")

        return {"quotient": result, "operation": "divide"}

    async def rpc_stats(self, params: dict, context: ExecutionContext):
        """
        Get server statistics.

        Method: stats
        Params: {}
        Returns:
            object: Statistics
        """
        return {
            "operation_count": self.operation_count,
            "websocket_clients": len(self.websocket_clients),
            "pending_requests": len(self.pending_requests)
        }

    async def rpc_log(self, params: dict, context: ExecutionContext):
        """
        Log a message (notification - no response expected).

        Method: log
        Params:
            message (string): Message to log
            level (string): Log level (optional, default: "info")
        Returns:
            null (this is typically used as a notification)
        """
        message = params.get("message", "")
        level = params.get("level", "info")

        print(f"[{level.upper()}] {message}")

        return {"logged": True}

    # ============================================================================
    # Hooks
    # ============================================================================

    async def before_request(self, method, params, request_id):
        """Log all incoming requests."""
        req_type = "notification" if request_id is None else "request"
        print(f"[BEFORE] {req_type} - method: {method}, id: {request_id}")

    async def after_request(self, method, params, request_id, result, error):
        """Log all completed requests."""
        status = "error" if error else "success"
        print(f"[AFTER] method: {method}, status: {status}")

    async def on_websocket_connect(self, client_id, websocket):
        """Log WebSocket connections."""
        print(f"[WS] Client connected: {client_id}")

        # Send welcome notification
        await self.send_notification_to_client(
            client_id,
            "welcome",
            {"message": "Connected to Calculator RPC", "client_id": client_id}
        )

    async def on_websocket_disconnect(self, client_id, websocket):
        """Log WebSocket disconnections."""
        print(f"[WS] Client disconnected: {client_id}")


async def main():
    """Run the calculator RPC server."""
    print("=" * 60)
    print("Calculator JSON-RPC 2.0 Server")
    print("=" * 60)
    print("\nStarting server on http://localhost:8000")
    print("WebSocket endpoint: ws://localhost:8000/ws")
    print("\nAvailable methods:")
    print("  - add(a, b)")
    print("  - subtract(a, b)")
    print("  - multiply(a, b)")
    print("  - divide(a, b)")
    print("  - stats()")
    print("  - log(message, level)")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    # Create and start server
    node = CalculatorNode(host="0.0.0.0", port=8000)

    try:
        await node.start_server()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        await node.shutdown()
        print("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
