---
title: NodeConfig
parent: Config
nav_order: 2
---
# NodeConfig
---

`NodeConfig` is a Pydantic model that encapsulates all configurable aspects of a node's behavior including retry policies, timeouts, rate limiting, circuit breakers, idempotency, state management, hooks, and custom settings.

**Import**:
```python
from spark.nodes.config import NodeConfig
from spark.nodes.policies import RetryPolicy, TimeoutPolicy, RateLimiterPolicy
```

**Basic Usage**:
```python
from spark.nodes import Node

class MyNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            retry=RetryPolicy(max_attempts=3),
            timeout=TimeoutPolicy(seconds=30.0)
        )
        super().__init__(config=config, **kwargs)

    async def process(self, context):
        # Node logic with retry and timeout applied
        return {'status': 'success'}
```

## Complete Field Reference

### Core Fields

#### `id`

**Type**: `str`
**Default**: Auto-generated UUID hex
**Description**: Unique identifier for the node instance.

**Usage**:
```python
config = NodeConfig(id="my_custom_node_id")
```

**Notes**:
- Automatically generated if not provided
- Used for node tracking, telemetry, and debugging
- Should be unique within a graph

#### `type`

**Type**: `str | None`
**Default**: `None`
**Description**: Type identifier for the node class. Used for serialization and introspection.

**Usage**:
```python
config = NodeConfig(type="ProcessingNode")
```

**Notes**:
- Automatically inferred from class name if not set
- Used in graph specifications for node reconstruction
- Helpful for filtering or querying nodes by type

#### `description`

**Type**: `str | None`
**Default**: `None`
**Description**: Human-readable description of the node's purpose.

**Usage**:
```python
config = NodeConfig(
    description="Processes user input and validates schema"
)
```

**Notes**:
- Used for documentation and visualization
- Included in graph specifications
- Helpful for understanding workflow logic

#### `live`

**Type**: `bool`
**Default**: `False`
**Description**: Whether the node runs continuously (long-running mode).

**Usage**:
```python
config = NodeConfig(live=True)  # Node runs until explicitly stopped
```

**Notes**:
- Live nodes are used in `TaskType.LONG_RUNNING` graphs
- They process messages from their mailbox continuously
- Typically used for streaming, monitoring, or event-driven workflows

#### `initial_state`

**Type**: `NodeState`
**Default**: `default_node_state()`
**Description**: Initial state for the node when created.

**Usage**:
```python
from spark.nodes.types import default_node_state

initial = default_node_state(custom_counter=0, custom_data=[])
config = NodeConfig(initial_state=initial)
```

**Fields in NodeState**:
- `context_snapshot`: Last execution context snapshot
- `processing`: Boolean flag for processing status
- `pending_inputs`: Queue of pending messages
- `process_count`: Number of executions
- Custom fields via `**kwargs`

### Resilience Policies

#### `retry`

**Type**: `RetryPolicy | None`
**Default**: `None` (no retry)
**Description**: Retry configuration for handling transient failures.

**Usage**:
```python
from spark.nodes.policies import RetryPolicy

config = NodeConfig(
    retry=RetryPolicy(
        max_attempts=4,              # Total attempts (including initial)
        delay=1.0,                   # Initial delay in seconds
        backoff_multiplier=2.0,      # Exponential backoff
        max_delay=60.0,              # Max delay between attempts
        retry_on=(ConnectionError, TimeoutError),  # Exception types to retry
        retry_filter=lambda e: "temporary" in str(e),  # Custom filter
        jitter=lambda d: d * random.uniform(0.8, 1.2)  # Add jitter
    )
)
```

**RetryPolicy Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_attempts` | int | 4 | Maximum number of attempts (must be ≥ 1) |
| `delay` | float | 1.0 | Initial delay between retries (seconds) |
| `backoff_multiplier` | float | 1.0 | Exponential backoff multiplier (must be ≥ 1.0) |
| `max_delay` | float \| None | None | Maximum delay between retries (seconds) |
| `retry_on` | tuple[type[BaseException], ...] | (Exception,) | Exception types eligible for retry |
| `retry_filter` | Callable[[BaseException], bool] \| None | None | Custom function to determine if exception is retryable |
| `jitter` | Callable[[float], float] \| None | None | Function to add jitter to delay |

**Example - Common Patterns**:
```python
# Simple retry with exponential backoff
retry = RetryPolicy(max_attempts=3, delay=1.0, backoff_multiplier=2.0)
# Attempts at: 0s, 1s, 3s

