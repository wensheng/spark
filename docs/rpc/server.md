---
title: RPC Server (RpcNode)
parent: RPC
nav_order: 1
---
# RPC Server (RpcNode)
---

The **RpcNode** class exposes a Spark node as a JSON-RPC 2.0 server, allowing remote clients to invoke its methods over HTTP or WebSocket connections. This enables service-oriented architectures and distributed workflows.

## Overview

RpcNode is a subclass of `Node` that adds:

- **JSON-RPC 2.0 server** with HTTP and WebSocket support
- **Method dispatch** to `rpc_*` handler methods
- **Lifecycle hooks** for authentication, logging, and custom logic
- **Server notifications** for pushing updates to WebSocket clients
- **SSL/TLS support** for secure HTTPS/WSS connections
- **Health check endpoint** for monitoring

## Basic Usage

### Creating an RPC Server

```python
from spark.nodes.rpc import RpcNode
from spark.nodes.types import ExecutionContext

class CalculatorNode(RpcNode):
    """Calculator service exposed via JSON-RPC."""

    async def rpc_add(self, params: dict, context: ExecutionContext):
        """Add two numbers.

        Method: add
        Params:
            a (number): First number
            b (number): Second number
        Returns:
            dict: {"sum": number}
        """
        a = params.get('a', 0)
        b = params.get('b', 0)
        return {'sum': a + b}

    async def rpc_multiply(self, params: dict, context: ExecutionContext):
        """Multiply two numbers.

        Method: multiply
        Params:
            a (number): First factor
            b (number): Second factor
        Returns:
            dict: {"product": number}
        """
        a = params.get('a', 1)
        b = params.get('b', 1)
        return {'product': a * b}

# Start server
import asyncio

async def main():
    node = CalculatorNode(host="0.0.0.0", port=8000)
    await node.start_server()

asyncio.run(main())
```

### Testing the Server

```bash
# Test with curl
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":5,"b":3},"id":1}'

# Response
{"jsonrpc":"2.0","result":{"sum":8},"id":1}
```

## Defining RPC Methods

### Method Naming Convention

RPC methods are defined by creating methods with the `rpc_` prefix:

- Method name: `rpc_<method>` handles RPC calls to `<method>`
- Dots and hashes in RPC method names are converted to underscores
  - `user.create` → `rpc_user_create`
  - `user-delete` → `rpc_user_delete`

```python
class UserService(RpcNode):
    async def rpc_user_create(self, params: dict, context: ExecutionContext):
        """Handles RPC method: user.create or user-create"""
        username = params.get('username')
        email = params.get('email')
        # Create user...
        return {'user_id': 123, 'username': username}

    async def rpc_user_get(self, params: dict, context: ExecutionContext):
        """Handles RPC method: user.get or user-get"""
        user_id = params.get('user_id')
        # Fetch user...
        return {'user_id': user_id, 'username': 'alice'}
```

### Method Signature

RPC methods must accept:

1. `params` (dict or list): RPC parameters from the request
2. `context` (ExecutionContext): Execution context with metadata

```python
async def rpc_methodName(
    self,
    params: dict,  # or List for positional params
    context: ExecutionContext
) -> dict:
    """Method handler.

    Args:
        params: RPC parameters (dict or list)
        context: Execution context

    Returns:
        Result dictionary (will be JSON-serialized)

    Raises:
        InvalidParamsError: If parameters are invalid
        MethodNotFoundError: If sub-method not found
        Exception: For other errors (becomes Internal Error)
    """
    pass
```

### Parameter Styles

JSON-RPC 2.0 supports two parameter styles:

#### Named Parameters (dict)

```python
async def rpc_createUser(self, params: dict, context: ExecutionContext):
    username = params.get('username')
    email = params.get('email')
    age = params.get('age', 18)  # Optional with default

    if not username:
        from spark.nodes.rpc import InvalidParamsError
        raise InvalidParamsError("Missing required parameter: username")

    return {'user_id': 123}
```

Client request:
```json
{
  "jsonrpc": "2.0",
  "method": "createUser",
  "params": {"username": "alice", "email": "alice@example.com"},
  "id": 1
}
```

#### Positional Parameters (list)

