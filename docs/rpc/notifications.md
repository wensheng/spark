---
title: Server Notifications
parent: RPC
nav_order: 2
---
# Server Notifications

Server notifications enable RpcNode servers to push real-time updates to WebSocket clients without waiting for a request. This is essential for event-driven architectures, real-time dashboards, and collaborative systems.

## Overview

JSON-RPC 2.0 notifications are one-way messages with no response expected:

```json
{
  "jsonrpc": "2.0",
  "method": "dataUpdated",
  "params": {
    "id": "user123",
    "timestamp": 1234567890
  }
}
```

Key characteristics:
- **No `id` field**: Distinguishes notifications from requests
- **No response**: Client doesn't send acknowledgment
- **One-way**: Server to client only (via WebSocket)
- **Asynchronous**: Sent at any time, not in response to a request

## Use Cases

### 1. Real-Time Updates

Push data changes to clients immediately:

```python
class DataService(RpcNode):
    async def rpc_updateData(self, params, context):
        data_id = params['id']
        new_value = params['value']

        # Update data
        self.data[data_id] = new_value

        # Notify all clients
        await self.broadcast_notification(
            "dataUpdated",
            {"id": data_id, "value": new_value}
        )

        return {'success': True}
```

### 2. Progress Updates

Report progress for long-running operations:

```python
async def rpc_processLargeFile(self, params, context):
    file_id = params['file_id']
    total_chunks = 100

    for i in range(total_chunks):
        # Process chunk
        process_chunk(i)

        # Send progress update
        await self.broadcast_notification(
            "progress",
            {
                "file_id": file_id,
                "progress": (i + 1) / total_chunks,
                "chunk": i + 1,
                "total": total_chunks
            }
        )

    return {'success': True}
```

### 3. System Events

Notify clients of system-wide events:

```python
async def _monitor_system(self):
    """Background task monitoring system health."""
    while True:
        await asyncio.sleep(10)

        # Check system metrics
        cpu_usage = get_cpu_usage()
        memory_usage = get_memory_usage()

        if cpu_usage > 0.8 or memory_usage > 0.9:
            await self.broadcast_notification(
                "systemAlert",
                {
                    "level": "warning",
                    "cpu": cpu_usage,
                    "memory": memory_usage,
                    "timestamp": time.time()
                }
            )
```

### 4. Collaborative Editing

Synchronize state across multiple clients:

```python
class CollaborativeEditor(RpcNode):
    async def rpc_editDocument(self, params, context):
        doc_id = params['doc_id']
        edit = params['edit']
        editor = params['editor']

        # Apply edit
        self.apply_edit(doc_id, edit)

        # Notify other clients (except the editor)
        for client_id in self.websocket_clients:
            if client_id != editor:
                await self.send_notification_to_client(
                    client_id,
                    "documentEdited",
                    {
                        "doc_id": doc_id,
                        "edit": edit,
                        "editor": editor
                    }
                )

        return {'success': True}
```

## Sending Notifications

### Broadcast to All Clients

Send a notification to all connected WebSocket clients:

```python
await self.broadcast_notification(
    method: str,      # Notification method name
    params: Union[Dict, List]  # Notification parameters
)
```

Example:

```python
class NotificationDemo(RpcNode):
    async def rpc_announceUpdate(self, params, context):
        message = params['message']

        # Broadcast to all clients
        await self.broadcast_notification(
            "announcement",
            {"message": message, "timestamp": time.time()}
        )

        return {'success': True, 'clients_notified': len(self.websocket_clients)}
```

### Send to Specific Client

Send a notification to a single WebSocket client:

```python
await self.send_notification_to_client(
    client_id: str,   # WebSocket client ID
    method: str,      # Notification method name
    params: Union[Dict, List]  # Notification parameters
)
```

Example:

```python
class PersonalizedNotifications(RpcNode):
    async def on_websocket_connect(self, client_id, websocket):
        """Send welcome message to new client."""
        await self.send_notification_to_client(
            client_id,
            "welcome",
            {
                "message": f"Welcome, {client_id}!",
                "server_time": time.time()
            }
        )

    async def rpc_subscribe(self, params, context):
        """Subscribe client to personalized updates."""
        client_id = params['client_id']
        topics = params['topics']

        # Store subscription
        self.subscriptions[client_id] = topics

        # Send confirmation
        await self.send_notification_to_client(
            client_id,
            "subscribed",
            {"topics": topics}
        )

        return {'success': True}
```

## WebSocket Client Management

### Tracking Clients

RpcNode automatically tracks connected WebSocket clients:

```python
class ClientTrackingNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.websocket_clients is a dict: {client_id: WebSocket}

    async def rpc_listClients(self, params, context):
        """List all connected clients."""
        return {
            'clients': list(self.websocket_clients.keys()),
            'count': len(self.websocket_clients)
        }
```

### Client Metadata

Store metadata about each client:

```python
class MetadataTrackingNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client_metadata = {}

    async def on_websocket_connect(self, client_id, websocket):
        """Store client metadata."""
        self.client_metadata[client_id] = {
            'connected_at': time.time(),
            'subscriptions': [],
            'last_activity': time.time()
        }

    async def on_websocket_disconnect(self, client_id, websocket):
        """Clean up client metadata."""
        if client_id in self.client_metadata:
            del self.client_metadata[client_id]

    async def rpc_updateActivity(self, params, context):
        """Update client activity timestamp."""
        client_id = params['client_id']
        if client_id in self.client_metadata:
            self.client_metadata[client_id]['last_activity'] = time.time()
        return {'success': True}
```

### Client IDs

Client IDs are automatically generated:
- Format: `ws_{counter}_{timestamp_ms}`
- Example: `ws_1_1609459200000`
- Unique per connection

Access in hooks:

```python
async def on_websocket_connect(self, client_id: str, websocket: WebSocket):
    print(f"New client: {client_id}")
```

## Subscription Management

Implement publish/subscribe patterns:

```python
class PubSubNode(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # topic -> set of client_ids
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)

    async def rpc_subscribe(self, params, context):
        """Subscribe to topics."""
        client_id = params['client_id']
        topics = params['topics']

        for topic in topics:
            self.subscriptions[topic].add(client_id)

        return {
            'success': True,
            'subscribed': topics,
            'total_subscriptions': sum(len(s) for s in self.subscriptions.values())
        }

    async def rpc_unsubscribe(self, params, context):
        """Unsubscribe from topics."""
        client_id = params['client_id']
        topics = params['topics']

        for topic in topics:
            self.subscriptions[topic].discard(client_id)

        return {'success': True, 'unsubscribed': topics}

    async def rpc_publish(self, params, context):
        """Publish message to topic."""
        topic = params['topic']
        message = params['message']

        # Send to all subscribers of this topic
        subscribers = self.subscriptions.get(topic, set())
        for client_id in subscribers:
            if client_id in self.websocket_clients:
                await self.send_notification_to_client(
                    client_id,
                    topic,
                    {"message": message, "timestamp": time.time()}
                )

        return {
            'success': True,
            'topic': topic,
            'subscribers_notified': len(subscribers)
        }

    async def on_websocket_disconnect(self, client_id, websocket):
        """Clean up subscriptions on disconnect."""
        for topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
```

## Background Notifications

Send periodic notifications in a background task:

```python
class PeriodicNotifications(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.notification_task = None

    async def start_server(self):
        """Start server and background task."""
        # Start background notification task
        self.notification_task = asyncio.create_task(
            self._send_periodic_notifications()
        )

        # Start server
        try:
            await super().start_server()
        finally:
            # Cancel background task on shutdown
            if self.notification_task:
                self.notification_task.cancel()
                try:
                    await self.notification_task
                except asyncio.CancelledError:
                    pass

    async def _send_periodic_notifications(self):
        """Send notifications every 30 seconds."""
        try:
            while True:
                await asyncio.sleep(30)

                if len(self.websocket_clients) > 0:
                    await self.broadcast_notification(
                        "heartbeat",
                        {
                            "timestamp": time.time(),
                            "clients": len(self.websocket_clients),
                            "status": "ok"
                        }
                    )
        except asyncio.CancelledError:
            pass
```

