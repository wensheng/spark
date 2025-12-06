---
title: Channels & Messaging
parent: Node
nav_order: 4
---
# Channels & Messaging

**Document Type**: Reference Documentation
**Audience**: Developers working with long-running nodes and inter-node communication
**Related**: [Node Fundamentals](/docs/nodes/fundamentals.md), [Execution Modes](/docs/graphs/execution-modes.md)

---

## Overview

Channels provide the messaging infrastructure for inter-node communication in Spark, particularly for long-running workflows where nodes operate as continuous workers. The channel abstraction builds on `asyncio.Queue` with additional features for metadata, instrumentation, and alternative backends.

**Location**: `spark/nodes/channels.py`

**Key Features**:
- Asynchronous message passing
- Metadata support for tracing and routing
- Acknowledgement callbacks
- Observer hooks for instrumentation
- Multiple channel implementations
- Graceful shutdown support

---

## Channel Abstraction

### BaseChannel Interface

```python
class BaseChannel:
    """Interface for asynchronous message channels."""

    async def send(self, message: ChannelMessage) -> None:
        """Asynchronously enqueue a message."""

    def send_nowait(self, message: ChannelMessage) -> None:
        """Enqueue a message without blocking."""

    async def receive(self) -> ChannelMessage:
        """Asynchronously receive the next message."""

    def empty(self) -> bool:
        """Return True if the channel has no pending messages."""

    def close(self) -> None:
        """Close the channel."""

    @property
    def name(self) -> str:
        """Return the channel name."""
```

### Design Principles

1. **Asynchronous First**: All operations are async-native
2. **Metadata-Rich**: Messages carry metadata for tracing and routing
3. **Observable**: Observer hooks for monitoring and instrumentation
4. **Extensible**: Abstract interface for alternative backends
5. **Fail-Safe**: Errors in observers don't crash channels

---

## ChannelMessage Structure

### Message Envelope

```python
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable

@dataclass(slots=True)
class ChannelMessage:
    """
    Envelope for channel payloads.

    Attributes:
        payload: Application data being transmitted
        metadata: Tracing, routing, and debugging information
        ack: Optional acknowledgement callback
        is_shutdown: Shutdown signal flag
    """

    payload: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    ack: Optional[Callable[[], Awaitable[None]]] = None
    is_shutdown: bool = False
```

### Message Creation

```python
from spark.nodes.channels import ChannelMessage

# Simple message
message = ChannelMessage(payload={'user_id': 123, 'query': 'hello'})

# Message with metadata
message = ChannelMessage(
    payload={'data': 'value'},
    metadata={
        'trace_id': 'abc-123',
        'timestamp': time.time(),
        'source_node': 'node_1'
    }
)

# Message with acknowledgement
async def on_processed():
    print("Message processed")

message = ChannelMessage(
    payload={'task': 'process'},
    ack=on_processed
)

# Shutdown message
shutdown_message = ChannelMessage(
    payload=None,
    is_shutdown=True
)
```

### Message Cloning

```python
# Clone with modifications
cloned = message.clone(
    payload={'new': 'data'},
    metadata={'additional': 'info'}
)

# Metadata is merged
# Original: {'trace_id': 'abc'}
# After clone: {'trace_id': 'abc', 'additional': 'info'}
```

### Acknowledgement Callback

```python
async def process_message(message: ChannelMessage):
    """Process message and acknowledge."""
    # Do work
    result = await process_payload(message.payload)

    # Acknowledge completion
    if message.ack:
        await message.ack()

    return result
```

---

## InMemoryChannel Implementation

### Overview

Default channel implementation backed by `asyncio.Queue`.

**Use Cases**:
- Standard inter-node communication
- In-process message passing
- Development and testing
- Single-machine workflows

### Creating Channels

```python
from spark.nodes.channels import InMemoryChannel

# Basic channel
channel = InMemoryChannel(name='my-channel')

# Channel with size limit
channel = InMemoryChannel(
    name='bounded-channel',
    maxsize=100  # Max 100 pending messages
)

# Channel with observers
def log_message(message, channel, phase):
    print(f"{phase}: {message.payload}")

channel = InMemoryChannel(
    name='observed-channel',
    observers=[log_message]
)
```

### Sending Messages

```python
# Async send (blocks if full)
message = ChannelMessage(payload={'data': 'value'})
await channel.send(message)

# Non-blocking send (raises QueueFull if full)
try:
    channel.send_nowait(message)
except asyncio.QueueFull:
    print("Channel full!")
```

### Receiving Messages

```python
# Async receive (blocks if empty)
message = await channel.receive()

# Check if empty first
if not channel.empty():
    message = await channel.receive()
```

### Channel Lifecycle