```python
async def rpc_add(self, a: int, b: int, context: ExecutionContext):
    """Add two numbers using positional params."""
    return {'sum': a + b}
```

Client request:
```json
{
  "jsonrpc": "2.0",
  "method": "add",
  "params": [5, 3],
  "id": 1
}
```

### Return Values

RPC methods must return:
- **dict**: Serializable result dictionary
- **None**: For notifications (no response expected)

```python
async def rpc_getData(self, params: dict, context: ExecutionContext):
    data_id = params.get('id')

    # Return result
    return {
        'id': data_id,
        'data': {'value': 42},
        'timestamp': time.time()
    }
```

### Error Handling

Raise exceptions for error conditions:

```python
from spark.nodes.rpc import InvalidParamsError, MethodNotFoundError

async def rpc_divide(self, params: dict, context: ExecutionContext):
    a = params.get('a', 0)
    b = params.get('b', 1)

    if b == 0:
        raise InvalidParamsError("Cannot divide by zero")

    return {'quotient': a / b}
```

Client receives:
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: Cannot divide by zero"
  },
  "id": 1
}
```

## Configuration

### Constructor Parameters

```python
class RpcNode(Node):
    def __init__(
        self,
        host: str = "127.0.0.1",           # Host to bind to
        port: int = 8000,                   # Port to bind to
        ssl_certfile: Optional[str] = None, # SSL certificate file
        ssl_keyfile: Optional[str] = None,  # SSL key file
        ssl_ca_certs: Optional[str] = None, # CA certificates file
        request_timeout: float = 30.0,      # Request timeout (seconds)
        **kwargs                             # Additional Node config
    ):
        pass
```

### HTTP Server Configuration

```python
# HTTP on localhost
node = CalculatorNode(host="127.0.0.1", port=8000)

# HTTP on all interfaces (for Docker/cloud)
node = CalculatorNode(host="0.0.0.0", port=8000)

# HTTP with custom timeout
node = CalculatorNode(
    host="0.0.0.0",
    port=8000,
    request_timeout=60.0  # 60 second timeout
)
```

### HTTPS/WSS with SSL

```python
# HTTPS with self-signed certificate
node = CalculatorNode(
    host="0.0.0.0",
    port=8443,
    ssl_certfile="/path/to/cert.pem",
    ssl_keyfile="/path/to/key.pem"
)

# HTTPS with CA chain
node = CalculatorNode(
    host="0.0.0.0",
    port=8443,
    ssl_certfile="/path/to/cert.pem",
    ssl_keyfile="/path/to/key.pem",
    ssl_ca_certs="/path/to/ca-bundle.crt"
)
```

#### Generating Self-Signed Certificates (Testing)

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -subj "/CN=localhost"

# Generate with SAN (Subject Alternative Names)
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 365 \
  -extensions SAN \
  -config <(cat /etc/ssl/openssl.cnf <(printf "[SAN]\nsubjectAltName=DNS:localhost,IP:127.0.0.1"))
```

**Warning**: Use proper CA-signed certificates in production.

## Server Lifecycle

### Starting the Server

```python
async def main():
    node = MyRpcNode(host="0.0.0.0", port=8000)

    # Start server (runs until shutdown)
    await node.start_server()

asyncio.run(main())
```

The `start_server()` method:
1. Starts the node's `go()` loop for processing messages
2. Starts the HTTP/WebSocket server
3. Blocks until server shuts down

### Graceful Shutdown

```python
async def main():
    node = MyRpcNode(host="0.0.0.0", port=8000)

    try:
        await node.start_server()
    except KeyboardInterrupt:
        print("Shutting down...")
        await node.shutdown()
        print("Server stopped")

asyncio.run(main())
```

The `shutdown()` method:
1. Signals shutdown event
2. Stops accepting new connections
3. Closes all WebSocket connections
4. Waits for pending requests to complete (with timeout)
5. Shuts down the HTTP server

### Background Tasks

Run background tasks alongside the server:

