---
title: RPC Client (RemoteRpcProxyNode)
parent: RPC
nav_order: 3
---
# RPC Client (RemoteRpcProxyNode)

The **RemoteRpcProxyNode** enables local Spark graphs to call remote RPC services transparently. It acts as a proxy that translates node inputs into JSON-RPC requests, forwards them to remote servers, and returns responses as node outputs.

## Overview

RemoteRpcProxyNode bridges local and remote workflows:

```
Local Graph:          Remote Service:
┌──────────┐         ┌────────────┐
│LocalNode │────────▶│ RpcNode    │
└──────────┘         │ (remote)   │
     │               └────────────┘
     ▼                      │
┌──────────┐               │
│ Proxy    │──────────────▶│
│ Node     │◀──────────────┘
└──────────┘
     │
     ▼
┌──────────┐
│NextNode  │
└──────────┘
```

Key features:
- **Transparent proxying**: Use like any other node
- **Multiple transports**: HTTP or WebSocket
- **Flexible input formats**: String, dict, or full JSON-RPC
- **Notification forwarding**: Server notifications published to event bus
- **Configurable timeouts**: Per-request timeout overrides
- **Connection management**: Automatic reconnection for WebSocket

## Basic Usage

### Simple HTTP Client

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig
from spark.nodes import Node
from spark.graphs import Graph

# Create proxy to remote service
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://remote-server:8000",
    transport="http"
)
proxy = RemoteRpcProxyNode(config=proxy_config)

# Use in graph
class PrepareDataNode(Node):
    async def process(self, context):
        return {
            'method': 'processData',
            'data': [1, 2, 3, 4, 5]
        }

prepare = PrepareDataNode()
prepare >> proxy  # Calls remote service

# Run graph
graph = Graph(start=prepare)
result = await graph.run()
print(result.content)  # Remote service response
```

### WebSocket Client with Notifications

```python
# Configure WebSocket transport
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://remote-server:8000",
    transport="websocket",
    auto_connect_websocket=True,
    forward_notifications_to_event_bus=True
)
proxy = RemoteRpcProxyNode(config=proxy_config)

# Subscribe to notifications
graph = Graph(start=proxy)
graph.event_bus.subscribe(
    "remote.rpc.dataUpdated",
    lambda event: print(f"Data updated: {event}")
)

# Run graph
await graph.run()
```

## Configuration

### RemoteRpcProxyConfig

```python
from spark.nodes.rpc_client import RemoteRpcProxyConfig

config = RemoteRpcProxyConfig(
    # Required
    endpoint="http://localhost:8000",  # HTTP endpoint

    # Transport
    transport="http",  # "http" or "websocket"
    ws_endpoint=None,  # Optional explicit WebSocket endpoint

    # HTTP settings
    headers={},  # Custom headers for all requests
    request_timeout=30.0,  # Request timeout in seconds

    # WebSocket settings
    connect_timeout=10.0,  # Connection timeout
    auto_connect_websocket=True,  # Auto-connect on first use

    # Method settings
    default_method=None,  # Fallback method if not specified

    # Notification settings
    notification_topic_prefix="remote.rpc",  # Event bus topic prefix
    notification_topic_key="topic",  # Key for topic in params
    notification_payload_key="payload",  # Key for payload in params
    forward_notifications_to_event_bus=True  # Forward to event bus
)
```

### Configuration Examples

#### Production HTTP Client

```python
config = RemoteRpcProxyConfig(
    endpoint="https://api.production.com",
    transport="http",
    headers={
        "Authorization": "Bearer <token>",
        "User-Agent": "Spark-RPC-Client/1.0"
    },
    request_timeout=60.0  # Longer timeout for production
)
```

#### WebSocket with Custom Endpoint

```python
config = RemoteRpcProxyConfig(
    endpoint="https://api.example.com",
    transport="websocket",
    ws_endpoint="wss://ws.example.com/rpc",  # Custom WS endpoint
    connect_timeout=15.0
)
```

#### Local Development

```python
config = RemoteRpcProxyConfig(
    endpoint="http://localhost:8000",
    transport="http",
    request_timeout=5.0  # Fast fail for development
)
```

## Input Formats

RemoteRpcProxyNode accepts multiple input formats for flexibility.

### Format 1: Simple Method Name

Pass just the method name as a string:

```python
class CallServiceNode(Node):
    async def process(self, context):
        # Return simple method name
        return "getData"

node >> proxy  # Calls "getData" with empty params
```

Client sends:
```json
{
  "jsonrpc": "2.0",
  "method": "getData",
  "params": {},
  "id": 1
}
```

### Format 2: Method with Parameters

Pass a dict with method and parameters:

```python
class CallWithParamsNode(Node):
    async def process(self, context):
        return {
            'method': 'getData',
            'id': 'user123'
        }