# Retry specific exceptions only
retry = RetryPolicy(
    max_attempts=5,
    retry_on=(requests.HTTPError, requests.Timeout)
)

# Retry with custom filter
retry = RetryPolicy(
    max_attempts=3,
    retry_filter=lambda e: hasattr(e, 'status_code') and e.status_code >= 500
)

# Add jitter to prevent thundering herd
import random
retry = RetryPolicy(
    max_attempts=4,
    jitter=lambda d: d * random.uniform(0.5, 1.5)
)
```

#### `timeout`

**Type**: `TimeoutPolicy | None`
**Default**: `None` (no timeout)
**Description**: Timeout enforcement for node execution.

**Usage**:
```python
from spark.nodes.policies import TimeoutPolicy

config = NodeConfig(
    timeout=TimeoutPolicy(seconds=30.0)
)
```

**TimeoutPolicy Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `seconds` | float | Maximum execution time in seconds |

**Example**:
```python
# Short timeout for fast operations
timeout = TimeoutPolicy(seconds=5.0)

# Long timeout for batch processing
timeout = TimeoutPolicy(seconds=300.0)

# Very short timeout for cache lookups
timeout = TimeoutPolicy(seconds=0.5)
```

**Notes**:
- Raises `NodeTimeoutError` if execution exceeds timeout
- Timeout includes retry delays if retry policy is also configured
- Use with caution for operations that can't be safely interrupted

#### `rate_limiter`

**Type**: `RateLimiterPolicy | None`
**Default**: `None` (no rate limiting)
**Description**: Rate limiting configuration using token bucket algorithm.

**Usage**:
```python
from spark.nodes.policies import RateLimiterPolicy, Rate

config = NodeConfig(
    rate_limiter=RateLimiterPolicy(
        resource_key="api_calls",    # Shared key for rate limiting
        rate=Rate(limit=10.0, burst=5)  # 10 ops/sec, burst of 5
    )
)
```

**RateLimiterPolicy Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `resource_key` | str | Identifier for the rate-limited resource |
| `rate` | Rate | Rate configuration (limit and burst) |
| `registry` | RateLimiterRegistry | Registry for shared rate limiters (default: global) |

**Rate Configuration**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | float | Required | Operations per second (must be > 0) |
| `burst` | int | 1 | Maximum burst size (must be ≥ 1) |

**Example - Common Patterns**:
```python
# API rate limit: 100 requests per second, burst of 10
rate_limiter = RateLimiterPolicy(
    resource_key="openai_api",
    rate=Rate(limit=100.0, burst=10)
)

# Database rate limit: 50 queries per second, no burst
rate_limiter = RateLimiterPolicy(
    resource_key="postgres_db",
    rate=Rate(limit=50.0, burst=1)
)

# Shared rate limiter across multiple nodes
rate_limiter = RateLimiterPolicy(
    resource_key="shared_api",  # Same key = shared limit
    rate=Rate(limit=20.0, burst=5)
)
```

**Notes**:
- Multiple nodes can share a rate limiter by using the same `resource_key`
- Token bucket refills continuously at the specified rate
- Burst allows short bursts above the steady-state rate

#### `circuit_breaker`

**Type**: `CircuitBreakerPolicy | None`
**Default**: `None` (no circuit breaker)
**Description**: Circuit breaker configuration to prevent cascading failures.

**Usage**:
```python
from spark.nodes.policies import CircuitBreakerPolicy, CircuitBreaker