```python
class MyRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_task = None

    async def start_server(self):
        # Start background task
        self.background_task = asyncio.create_task(
            self._periodic_cleanup()
        )

        # Start server
        try:
            await super().start_server()
        finally:
            # Clean up background task
            if self.background_task:
                self.background_task.cancel()
                await self.background_task

    async def _periodic_cleanup(self):
        """Run periodic cleanup."""
        while True:
            await asyncio.sleep(60)
            # Do cleanup...
```

## Lifecycle Hooks

RpcNode provides hooks for customizing behavior at different lifecycle stages.

### before_request

Called before processing each RPC request. Use for:
- Authentication
- Authorization
- Rate limiting
- Logging
- Request validation

```python
class AuthenticatedRpcNode(RpcNode):
    async def before_request(
        self,
        method: str,
        params: Union[Dict, List],
        request_id: Optional[Union[str, int]]
    ):
        """
        Hook called before processing each request.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Request ID (None for notifications)

        Raises:
            Exception: To reject the request
        """
        # Authentication example
        # Note: In production, extract token from HTTP headers
        # or WebSocket handshake

        # Validate authentication token
        if not self._is_authenticated():
            raise PermissionError("Authentication required")

        # Log request
        req_type = "notification" if request_id is None else "request"
        print(f"[{req_type}] {method} - id: {request_id}")
```

### after_request

Called after processing each RPC request. Use for:
- Logging
- Metrics collection
- Audit trails
- Cleanup

```python
class MetricsRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.request_count = 0
        self.error_count = 0

    async def after_request(
        self,
        method: str,
        params: Union[Dict, List],
        request_id: Optional[Union[str, int]],
        result: Any,
        error: Optional[str]
    ):
        """
        Hook called after processing each request.

        Args:
            method: RPC method name
            params: Method parameters
            request_id: Request ID (None for notifications)
            result: Result from handler (None if error)
            error: Error message (None if success)
        """
        self.request_count += 1

        if error:
            self.error_count += 1
            print(f"[ERROR] {method}: {error}")
        else:
            print(f"[SUCCESS] {method}")

        # Record metrics
        self._record_metric(method, error is None)
```

### on_websocket_connect

Called when a WebSocket client connects. Use for:
- Client registration
- Authentication
- Sending welcome messages
- Subscription setup

```python
class NotifyingRpcNode(RpcNode):
    async def on_websocket_connect(
        self,
        client_id: str,
        websocket: WebSocket
    ):
        """
        Hook called when WebSocket client connects.

        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection
        """
        print(f"Client connected: {client_id}")

        # Send welcome notification
        await self.send_notification_to_client(
            client_id,
            "welcome",
            {
                "message": "Connected to RPC server",
                "client_id": client_id,
                "server_version": "1.0.0"
            }
        )
```

### on_websocket_disconnect

Called when a WebSocket client disconnects. Use for:
- Client cleanup
- Subscription cleanup
- Logging

```python
class SubscriptionRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.subscriptions = {}

    async def on_websocket_disconnect(
        self,
        client_id: str,
        websocket: WebSocket
    ):
        """
        Hook called when WebSocket client disconnects.

        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection
        """
        print(f"Client disconnected: {client_id}")

        # Clean up subscriptions
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
```

## Request Context Access

The `context` parameter provides access to execution context:

```python
async def rpc_processData(self, params: dict, context: ExecutionContext):
    # Access inputs
    data = context.inputs.content

    # Access metadata
    metadata = context.inputs.metadata

    # Access graph state (if node is in a graph)
    if context.graph_state:
        counter = await context.graph_state.get('request_count', 0)
        await context.graph_state.set('request_count', counter + 1)

    # Access node state
    self.state.processing  # Boolean
    self.state.process_count  # Integer

    return {'processed': True}
```

## Health Check Endpoint

Every RpcNode automatically provides a health check endpoint:

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "node": "CalculatorNode",
  "websocket_clients": 3,
  "pending_requests": 2
}
```

Use for:
- Load balancer health checks
- Monitoring and alerting
- Service discovery

## Advanced Patterns

### Wrapping a Graph as an RPC Service

Expose an entire graph as an RPC service:

```python
from spark.graphs import Graph, Task
from spark.nodes.types import NodeMessage