node >> proxy  # Calls "getData" with params {"id": "user123"}
```

Client sends:
```json
{
  "jsonrpc": "2.0",
  "method": "getData",
  "params": {"id": "user123"},
  "id": 1
}
```

### Format 3: Full JSON-RPC Payload

Pass a complete JSON-RPC 2.0 request:

```python
class FullPayloadNode(Node):
    async def process(self, context):
        return {
            'jsonrpc': '2.0',
            'method': 'getData',
            'params': {'id': 'user123'},
            'id': 42
        }

node >> proxy  # Uses exact payload
```

Client sends:
```json
{
  "jsonrpc": "2.0",
  "method": "getData",
  "params": {"id": "user123"},
  "id": 42
}
```

### Format 4: Notification (No Response)

Set `notify` flag to send notification:

```python
class NotificationNode(Node):
    async def process(self, context):
        return {
            'method': 'log',
            'message': 'Processing complete',
            'notify': True  # No response expected
        }

node >> proxy  # Sends notification
```

Client sends (no `id` field):
```json
{
  "jsonrpc": "2.0",
  "method": "log",
  "params": {"message": "Processing complete"}
}
```

## Transport Options

### HTTP Transport

**Use when**:
- Making infrequent requests
- Requests are independent
- Load balancing is needed
- Debugging with standard HTTP tools

**Configuration**:

```python
config = RemoteRpcProxyConfig(
    endpoint="http://service:8000",
    transport="http",
    request_timeout=30.0,
    headers={"Authorization": "Bearer token"}
)
proxy = RemoteRpcProxyNode(config=config)
```

**Features**:
- Stateless: Each request creates new connection
- Works through HTTP proxies and load balancers
- Easy to debug with curl/Postman
- Supports standard HTTP authentication

**Limitations**:
- Higher latency (connection overhead)
- No server notifications
- No persistent connection

### WebSocket Transport

**Use when**:
- Making frequent requests
- Need low latency
- Want server notifications
- Building real-time applications

**Configuration**:

```python
config = RemoteRpcProxyConfig(
    endpoint="http://service:8000",  # Auto-converts to ws://
    transport="websocket",
    auto_connect_websocket=True,
    connect_timeout=10.0,
    request_timeout=30.0
)
proxy = RemoteRpcProxyNode(config=config)
```

**WebSocket URL Resolution**:
- `http://host:port` → `ws://host:port/ws`
- `https://host:port` → `wss://host:port/ws`
- Explicit: `ws_endpoint="ws://host:port/custom"`

**Features**:
- Persistent connection (lower latency)
- Bidirectional: Receive server notifications
- Efficient for high-frequency requests
- Automatic reconnection

**Limitations**:
- More complex connection management
- May not work through all proxies
- Single connection (no connection pooling)

## Request/Response Handling

### Successful Response

```python
class FetchDataNode(Node):
    async def process(self, context):
        return {'method': 'getData', 'id': 'user123'}

fetch = FetchDataNode()
fetch >> proxy

graph = Graph(start=fetch)
result = await graph.run()

# result.content contains the RPC response
print(result.content)
# {"id": "user123", "data": {...}, "found": true}
```

### Error Handling

```python
from spark.nodes.exceptions import NodeExecutionError

class SafeCallNode(Node):
    async def process(self, context):
        return {'method': 'riskyOperation', 'data': 'test'}

safe = SafeCallNode()
safe >> proxy

try:
    result = await graph.run()
except NodeExecutionError as e:
    print(f"RPC call failed: {e}")
    # Handle error...
```

### Timeout Override

Override default timeout per request:

```python
class CustomTimeoutNode(Node):
    async def process(self, context):
        return {
            'method': 'longRunningOp',
            'params': {'data': 'test'},
            'metadata': {
                'rpc': {
                    'timeout': 120.0  # 2 minute timeout
                }
            }
        }
```

Or via NodeMessage metadata:

```python
from spark.nodes.types import NodeMessage

message = NodeMessage(
    content={'method': 'longOp'},
    metadata={
        'rpc': {'timeout': 120.0}
    }
)
```

## Notification Forwarding

Server notifications are automatically forwarded to the graph event bus.

### Receiving Notifications

```python
# Configure proxy with notification forwarding
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://localhost:8000",
    transport="websocket",
    forward_notifications_to_event_bus=True,
    notification_topic_prefix="remote.rpc"
)
proxy = RemoteRpcProxyNode(config=proxy_config)

# Create graph
graph = Graph(start=proxy)

# Subscribe to notifications
def handle_data_update(event):
    print(f"Data updated: {event}")

graph.event_bus.subscribe("remote.rpc.dataUpdated", handle_data_update)

# Run graph
await graph.run()
```

### Notification Topic Mapping