config = NodeConfig(
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key="external_service",
        circuit_breaker=CircuitBreaker(
            failure_threshold=5,    # Open after 5 failures
            window=30.0,            # In a 30-second window
            reset_timeout=15.0      # Try again after 15 seconds
        )
    )
)
```

**CircuitBreakerPolicy Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `breaker_key` | str | Identifier for the circuit breaker |
| `circuit_breaker` | CircuitBreaker | Circuit breaker configuration |
| `registry` | CircuitBreakerRegistry | Registry for shared circuit breakers (default: global) |

**CircuitBreaker Configuration**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `failure_threshold` | int | 5 | Number of failures before opening (must be ≥ 1) |
| `window` | float | 30.0 | Time window for counting failures (seconds, must be > 0) |
| `reset_timeout` | float | 15.0 | Time before trying again (seconds, must be > 0) |

**Circuit Breaker States**:
- **Closed**: Normal operation, requests flow through
- **Open**: Too many failures, requests are blocked
- **Half-Open**: Testing if service has recovered

**Example - Common Patterns**:
```python
# Conservative: Open quickly, recover slowly
circuit = CircuitBreakerPolicy(
    breaker_key="flaky_api",
    circuit_breaker=CircuitBreaker(
        failure_threshold=3,
        window=10.0,
        reset_timeout=60.0
    )
)

# Aggressive: Tolerate more failures, recover quickly
circuit = CircuitBreakerPolicy(
    breaker_key="reliable_api",
    circuit_breaker=CircuitBreaker(
        failure_threshold=10,
        window=60.0,
        reset_timeout=5.0
    )
)

# Shared circuit breaker across nodes
circuit = CircuitBreakerPolicy(
    breaker_key="shared_db",  # Same key = shared state
    circuit_breaker=CircuitBreaker(
        failure_threshold=5,
        window=30.0,
        reset_timeout=15.0
    )
)
```

**Notes**:
- Multiple nodes can share a circuit breaker using the same `breaker_key`
- Raises `CircuitBreakerOpenError` when circuit is open
- Automatically resets after successful execution in half-open state

#### `idempotency`

**Type**: `IdempotencyPolicy | None`
**Default**: `None` (no idempotency)
**Description**: Idempotency configuration to prevent duplicate operations.

**Usage**:
```python
from spark.nodes.policies import IdempotencyPolicy, IdempotencyConfig

config = NodeConfig(
    idempotency=IdempotencyPolicy(
        config=IdempotencyConfig(
            key_field="idempotency_key",
            key_resolver=lambda ctx: ctx.inputs.content.get("request_id")
        )
    )
)
```

**IdempotencyPolicy Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `config` | IdempotencyConfig | Idempotency configuration |

**IdempotencyConfig Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `store` | IdempotencyStore | InMemoryIdempotencyStore() | Storage backend for idempotency records |
| `key_field` | str | "idempotency_key" | Field name in inputs or state containing key |
| `key_resolver` | Callable \| None | None | Custom function to extract idempotency key |

**Example - Common Patterns**:
```python
# Simple field-based idempotency
idempotency = IdempotencyPolicy(
    config=IdempotencyConfig(key_field="request_id")
)

# Custom key resolver
idempotency = IdempotencyPolicy(
    config=IdempotencyConfig(
        key_resolver=lambda ctx: f"{ctx.inputs.content['user_id']}:{ctx.inputs.content['action']}"
    )
)

# Content-based idempotency (hash of inputs)
import hashlib
import json