```python
# Create channel
channel = InMemoryChannel(name='worker-channel')

# Use channel
await channel.send(ChannelMessage(payload={'task': 1}))
message = await channel.receive()

# Close channel
channel.close()

# Further sends raise ChannelClosed
try:
    await channel.send(ChannelMessage(payload={}))
except ChannelClosed:
    print("Channel closed")
```

---

## ForwardingChannel

### Overview

Channel wrapper that forwards messages to downstream channels with metadata enrichment.

**Use Cases**:
- Per-edge instrumentation
- Metadata enrichment
- Message routing
- Fan-out patterns

### Creating Forwarding Channels

```python
from spark.nodes.channels import ForwardingChannel, InMemoryChannel

# Downstream channel
downstream = InMemoryChannel(name='downstream')

# Forwarding channel with metadata defaults
forwarder = ForwardingChannel(
    downstream=downstream,
    name='forwarder',
    metadata_defaults={
        'source': 'node_a',
        'priority': 'high'
    }
)
```

### Metadata Enrichment

```python
# Send message through forwarder
message = ChannelMessage(
    payload={'data': 'value'},
    metadata={'trace_id': 'abc'}
)

await forwarder.send(message)

# Downstream receives enriched message:
# metadata = {
#     'trace_id': 'abc',
#     'source': 'node_a',
#     'priority': 'high'
# }
```

### Observer Pattern

```python
def trace_edge(message, channel, phase):
    """Trace messages crossing edges."""
    print(f"[{channel.name}] {phase}: {message.metadata.get('trace_id')}")

forwarder = ForwardingChannel(
    downstream=downstream,
    observers=[trace_edge]
)

# Observers called on send and receive
await forwarder.send(message)  # Calls trace_edge with phase='send'
msg = await forwarder.receive()  # Calls trace_edge with phase='receive'
```

---

## Observer Hooks

### Observer Callable

```python
from typing import Union

ObserverCallable = Callable[
    [ChannelMessage, BaseChannel, str],  # message, channel, phase
    Union[None, Awaitable[None]]
]
```

### Synchronous Observer

```python
def sync_observer(message: ChannelMessage, channel: BaseChannel, phase: str) -> None:
    """Synchronous observer for logging."""
    print(f"[{channel.name}] {phase}: {message.payload}")

channel = InMemoryChannel(name='sync-observed', observers=[sync_observer])
```

### Asynchronous Observer

```python
async def async_observer(message: ChannelMessage, channel: BaseChannel, phase: str) -> None:
    """Asynchronous observer for metrics."""
    await record_metric(
        name=f"channel.{phase}",
        value=1,
        tags={'channel': channel.name}
    )

channel = InMemoryChannel(name='async-observed', observers=[async_observer])
```

### Observer Phases

Observers are called in two phases:
- **send**: When message is enqueued
- **receive**: When message is dequeued

```python
def phase_aware_observer(message, channel, phase):
    if phase == 'send':
        print(f"Sent: {message.payload}")
    elif phase == 'receive':
        print(f"Received: {message.payload}")

channel = InMemoryChannel(observers=[phase_aware_observer])
```

### Error Handling in Observers

```python
def failing_observer(message, channel, phase):
    raise Exception("Observer error!")

# Observer errors are caught and ignored
# Channel operations continue normally
channel = InMemoryChannel(observers=[failing_observer])

await channel.send(message)  # Succeeds despite observer error
```

---

## Mailbox Pattern

### Node Mailboxes

Each node has a `mailbox` attribute for receiving messages in long-running mode:

```python
from spark.nodes import Node
from spark.nodes.channels import InMemoryChannel

class WorkerNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Node automatically has mailbox
        # self.mailbox = InMemoryChannel(name=f'node:{self.id}')

    async def go(self):
        """Continuous worker loop."""
        while not self._stop_flag:
            # Receive from mailbox
            message = await self.mailbox.receive()

            if message.is_shutdown:
                break

            # Process message
            await self.process_message(message)

    async def process_message(self, message):
        """Handle incoming message."""
        payload = message.payload
        # Process payload...
```

### Message Routing

```python
# Node A sends to Node B's mailbox
await node_b.mailbox.send(ChannelMessage(
    payload={'task': 'process', 'data': data}
))
```

### Custom Mailbox Configuration

```python
class CustomMailboxNode(Node):
    def __init__(self, **kwargs):
        # Custom mailbox with size limit
        custom_mailbox = InMemoryChannel(
            name=f'custom-{uuid4().hex}',
            maxsize=50
        )

        super().__init__(mailbox=custom_mailbox, **kwargs)
```

---

## Long-Running Mode Usage

### Worker Node Pattern

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.channels import ChannelMessage