By default, notifications are published to:
```
{notification_topic_prefix}.{method}
```

Example:
- Server sends: `{"method": "dataUpdated", "params": {...}}`
- Published to: `remote.rpc.dataUpdated`

### Custom Topic Mapping

Override topic via params:

```python
# Server sends notification with custom topic
await self.broadcast_notification(
    "update",
    {
        "topic": "custom.topic.name",  # Custom topic
        "payload": {"data": "value"}    # Actual payload
    }
)

# Client receives on custom topic
graph.event_bus.subscribe("custom.topic.name", handler)
```

Configure topic keys:

```python
config = RemoteRpcProxyConfig(
    endpoint="http://localhost:8000",
    transport="websocket",
    notification_topic_key="topic",    # Key for topic
    notification_payload_key="payload" # Key for payload
)
```

## Connection Management

### Automatic Connection

WebSocket connections are established automatically:

```python
config = RemoteRpcProxyConfig(
    endpoint="http://localhost:8000",
    transport="websocket",
    auto_connect_websocket=True  # Connect on first use
)
proxy = RemoteRpcProxyNode(config=config)

# Connection established on first RPC call
result = await proxy.run(...)
```

### Manual Connection Control

```python
# Disable auto-connect
config = RemoteRpcProxyConfig(
    endpoint="http://localhost:8000",
    transport="websocket",
    auto_connect_websocket=False
)
proxy = RemoteRpcProxyNode(config=config)

# Manually connect
await proxy._ensure_transport()
transport = proxy._transport
await transport.connect()

# Use proxy
result = await proxy.run(...)

# Manually disconnect
await transport.close()
```

### Connection Monitoring

```python
class MonitoredProxy(RemoteRpcProxyNode):
    async def process(self, context):
        transport = await self._ensure_transport()

        if hasattr(transport, 'is_connected'):
            if not transport.is_connected():
                print("Warning: Not connected, will reconnect")

        return await super().process(context)
```

## Advanced Patterns

### Pattern 1: Distributed Pipeline

Chain remote services:

```python
# Service 1: Data ingestion
ingest_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(
        endpoint="http://ingest-service:8000"
    )
)

# Service 2: Data processing
process_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(
        endpoint="http://process-service:8000"
    )
)

# Service 3: Data storage
store_proxy = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(
        endpoint="http://store-service:8000"
    )
)

# Chain services
prepare >> ingest_proxy >> process_proxy >> store_proxy >> finalize

graph = Graph(start=prepare)
```

### Pattern 2: Parallel Remote Calls

Call multiple services in parallel:

```python
from spark.nodes import Node

class FanOutNode(Node):
    """Fan out to multiple proxy nodes."""
    async def process(self, context):
        data = context.inputs.content
        return {'method': 'process', 'data': data}

class FanInNode(Node):
    """Collect results from proxies."""
    async def process(self, context):
        # Collect from multiple sources
        results = []
        # Implementation depends on your graph structure
        return {'combined': results}

# Create multiple proxies
proxy1 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service1:8000")
)
proxy2 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service2:8000")
)
proxy3 = RemoteRpcProxyNode(
    config=RemoteRpcProxyConfig(endpoint="http://service3:8000")
)

# Connect in parallel
fan_out = FanOutNode()
fan_in = FanInNode()

fan_out >> proxy1 >> fan_in
fan_out >> proxy2 >> fan_in
fan_out >> proxy3 >> fan_in
```

### Pattern 3: Retry with Fallback

Implement retry logic:

```python
from spark.nodes import Node
from spark.nodes.exceptions import NodeExecutionError

class RetryProxyNode(Node):
    def __init__(self, primary_proxy, fallback_proxy, max_retries=3, **kwargs):
        super().__init__(**kwargs)
        self.primary = primary_proxy
        self.fallback = fallback_proxy
        self.max_retries = max_retries

    async def process(self, context):
        # Try primary
        for attempt in range(self.max_retries):
            try:
                return await self.primary.process(context)
            except NodeExecutionError as e:
                if attempt == self.max_retries - 1:
                    # Try fallback
                    try:
                        return await self.fallback.process(context)
                    except:
                        raise e
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

primary = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(...))
fallback = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(...))
retry = RetryProxyNode(primary, fallback)
```

### Pattern 4: Load Balancing

Round-robin across multiple endpoints:

```python
class LoadBalancedProxy(Node):
    def __init__(self, endpoints, **kwargs):
        super().__init__(**kwargs)
        self.proxies = [
            RemoteRpcProxyNode(config=RemoteRpcProxyConfig(endpoint=ep))
            for ep in endpoints
        ]
        self.current = 0

    async def process(self, context):
        # Round-robin
        proxy = self.proxies[self.current]
        self.current = (self.current + 1) % len(self.proxies)

        return await proxy.process(context)

# Use with multiple endpoints
endpoints = [
    "http://service1:8000",
    "http://service2:8000",
    "http://service3:8000"
]
load_balanced = LoadBalancedProxy(endpoints)
```