def content_hash(ctx):
    content = json.dumps(ctx.inputs.content, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()

idempotency = IdempotencyPolicy(
    config=IdempotencyConfig(key_resolver=content_hash)
)
```

**Notes**:
- If key is found in store, returns cached result without re-execution
- Default store is in-memory; use custom store for persistence
- Key must be hashable (string, int, tuple, etc.)

### State Management

#### `keep_in_state`

**Type**: `list[str]`
**Default**: `[]` (empty list)
**Description**: List of input keys to persist in node state across executions.

**Usage**:
```python
config = NodeConfig(
    keep_in_state=['user_id', 'session_token', 'context_data']
)
```

**Example**:
```python
class SessionNode(Node):
    def __init__(self):
        config = NodeConfig(keep_in_state=['session_id', 'user_state'])
        super().__init__(config=config)

    async def process(self, context):
        # Access persisted state from previous execution
        session_id = context.state.get('session_id')
        user_state = context.state.get('user_state', {})

        # Modify state
        user_state['last_action'] = 'processed'

        return {
            'session_id': session_id,
            'user_state': user_state,
            'result': 'success'
        }
```

**Notes**:
- Only specified keys from `process()` return value are kept in state
- State persists across multiple `run()` calls
- Useful for maintaining context in multi-step workflows

### Hooks

#### `pre_process_hooks`

**Type**: `list[Callable[[ExecutionContext], None]]`
**Default**: `[]` (empty list)
**Description**: Hooks called before the `process()` method executes.

**Usage**:
```python
def log_start(context):
    print(f"Starting execution with inputs: {context.inputs.content}")

def validate_inputs(context):
    if not context.inputs.content:
        raise ValueError("Empty inputs not allowed")

config = NodeConfig(
    pre_process_hooks=[log_start, validate_inputs]
)
```

**Hook Signature**:
```python
def hook(context: ExecutionContext) -> None:
    # Can modify context.inputs, context.state, etc.
    pass
```

**Example - Common Patterns**:
```python
# Logging hook
def log_hook(context):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Node execution starting: {context.inputs.content}")

# Validation hook
def validate_hook(context):
    required_keys = ['user_id', 'action']
    for key in required_keys:
        if key not in context.inputs.content:
            raise ValueError(f"Missing required key: {key}")

# Metric collection hook
def metric_hook(context):
    context.state['start_time'] = time.time()

# Input transformation hook
def transform_hook(context):
    # Normalize inputs
    if isinstance(context.inputs.content, str):
        context.inputs.content = {'text': context.inputs.content}

config = NodeConfig(
    pre_process_hooks=[log_hook, validate_hook, metric_hook, transform_hook]
)
```

**Notes**:
- Hooks execute in order
- Can modify context in-place
- Exceptions in hooks prevent process() execution
- Useful for cross-cutting concerns (logging, validation, metrics)

#### `post_process_hooks`

**Type**: `list[Callable[[ExecutionContext], None]]`
**Default**: `[]` (empty list)
**Description**: Hooks called after the `process()` method executes successfully.

**Usage**:
```python
def log_completion(context):
    print(f"Completed with outputs: {context.outputs}")

def save_metrics(context):
    duration = time.time() - context.state.get('start_time', 0)
    print(f"Execution took {duration:.2f}s")

config = NodeConfig(
    post_process_hooks=[log_completion, save_metrics]
)
```

**Hook Signature**:
```python
def hook(context: ExecutionContext) -> None:
    # Can access context.outputs, context.state, etc.
    pass
```

**Example - Common Patterns**:
```python
# Logging hook
def log_hook(context):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Node execution completed: {context.outputs}")

# Metric collection hook
def metric_hook(context):
    start_time = context.state.get('start_time')
    if start_time:
        duration = time.time() - start_time
        context.metadata.duration = duration

# Cleanup hook
def cleanup_hook(context):
    # Clean up temporary resources
    temp_file = context.state.get('temp_file')
    if temp_file:
        os.remove(temp_file)

# Notification hook
def notify_hook(context):
    if context.outputs.get('critical'):
        send_alert(context.outputs)

config = NodeConfig(
    post_process_hooks=[log_hook, metric_hook, cleanup_hook, notify_hook]
)
```

**Notes**:
- Hooks execute in order
- Only called if process() succeeds
- Not called if process() raises exception
- Useful for cleanup, logging, metrics, notifications

### Observability

#### `redact_keys`

**Type**: `Set[str] | None`
**Default**: `None` (no redaction)
**Description**: Set of keys to redact in logs and telemetry.

**Usage**:
```python
config = NodeConfig(
    redact_keys={'password', 'api_key', 'secret', 'token', 'ssn'}
)
```

**Example**:
```python
class AuthNode(Node):
    def __init__(self):
        config = NodeConfig(
            redact_keys={'password', 'access_token', 'refresh_token'}
        )
        super().__init__(config=config)

    async def process(self, context):
        # These will be redacted in logs
        password = context.inputs.content['password']
        token = context.inputs.content['access_token']

        # Process authentication
        return {'authenticated': True, 'token': token}
```

**Notes**:
- Redacts specified keys in error snapshots and telemetry
- Case-sensitive matching
- Applies to nested dictionaries
- Use for PII and sensitive data

#### `event_sink`

**Type**: `EventSink | None`
**Default**: `None` (no event sink)
**Description**: Custom event sink for structured node lifecycle events.

**Usage**:
```python
from spark.nodes.types import EventSink

class MyEventSink(EventSink):
    async def emit(self, event: dict) -> None:
        # Send to custom logging/monitoring system
        print(f"Event: {event}")

config = NodeConfig(event_sink=MyEventSink())
```

**Event Structure**:
```python
{
    'node_id': 'node_123',
    'event_type': 'node_started' | 'node_finished' | 'node_failed',
    'timestamp': 1234567890.123,
    'data': {...}
}
```

**Example - Common Patterns**:
```python
# DataDog event sink
class DataDogEventSink(EventSink):
    async def emit(self, event: dict):
        from datadog import statsd
        statsd.increment(f"spark.node.{event['event_type']}")

# CloudWatch event sink
class CloudWatchEventSink(EventSink):
    async def emit(self, event: dict):
        import boto3
        client = boto3.client('logs')
        client.put_log_events(
            logGroupName='spark-events',
            logStreamName='node-events',
            logEvents=[{
                'timestamp': int(event['timestamp'] * 1000),
                'message': json.dumps(event)
            }]
        )

# File-based event sink
class FileEventSink(EventSink):
    def __init__(self, filepath):
        self.filepath = filepath

    async def emit(self, event: dict):
        with open(self.filepath, 'a') as f:
            f.write(json.dumps(event) + '\n')

config = NodeConfig(event_sink=FileEventSink('events.jsonl'))
```

### Validation and Human-in-the-Loop

#### `validators`

**Type**: `tuple[Callable[[Mapping[str, Any]], None | str], ...]`
**Default**: `()` (empty tuple)
**Description**: Validators for node outputs before resolution.

**Usage**:
```python
def validate_format(outputs):
    if 'result' not in outputs:
        return "Missing required field: result"
    return None  # Valid

def validate_range(outputs):
    value = outputs.get('value', 0)
    if not 0 <= value <= 100:
        return f"Value {value} out of range [0, 100]"
    return None

config = NodeConfig(
    validators=(validate_format, validate_range)
)
```

**Validator Signature**:
```python
def validator(outputs: Mapping[str, Any]) -> None | str:
    # Return None if valid
    # Return error message string if invalid
    pass
```

**Example**:
```python
# Schema validator
def schema_validator(outputs):
    required_keys = ['status', 'data', 'timestamp']
    missing = [k for k in required_keys if k not in outputs]
    if missing:
        return f"Missing required keys: {', '.join(missing)}"
    return None

# Type validator
def type_validator(outputs):
    if not isinstance(outputs.get('data'), dict):
        return "Field 'data' must be a dictionary"
    return None

# Business logic validator
def business_validator(outputs):
    if outputs.get('amount', 0) > 10000:
        return "Amount exceeds transaction limit"
    return None

config = NodeConfig(
    validators=(schema_validator, type_validator, business_validator)
)
```

**Notes**:
- Validators execute in order
- First failing validator stops execution
- Raise `NodeExecutionError` if validation fails
- Useful for output validation and business rules

#### `human_policy`

**Type**: `HumanInLoopPolicy | None`
**Default**: `None` (no human intervention)
**Description**: Policy for human-in-the-loop intervention points.

**Usage**:
```python
from spark.nodes.human import HumanApprovalPolicy

config = NodeConfig(
    human_policy=HumanApprovalPolicy(
        approver="admin@example.com",
        timeout_seconds=300  # 5 minutes to approve
    )
)
```

**Notes**:
- Requires human approval before node execution continues
- Blocks execution until approval/rejection received
- See [Human-in-the-Loop](../nodes/human.md) for details

## Complete Configuration Example

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.policies import (
    RetryPolicy,
    TimeoutPolicy,
    RateLimiterPolicy,
    CircuitBreakerPolicy,
    IdempotencyPolicy,
    IdempotencyConfig,
    Rate,
    CircuitBreaker
)

class ProductionNode(Node):
    def __init__(self, **kwargs):
        config = NodeConfig(
            id="production_node_001",
            type="ProductionNode",
            description="Production-grade node with all resilience features",

            # Retry with exponential backoff
            retry=RetryPolicy(
                max_attempts=3,
                delay=1.0,
                backoff_multiplier=2.0,
                max_delay=30.0,
                retry_on=(ConnectionError, TimeoutError)
            ),

            # 30-second timeout
            timeout=TimeoutPolicy(seconds=30.0),

            # Rate limit: 100 ops/sec, burst of 10
            rate_limiter=RateLimiterPolicy(
                resource_key="api_calls",
                rate=Rate(limit=100.0, burst=10)
            ),

            # Circuit breaker: open after 5 failures in 30 seconds
            circuit_breaker=CircuitBreakerPolicy(
                breaker_key="external_api",
                circuit_breaker=CircuitBreaker(
                    failure_threshold=5,
                    window=30.0,
                    reset_timeout=15.0
                )
            ),

            # Idempotency based on request_id
            idempotency=IdempotencyPolicy(
                config=IdempotencyConfig(
                    key_field="request_id"
                )
            ),

            # Persist state
            keep_in_state=['session_id', 'user_context'],

            # Pre-process hooks
            pre_process_hooks=[
                lambda ctx: print(f"Starting: {ctx.inputs.content}"),
            ],

            # Post-process hooks
            post_process_hooks=[
                lambda ctx: print(f"Completed: {ctx.outputs}"),
            ],

            # Redact sensitive keys
            redact_keys={'password', 'api_key', 'secret'},

            # Output validators
            validators=(
                lambda o: None if 'result' in o else "Missing result",
            )
        )

        super().__init__(config=config, **kwargs)

    async def process(self, context):
        # Process with all resilience features applied
        result = await self.call_external_api(context.inputs.content)
        return {'result': result, 'status': 'success'}
```

## Configuration Patterns

### Development Configuration

```python
config = NodeConfig(
    # No resilience features for faster debugging
    retry=None,
    timeout=None,

    # Verbose logging
    pre_process_hooks=[lambda ctx: print(f"DEBUG: {ctx.inputs}")],
    post_process_hooks=[lambda ctx: print(f"DEBUG: {ctx.outputs}")],

    # No redaction for debugging
    redact_keys=None
)
```

### Production Configuration

```python
config = NodeConfig(
    # Full resilience stack
    retry=RetryPolicy(max_attempts=3, backoff_multiplier=2.0),
    timeout=TimeoutPolicy(seconds=30.0),
    rate_limiter=RateLimiterPolicy(
        resource_key="prod_api",
        rate=Rate(limit=100.0, burst=10)
    ),
    circuit_breaker=CircuitBreakerPolicy(
        breaker_key="prod_service",
        circuit_breaker=CircuitBreaker(failure_threshold=5)
    ),

    # Security
    redact_keys={'password', 'api_key', 'token', 'ssn'},

    # Monitoring
    pre_process_hooks=[metrics_hook, trace_hook],
    post_process_hooks=[metrics_hook, alert_hook]
)
```

### Testing Configuration

```python
config = NodeConfig(
    # Fast timeouts for tests
    timeout=TimeoutPolicy(seconds=1.0),

    # No retry for predictable tests
    retry=None,

    # Capture events for assertions
    event_sink=TestEventSink(),

    # Strict validation
    validators=(strict_schema_validator,)
)
```

## See Also

- [Node Guide](../nodes/nodes.md) - Node architecture and usage
- [Capabilities](../nodes/capabilities.md) - Policy system details
- [AgentConfig Reference](agent-config.md) - Agent configuration
- [Graph Configuration](../graphs/graphs.md) - Graph-level configuration