class ContinuousWorker(Node):
    """Node that runs continuously processing messages."""

    def __init__(self, **kwargs):
        config = NodeConfig(live=True)  # Enable continuous mode
        super().__init__(config=config, **kwargs)

    async def go(self):
        """Main worker loop."""
        print(f"Worker {self.id} starting")

        while not self._stop_flag:
            try:
                # Wait for message from mailbox
                message = await self.mailbox.receive()

                # Check for shutdown signal
                if message.is_shutdown:
                    print(f"Worker {self.id} shutting down")
                    break

                # Process message
                result = await self.process_payload(message.payload)

                # Send to next node(s)
                next_nodes = self.get_next_nodes()
                for next_node in next_nodes:
                    await next_node.mailbox.send(
                        ChannelMessage(payload=result)
                    )

                # Acknowledge processing
                if message.ack:
                    await message.ack()

            except Exception as e:
                print(f"Worker {self.id} error: {e}")

        print(f"Worker {self.id} stopped")

    async def process_payload(self, payload):
        """Process message payload."""
        # Implementation
        return {'processed': payload}
```

### Graph with Long-Running Nodes

```python
from spark.graphs import Graph, Task, TaskType

# Create worker nodes
worker1 = ContinuousWorker()
worker2 = ContinuousWorker()
worker3 = ContinuousWorker()

# Connect into pipeline
worker1 >> worker2 >> worker3

# Create graph
graph = Graph(start=worker1)

# Run in long-running mode
task = Task(
    inputs=NodeMessage(content={'data': 'initial'}),
    type=TaskType.LONG_RUNNING,
    budget=Budget(max_seconds=60)
)

result = await graph.run(task)
```

### Graceful Shutdown

```python
class ShutdownAwareWorker(Node):
    """Worker with graceful shutdown handling."""

    def __init__(self, **kwargs):
        config = NodeConfig(live=True)
        super().__init__(config=config, **kwargs)
        self.in_flight = 0

    async def go(self):
        """Worker loop with graceful shutdown."""
        while True:
            message = await self.mailbox.receive()

            if message.is_shutdown:
                # Wait for in-flight work to complete
                while self.in_flight > 0:
                    await asyncio.sleep(0.1)

                # Propagate shutdown to next nodes
                for next_node in self.get_next_nodes():
                    await next_node.mailbox.send(
                        ChannelMessage(payload=None, is_shutdown=True)
                    )

                break

            # Track in-flight work
            self.in_flight += 1

            try:
                result = await self.process_payload(message.payload)

                for next_node in self.get_next_nodes():
                    await next_node.mailbox.send(
                        ChannelMessage(payload=result)
                    )

            finally:
                self.in_flight -= 1
```

---

## Custom Channel Development

### Custom Channel Interface

```python
from spark.nodes.channels import BaseChannel, ChannelMessage

class RedisChannel(BaseChannel):
    """Channel backed by Redis pub/sub."""

    def __init__(self, redis_url: str, channel_name: str, **kwargs):
        super().__init__(name=channel_name)
        self.redis_url = redis_url
        self.client = None
        self.pubsub = None

    async def send(self, message: ChannelMessage) -> None:
        """Publish message to Redis."""
        if self.client is None:
            await self._connect()

        # Serialize message
        payload = self._serialize(message)

        # Publish to Redis
        await self.client.publish(self.name, payload)

    async def receive(self) -> ChannelMessage:
        """Subscribe and receive from Redis."""
        if self.pubsub is None:
            await self._subscribe()

        # Receive from Redis
        msg = await self.pubsub.get_message()

        # Deserialize
        return self._deserialize(msg['data'])

    def empty(self) -> bool:
        """Check if messages are pending."""
        # Redis pub/sub doesn't queue, so always "empty"
        return True

    def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            self.client.close()

    async def _connect(self):
        """Connect to Redis."""
        import redis.asyncio as redis
        self.client = await redis.from_url(self.redis_url)

    async def _subscribe(self):
        """Subscribe to channel."""
        self.pubsub = self.client.pubsub()
        await self.pubsub.subscribe(self.name)

    def _serialize(self, message: ChannelMessage) -> bytes:
        """Serialize message to bytes."""
        import pickle
        return pickle.dumps(message)

    def _deserialize(self, data: bytes) -> ChannelMessage:
        """Deserialize bytes to message."""
        import pickle
        return pickle.loads(data)
```

### Using Custom Channel

```python
# Create custom channel
redis_channel = RedisChannel(
    redis_url="redis://localhost:6379",
    channel_name="spark-messages"
)

# Use in node
class RedisWorker(Node):
    def __init__(self, **kwargs):
        super().__init__(mailbox=redis_channel, **kwargs)

    async def go(self):
        while not self._stop_flag:
            message = await self.mailbox.receive()
            # Process...
```

---

## QueueBridge

### Compatibility Layer

`QueueBridge` provides a queue-like API for legacy code:

```python
from spark.nodes.channels import QueueBridge, InMemoryChannel