### Pattern 5: Request Transformation

Transform requests before sending:

```python
class TransformingProxy(Node):
    def __init__(self, proxy, **kwargs):
        super().__init__(**kwargs)
        self.proxy = proxy

    async def process(self, context):
        # Transform input
        original = context.inputs.content
        transformed = self._transform_request(original)

        # Update context
        from spark.nodes.types import NodeMessage
        context.inputs = NodeMessage(content=transformed)

        # Call proxy
        result = await self.proxy.process(context)

        # Transform output
        return self._transform_response(result.content)

    def _transform_request(self, data):
        # Custom transformation
        return {
            'method': 'processData',
            'params': {'data': data, 'version': '2.0'}
        }

    def _transform_response(self, data):
        # Custom transformation
        return data.get('result')
```

## Testing

### Testing with Mock Server

```python
import pytest
from spark.nodes.rpc import RpcNode

class MockRpcNode(RpcNode):
    async def rpc_testMethod(self, params, context):
        return {'result': params['input'] * 2}

@pytest.mark.asyncio
async def test_proxy():
    # Start mock server
    server = MockRpcNode(host="127.0.0.1", port=8888)
    server_task = asyncio.create_task(server.start_server())

    # Wait for server to start
    await asyncio.sleep(1)

    try:
        # Create proxy
        proxy = RemoteRpcProxyNode(
            config=RemoteRpcProxyConfig(endpoint="http://127.0.0.1:8888")
        )

        # Test proxy
        from spark.nodes.types import ExecutionContext, NodeMessage
        context = ExecutionContext(
            inputs=NodeMessage(content={'method': 'testMethod', 'input': 5})
        )
        result = await proxy.process(context)

        assert result.content == {'result': 10}

    finally:
        # Cleanup
        await server.shutdown()
        server_task.cancel()
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_full_workflow():
    # Test with real remote service
    proxy = RemoteRpcProxyNode(
        config=RemoteRpcProxyConfig(
            endpoint="http://test-service:8000"
        )
    )

    # Create test graph
    class TestNode(Node):
        async def process(self, context):
            return {'method': 'getData', 'id': 'test123'}

    test_node = TestNode()
    test_node >> proxy

    graph = Graph(start=test_node)
    result = await graph.run()

    assert result.content['found'] == True
```

## Troubleshooting

### Connection Refused

```python
# Problem: Cannot connect to service
# Solution: Check endpoint and network connectivity

try:
    result = await proxy.run(...)
except NodeExecutionError as e:
    if "Connection refused" in str(e):
        print("Service is not running or not accessible")
        # Check: Is service running? Is firewall blocking?
```

### Timeout Errors

```python
# Problem: Requests timing out
# Solution: Increase timeout or optimize service

config = RemoteRpcProxyConfig(
    endpoint="http://slow-service:8000",
    request_timeout=120.0  # Increase timeout
)
```

### WebSocket Disconnections

```python
# Problem: WebSocket keeps disconnecting
# Solution: Check network stability, use HTTP for unreliable networks

# Switch to HTTP for stability
config = RemoteRpcProxyConfig(
    endpoint="http://service:8000",
    transport="http"  # More stable for unreliable networks
)
```

### Missing Notifications

```python
# Problem: Not receiving server notifications
# Solution: Verify WebSocket and forwarding config

config = RemoteRpcProxyConfig(
    endpoint="http://service:8000",
    transport="websocket",  # Must use WebSocket
    forward_notifications_to_event_bus=True,  # Must be enabled
    auto_connect_websocket=True  # Must connect
)

# Verify subscription
graph.event_bus.subscribe(
    "remote.rpc.notificationMethod",  # Correct topic
    handler
)
```

## Best Practices

1. **Use HTTP for stateless operations**: Simpler, more reliable
2. **Use WebSocket for real-time**: Lower latency, notifications
3. **Set appropriate timeouts**: Balance responsiveness vs. patience
4. **Handle errors gracefully**: Network errors will happen
5. **Log RPC calls**: Aid debugging in distributed systems
6. **Monitor connection health**: Detect issues early
7. **Use load balancing**: Distribute load across services
8. **Implement retries**: With exponential backoff
9. **Transform at boundaries**: Keep services decoupled
10. **Test with mocks**: Unit test without real services

## Next Steps

- [RPC Server](./server.md) - Create RPC services
- [Server Notifications](./notifications.md) - Push notifications from server
- [RPC Security](./security.md) - Secure RPC communications
- [RPC Patterns](./patterns.md) - Advanced patterns and examples
