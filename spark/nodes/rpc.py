"""
JSON-RPC 2.0 Node Server Implementation

Provides a Node subclass that exposes itself as a JSON-RPC 2.0 server
supporting both HTTP and WebSocket transports with optional HTTPS/WSS.

Example usage:
    class MyRpcNode(RpcNode):
        async def rpc_add(self, params, context):
            return {"sum": params["a"] + params["b"]}

    node = MyRpcNode(host="0.0.0.0", port=8000)
    await node.start_server()

Spec: https://www.jsonrpc.org/specification
"""

import asyncio
import json
import ssl
import time
import traceback
from typing import Any, Dict, List, Optional, Union

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

from spark.nodes import Node
from spark.nodes.channels import ChannelMessage
from spark.nodes.types import ExecutionContext


# JSON-RPC 2.0 Error Codes
class JsonRpcError:
    """Standard JSON-RPC 2.0 error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Server errors (-32000 to -32099)
    SERVER_ERROR = -32000
    TIMEOUT_ERROR = -32001
    RATE_LIMIT_ERROR = -32002


class RpcNode(Node):
    """
    A Node that exposes itself as a JSON-RPC 2.0 server.

    Supports:
    - HTTP POST requests (single and batch)
    - WebSocket connections (bidirectional)
    - HTTPS/WSS with SSL certificates
    - Full JSON-RPC 2.0 specification
    - Request/response pattern with timeouts
    - Notifications (no response expected)

    Args:
        host: Host to bind to (default: "127.0.0.1")
        port: Port to bind to (default: 8000)
        ssl_certfile: Path to SSL certificate file for HTTPS
        ssl_keyfile: Path to SSL key file for HTTPS
        ssl_ca_certs: Path to CA certificates file (optional)
        request_timeout: Timeout for RPC request processing (default: 30s)
        **kwargs: Additional Node configuration

    Methods to override:
        - rpc_<method_name>: Handle specific RPC methods
        - before_request: Hook called before each request
        - after_request: Hook called after each request
        - on_websocket_connect: Hook called when WebSocket connects
        - on_websocket_disconnect: Hook called when WebSocket disconnects
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        ssl_ca_certs: Optional[str] = None,
        request_timeout: float = 30.0,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.host = host
        self.port = port
        self.ssl_certfile = ssl_certfile
        self.ssl_keyfile = ssl_keyfile
        self.ssl_ca_certs = ssl_ca_certs
        self.request_timeout = request_timeout

        # Track pending requests for response routing
        self.pending_requests: Dict[Union[str, int], asyncio.Future] = {}

        # Track active WebSocket connections
        self.websocket_clients: Dict[str, WebSocket] = {}
        self._ws_counter = 0

        # Server state
        self.server: Optional[uvicorn.Server] = None
        self.server_task: Optional[asyncio.Task] = None
        self.node_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Build Starlette application
        self.app = self._build_app()

    def _build_app(self) -> Starlette:
        """Build Starlette application with routes."""
        return Starlette(
            routes=[
                Route("/", self._handle_http_rpc, methods=["POST"]),
                Route("/health", self._health_check, methods=["GET"]),
                WebSocketRoute("/ws", self._handle_websocket),
            ],
            on_shutdown=[self._on_app_shutdown],
        )

    # ============================================================================
    # HTTP Endpoint
    # ============================================================================

    async def _handle_http_rpc(self, request):
        """Handle HTTP POST JSON-RPC 2.0 requests."""
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return self._json_error_response(None, JsonRpcError.PARSE_ERROR, "Parse error")

        # Handle batch requests
        if isinstance(body, list):
            if len(body) == 0:
                return self._json_error_response(None, JsonRpcError.INVALID_REQUEST, "Invalid Request")

            responses = await self._handle_batch(body)
            # Filter out None (notifications have no response)
            responses = [r for r in responses if r is not None]

            if len(responses) == 0:
                # All were notifications
                return Response(status_code=204)

            return JSONResponse(responses)

        # Handle single request
        response = await self._handle_single_request(body)

        if response is None:
            # Notification - no response
            return Response(status_code=204)

        return JSONResponse(response)

    async def _handle_batch(self, requests: List[Dict]) -> List[Optional[Dict]]:
        """Handle batch JSON-RPC requests."""
        tasks = [self._handle_single_request(req) for req in requests]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error responses
        results = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                request_id = requests[i].get("id")
                results.append(
                    self._error_dict(request_id, JsonRpcError.INTERNAL_ERROR, f"Internal error: {str(response)}")
                )
            else:
                results.append(response)

        return results

    async def _handle_single_request(self, body: Dict) -> Optional[Dict]:
        """
        Handle a single JSON-RPC 2.0 request.

        Returns:
            Response dict or None for notifications
        """
        # Validate JSON-RPC 2.0 format
        if not isinstance(body, dict):
            return self._error_dict(None, JsonRpcError.INVALID_REQUEST, "Invalid Request")

        jsonrpc = body.get("jsonrpc")
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")

        # Validate required fields
        if jsonrpc != "2.0":
            return self._error_dict(request_id, JsonRpcError.INVALID_REQUEST, "Invalid Request: jsonrpc must be '2.0'")

        if not isinstance(method, str):
            return self._error_dict(request_id, JsonRpcError.INVALID_REQUEST, "Invalid Request: method must be string")

        if not isinstance(params, (dict, list)):
            return self._error_dict(
                request_id, JsonRpcError.INVALID_REQUEST, "Invalid Request: params must be object or array"
            )

        # Process the request
        try:
            result = await self._process_rpc_request(method, params, request_id)

            # Notification (no id) - don't send response
            if request_id is None:
                return None

            return {"jsonrpc": "2.0", "result": result, "id": request_id}

        except MethodNotFoundError as e:
            if request_id is None:
                return None
            return self._error_dict(request_id, JsonRpcError.METHOD_NOT_FOUND, str(e))

        except InvalidParamsError as e:
            if request_id is None:
                return None
            return self._error_dict(request_id, JsonRpcError.INVALID_PARAMS, str(e))

        except asyncio.TimeoutError:
            if request_id is None:
                return None
            return self._error_dict(request_id, JsonRpcError.TIMEOUT_ERROR, "Request timeout")

        except Exception as e:
            if request_id is None:
                return None
            return self._error_dict(request_id, JsonRpcError.INTERNAL_ERROR, f"Internal error: {str(e)}")

    # ============================================================================
    # WebSocket Endpoint
    # ============================================================================

    async def _handle_websocket(self, websocket: WebSocket):
        """Handle WebSocket JSON-RPC 2.0 connections."""
        await websocket.accept()

        # Generate client ID
        self._ws_counter += 1
        client_id = f"ws_{self._ws_counter}_{int(time.time() * 1000)}"
        self.websocket_clients[client_id] = websocket

        try:
            # Call hook
            await self.on_websocket_connect(client_id, websocket)

            # Process messages
            while True:
                # Receive message
                try:
                    data = await websocket.receive_text()
                except WebSocketDisconnect:
                    break

                # Parse JSON
                try:
                    body = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json(self._error_dict(None, JsonRpcError.PARSE_ERROR, "Parse error"))
                    continue

                # Handle batch or single request
                if isinstance(body, list):
                    responses = await self._handle_batch(body)
                    # Send non-notification responses
                    responses = [r for r in responses if r is not None]
                    if len(responses) > 0:
                        await websocket.send_json(responses)
                else:
                    response = await self._handle_single_request(body)
                    if response is not None:
                        await websocket.send_json(response)

        except Exception as e:
            print(f"WebSocket error for {client_id}: {e}")
            traceback.print_exc()

        finally:
            # Cleanup
            self.websocket_clients.pop(client_id, None)
            await self.on_websocket_disconnect(client_id, websocket)

    async def send_notification_to_client(self, client_id: str, method: str, params: Union[Dict, List]):
        """
        Send a JSON-RPC notification to a specific WebSocket client.

        Args:
            client_id: WebSocket client ID
            method: RPC method name
            params: Method parameters
        """
        if client_id not in self.websocket_clients:
            raise ValueError(f"Client {client_id} not connected")

        websocket = self.websocket_clients[client_id]
        notification = {"jsonrpc": "2.0", "method": method, "params": params}

        await websocket.send_json(notification)

    async def broadcast_notification(self, method: str, params: Union[Dict, List]):
        """
        Broadcast a JSON-RPC notification to all connected WebSocket clients.

        Args:
            method: RPC method name
            params: Method parameters
        """
        notification = {"jsonrpc": "2.0", "method": method, "params": params}

        # Send to all clients
        tasks = []
        for websocket in self.websocket_clients.values():
            tasks.append(websocket.send_json(notification))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ============================================================================
    # RPC Request Processing
    # ============================================================================

    async def _process_rpc_request(
        self, method: str, params: Union[Dict, List], request_id: Optional[Union[str, int]]
    ) -> Any:
        """
        Process a JSON-RPC request by putting it in the node's mailbox.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Request ID (None for notifications)

        Returns:
            Result from RPC method handler
        """
        # Call before_request hook
        await self.before_request(method, params, request_id)

        # Create future to wait for response (if not a notification)
        future = None
        if request_id is not None:
            future = asyncio.Future()
            self.pending_requests[request_id] = future

        # Create mailbox message
        message = ChannelMessage(
            payload={
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": request_id,
                "_is_rpc": True,
                "_timestamp": time.time(),
            }
        )

        # Send to mailbox for node to process
        await self.mailbox.send(message)

        # If notification, return immediately
        if request_id is None:
            return None

        # Wait for response with timeout
        assert future is not None, "Future should not be None for non-notification requests"
        try:
            result = await asyncio.wait_for(future, timeout=self.request_timeout)

            # Call after_request hook
            await self.after_request(method, params, request_id, result, None)

            return result

        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            await self.after_request(method, params, request_id, None, "timeout")
            raise

        except Exception as e:
            self.pending_requests.pop(request_id, None)
            await self.after_request(method, params, request_id, None, str(e))
            raise

    async def process(self, context: ExecutionContext):
        """
        Process messages from mailbox (both RPC and regular messages).

        Override this method if you need custom message processing logic.
        For handling RPC methods, override rpc_<method> methods instead.
        """
        message = context.inputs.content

        # Check if this is an RPC message
        if message.get("_is_rpc"):
            return await self._handle_rpc_message(message, context)
        else:
            # Regular node message (not from RPC)
            return await self._process_regular_message(message, context)

    async def _handle_rpc_message(self, message: Dict, context: ExecutionContext):
        """Handle RPC message from mailbox."""
        method = message["method"]
        params = message["params"]
        request_id = message["id"]

        try:
            # Dispatch to RPC method handler
            result = await self._dispatch_rpc_method(method, params, context)

            # Send response back to waiting HTTP/WS handler (if this was a request)
            if request_id is not None and request_id in self.pending_requests:
                future = self.pending_requests.pop(request_id)
                if not future.done():
                    future.set_result(result)

            return {"rpc_handled": True, "method": method, "success": True}

        except Exception as e:
            # Send error back to waiting handler
            if request_id is not None and request_id in self.pending_requests:
                future = self.pending_requests.pop(request_id)
                if not future.done():
                    future.set_exception(e)

            return {"rpc_handled": True, "method": method, "success": False, "error": str(e)}

    async def _dispatch_rpc_method(self, method: str, params: Union[Dict, List], context: ExecutionContext) -> Any:
        """
        Dispatch RPC method to appropriate handler.

        Looks for methods named rpc_<method> on the node instance.
        For methods with dots (e.g., "user.create"), converts to rpc_user_create.

        Args:
            method: RPC method name
            params: Method parameters
            context: Execution context

        Returns:
            Result from method handler

        Raises:
            MethodNotFoundError: If method handler not found
            InvalidParamsError: If params are invalid for method
        """
        # Convert method name to handler name (e.g., "user.create" -> "rpc_user_create")
        handler_name = f"rpc_{method.replace('.', '_').replace('-', '_')}"

        if not hasattr(self, handler_name):
            raise MethodNotFoundError(f"Method not found: {method}")

        handler = getattr(self, handler_name)

        # Call handler with params and context
        try:
            if isinstance(params, dict):
                result = await handler(params, context)
            elif isinstance(params, list):
                result = await handler(*params, context=context)
            else:
                raise InvalidParamsError(f"Invalid params type: {type(params)}")

            return result

        except TypeError as e:
            # Likely wrong number/type of parameters
            raise InvalidParamsError(f"Invalid params: {str(e)}")

    async def _process_regular_message(self, message: Dict, context: ExecutionContext):
        """
        Process non-RPC messages from mailbox.

        Override this if your node receives messages from other sources
        (e.g., other nodes in a graph).
        """
        return {"regular_message": True, "content": message}

    # ============================================================================
    # Server Lifecycle
    # ============================================================================

    async def start_server(self):
        """
        Start the HTTP/WebSocket server and node's go() loop.

        This method will run until the server is shut down.
        """
        # Start node's continuous processing loop
        self.node_task = asyncio.create_task(self.go())

        # Configure SSL if certificates provided
        ssl_context = None
        if self.ssl_certfile and self.ssl_keyfile:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=self.ssl_certfile, keyfile=self.ssl_keyfile)

            if self.ssl_ca_certs:
                ssl_context.load_verify_locations(cafile=self.ssl_ca_certs)

        # Configure uvicorn server
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            ssl_certfile=self.ssl_certfile,
            ssl_keyfile=self.ssl_keyfile,
            log_level="info",
        )

        self.server = uvicorn.Server(config)
        self.server_task = asyncio.create_task(self.server.serve())

        # Wait for server and node
        await asyncio.gather(self.node_task, self.server_task)

    async def shutdown(self):
        """Gracefully shutdown the server and node."""
        # Signal shutdown
        self._shutdown_event.set()

        # Stop HTTP server
        if self.server:
            self.server.should_exit = True

        # Close all WebSocket connections
        for websocket in list(self.websocket_clients.values()):
            await websocket.close()

        # Send shutdown message to mailbox
        await self.mailbox.send(ChannelMessage(payload={}, is_shutdown=True))

        # Wait for tasks to complete (with timeout)
        tasks = []
        if self.node_task:
            tasks.append(self.node_task)
        if self.server_task:
            tasks.append(self.server_task)

        if tasks:
            await asyncio.wait(tasks, timeout=5.0)

    async def _on_app_shutdown(self):
        """Called when Starlette app shuts down."""
        await self.shutdown()

    # ============================================================================
    # Health Check
    # ============================================================================

    async def _health_check(self, request):
        """Health check endpoint."""
        return JSONResponse({
            "status": "ok",
            "node": self.__class__.__name__,
            "websocket_clients": len(self.websocket_clients),
            "pending_requests": len(self.pending_requests),
        })

    # ============================================================================
    # Helper Methods
    # ============================================================================

    def _json_error_response(self, request_id, code: int, message: str) -> JSONResponse:
        """Create JSON-RPC error response."""
        return JSONResponse(self._error_dict(request_id, code, message))

    def _error_dict(self, request_id: Optional[Union[str, int]], code: int, message: str, data: Any = None) -> Dict:
        """Create JSON-RPC error dict."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data

        return {"jsonrpc": "2.0", "error": error, "id": request_id}

    # ============================================================================
    # Hooks (Override in Subclasses)
    # ============================================================================

    async def before_request(self, method: str, params: Union[Dict, List], request_id: Optional[Union[str, int]]):
        """
        Hook called before processing each RPC request.

        Override this for logging, authentication, rate limiting, etc.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Request ID (None for notifications)
        """
        pass

    async def after_request(
        self,
        method: str,
        params: Union[Dict, List],
        request_id: Optional[Union[str, int]],
        result: Any,
        error: Optional[str],
    ):
        """
        Hook called after processing each RPC request.

        Override this for logging, metrics, etc.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Request ID (None for notifications)
            result: Result from method handler (None if error)
            error: Error message (None if success)
        """
        pass

    async def on_websocket_connect(self, client_id: str, websocket: WebSocket):
        """
        Hook called when a WebSocket client connects.

        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection
        """
        pass

    async def on_websocket_disconnect(self, client_id: str, websocket: WebSocket):
        """
        Hook called when a WebSocket client disconnects.

        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection
        """
        pass


# ============================================================================
# Exceptions
# ============================================================================


class MethodNotFoundError(Exception):
    """Raised when RPC method is not found."""

    pass


class InvalidParamsError(Exception):
    """Raised when RPC method parameters are invalid."""

    pass
