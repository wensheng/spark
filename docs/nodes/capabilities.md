# Capabilities System

**Document Type**: Reference Documentation
**Audience**: Developers adding resilience and control to nodes
**Related**: [Node Fundamentals](/docs/nodes/fundamentals.md), [Node Configuration](/docs/config/node-config.md)

---

## Overview

The Capabilities System (implemented as Policies in `spark/nodes/policies.py`) provides declarative mechanisms for enhancing nodes with resilience, resource control, and execution policies. Instead of implementing retry logic, timeouts, or rate limiting manually in every node, you configure these capabilities via `NodeConfig` and the framework applies them automatically.

**Key Benefits**:
- **Declarative**: Configure behavior without boilerplate code
- **Composable**: Combine multiple capabilities on a single node
- **Testable**: Capabilities are independently testable
- **Transparent**: Applied automatically via wrapper pattern
- **Reusable**: Same configuration across multiple nodes

**Available Capabilities**:
1. **RetryCapability**: Automatic retry with backoff strategies
2. **TimeoutCapability**: Execution time limits
3. **RateLimitCapability**: Token-bucket rate limiting
4. **CircuitBreakerCapability**: Failure isolation
5. **IdempotencyCapability**: Deduplication of operations
6. **BatchCapability**: Batch processing strategies (via node design pattern)

---

## Architecture

### Wrapper Pattern

Capabilities are implemented using the **process wrapper pattern**. Each capability wraps the node's `_process()` method with additional logic:

```
Original:  context -> _process() -> result

With Retry:
  context -> RetryWrapper -> _process() -> result
                   ↑ retry on failure ↑

With Multiple:
  context -> IdempotencyWrapper
              -> RateLimiterWrapper
                  -> CircuitBreakerWrapper
                      -> TimeoutWrapper
                          -> RetryWrapper
                              -> _process() -> result
```

### Application Order

Policies are applied in a specific order (outer to inner):
1. **Idempotency** - Check early to avoid unnecessary work
2. **RateLimiter** - Throttle before execution
3. **CircuitBreaker** - Check circuit state
4. **Timeout** - Wrap execution with time limit
5. **Retry** - Outermost retry logic

This order ensures optimal behavior: idempotency checks happen first, rate limits are respected, circuit breakers prevent wasted attempts, timeouts constrain each attempt, and retries wrap the entire execution.

---

## RetryCapability

### Overview

Automatically retry failed operations with configurable backoff strategies.

**Use Cases**:
- Transient API failures
- Network interruptions
- Temporary resource unavailability
- Rate limit recovery

### Configuration

```python
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy

config = NodeConfig(
    retry=RetryPolicy(
        max_attempts=5,              # Maximum retry attempts
        backoff='exponential',        # Backoff strategy
        initial_delay=1.0,           # Initial delay in seconds
        max_delay=60.0,              # Maximum delay cap
        backoff_factor=2.0,          # Multiplier for exponential
        jitter=True,                 # Add random jitter
        retriable_exceptions=None    # Which exceptions to retry
    )
)

node = MyNode(config=config)
```

### Backoff Strategies

#### Exponential Backoff (Default)

Delay doubles with each attempt:

```python
retry=RetryPolicy(
    max_attempts=5,
    backoff='exponential',
    initial_delay=1.0,
    max_delay=60.0,
    backoff_factor=2.0
)

# Delays: 1s, 2s, 4s, 8s, 16s
```

**Formula**: `delay = min(initial_delay * (backoff_factor ** attempt), max_delay)`

#### Linear Backoff

Delay increases linearly:

```python
retry=RetryPolicy(
    max_attempts=5,
    backoff='linear',
    initial_delay=2.0,
    backoff_factor=1.5
)

# Delays: 2s, 3.5s, 5s, 6.5s, 8s
```

**Formula**: `delay = initial_delay + (backoff_factor * attempt)`

#### Constant Backoff

Fixed delay between attempts:

```python
retry=RetryPolicy(
    max_attempts=3,
    backoff='constant',
    initial_delay=5.0
)

# Delays: 5s, 5s, 5s
```

#### Jitter

Add randomness to prevent thundering herd:

```python
retry=RetryPolicy(
    max_attempts=3,
    backoff='exponential',
    initial_delay=1.0,
    jitter=True  # Adds ±25% randomness
)

# Without jitter: 1s, 2s, 4s
# With jitter: ~0.8s, ~1.9s, ~3.7s (varies)
```

### Retriable Exceptions

Control which exceptions trigger retries:

```python
from requests.exceptions import RequestException, Timeout

retry=RetryPolicy(
    max_attempts=3,
    retriable_exceptions=(RequestException, Timeout)
)

# Only RequestException and Timeout are retried
# Other exceptions fail immediately
```

Default: All exceptions are retriable (retry on any error).

### Complete Example

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy
from spark.nodes.types import ExecutionContext

class APICallNode(Node):
    """Node that calls external API with retry."""

    def __init__(self, **kwargs):
        config = NodeConfig(
            retry=RetryPolicy(
                max_attempts=5,
                backoff='exponential',
                initial_delay=1.0,
                max_delay=30.0,
                jitter=True
            )
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Automatically retried on failure
        response = await self.call_api()
        return {'data': response}

    async def call_api(self):
        # May raise exceptions - will be retried
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.example.com/data') as resp:
                return await resp.json()
```

### Monitoring Retries

Track retry attempts via execution context:

```python
class MonitoredNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        # Access current attempt number
        attempt = context.metadata.attempt

        print(f"Attempt {attempt}")

        # Your logic here
        return {'attempt': attempt}
```

---

## TimeoutCapability

### Overview

Enforce maximum execution time for node operations.

**Use Cases**:
- Prevent hung operations
- Enforce SLAs
- Resource cleanup on slow operations
- Fail-fast patterns

### Configuration

```python
from spark.nodes.policies import TimeoutPolicy

config = NodeConfig(
    timeout=TimeoutPolicy(seconds=30.0)
)

node = MyNode(config=config)
```

### Timeout Behavior

When a timeout occurs:
1. Operation is cancelled via `asyncio.CancelledError`
2. `NodeTimeoutError` is raised
3. Context snapshot captured for debugging
4. Retries can wrap timeout (if configured)

### Example

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import TimeoutPolicy
from spark.nodes.exceptions import NodeTimeoutError

class TimedNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            timeout=TimeoutPolicy(seconds=5.0)
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Will timeout after 5 seconds
        await asyncio.sleep(10)  # Takes too long!
        return {'done': True}

# Usage
try:
    await node.run(inputs)
except NodeTimeoutError as e:
    print(f"Node timed out after {e.timeout}s")
```

### Combining with Retry

```python
config = NodeConfig(
    retry=RetryPolicy(max_attempts=3),
    timeout=TimeoutPolicy(seconds=10.0)
)

# Each retry attempt has 10s timeout
# Total possible time: 30s (3 attempts × 10s)
```

---

## RateLimitCapability

### Overview

Throttle node execution using token bucket algorithm.

**Use Cases**:
- API rate limiting
- Resource protection
- Cost control
- Quota management

### Configuration

```python
from spark.nodes.policies import RateLimiterPolicy, Rate

config = NodeConfig(
    rate_limiter=RateLimiterPolicy(
        resource_key='api-calls',    # Shared resource identifier
        rate=Rate(limit=10.0, burst=2)  # 10 tokens/sec, burst of 2
    )
)

node = MyNode(config=config)
```

### Token Bucket Algorithm

The rate limiter uses a **token bucket** algorithm:

- **Bucket capacity**: `burst` parameter
- **Refill rate**: `limit` tokens per second
- **Consumption**: 1 token per execution

```python
rate=Rate(limit=5.0, burst=10)

# Bucket starts full: 10 tokens
# Refills at 5 tokens/second
# Each execution consumes 1 token
```

**Behavior**:
- If tokens available: Execute immediately
- If no tokens: Wait until tokens refill
- Burst allows temporary exceeding of sustained rate

### Resource Keys

Multiple nodes can share rate limits via `resource_key`:

```python
# Both nodes share same rate limit
node1 = APINode(config=NodeConfig(
    rate_limiter=RateLimiterPolicy(
        resource_key='shared-api',
        rate=Rate(limit=10.0, burst=2)
    )
))

node2 = APINode(config=NodeConfig(
    rate_limiter=RateLimiterPolicy(
        resource_key='shared-api',  # Same key!
        rate=Rate(limit=10.0, burst=2)
    )
))

# Combined rate: 10 calls/second across both nodes
```

### Example: API Rate Limiting

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RateLimiterPolicy, Rate

class RateLimitedAPINode(Node):
    """Node with API rate limiting."""

    def __init__(self, **kwargs):
        config = NodeConfig(
            rate_limiter=RateLimiterPolicy(
                resource_key='openai-api',
                rate=Rate(
                    limit=50.0,   # 50 requests per second
                    burst=10      # Allow burst of 10
                )
            )
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Automatically rate limited
        response = await self.call_openai_api()
        return {'response': response}
```

### Registry Management

Rate limiters use a global registry (`RateLimiterRegistry`) to coordinate across nodes:

```python
from spark.nodes.policies import _DEFAULT_RATE_REGISTRY

# All nodes share the default registry
# Custom registry can be provided if needed
```

---

## CircuitBreakerCapability

### Overview

Prevent cascading failures by "opening" the circuit after repeated failures.

**Use Cases**:
- Failing dependency protection
- Cascade failure prevention
- System degradation handling
- Fast-fail patterns

### Configuration

```python
from spark.nodes.policies import CircuitBreakerPolicy, CircuitBreaker

config = NodeConfig(
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key='external-service',
        breaker=CircuitBreaker(
            failure_threshold=5,    # Open after 5 failures
            window=30.0,           # Within 30 second window
            reset_timeout=15.0     # Try again after 15 seconds
        )
    )
)

node = MyNode(config=config)
```

### Circuit States

```
CLOSED → (failures reach threshold) → OPEN → (reset timeout) → HALF_OPEN
   ↑                                                                 |
   └─────────────────── (success) ──────────────────────────────────┘
```

1. **CLOSED** (normal): Operations proceed normally
2. **OPEN** (failed): All operations fail immediately
3. **HALF_OPEN** (testing): Allow one operation to test recovery

### Behavior by State

| State | Behavior | Transition |
|-------|----------|------------|
| CLOSED | Execute normally | → OPEN after threshold failures |
| OPEN | Fail immediately with `CircuitBreakerOpenError` | → HALF_OPEN after reset timeout |
| HALF_OPEN | Allow one test execution | → CLOSED on success, → OPEN on failure |

### Parameters

- **failure_threshold**: Number of failures to open circuit
- **window**: Time window for counting failures (seconds)
- **reset_timeout**: Time to wait before entering HALF_OPEN (seconds)

### Example

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import CircuitBreakerPolicy, CircuitBreaker
from spark.nodes.exceptions import CircuitBreakerOpenError

class ProtectedNode(Node):
    """Node protected by circuit breaker."""

    def __init__(self, **kwargs):
        config = NodeConfig(
            circuit_breaker=CircuitBreakerPolicy(
                breaker_key='database',
                breaker=CircuitBreaker(
                    failure_threshold=3,
                    window=10.0,
                    reset_timeout=5.0
                )
            )
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Protected by circuit breaker
        result = await self.query_database()
        return {'result': result}

# Usage
try:
    await node.run(inputs)
except CircuitBreakerOpenError as e:
    print(f"Circuit open for key: {e.key}")
    print(f"Retry after: {e.retry_after}s")
```

### Shared Circuit Breakers

Multiple nodes can share circuit breakers via `breaker_key`:

```python
# Both nodes share circuit state
node1 = DBNode(config=NodeConfig(
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key='shared-db',
        breaker=CircuitBreaker(...)
    )
))

node2 = DBNode(config=NodeConfig(
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key='shared-db',  # Same key
        breaker=CircuitBreaker(...)
    )
))
```

---

## IdempotencyCapability

### Overview

Deduplicate operations based on content hash or custom keys.

**Use Cases**:
- Prevent duplicate processing
- Retry safety
- Exactly-once semantics
- Request deduplication

### Configuration

```python
from spark.nodes.policies import IdempotencyPolicy, IdempotencyConfig

config = NodeConfig(
    idempotency=IdempotencyPolicy(
        idempotency_config=IdempotencyConfig(
            key_fn=None,              # Custom key function
            ttl_seconds=3600.0,       # Cache TTL
            use_content_hash=True     # Hash inputs
        )
    )
)

node = MyNode(config=config)
```

### Content Hash Strategy

By default, idempotency uses content hash of inputs:

```python
config = NodeConfig(
    idempotency=IdempotencyPolicy(
        idempotency_config=IdempotencyConfig(
            use_content_hash=True
        )
    )
)

# Same inputs = same hash = cached result
await node.run(NodeMessage(content={'user_id': 123}))  # Executes
await node.run(NodeMessage(content={'user_id': 123}))  # Returns cached
```

### Custom Key Function

Provide custom logic for generating idempotency keys:

```python
def custom_key(context: ExecutionContext) -> str:
    """Generate key from user_id and timestamp."""
    user_id = context.inputs.content['user_id']
    timestamp = context.inputs.content['timestamp']
    return f"{user_id}:{timestamp}"

config = NodeConfig(
    idempotency=IdempotencyPolicy(
        idempotency_config=IdempotencyConfig(
            key_fn=custom_key,
            use_content_hash=False
        )
    )
)
```

### TTL (Time-To-Live)

Control how long results are cached:

```python
config = NodeConfig(
    idempotency=IdempotencyPolicy(
        idempotency_config=IdempotencyConfig(
            ttl_seconds=300.0  # 5 minutes
        )
    )
)

# After 5 minutes, same inputs will re-execute
```

### Example

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import IdempotencyPolicy, IdempotencyConfig

class IdempotentNode(Node):
    """Node with idempotency."""

    def __init__(self, **kwargs):
        config = NodeConfig(
            idempotency=IdempotencyPolicy(
                idempotency_config=IdempotencyConfig(
                    ttl_seconds=3600.0
                )
            )
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Expensive operation
        result = await self.expensive_computation()
        return {'result': result}

# First call executes
result1 = await node.run(NodeMessage(content={'data': 'test'}))

# Second call returns cached result (same inputs)
result2 = await node.run(NodeMessage(content={'data': 'test'}))

# Different inputs execute again
result3 = await node.run(NodeMessage(content={'data': 'other'}))
```

---

## BatchCapability

### Overview

Process multiple items in batches rather than individually.

**Note**: Batch processing is implemented as a **node design pattern** rather than a declarative capability. Nodes override `process_item()` method and configure batch behavior.

**Use Cases**:
- Bulk API calls
- Database batch inserts
- Parallel processing
- Throughput optimization

### Implementation Pattern

```python
from spark.nodes import Node
from spark.nodes.types import ExecutionContext

class BatchProcessingNode(Node):
    """Node that processes items in batches."""

    def __init__(self, batch_size=10, **kwargs):
        super().__init__(**kwargs)
        self.batch_size = batch_size

    async def process(self, context: ExecutionContext) -> dict:
        """Batch multiple items and process together."""
        items = context.inputs.content.get('items', [])

        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            batch_result = await self.process_batch(batch)
            results.extend(batch_result)

        return {'results': results}

    async def process_batch(self, batch: list) -> list:
        """Process a single batch."""
        # Bulk operation
        return [self.transform(item) for item in batch]

    def transform(self, item):
        """Transform single item."""
        return item * 2
```

### Batch Strategies

#### All-or-Nothing

```python
class AllOrNothingBatch(Node):
    async def process_batch(self, batch: list) -> list:
        try:
            # All succeed or all fail
            results = await self.bulk_insert(batch)
            return results
        except Exception as e:
            # Entire batch fails
            raise
```

#### Skip Failed

```python
class SkipFailedBatch(Node):
    async def process_batch(self, batch: list) -> list:
        results = []
        for item in batch:
            try:
                result = await self.process_item(item)
                results.append({'success': True, 'data': result})
            except Exception as e:
                results.append({'success': False, 'error': str(e)})
        return results
```

#### Collect Errors

```python
class CollectErrorsBatch(Node):
    async def process_batch(self, batch: list) -> dict:
        successes = []
        errors = []

        for item in batch:
            try:
                result = await self.process_item(item)
                successes.append(result)
            except Exception as e:
                errors.append({'item': item, 'error': str(e)})

        return {
            'successes': successes,
            'errors': errors,
            'total': len(batch)
        }
```

### Time-Based Batching

```python
import asyncio
from collections import deque

class TimeBasedBatch(Node):
    def __init__(self, batch_size=10, max_wait=5.0, **kwargs):
        super().__init__(**kwargs)
        self.batch_size = batch_size
        self.max_wait = max_wait
        self.pending = deque()

    async def process(self, context: ExecutionContext) -> dict:
        item = context.inputs.content
        self.pending.append(item)

        # Wait for batch to fill or timeout
        start_time = asyncio.get_event_loop().time()
        while len(self.pending) < self.batch_size:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= self.max_wait:
                break
            await asyncio.sleep(0.1)

        # Process accumulated batch
        batch = list(self.pending)
        self.pending.clear()

        results = await self.process_batch(batch)
        return {'results': results}
```

---

## Combining Multiple Capabilities

### Configuration

```python
from spark.nodes.config import NodeConfig
from spark.nodes.policies import (
    RetryPolicy,
    TimeoutPolicy,
    RateLimiterPolicy,
    CircuitBreakerPolicy,
    IdempotencyPolicy,
    Rate,
    CircuitBreaker,
    IdempotencyConfig
)

config = NodeConfig(
    # Idempotency (innermost)
    idempotency=IdempotencyPolicy(
        idempotency_config=IdempotencyConfig(ttl_seconds=300.0)
    ),

    # Rate limiting
    rate_limiter=RateLimiterPolicy(
        resource_key='api',
        rate=Rate(limit=10.0, burst=2)
    ),

    # Circuit breaker
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key='service',
        breaker=CircuitBreaker(
            failure_threshold=5,
            window=30.0,
            reset_timeout=15.0
        )
    ),

    # Timeout (per attempt)
    timeout=TimeoutPolicy(seconds=30.0),

    # Retry (outermost)
    retry=RetryPolicy(
        max_attempts=3,
        backoff='exponential',
        initial_delay=1.0
    )
)

node = ResilientNode(config=config)
```

### Execution Flow

```
1. Idempotency check (fast path if cached)
2. Rate limiter acquire token
3. Circuit breaker check state
4. Timeout wrapper starts
5.   Retry wrapper (attempt 1)
6.     Process executes
7.   Retry wrapper (attempt 2 if failure)
8.     Process executes
9. Timeout wrapper ends
10. Circuit breaker record result
11. Rate limiter release token (no-op for token bucket)
12. Idempotency cache result
```

### Example: Production-Ready Node

```python
class ProductionNode(Node):
    """Node with full production resilience."""

    def __init__(self, **kwargs):
        config = NodeConfig(
            # Deduplication
            idempotency=IdempotencyPolicy(
                idempotency_config=IdempotencyConfig(
                    ttl_seconds=3600.0
                )
            ),

            # Rate limiting (50 req/s)
            rate_limiter=RateLimiterPolicy(
                resource_key='external-api',
                rate=Rate(limit=50.0, burst=10)
            ),

            # Circuit breaker (5 failures in 30s)
            circuit_breaker=CircuitBreakerPolicy(
                breaker_key='external-api',
                breaker=CircuitBreaker(
                    failure_threshold=5,
                    window=30.0,
                    reset_timeout=60.0
                )
            ),

            # 30s timeout per attempt
            timeout=TimeoutPolicy(seconds=30.0),

            # 3 retries with exponential backoff
            retry=RetryPolicy(
                max_attempts=3,
                backoff='exponential',
                initial_delay=1.0,
                max_delay=10.0,
                jitter=True
            )
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # All capabilities applied automatically
        response = await self.call_external_api()
        return {'response': response}
```

---

## Custom Capability Development

### Creating a Custom Capability

Custom capabilities implement the `SupportsProcessWrapper` protocol:

```python
from spark.nodes.policies import SupportsProcessWrapper, ProcessFn, ProcessWrapper
from spark.nodes.base import BaseNode
from spark.nodes.types import ExecutionContext

class LoggingCapability(SupportsProcessWrapper):
    """Custom capability that logs execution."""

    def __init__(self, log_inputs=True, log_outputs=True):
        self.log_inputs = log_inputs
        self.log_outputs = log_outputs

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Build process wrapper for this capability."""

        async def wrapper(context: ExecutionContext, process_fn: ProcessFn):
            if self.log_inputs:
                print(f"[{node.id}] Inputs: {context.inputs.content}")

            result = await process_fn(context)

            if self.log_outputs:
                print(f"[{node.id}] Outputs: {result}")

            return result

        return wrapper
```

### Using Custom Capability

```python
# Add custom capability to NodeConfig
# (Currently requires extending NodeConfig)

class ExtendedNodeConfig(NodeConfig):
    logging: LoggingCapability | None = None

class CustomNode(Node):
    def _get_default_config(self):
        return ExtendedNodeConfig()

    def _apply_policies(self):
        super()._apply_policies()

        # Apply custom capability
        if hasattr(self.config, 'logging') and self.config.logging:
            wrapper = self.config.logging.build_wrapper(self)
            # Compose with existing wrappers
```

### Wrapper Composition

```python
from spark.nodes.policies import compose_process_wrappers

# Multiple wrappers compose correctly
wrappers = [
    retry_wrapper,
    timeout_wrapper,
    logging_wrapper
]

composed = compose_process_wrappers(base_process, wrappers)
```

---

## Testing Capabilities

### Testing Retry

```python
import pytest
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy

@pytest.mark.asyncio
async def test_retry_capability():
    attempts = []

    class FlakyNode(Node):
        async def process(self, context):
            attempts.append(1)
            if len(attempts) < 3:
                raise Exception("Temporary failure")
            return {'success': True}

    config = NodeConfig(
        retry=RetryPolicy(max_attempts=5, backoff='constant')
    )
    node = FlakyNode(config=config)

    result = await node.run(NodeMessage(content={}))

    assert len(attempts) == 3
    assert result.content['success'] is True
```

### Testing Timeout

```python
@pytest.mark.asyncio
async def test_timeout_capability():
    from spark.nodes.exceptions import NodeTimeoutError

    class SlowNode(Node):
        async def process(self, context):
            await asyncio.sleep(10)
            return {'done': True}

    config = NodeConfig(
        timeout=TimeoutPolicy(seconds=1.0)
    )
    node = SlowNode(config=config)

    with pytest.raises(NodeTimeoutError):
        await node.run(NodeMessage(content={}))
```

### Testing Rate Limiting

```python
@pytest.mark.asyncio
async def test_rate_limit_capability():
    from spark.nodes.policies import Rate

    call_times = []

    class APINode(Node):
        async def process(self, context):
            call_times.append(asyncio.get_event_loop().time())
            return {'done': True}

    config = NodeConfig(
        rate_limiter=RateLimiterPolicy(
            resource_key='test',
            rate=Rate(limit=2.0, burst=1)  # 2 per second
        )
    )
    node = APINode(config=config)

    # Call 3 times rapidly
    await node.run(NodeMessage(content={}))
    await node.run(NodeMessage(content={}))
    await node.run(NodeMessage(content={}))

    # Third call should be delayed
    assert call_times[2] - call_times[0] >= 0.5  # Rate limited
```

---

## Best Practices

### 1. Start with Minimal Capabilities

```python
# Start simple
config = NodeConfig(
    retry=RetryPolicy(max_attempts=3)
)

# Add more as needed
config = NodeConfig(
    retry=RetryPolicy(max_attempts=3),
    timeout=TimeoutPolicy(seconds=30.0)
)
```

### 2. Match Capabilities to Use Case

```python
# External API: retry + rate limit + circuit breaker
api_config = NodeConfig(
    retry=RetryPolicy(max_attempts=3),
    rate_limiter=RateLimiterPolicy(...),
    circuit_breaker=CircuitBreakerPolicy(...)
)

# Internal computation: timeout only
compute_config = NodeConfig(
    timeout=TimeoutPolicy(seconds=60.0)
)
```

### 3. Share Resource Keys

```python
# All API nodes share rate limit
api_rate_limiter = RateLimiterPolicy(
    resource_key='external-api',
    rate=Rate(limit=50.0, burst=10)
)

node1 = APINode(config=NodeConfig(rate_limiter=api_rate_limiter))
node2 = APINode(config=NodeConfig(rate_limiter=api_rate_limiter))
```

### 4. Use Idempotency for Retry Safety

```python
# Combination is safe for retries
config = NodeConfig(
    retry=RetryPolicy(max_attempts=5),
    idempotency=IdempotencyPolicy(...)
)
# Retries won't duplicate side effects
```

### 5. Set Appropriate Timeouts

```python
# Timeout > typical execution time
config = NodeConfig(
    timeout=TimeoutPolicy(seconds=30.0)  # Node typically takes 5-10s
)
```

---

## Performance Considerations

### Overhead

Each capability adds minimal overhead:
- **Retry**: No overhead on success, backoff delay on failure
- **Timeout**: Task creation overhead (~microseconds)
- **Rate Limiter**: Lock acquisition + refill calculation
- **Circuit Breaker**: Lock acquisition + state check
- **Idempotency**: Hash computation + cache lookup

### Optimization Tips

1. **Idempotency**: Use short TTLs to limit cache size
2. **Rate Limiting**: Use burst capacity for bursty workloads
3. **Circuit Breaker**: Tune thresholds to avoid false opens
4. **Timeout**: Set generously to avoid premature cancellation

---

## Related Documentation

- [Node Fundamentals](/docs/nodes/fundamentals.md) - Basic node concepts
- [Node Configuration](/docs/config/node-config.md) - Complete config reference
- [Error Handling](/docs/agents/error-handling.md) - Exception types
- [Best Practices: Nodes](/docs/best-practices/nodes.md) - Production patterns

---

## Summary

The Capabilities System provides:
- **RetryCapability**: Automatic retry with backoff strategies (exponential, linear, constant)
- **TimeoutCapability**: Execution time limits with cancellation
- **RateLimitCapability**: Token bucket rate limiting with shared resource keys
- **CircuitBreakerCapability**: Failure isolation with state management (closed/open/half-open)
- **IdempotencyCapability**: Deduplication via content hash or custom keys
- **BatchCapability**: Design pattern for bulk processing

Capabilities are declarative, composable, and transparent - configure once, apply automatically.
