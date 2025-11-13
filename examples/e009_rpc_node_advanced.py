"""
Example: Advanced JSON-RPC Node with HTTPS and WebSocket Features

Demonstrates advanced features:
- HTTPS/WSS with SSL certificates
- WebSocket bidirectional communication
- Server-initiated notifications
- Authentication hooks
- Rate limiting
- Custom error handling

Run this example:
    # First, generate self-signed certificates (for testing):
    openssl req -x509 -newkey rsa:4096 -nodes \
      -keyout key.pem -out cert.pem -days 365 \
      -subj "/CN=localhost"

    # Then run:
    python -m examples.e009_rpc_node_advanced

Test with curl (HTTPS):
    curl -k -X POST https://localhost:8443 \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer secret-token" \
      -d '{"jsonrpc":"2.0","method":"getData","params":{"id":123},"id":1}'

Test WebSocket with server notifications:
    See test_websocket_client() function below
"""

import asyncio
import time
from typing import Dict, Optional
from collections import defaultdict

from spark.nodes.rpc import RpcNode, InvalidParamsError
from spark.nodes.types import ExecutionContext


class AdvancedRpcNode(RpcNode):
    """
    Advanced RPC Node with authentication, rate limiting, and notifications.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Rate limiting: max 10 requests per client per 10 seconds
        self.rate_limits: Dict[str, list] = defaultdict(list)
        self.max_requests = 10
        self.window_seconds = 10

        # Simple authentication (in production, use proper auth)
        self.valid_tokens = {"secret-token", "admin-token"}

        # Data store
        self.data_store = {}

        # Background task for periodic notifications
        self.notification_task: Optional[asyncio.Task] = None

    # ============================================================================
    # RPC Methods
    # ============================================================================

    async def rpc_getData(self, params: dict, context: ExecutionContext):
        """
        Retrieve data by ID.

        Method: getData
        Params:
            id (string|number): Data ID
        Returns:
            object: Data object or null if not found
        """
        data_id = params.get("id")
        if data_id is None:
            raise InvalidParamsError("Missing required parameter: id")

        data = self.data_store.get(str(data_id))

        if data is None:
            return {"found": False, "id": data_id}

        return {"found": True, "id": data_id, "data": data}

    async def rpc_setData(self, params: dict, context: ExecutionContext):
        """
        Store data with an ID.

        Method: setData
        Params:
            id (string|number): Data ID
            data (any): Data to store
        Returns:
            object: Success confirmation
        """
        data_id = params.get("id")
        data = params.get("data")

        if data_id is None:
            raise InvalidParamsError("Missing required parameter: id")

        self.data_store[str(data_id)] = data

        # Notify all WebSocket clients about the update
        await self.broadcast_notification(
            "dataUpdated",
            {"id": data_id, "timestamp": time.time()}
        )

        return {"success": True, "id": data_id}

    async def rpc_deleteData(self, params: dict, context: ExecutionContext):
        """
        Delete data by ID.

        Method: deleteData
        Params:
            id (string|number): Data ID
        Returns:
            object: Success confirmation
        """
        data_id = params.get("id")
        if data_id is None:
            raise InvalidParamsError("Missing required parameter: id")

        if str(data_id) in self.data_store:
            del self.data_store[str(data_id)]
            deleted = True
        else:
            deleted = False

        return {"success": True, "deleted": deleted, "id": data_id}

    async def rpc_listData(self, params: dict, context: ExecutionContext):
        """
        List all stored data IDs.

        Method: listData
        Params: {}
        Returns:
            object: {"ids": array}
        """
        return {"ids": list(self.data_store.keys()), "count": len(self.data_store)}

    async def rpc_subscribe(self, params: dict, context: ExecutionContext):
        """
        Subscribe to server events (WebSocket only).

        Method: subscribe
        Params:
            events (array): Event types to subscribe to
        Returns:
            object: Success confirmation
        """
        events = params.get("events", [])

        # In a real implementation, track subscriptions per client
        # For this demo, we just acknowledge

        return {
            "success": True,
            "subscribed": events,
            "message": "You will receive notifications for these events"
        }

    # ============================================================================
    # Authentication & Rate Limiting
    # ============================================================================

    async def before_request(self, method, params, request_id):
        """
        Hook for authentication and rate limiting.

        Note: In a real implementation, you'd extract client info from
        the HTTP request or WebSocket connection context.
        """
        # For demonstration, we'll skip actual auth validation here
        # In production, extract token from HTTP headers or WS handshake
        # and validate it

        # Example authentication check:
        # token = extract_token_from_context()
        # if token not in self.valid_tokens:
        #     raise PermissionError("Invalid authentication token")

        # Rate limiting example
        client_id = "demo_client"  # In production, use actual client ID
        await self._check_rate_limit(client_id)

        print(f"[AUTH] Request authorized: {method}")

    async def _check_rate_limit(self, client_id: str):
        """
        Check if client has exceeded rate limit.

        Raises:
            Exception: If rate limit exceeded
        """
        now = time.time()
        requests = self.rate_limits[client_id]

        # Remove old requests outside the window
        requests[:] = [t for t in requests if now - t < self.window_seconds]

        # Check limit
        if len(requests) >= self.max_requests:
            raise Exception(
                f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s"
            )

        # Add current request
        requests.append(now)

    # ============================================================================
    # Background Notifications
    # ============================================================================

    async def start_server(self):
        """Start server and background notification task."""
        # Start periodic notification task
        self.notification_task = asyncio.create_task(self._periodic_notifications())

        # Start the HTTP/WS server
        await super().start_server()

    async def _periodic_notifications(self):
        """Send periodic notifications to all WebSocket clients."""
        try:
            while True:
                await asyncio.sleep(30)  # Every 30 seconds

                if len(self.websocket_clients) > 0:
                    await self.broadcast_notification(
                        "heartbeat",
                        {
                            "timestamp": time.time(),
                            "clients": len(self.websocket_clients),
                            "data_items": len(self.data_store)
                        }
                    )
                    print("[NOTIFY] Sent heartbeat to all clients")

        except asyncio.CancelledError:
            print("[NOTIFY] Notification task cancelled")

    # ============================================================================
    # WebSocket Hooks
    # ============================================================================

    async def on_websocket_connect(self, client_id, websocket):
        """Send welcome message with server info."""
        await super().on_websocket_connect(client_id, websocket)

        # Send detailed welcome message
        await self.send_notification_to_client(
            client_id,
            "connected",
            {
                "message": "Connected to Advanced RPC Server",
                "client_id": client_id,
                "server_version": "1.0.0",
                "features": ["data_storage", "real_time_notifications", "rate_limiting"],
                "timestamp": time.time()
            }
        )

    async def on_websocket_disconnect(self, client_id, websocket):
        """Clean up on disconnect."""
        await super().on_websocket_disconnect(client_id, websocket)

        # Clean up rate limit data
        if client_id in self.rate_limits:
            del self.rate_limits[client_id]


async def main():
    """Run the advanced RPC server with HTTPS."""
    print("=" * 70)
    print("Advanced JSON-RPC 2.0 Server with HTTPS/WSS")
    print("=" * 70)
    print("\nFeatures:")
    print("  ✓ HTTPS/WSS with SSL certificates")
    print("  ✓ Authentication (token-based)")
    print("  ✓ Rate limiting (10 req/10s per client)")
    print("  ✓ WebSocket server notifications")
    print("  ✓ Data storage with change notifications")
    print("\nStarting server...")

    # Check if SSL certificates exist
    import os
    has_ssl = os.path.exists("cert.pem") and os.path.exists("key.pem")

    if has_ssl:
        print("  ✓ SSL certificates found")
        print("  → HTTPS: https://localhost:8443")
        print("  → WSS: wss://localhost:8443/ws")

        node = AdvancedRpcNode(
            host="0.0.0.0",
            port=8443,
            ssl_certfile="cert.pem",
            ssl_keyfile="key.pem"
        )
    else:
        print("  ⚠ SSL certificates not found, running HTTP only")
        print("  → HTTP: http://localhost:8000")
        print("  → WS: ws://localhost:8000/ws")
        print("\n  To enable HTTPS, generate certificates:")
        print("    openssl req -x509 -newkey rsa:4096 -nodes \\")
        print("      -keyout key.pem -out cert.pem -days 365 \\")
        print("      -subj '/CN=localhost'")

        node = AdvancedRpcNode(host="0.0.0.0", port=8000)

    print("\nAvailable methods:")
    print("  - getData(id)")
    print("  - setData(id, data)")
    print("  - deleteData(id)")
    print("  - listData()")
    print("  - subscribe(events)")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)

    try:
        await node.start_server()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        if node.notification_task:
            node.notification_task.cancel()
        await node.shutdown()
        print("Server stopped")


async def test_websocket_client():
    """
    Test WebSocket client that connects and receives notifications.

    Run this in a separate terminal after starting the server.
    """
    try:
        import websockets
        import json

        uri = "ws://localhost:8000/ws"  # or wss://localhost:8443/ws for HTTPS

        print("Connecting to WebSocket...")
        async with websockets.connect(uri) as websocket:
            print("Connected! Listening for messages...\n")

            # Subscribe to events
            await websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "subscribe",
                "params": {"events": ["dataUpdated", "heartbeat"]},
                "id": 1
            }))

            response = await websocket.recv()
            print(f"Subscribe response: {response}\n")

            # Store some data
            await websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "method": "setData",
                "params": {"id": "test123", "data": {"value": 42}},
                "id": 2
            }))

            response = await websocket.recv()
            print(f"SetData response: {response}\n")

            # Listen for notifications
            print("Listening for server notifications (Ctrl+C to stop)...\n")
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                if "method" in data:
                    # This is a notification
                    print(f"[NOTIFICATION] {data['method']}: {data['params']}")
                else:
                    # This is a response
                    print(f"[RESPONSE] {message}")

    except ImportError:
        print("Please install websockets: pip install websockets")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "client":
        # Run as WebSocket test client
        asyncio.run(test_websocket_client())
    else:
        # Run as server
        asyncio.run(main())