## Notification Patterns

### Pattern 1: Event Sourcing

Broadcast all state changes:

```python
class EventSourcedNode(RpcNode):
    async def rpc_updateState(self, params, context):
        # Apply state change
        event = self._apply_change(params)

        # Broadcast event to all clients
        await self.broadcast_notification(
            "stateChanged",
            {
                "event_type": event.type,
                "event_data": event.data,
                "timestamp": event.timestamp
            }
        )

        return {'success': True, 'event_id': event.id}
```

### Pattern 2: Request/Notification Pair

Respond with request, then send follow-up notifications:

```python
class AsyncProcessingNode(RpcNode):
    async def rpc_startJob(self, params, context):
        job_id = params['job_id']
        client_id = params.get('client_id')

        # Start async job
        asyncio.create_task(self._process_job(job_id, client_id))

        # Immediate response
        return {
            'success': True,
            'job_id': job_id,
            'status': 'started'
        }

    async def _process_job(self, job_id, client_id):
        """Process job and send notifications."""
        try:
            # Processing steps...
            for step in range(5):
                await asyncio.sleep(1)

                # Send progress notification
                if client_id:
                    await self.send_notification_to_client(
                        client_id,
                        "jobProgress",
                        {
                            "job_id": job_id,
                            "step": step + 1,
                            "total": 5
                        }
                    )

            # Send completion notification
            if client_id:
                await self.send_notification_to_client(
                    client_id,
                    "jobComplete",
                    {"job_id": job_id, "result": "success"}
                )
        except Exception as e:
            # Send error notification
            if client_id:
                await self.send_notification_to_client(
                    client_id,
                    "jobFailed",
                    {"job_id": job_id, "error": str(e)}
                )
```

### Pattern 3: Targeted Notifications by Role

Send notifications based on client roles:

```python
class RoleBasedNotifications(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client_roles = {}  # client_id -> role

    async def rpc_authenticate(self, params, context):
        client_id = params['client_id']
        role = params['role']

        self.client_roles[client_id] = role
        return {'success': True, 'role': role}

    async def _notify_by_role(self, role: str, method: str, params: dict):
        """Send notification to all clients with specific role."""
        for client_id, client_role in self.client_roles.items():
            if client_role == role and client_id in self.websocket_clients:
                await self.send_notification_to_client(
                    client_id, method, params
                )

    async def rpc_adminAction(self, params, context):
        """Admin action that notifies all users."""
        action = params['action']

        # Notify all regular users
        await self._notify_by_role(
            "user",
            "adminNotification",
            {"action": action, "timestamp": time.time()}
        )

        # Notify other admins
        await self._notify_by_role(
            "admin",
            "adminLog",
            {"action": action, "timestamp": time.time()}
        )

        return {'success': True}
```

## Client-Side Handling

