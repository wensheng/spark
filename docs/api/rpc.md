# RPC Classes

This document provides comprehensive API reference for Spark's RPC (Remote Procedure Call) system. These classes enable distributed workflows by exposing nodes as JSON-RPC 2.0 services and calling remote services from local graphs.

## Table of Contents

- [RpcNode](#rpcnode)
- [RemoteRpcProxyNode](#remoterpcproxynode)
- [RemoteRpcProxyConfig](#remoterpcproxyconfig)
- [Transport Classes](#transport-classes)
  - [JsonRpcTransport](#jsonrpctransport)
  - [HttpJsonRpcTransport](#httpjsonrpctransport)
  - [WebSocketJsonRpcTransport](#websocketjsonrpctransport)
- [Error Codes and Exceptions](#error-codes-and-exceptions)
- [Message Formats](#message-formats)

---

## RpcNode

**Module**: `spark.nodes.rpc`

**Inheritance**: `Node`

### Overview

`RpcNode` is a Node subclass that exposes itself as a JSON-RPC 2.0 server. It supports HTTP POST requests, WebSocket connections, and HTTPS/WSS with SSL certificates. The node complies with the full JSON-RPC 2.0 specification and provides request/response patterns with timeouts, notifications, and server-initiated push messages.

### Class Signature

```python
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
    """
```

### Constructor

```python
def __init__(
    self,
    host: str = "127.0.0.1",
    port: int = 8000,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
    ssl_ca_certs: Optional[str] = None,
    request_timeout: float = 30.0,
    **kwargs
) -> None
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | `str` | `"127.0.0.1"` | Host to bind to |
| `port` | `int` | `8000` | Port to bind to |
| `ssl_certfile` | `Optional[str]` | `None` | Path to SSL certificate file for HTTPS |
| `ssl_keyfile` | `Optional[str]` | `None` | Path to SSL key file for HTTPS |
| `ssl_ca_certs` | `Optional[str]` | `None` | Path to CA certificates file (optional) |
| `request_timeout` | `float` | `30.0` | Timeout for RPC request processing in seconds |
| `**kwargs` | - | - | Additional Node configuration |

### Key Attributes

#### `pending_requests: Dict[Union[str, int], asyncio.Future]`
Tracks pending requests for response routing. Maps request IDs to futures awaiting responses.

#### `websocket_clients: Dict[str, WebSocket]`
Tracks active WebSocket connections. Maps client IDs to WebSocket instances.

#### `server: Optional[uvicorn.Server]`
The underlying uvicorn server instance.

#### `app: Starlette`
The Starlette application with routes for HTTP and WebSocket endpoints.

### RPC Method Handlers

To handle RPC methods, override methods named `rpc_<method>` on your RpcNode subclass:

```python
async def rpc_<method_name>(self, params: Union[Dict, List], context: ExecutionContext) -> Any
```

**Method Name Conversion**: Methods with dots or dashes are converted to underscores. For example:
- `user.create` → `rpc_user_create`
- `data-fetch` → `rpc_data_fetch`

**Parameters**:
- `params`: Method parameters (dict or list depending on JSON-RPC call)
- `context`: ExecutionContext with request metadata

**Returns**: Result to be sent back to client (will be JSON-serialized)

**Raises**:
- `MethodNotFoundError`: If method handler not found
- `InvalidParamsError`: If params are invalid for method

### Key Methods

#### `start_server()`

Start the HTTP/WebSocket server and node's continuous processing loop.

```python
async def start_server(self) -> None
```

This method will run until the server is shut down. It starts both the uvicorn server and the node's `go()` loop for processing messages.

**Example**:
```python
node = MyRpcNode(host="0.0.0.0", port=8000)
await node.start_server()
```

#### `stop_server()`

Stop the server and node processing gracefully.

```python
async def stop_server(self) -> None
```

#### `send_notification_to_client()`

Send a JSON-RPC notification to a specific WebSocket client.

```python
async def send_notification_to_client(
    self,
    client_id: str,
    method: str,
    params: Union[Dict, List]
) -> None
```

**Parameters**:
- `client_id`: WebSocket client ID
- `method`: RPC method name
- `params`: Method parameters

**Raises**: `ValueError` if client not connected

#### `broadcast_notification()`

Broadcast a JSON-RPC notification to all connected WebSocket clients.

```python
async def broadcast_notification(
    self,
    method: str,
    params: Union[Dict, List]
) -> None
```

**Parameters**:
- `method`: RPC method name
- `params`: Method parameters

### Lifecycle Hooks

Override these methods for custom behavior:

#### `before_request()`

Called before each RPC request is processed.

```python
async def before_request(
    self,
    method: str,
    params: Union[Dict, List],
    request_id: Optional[Union[str, int]]
) -> None
```

Use for authentication, logging, rate limiting, etc.

#### `after_request()`

Called after each RPC request completes.

```python
async def after_request(
    self,
    method: str,
    params: Union[Dict, List],
    request_id: Optional[Union[str, int]],
    result: Any,
    error: Optional[str]
) -> None
```

Use for logging, metrics, cleanup, etc.

#### `on_websocket_connect()`

Called when a WebSocket client connects.

```python
async def on_websocket_connect(
    self,
    client_id: str,
    websocket: WebSocket
) -> None
```

#### `on_websocket_disconnect()`

Called when a WebSocket client disconnects.

```python
async def on_websocket_disconnect(
    self,
    client_id: str,
    websocket: WebSocket
) -> None
```

### Endpoints

The RpcNode exposes three endpoints:

1. **HTTP RPC**: `POST /` - JSON-RPC 2.0 requests (single or batch)
2. **WebSocket**: `ws://host:port/ws` - Bidirectional JSON-RPC 2.0 over WebSocket
3. **Health Check**: `GET /health` - Server status endpoint

### Example

```python
from spark.nodes.rpc import RpcNode

class MyRpcNode(RpcNode):
    async def rpc_add(self, params, context):
        """Handle 'add' RPC method."""
        return {"sum": params["a"] + params["b"]}

    async def rpc_getData(self, params, context):
        """Handle 'getData' RPC method."""
        data_id = params.get("id")
        return {"data": self.fetch_data(data_id)}

    async def before_request(self, method, params, request_id):
        """Log all requests."""
        print(f"Request: {method} with params {params}")

    async def on_websocket_connect(self, client_id, websocket):
        """Send welcome message to new WebSocket clients."""
        await self.send_notification_to_client(
            client_id, "welcome", {"message": "Connected"}
        )

# Start server
node = MyRpcNode(host="0.0.0.0", port=8000)
await node.start_server()

# With HTTPS/WSS
node = MyRpcNode(
    host="0.0.0.0",
    port=8443,
    ssl_certfile="cert.pem",
    ssl_keyfile="key.pem"
)
await node.start_server()
```

---

## RemoteRpcProxyNode

**Module**: `spark.nodes.rpc_client`

**Inheritance**: `Node`

### Overview

`RemoteRpcProxyNode` allows local Spark graphs to proxy calls to remote RPC nodes as if they were local nodes. It transparently converts node inputs into JSON-RPC requests, forwards them over HTTP or WebSocket transport, and optionally forwards server notifications to the graph event bus.

### Class Signature

```python
class RemoteRpcProxyNode(Node):
    """Node that proxies inputs to a remote JSON-RPC service."""
```

### Constructor

```python
def __init__(
    self,
    config: Optional[RemoteRpcProxyConfig] = None,
    **kwargs: Any
) -> None
```

**Parameters**:
- `config`: RemoteRpcProxyConfig instance with endpoint and transport settings
- `**kwargs`: Additional Node configuration

### Key Methods

#### `process()`

Translate inputs into JSON-RPC request(s) and forward them to remote service.

```python
async def process(self, context: ExecutionContext) -> NodeMessage
```

**Parameters**:
- `context`: ExecutionContext with inputs to proxy

**Returns**: NodeMessage with remote response or notification status

**Raises**:
- `NodeExecutionError`: On transport failures (timeout, connection error)
- `ContextValidationError`: On invalid input format

### Input Formats

The proxy node accepts various input formats:

```python
# 1. Simple method name
context.inputs.content = "getData"

# 2. Method with parameters
context.inputs.content = {
    "method": "getData",
    "id": "test123"
}

# 3. Full JSON-RPC payload
context.inputs.content = {
    "jsonrpc": "2.0",
    "method": "getData",
    "params": {"id": "test123"},
    "id": 1
}

# 4. Notification (no response expected)
context.inputs.content = {
    "method": "log",
    "params": {"message": "Hello"},
    "notify": True
}
```

### Example

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig
from spark.nodes import Node
from spark.graphs import Graph

# Local processing node
class LocalNode(Node):
    async def process(self, context):
        # Prepare data for remote service
        return {
            'method': 'getData',
            'id': context.inputs.content.get('user_id')
        }

# Configure proxy to remote service
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://remote-server:8000",
    transport="http"
)
proxy = RemoteRpcProxyNode(config=proxy_config)

# Connect nodes
local_node = LocalNode()
local_node >> proxy

# Run graph - calls remote service transparently
graph = Graph(start=local_node)
result = await graph.run()
```

---

## RemoteRpcProxyConfig

**Module**: `spark.nodes.rpc_client`

**Inheritance**: `NodeConfig`

### Overview

Configuration class for RemoteRpcProxyNode with endpoint, transport, and behavior settings.

### Class Signature

```python
class RemoteRpcProxyConfig(NodeConfig):
    """Configuration for RemoteRpcProxyNode."""
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `endpoint` | `str` | `"http://127.0.0.1:8000"` | JSON-RPC HTTP endpoint |
| `transport` | `RemoteTransportMode` | `'http'` | Transport mode: 'http' or 'websocket' |
| `ws_endpoint` | `Optional[str]` | `None` | Explicit WebSocket endpoint (auto-derived if not provided) |
| `headers` | `dict[str, str]` | `{}` | Static headers sent with each request |
| `request_timeout` | `Optional[float]` | `30.0` | Per-request timeout in seconds |
| `connect_timeout` | `float` | `10.0` | Connect timeout for WebSocket transport |
| `default_method` | `Optional[str]` | `None` | Fallback method name if inputs don't specify one |
| `notification_topic_prefix` | `str` | `"remote.rpc"` | Event bus topic prefix for remote notifications |
| `notification_topic_key` | `str` | `"topic"` | Key name for event topic in remote params |
| `notification_payload_key` | `str` | `"payload"` | Key name for payload in remote params |
| `forward_notifications_to_event_bus` | `bool` | `True` | Publish remote notifications to graph event bus |
| `auto_connect_websocket` | `bool` | `True` | Open WebSocket connection eagerly |

### Example

```python
from spark.nodes.rpc_client import RemoteRpcProxyConfig

# HTTP transport
config = RemoteRpcProxyConfig(
    endpoint="http://api.example.com:8000",
    transport="http",
    request_timeout=60.0,
    headers={"Authorization": "Bearer token"}
)

# WebSocket transport with notifications
config = RemoteRpcProxyConfig(
    endpoint="http://api.example.com:8000",
    transport="websocket",
    auto_connect_websocket=True,
    forward_notifications_to_event_bus=True
)
```

---

## Transport Classes

### JsonRpcTransport

**Module**: `spark.nodes.rpc_transport`

**Type**: Protocol

### Overview

Protocol interface implemented by all JSON-RPC transports. Defines the common interface for HTTP and WebSocket transports.

### Protocol Methods

```python
async def connect(self) -> None
```
Establish connection to remote server (if applicable).

```python
async def close(self) -> None
```
Close the transport connection.

```python
async def request(
    self,
    payload: JsonRpcPayload,
    *,
    timeout: Optional[float] = None
) -> JsonRpcResponse
```
Send a JSON-RPC request and return the response.

```python
async def notify(self, payload: JsonRpcPayload) -> None
```
Send a JSON-RPC notification (fire-and-forget).

```python
def register_notification_handler(
    self,
    handler: NotificationHandler
) -> Callable[[], None]
```
Register a callback for server-initiated notifications. Returns unregister function.

```python
def is_connected(self) -> bool
```
Check if transport is connected.

---

### HttpJsonRpcTransport

**Module**: `spark.nodes.rpc_transport`

### Overview

JSON-RPC transport over HTTP POST requests. Suitable for synchronous request/response flows.

### Constructor

```python
def __init__(
    self,
    endpoint: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = 30.0,
    ssl_context: Optional[ssl.SSLContext] = None,
    session: Optional[ClientSession] = None
) -> None
```

**Parameters**:
- `endpoint`: HTTP endpoint URL
- `headers`: Optional HTTP headers
- `timeout`: Default request timeout in seconds
- `ssl_context`: Optional SSL context for HTTPS
- `session`: Optional aiohttp ClientSession (created automatically if not provided)

### Example

```python
from spark.nodes.rpc_transport import HttpJsonRpcTransport

transport = HttpJsonRpcTransport(
    endpoint="https://api.example.com/rpc",
    headers={"Authorization": "Bearer token"},
    timeout=60.0
)

# Send request
response = await transport.request({
    "jsonrpc": "2.0",
    "method": "getData",
    "params": {"id": "123"},
    "id": 1
})

# Send notification
await transport.notify({
    "jsonrpc": "2.0",
    "method": "log",
    "params": {"message": "Hello"}
})

await transport.close()
```

---

### WebSocketJsonRpcTransport

**Module**: `spark.nodes.rpc_transport`

### Overview

JSON-RPC transport over WebSocket connections. Supports bidirectional communication with server-initiated notifications.

### Constructor

```python
def __init__(
    self,
    endpoint: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    connect_timeout: float = 10.0,
    request_timeout: Optional[float] = 30.0,
    ssl_context: Optional[ssl.SSLContext] = None
) -> None
```

**Parameters**:
- `endpoint`: WebSocket endpoint URL (ws:// or wss://)
- `headers`: Optional headers for WebSocket handshake
- `connect_timeout`: Connection establishment timeout in seconds
- `request_timeout`: Default request timeout in seconds
- `ssl_context`: Optional SSL context for WSS

### Key Methods

#### `connect()`

Establish WebSocket connection.

```python
async def connect(self) -> None
```

#### `register_notification_handler()`

Register callback for server-initiated notifications.

```python
def register_notification_handler(
    self,
    handler: NotificationHandler
) -> Callable[[], None]
```

### Example

```python
from spark.nodes.rpc_transport import WebSocketJsonRpcTransport

transport = WebSocketJsonRpcTransport(
    endpoint="wss://api.example.com/ws",
    headers={"Authorization": "Bearer token"}
)

# Register notification handler
def on_notification(message):
    print(f"Notification: {message}")

unregister = transport.register_notification_handler(on_notification)

# Connect
await transport.connect()

# Send request
response = await transport.request({
    "jsonrpc": "2.0",
    "method": "subscribe",
    "params": {"channel": "updates"},
    "id": 1
})

# Server can now send notifications
# ...

await transport.close()
```

---

## Error Codes and Exceptions

### JsonRpcError

**Module**: `spark.nodes.rpc`

Standard JSON-RPC 2.0 error codes:

| Error Code | Constant | Description |
|------------|----------|-------------|
| -32700 | `PARSE_ERROR` | Invalid JSON received |
| -32600 | `INVALID_REQUEST` | JSON-RPC request invalid |
| -32601 | `METHOD_NOT_FOUND` | Method does not exist |
| -32602 | `INVALID_PARAMS` | Invalid method parameters |
| -32603 | `INTERNAL_ERROR` | Internal server error |
| -32000 | `SERVER_ERROR` | Generic server error |
| -32001 | `TIMEOUT_ERROR` | Request timeout |
| -32002 | `RATE_LIMIT_ERROR` | Rate limit exceeded |

### Transport Exceptions

**Module**: `spark.nodes.rpc_transport`

#### `JsonRpcTransportError`
Base exception for all transport failures.

#### `JsonRpcTimeoutError`
Raised when a request exceeds its timeout.

#### `JsonRpcConnectionError`
Raised when transport cannot reach the remote server.

#### `JsonRpcProtocolError`
Raised when remote server returns invalid JSON-RPC payload.

### RPC Method Exceptions

**Module**: `spark.nodes.rpc`

#### `MethodNotFoundError`
Raised when RPC method handler not found.

#### `InvalidParamsError`
Raised when method parameters are invalid.

---

## Message Formats

### JSON-RPC 2.0 Request

```json
{
  "jsonrpc": "2.0",
  "method": "methodName",
  "params": {"param1": "value1", "param2": 123},
  "id": 1
}
```

### JSON-RPC 2.0 Response

```json
{
  "jsonrpc": "2.0",
  "result": {"key": "value"},
  "id": 1
}
```

### JSON-RPC 2.0 Error Response

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "Method not found"
  },
  "id": 1
}
```

### JSON-RPC 2.0 Notification

```json
{
  "jsonrpc": "2.0",
  "method": "notificationMethod",
  "params": {"event": "update"}
}
```

Note: Notifications do not include an `id` field and do not expect a response.

### Batch Requests

```json
[
  {"jsonrpc": "2.0", "method": "method1", "params": {}, "id": 1},
  {"jsonrpc": "2.0", "method": "method2", "params": {}, "id": 2}
]
```

Batch responses return an array of response objects.

---

## Use Cases

### Microservices Architecture

Expose different Spark graphs as RPC services and compose them into distributed workflows.

### Remote Computation

Offload heavy computation to remote workers while keeping orchestration local.

### Service Integration

Integrate external services into Spark workflows using RemoteRpcProxyNode.

### Agent Coordination

Coordinate multiple agents across different hosts using RPC for communication.

---

## Best Practices

1. **Authentication**: Implement authentication in `before_request()` hook
2. **Rate Limiting**: Use `before_request()` for rate limiting logic
3. **Error Handling**: Return proper JSON-RPC error codes from handlers
4. **Timeouts**: Set appropriate timeouts based on operation complexity
5. **SSL/TLS**: Use HTTPS/WSS in production for security
6. **Health Checks**: Monitor `/health` endpoint for service availability
7. **Notifications**: Use WebSocket transport for real-time updates
8. **Batch Requests**: Use batch requests when making multiple related calls
