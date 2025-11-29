import asyncio
import pytest
from typing import Any
from unittest.mock import Mock, AsyncMock

from spark.nodes.base import BaseNode
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.nodes.config import NodeConfig
from spark.nodes.nodes import Node
from spark.nodes.policies import (
    RetryPolicy,
    TimeoutPolicy,
    RateLimiterPolicy,
    Rate,
    CircuitBreaker,
    CircuitBreakerPolicy,
    IdempotencyPolicy,
    IdempotencyConfig,
    InMemoryIdempotencyStore,
)
from spark.nodes.exceptions import NodeExecutionError, NodeTimeoutError, CircuitBreakerOpenError

# Mock classes and objects
class MockNode(Node):
    async def process(self, context: ExecutionContext) -> Any:
        return context.inputs.content

class FailingNode(Node):
    def __init__(self, fail_count=1, error_type=ValueError, **kwargs):
        super().__init__(**kwargs)
        self.fail_count = fail_count
        self.attempts = 0
        self.error_type = error_type

    async def process(self, context: ExecutionContext) -> Any:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise self.error_type("Simulated failure")
        return context.inputs.content

class SlowNode(Node):
    def __init__(self, delay=0.1, **kwargs):
        super().__init__(**kwargs)
        self.delay = delay

    async def process(self, context: ExecutionContext) -> Any:
        await asyncio.sleep(self.delay)
        return context.inputs.content

@pytest.mark.asyncio
async def test_retry_policy():
    # Configure retry policy: 3 attempts max
    retry_policy = RetryPolicy(max_attempts=3, delay=0.01)
    config = NodeConfig(retry=retry_policy)
    
    # Case 1: Success on first retry (fail once)
    node = FailingNode(fail_count=1, config=config)
    result = await node.do(NodeMessage(content="data"))
    assert result.content == "data"
    assert node.attempts == 2

    # Case 2: Exhaust retries (fail 3 times)
    node = FailingNode(fail_count=3, config=config)
    with pytest.raises(NodeExecutionError) as excinfo:
        await node.do(NodeMessage(content="data"))
    assert excinfo.value.kind == "retry_exhausted"
    assert node.attempts == 3

@pytest.mark.asyncio
async def test_timeout_policy():
    # Configure timeout policy: 0.05 seconds
    timeout_policy = TimeoutPolicy(seconds=0.05)
    config = NodeConfig(timeout=timeout_policy)
    
    # Case 1: Operation within timeout
    node = SlowNode(delay=0.01, config=config)
    result = await node.do(NodeMessage(content="data"))
    assert result.content == "data"

    # Case 2: Operation exceeds timeout
    node = SlowNode(delay=0.1, config=config)
    with pytest.raises(NodeTimeoutError):
        await node.do(NodeMessage(content="data"))

@pytest.mark.asyncio
async def test_rate_limiter_policy():
    # Configure rate limit: 10 per second
    rate = Rate(limit=10, burst=1)
    rate_policy = RateLimiterPolicy(resource_key="test_resource", rate=rate)
    config = NodeConfig(rate_limiter=rate_policy)
    
    node = MockNode(config=config)
    
    # Acquire token and run
    result = await node.do(NodeMessage(content="data"))
    assert result.content == "data"
    
    # (More complex rate limit timing tests could be added, but this verifies integration)

@pytest.mark.asyncio
async def test_circuit_breaker_policy():
    # Configure circuit breaker: 2 failures opens circuit
    cb = CircuitBreaker(failure_threshold=2, window=1.0, reset_timeout=0.1)
    cb_policy = CircuitBreakerPolicy(breaker_key="test_breaker", circuit_breaker=cb)
    config = NodeConfig(circuit_breaker=cb_policy)
    
    node = FailingNode(fail_count=10, config=config)
    
    # Failure 1
    with pytest.raises(ValueError):
        await node.do(NodeMessage(content="data"))
        
    # Failure 2 - Should open circuit
    with pytest.raises(ValueError):
        await node.do(NodeMessage(content="data"))
        
    # Next attempt should raise CircuitBreakerOpenError immediately
    with pytest.raises(NodeExecutionError) as excinfo:
        await node.do(NodeMessage(content="data"))
    assert excinfo.value.kind == "circuit_open"
    assert isinstance(excinfo.value.original, CircuitBreakerOpenError)

@pytest.mark.asyncio
async def test_idempotency_policy():
    store = InMemoryIdempotencyStore()
    idempotency_config = IdempotencyConfig(store=store, key_field="id")
    idempotency_policy = IdempotencyPolicy(config=idempotency_config)
    config = NodeConfig(idempotency=idempotency_policy)
    
    node = MockNode(config=config)
    
    # First run: should execute
    inputs = NodeMessage(content={"id": "req1", "value": "foo"})
    result1 = await node.do(inputs)
    assert result1.content == {"id": "req1", "value": "foo"}
    
    # Verify store has record
    record = await store.get("req1")
    assert record is not None
    
    # Second run: should replay
    # We modify the process behavior to fail or return distinct value to prove replay
    node.process = AsyncMock(return_value={"id": "req1", "value": "bar"}) 
    
    result2 = await node.do(inputs)
    # Should return original result, not new mock value
    assert result2.content == {"id": "req1", "value": "foo"}
    # Mock should not have been called
    node.process.assert_not_called()

@pytest.mark.asyncio
async def test_policy_order():
    # Test that Retry wraps Timeout (Timeout is inside retry loop)
    # If Retry was inside Timeout, one timeout would kill all retries.
    # Correct: Retry(Timeout(Node))
    
    retry_policy = RetryPolicy(max_attempts=2, delay=0.01)
    timeout_policy = TimeoutPolicy(seconds=0.05)
    config = NodeConfig(retry=retry_policy, timeout=timeout_policy)
    
    # Node fails with timeout first time, then succeeds
    # We simulate this by having a node that is slow once, then fast.
    class FlakySlowNode(Node):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.attempts = 0
            
        async def process(self, context: ExecutionContext) -> Any:
            self.attempts += 1
            if self.attempts == 1:
                await asyncio.sleep(0.1) # Trigger timeout
            return "success"

    node = FlakySlowNode(config=config)
    
    # 1. Attempt 1: sleeps 0.1s -> TimeoutPolicy raises NodeTimeoutError -> RetryPolicy catches and retries
    # 2. Attempt 2: returns immediately -> Success
    result = await node.do(NodeMessage(content="start"))
    assert result.content == "success"
    assert node.attempts == 2