class GraphRpcNode(RpcNode):
    def __init__(self, graph: Graph, **kwargs):
        super().__init__(**kwargs)
        self.graph = graph

    async def rpc_execute(self, params: dict, context: ExecutionContext):
        """Execute the graph with given inputs."""
        # Create task from params
        task = Task(inputs=NodeMessage(content=params))

        # Run graph
        result = await self.graph.run(task)

        return {
            'success': True,
            'result': result.content if result else None
        }

# Create graph
my_graph = Graph(start=my_node)

# Wrap in RPC node
rpc_node = GraphRpcNode(graph=my_graph, host="0.0.0.0", port=8000)
await rpc_node.start_server()
```

### State Management in RPC Nodes

Maintain state across requests:

```python
class StatefulRpcNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_store = {}
        self.request_count = 0

    async def rpc_set(self, params: dict, context: ExecutionContext):
        """Store data."""
        key = params.get('key')
        value = params.get('value')
        self.data_store[key] = value
        self.request_count += 1
        return {'success': True}

    async def rpc_get(self, params: dict, context: ExecutionContext):
        """Retrieve data."""
        key = params.get('key')
        value = self.data_store.get(key)
        return {'key': key, 'value': value}
```

### Rate Limiting

Implement rate limiting in `before_request`:

```python
from collections import defaultdict
import time

class RateLimitedRpcNode(RpcNode):
    def __init__(self, max_requests=10, window_seconds=10, **kwargs):
        super().__init__(**kwargs)
        self.rate_limits = defaultdict(list)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def before_request(self, method, params, request_id):
        # Note: In production, extract client ID from request headers
        client_id = "demo_client"

        now = time.time()
        requests = self.rate_limits[client_id]

        # Remove old requests outside window
        requests[:] = [t for t in requests if now - t < self.window_seconds]

        # Check limit
        if len(requests) >= self.max_requests:
            raise Exception(
                f"Rate limit exceeded: {self.max_requests} requests "
                f"per {self.window_seconds}s"
            )

        # Add current request
        requests.append(now)
```

## Error Handling

### Custom Error Responses

```python
async def rpc_customError(self, params: dict, context: ExecutionContext):
    from spark.nodes.rpc import InvalidParamsError

    # Raise with custom data
    raise InvalidParamsError(
        "Invalid parameter 'age'",
        data={'parameter': 'age', 'expected': 'integer > 0'}
    )
```

Client receives:
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: Invalid parameter 'age'",
    "data": {
      "parameter": "age",
      "expected": "integer > 0"
    }
  },
  "id": 1
}
```

### Catching Exceptions

```python
async def rpc_safeOperation(self, params: dict, context: ExecutionContext):
    try:
        result = self.dangerous_operation(params)
        return {'success': True, 'result': result}
    except ValueError as e:
        # Return error as result (not exception)
        return {'success': False, 'error': str(e)}
    except Exception as e:
        # Re-raise for JSON-RPC error response
        raise
```

## Testing

### Testing with curl

```bash
# Simple request
curl -X POST http://localhost:8000 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"add","params":{"a":5,"b":3},"id":1}'

# Notification (no id)
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
```

### Testing with Python

```python
import asyncio
import httpx

async def test_rpc():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000",
            json={
                "jsonrpc": "2.0",
                "method": "add",
                "params": {"a": 5, "b": 3},
                "id": 1
            }
        )
        print(response.json())

asyncio.run(test_rpc())
```

### Unit Testing

```python
import pytest
from spark.nodes.rpc import RpcNode
from spark.nodes.types import ExecutionContext, NodeMessage

class TestCalculatorNode(RpcNode):
    async def rpc_add(self, params, context):
        return {'sum': params['a'] + params['b']}

@pytest.mark.asyncio
async def test_rpc_add():
    node = TestCalculatorNode()
    context = ExecutionContext(inputs=NodeMessage(content={}))

    result = await node.rpc_add({'a': 5, 'b': 3}, context)
    assert result == {'sum': 8}
```

## Next Steps

- [Server Notifications](./notifications.md) - Push notifications to clients
- [RPC Client](./client.md) - Call RPC servers from graphs
- [RPC Security](./security.md) - Secure your RPC services
- [RPC Patterns](./patterns.md) - Common patterns and examples