# Create channel
channel = InMemoryChannel()

# Wrap with bridge
queue = QueueBridge(channel)

# Use like asyncio.Queue
await queue.put({'data': 'value'})  # Wraps in ChannelMessage
data = await queue.get()  # Unwraps payload

# Check empty
if not queue.empty():
    data = await queue.get()
```

**Note**: New code should use channels directly. QueueBridge is for backward compatibility.

---

## Best Practices

### 1. Use Descriptive Channel Names

```python
# Good: Descriptive name
channel = InMemoryChannel(name='user-processor-to-validator')

# Less ideal: Generic name
channel = InMemoryChannel(name='channel1')
```

### 2. Set Appropriate Mailbox Sizes

```python
# Bounded mailbox for backpressure
mailbox = InMemoryChannel(
    name=f'worker-{id}',
    maxsize=100  # Prevents unbounded growth
)
```

### 3. Always Check Shutdown Signals

```python
async def go(self):
    while not self._stop_flag:
        message = await self.mailbox.receive()

        # Always check shutdown first
        if message.is_shutdown:
            break

        # Process message...
```

### 4. Use Metadata for Tracing

```python
# Include trace information
message = ChannelMessage(
    payload={'data': 'value'},
    metadata={
        'trace_id': trace_id,
        'span_id': span_id,
        'timestamp': time.time()
    }
)
```

### 5. Handle Acknowledgements

```python
# Create ack callback
async def ack_handler():
    await update_status('completed')

message = ChannelMessage(
    payload={'task': 'process'},
    ack=ack_handler
)

# Sender creates ack, receiver calls it
await channel.send(message)

# Receiver
msg = await channel.receive()
result = await process(msg.payload)
if msg.ack:
    await msg.ack()  # Signal completion
```

---

## Performance Considerations

### Channel Overhead

- **InMemoryChannel**: Minimal overhead (~1-2 µs per message)
- **ForwardingChannel**: Small overhead for metadata merging
- **Observers**: Add ~1-5 µs per observer per message

### Optimization Tips

1. **Batch Messages**: Send multiple items in single payload when possible
2. **Limit Observers**: Only add necessary observers
3. **Avoid Large Payloads**: Keep messages small, use references for large data
4. **Monitor Queue Sizes**: Set `maxsize` to detect backpressure

### Bounded vs Unbounded Queues

```python
# Unbounded (default) - can grow without limit
channel = InMemoryChannel(maxsize=0)

# Bounded - provides backpressure
channel = InMemoryChannel(maxsize=100)
```

**Recommendation**: Use bounded queues in production to prevent memory exhaustion.

---

## Testing Channels

### Basic Channel Test

```python
import pytest
from spark.nodes.channels import InMemoryChannel, ChannelMessage

@pytest.mark.asyncio
async def test_channel_send_receive():
    """Test basic send/receive."""
    channel = InMemoryChannel()

    # Send message
    message = ChannelMessage(payload={'data': 'test'})
    await channel.send(message)

    # Receive message
    received = await channel.receive()

    assert received.payload == {'data': 'test'}
```

### Testing with Observers

```python
@pytest.mark.asyncio
async def test_channel_observers():
    """Test observer hooks."""
    observed_phases = []

    def observer(message, channel, phase):
        observed_phases.append(phase)

    channel = InMemoryChannel(observers=[observer])

    message = ChannelMessage(payload={'test': True})

    await channel.send(message)  # Triggers 'send' phase
    await channel.receive()  # Triggers 'receive' phase

    assert observed_phases == ['send', 'receive']
```

### Testing Shutdown

```python
@pytest.mark.asyncio
async def test_shutdown_signal():
    """Test shutdown message handling."""
    channel = InMemoryChannel()

    # Send shutdown
    shutdown_msg = ChannelMessage(payload=None, is_shutdown=True)
    await channel.send(shutdown_msg)

    # Receive and check
    msg = await channel.receive()
    assert msg.is_shutdown is True
```

---

## Related Documentation

- [Node Fundamentals](/docs/nodes/fundamentals.md) - Basic node concepts
- [Execution Modes](/docs/graphs/execution-modes.md) - Long-running workflows
- [Node System Architecture](/docs/architecture/node-system.md) - Design principles

---

## Summary

Channels provide messaging infrastructure for Spark:
- **ChannelMessage**: Rich message envelope with payload, metadata, ack, and shutdown flag
- **InMemoryChannel**: Default `asyncio.Queue`-based implementation
- **ForwardingChannel**: Metadata enrichment and message routing
- **Mailbox Pattern**: Per-node channels for long-running workers
- **Observer Hooks**: Instrumentation and monitoring
- **Custom Channels**: Extensible interface for alternative backends

Channels enable decoupled, asynchronous communication between nodes in long-running workflows.