### JavaScript/TypeScript Client

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  console.log('Connected');

  // Subscribe to notifications
  ws.send(JSON.stringify({
    jsonrpc: '2.0',
    method: 'subscribe',
    params: { client_id: 'client1', topics: ['dataUpdated'] },
    id: 1
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.method) {
    // This is a notification
    console.log('Notification:', message.method, message.params);

    // Handle specific notifications
    switch (message.method) {
      case 'dataUpdated':
        handleDataUpdate(message.params);
        break;
      case 'heartbeat':
        updateHeartbeat(message.params);
        break;
    }
  } else {
    // This is a response to a request
    console.log('Response:', message.result || message.error);
  }
};
```

### Python Client

```python
import asyncio
import websockets
import json

async def handle_notifications():
    uri = "ws://localhost:8000/ws"

    async with websockets.connect(uri) as websocket:
        # Subscribe
        await websocket.send(json.dumps({
            "jsonrpc": "2.0",
            "method": "subscribe",
            "params": {"client_id": "py_client", "topics": ["dataUpdated"]},
            "id": 1
        }))

        # Receive response
        response = await websocket.recv()
        print(f"Subscribed: {response}")

        # Listen for notifications
        async for message in websocket:
            data = json.loads(message)

            if 'method' in data:
                # Notification
                print(f"Notification: {data['method']}")
                print(f"Params: {data['params']}")
            else:
                # Response
                print(f"Response: {data}")

asyncio.run(handle_notifications())
```

## Error Handling

### Network Failures

Handle disconnections gracefully:

```python
class ResilientNotifications(RpcNode):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pending_notifications = defaultdict(list)

    async def send_notification_to_client(self, client_id, method, params):
        """Send notification with error handling."""
        try:
            await super().send_notification_to_client(client_id, method, params)
        except Exception as e:
            print(f"Failed to send notification to {client_id}: {e}")
            # Queue for retry
            self.pending_notifications[client_id].append({
                'method': method,
                'params': params,
                'timestamp': time.time()
            })

    async def on_websocket_connect(self, client_id, websocket):
        """Resend pending notifications on reconnect."""
        if client_id in self.pending_notifications:
            for notification in self.pending_notifications[client_id]:
                await self.send_notification_to_client(
                    client_id,
                    notification['method'],
                    notification['params']
                )
            del self.pending_notifications[client_id]
```

### Rate Limiting Notifications

Prevent overwhelming clients:

```python
class RateLimitedNotifications(RpcNode):
    def __init__(self, max_per_second=10, **kwargs):
        super().__init__(**kwargs)
        self.max_per_second = max_per_second
        self.notification_times = defaultdict(list)

    async def _rate_limited_notify(self, client_id, method, params):
        """Send notification with rate limiting."""
        now = time.time()
        times = self.notification_times[client_id]

        # Remove old timestamps
        times[:] = [t for t in times if now - t < 1.0]

        # Check limit
        if len(times) >= self.max_per_second:
            print(f"Rate limit hit for {client_id}, dropping notification")
            return

        # Send notification
        await self.send_notification_to_client(client_id, method, params)
        times.append(now)
```

## Best Practices

### 1. Design Clear Notification Schema

Document all notification types:

```python
"""
Notification Types:
- dataUpdated: Data change notification
  Params: {id: str, value: any, timestamp: float}

- progress: Progress update
  Params: {job_id: str, progress: float, message: str}

- heartbeat: Server health check
  Params: {timestamp: float, status: str}

- error: Error notification
  Params: {error: str, code: int, details: any}
"""
```

### 2. Include Timestamps

Always include timestamps for ordering:

```python
await self.broadcast_notification(
    "event",
    {
        "data": data,
        "timestamp": time.time()  # Always include
    }
)
```

### 3. Version Notifications

Include version for schema evolution:

```python
await self.broadcast_notification(
    "dataUpdated",
    {
        "version": "1.0",
        "data": data
    }
)
```

### 4. Batch Related Notifications

Avoid notification storms:

```python
async def _batch_notifications(self):
    """Send batched notifications every second."""
    batch = []

    while True:
        await asyncio.sleep(1.0)

        if batch:
            await self.broadcast_notification(
                "batch",
                {"updates": batch, "count": len(batch)}
            )
            batch.clear()
```

### 5. Log All Notifications

Track notification delivery:

```python
async def broadcast_notification(self, method, params):
    print(f"Broadcasting {method} to {len(self.websocket_clients)} clients")
    await super().broadcast_notification(method, params)
```

## Next Steps

- [RPC Client](./client.md) - Receive notifications in RemoteRpcProxyNode
- [RPC Security](./security.md) - Secure notification channels
- [RPC Patterns](./patterns.md) - Advanced notification patterns
