"""
Policies for the Spark framework.
"""

import asyncio
import time
from collections import deque
from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol, runtime_checkable

from spark.nodes.types import ExecutionContext, NodeMessage, _safe_copy
from spark.nodes.base import BaseNode
from spark.nodes.exceptions import (
    CircuitBreakerOpenError,
    NodeExecutionError,
    NodeTimeoutError,
)


ProcessFn = Callable[[ExecutionContext], Awaitable[Any]]
ProcessWrapper = Callable[[ExecutionContext, ProcessFn], Awaitable[Any]]


@runtime_checkable
class SupportsProcessWrapper(Protocol):
    """Protocol for policies that expose a wrapper builder instead of mutating nodes."""

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:  # pragma: no cover - interface
        """Return a coroutine wrapper that applies this policy around a process function."""


def compose_process_wrappers(base_process: ProcessFn, wrappers: list[ProcessWrapper]) -> ProcessFn:
    """Compose a sequence of process wrappers around the provided base process."""
    wrapped = base_process
    for wrapper in wrappers:
        previous = wrapped

        async def wrapped_process(
            context: ExecutionContext,
            *,
            _wrapper=wrapper,
            _previous=previous,
        ) -> Any:
            return await _wrapper(context, _previous)

        wrapped = wrapped_process
    return wrapped


@dataclass(frozen=True, slots=True)
class Rate:
    """Simple rate limiter configuration."""

    limit: float
    burst: int = 1

    def __post_init__(self) -> None:
        """Validate rate limiter configuration parameters."""
        if not isinstance(self.limit, (int, float)) or self.limit <= 0:
            raise ValueError("limit must be a positive number")
        if not isinstance(self.burst, int) or self.burst < 1:
            raise ValueError("burst must be a positive integer")


class _TokenBucket:
    """Asynchronous token bucket implementing a basic rate limiter."""

    def __init__(self, rate: Rate) -> None:
        """Initialize token bucket with the given rate configuration."""
        self.rate = rate
        self._capacity = float(rate.burst)
        self._tokens = float(rate.burst)
        self._last_refill = time.perf_counter()
        self._lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        """Refill tokens based on elapsed time since last refill."""
        if now <= self._last_refill:
            return
        delta = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + delta * self.rate.limit)
        self._last_refill = now

    async def acquire(self) -> None:
        """Acquire a token, blocking until one is available."""
        while True:
            async with self._lock:
                now = time.perf_counter()
                self._refill(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                needed = 1.0 - self._tokens
                wait_time = needed / self.rate.limit if self.rate.limit > 0 else 0.0
            await asyncio.sleep(wait_time if wait_time > 0 else 0)

    def release(self) -> None:
        """Release a token (no-op for token bucket implementation)."""
        # Token buckets rely on time-based refill; release is a no-op placeholder.
        return None


class RateLimiterRegistry:
    """Registry that manages token buckets per resource key."""

    def __init__(self) -> None:
        """Initialize the rate limiter registry."""
        self._buckets: dict[str, _TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def _get_bucket(self, resource_key: str, rate: Rate) -> _TokenBucket:
        """Get or create a token bucket for the given resource key and rate."""
        async with self._lock:
            bucket = self._buckets.get(resource_key)
            if bucket is None or bucket.rate != rate:
                bucket = _TokenBucket(rate)
                self._buckets[resource_key] = bucket
            return bucket

    async def acquire(self, resource_key: str, rate: Rate) -> _TokenBucket:
        """Acquire a token from the bucket for the given resource key and rate."""
        bucket = await self._get_bucket(resource_key, rate)
        await bucket.acquire()
        return bucket


_DEFAULT_RATE_REGISTRY: RateLimiterRegistry = RateLimiterRegistry()


@dataclass(frozen=True, slots=True)
class CircuitBreaker:
    """Configuration for circuit breaker behaviour."""

    failure_threshold: int = 5
    window: float = 30.0
    reset_timeout: float = 15.0

    def __post_init__(self) -> None:
        """Validate circuit breaker configuration parameters."""
        if not isinstance(self.failure_threshold, int) or self.failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        if not isinstance(self.window, (int, float)) or self.window <= 0:
            raise ValueError("window must be a positive number of seconds")
        if not isinstance(self.reset_timeout, (int, float)) or self.reset_timeout <= 0:
            raise ValueError("reset_timeout must be a positive number of seconds")


class _CircuitBreakerState:
    """Runtime state for a circuit breaker."""

    def __init__(self, key: str, config: CircuitBreaker) -> None:
        """Initialize circuit breaker state with the given key and configuration."""
        self.key = key
        self.config = config
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._failures: deque[float] = deque()
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        """Remove old failure records outside the time window."""
        window_start = now - self.config.window
        while self._failures and self._failures[0] < window_start:
            self._failures.popleft()

    async def allow(self) -> None:
        """Check if the circuit breaker allows execution or raises an error."""
        async with self._lock:
            now = time.perf_counter()
            if self._state == "open":
                assert self._opened_at is not None
                elapsed = now - self._opened_at
                if elapsed >= self.config.reset_timeout:
                    self._state = "half_open"
                else:
                    raise CircuitBreakerOpenError(
                        key=self.key,
                        retry_after=max(self.config.reset_timeout - elapsed, 0.0),
                    )

            # closed or half-open fall through
            self._prune(now)

    async def record_success(self) -> None:
        """Record a successful execution and reset the circuit breaker to closed state."""
        async with self._lock:
            self._failures.clear()
            self._state = "closed"
            self._opened_at = None

    async def record_failure(self) -> None:
        """Record a failed execution and potentially open the circuit breaker."""
        async with self._lock:
            now = time.perf_counter()
            self._prune(now)
            self._failures.append(now)
            if self._state == "half_open":
                self._open(now)
                return
            if len(self._failures) >= self.config.failure_threshold:
                self._open(now)

    def _open(self, now: float) -> None:
        """Open the circuit breaker and record the opening time."""
        self._state = "open"
        self._opened_at = now


class CircuitBreakerRegistry:
    """Registry managing shared circuit breaker state per resource key."""

    def __init__(self) -> None:
        """Initialize the circuit breaker registry."""
        self._breakers: dict[str, _CircuitBreakerState] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, config: CircuitBreaker) -> _CircuitBreakerState:
        """Get or create a circuit breaker state for the given key and configuration."""
        async with self._lock:
            state = self._breakers.get(key)
            if state is None or state.config != config:
                state = _CircuitBreakerState(key, config)
                self._breakers[key] = state
            return state


_DEFAULT_BREAKER_REGISTRY: CircuitBreakerRegistry = CircuitBreakerRegistry()


@dataclass(slots=True)
class RetryPolicy:
    """Configuration for retrying node processing."""

    max_attempts: int = 4
    delay: float = 1.0
    backoff_multiplier: float = 1.0
    max_delay: float | None = None
    retry_on: tuple[type[BaseException], ...] = (Exception,)
    retry_filter: Callable[[BaseException], bool] | None = None
    jitter: Callable[[float], float] | None = None

    def __post_init__(self) -> None:
        """Validate retry policy configuration parameters."""
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if not isinstance(self.delay, (int, float)) or self.delay < 0:
            raise ValueError("delay must be a non-negative number")
        if not isinstance(self.backoff_multiplier, (int, float)) or self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be >= 1.0")
        if self.max_delay is not None and (not isinstance(self.max_delay, (int, float)) or self.max_delay <= 0):
            raise ValueError("max_delay must be a positive number when provided")
        if not isinstance(self.retry_on, tuple):
            self.retry_on = tuple(self.retry_on)  # type: ignore[assignment]
        if not all(isinstance(exc, type) and issubclass(exc, BaseException) for exc in self.retry_on):
            raise TypeError("retry_on must be tuple of exception types")

    def allows_retry(self, attempt_number: int) -> bool:
        """Return True if another attempt is allowed after *attempt_number* failures."""
        return attempt_number + 1 < self.max_attempts

    def is_retryable_exception(self, error: BaseException) -> bool:
        """Return True if *error* is eligible for retry based on type and filter."""
        if not isinstance(error, self.retry_on):
            return False
        if self.retry_filter is not None and not self.retry_filter(error):
            return False
        return True

    def get_delay(self, attempt_number: int) -> float:
        """Compute delay (in seconds) before the next retry."""
        if self.delay <= 0:
            return 0.0
        delay = float(self.delay) * (float(self.backoff_multiplier) ** attempt_number)
        if self.max_delay is not None:
            delay = min(delay, float(self.max_delay))
        if self.jitter is not None:
            delay = float(self.jitter(delay))
        return max(delay, 0.0)

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Return a coroutine wrapper that retries failed process calls."""

        async def wrapper(context: ExecutionContext, call_next: ProcessFn) -> Any:
            attempt_number = 0
            while True:
                try:
                    return await call_next(context)
                except Exception as exc:
                    if not self.is_retryable_exception(exc):
                        raise
                    if not self.allows_retry(attempt_number):
                        raise NodeExecutionError(
                            kind="retry_exhausted",
                            node=node,
                            stage="_process",
                            original=exc,
                            ctx_snapshot=context.snapshot(),
                        ) from exc

                    delay = self.get_delay(attempt_number)
                    attempt_number += 1
                    if delay > 0:
                        await asyncio.sleep(delay)

        return wrapper

    def __call__(self, node: BaseNode) -> BaseNode:
        """Configuration objects should not be invoked directly."""
        raise TypeError("RetryPolicy no longer mutates nodes directly; assign it via NodeConfig(retry=...) instead.")


@dataclass(slots=True)
class TimeoutPolicy:
    """Configuration for timeout policy."""

    seconds: float

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Return a coroutine wrapper that enforces the timeout without mutating the node."""

        async def wrapper(context: ExecutionContext, call_next: ProcessFn) -> Any:
            try:
                return await asyncio.wait_for(call_next(context), self.seconds)
            except asyncio.TimeoutError as exc:
                raise NodeTimeoutError(
                    node=node,
                    stage="_process",
                    timeout=self.seconds,
                ) from exc

        return wrapper

    def __call__(self, node: BaseNode) -> BaseNode:
        """Configuration objects should not be invoked directly."""
        raise TypeError(
            "TimeoutPolicy no longer mutates nodes directly; assign it via NodeConfig(timeout=...) instead."
        )


@dataclass(slots=True)
class RateLimiterPolicy:
    """Configuration for rate limiting policy."""

    resource_key: str
    rate: Rate
    registry: RateLimiterRegistry = field(default_factory=lambda: _DEFAULT_RATE_REGISTRY)

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Return a coroutine wrapper that enforces rate limits."""

        async def wrapper(context: ExecutionContext, call_next: ProcessFn) -> Any:
            bucket = await self.registry.acquire(self.resource_key, self.rate)
            try:
                return await call_next(context)
            finally:
                bucket.release()

        return wrapper

    def __call__(self, node: BaseNode) -> BaseNode:
        """Configuration objects should not be invoked directly."""
        raise TypeError(
            "RateLimiterPolicy no longer mutates nodes directly; assign it via NodeConfig(rate_limiter=...) instead."
        )


@dataclass(slots=True)
class CircuitBreakerPolicy:
    """Configuration for circuit breaker policy."""

    breaker_key: str
    circuit_breaker: CircuitBreaker
    registry: CircuitBreakerRegistry = field(default_factory=lambda: _DEFAULT_BREAKER_REGISTRY)

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Return a coroutine wrapper that enforces the circuit breaker."""

        async def wrapper(context: ExecutionContext, call_next: ProcessFn) -> Any:
            state = await self.registry.get(self.breaker_key, self.circuit_breaker)
            try:
                await state.allow()
            except CircuitBreakerOpenError as exc:
                raise NodeExecutionError(
                    kind="circuit_open",
                    node=node,
                    stage="_process",
                    original=exc,
                    ctx_snapshot=context.snapshot(),
                ) from exc

            try:
                result = await call_next(context)
                await state.record_success()
                return result
            except Exception:  # Capture all exceptions to record failure
                await state.record_failure()
                raise

        return wrapper

    def __call__(self, node: BaseNode) -> BaseNode:
        """Configuration objects should not be invoked directly."""
        raise TypeError(
            "CircuitBreakerPolicy no longer mutates nodes directly; assign it via NodeConfig(circuit_breaker=...) instead."
        )


@dataclass(slots=True)
class IdempotencyRecord:
    """Snapshot of a successful node execution for idempotency replay."""

    process_result: Any
    resolve_result: Any
    ctx_snapshot: dict[str, Any]
    flag: str | None = None
    stored_at: float = field(default_factory=time.time)

    def clone(self) -> "IdempotencyRecord":
        """Create a deep copy of this idempotency record."""
        return IdempotencyRecord(
            process_result=_safe_copy(self.process_result),
            resolve_result=_safe_copy(self.resolve_result),
            ctx_snapshot=_safe_copy(self.ctx_snapshot),
            flag=self.flag,
            stored_at=self.stored_at,
        )


@runtime_checkable
class IdempotencyStore(Protocol):
    """Protocol for persisting idempotency records."""

    async def get(self, key: Hashable) -> IdempotencyRecord | None:  # pragma: no cover - interface
        """Retrieve an idempotency record by key."""

    async def set(self, key: Hashable, record: IdempotencyRecord) -> None:  # pragma: no cover - interface
        """Store an idempotency record by key."""

    async def delete(self, key: Hashable) -> None:  # pragma: no cover - interface
        """Delete an idempotency record by key."""


class InMemoryIdempotencyStore:
    """Simple in-memory idempotency backend safe for async use."""

    def __init__(self) -> None:
        """Initialize the in-memory idempotency store."""
        self._records: dict[Hashable, IdempotencyRecord] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: Hashable) -> IdempotencyRecord | None:
        """Retrieve an idempotency record by key, returning a clone if found."""
        async with self._lock:
            record = self._records.get(key)
        if record is None:
            return None
        return record.clone()

    async def set(self, key: Hashable, record: IdempotencyRecord) -> None:
        """Store an idempotency record by key, creating a clone for storage."""
        async with self._lock:
            self._records[key] = record.clone()

    async def delete(self, key: Hashable) -> None:
        """Remove an idempotency record by key if it exists."""
        async with self._lock:
            self._records.pop(key, None)

    def __len__(self) -> int:  # pragma: no cover - convenience
        """Return the number of stored idempotency records."""
        return len(self._records)


@dataclass(slots=True)
class IdempotencyConfig:
    """Configuration for idempotency handling to prevent duplicate operations."""

    store: IdempotencyStore = field(default_factory=InMemoryIdempotencyStore)
    key_field: str = "idempotency_key"
    key_resolver: Callable[[ExecutionContext], Hashable | None] | None = None


@dataclass(slots=True)
class IdempotencyPolicy:
    """Policy for ensuring operation idempotency through replay detection."""

    config: IdempotencyConfig

    def build_wrapper(self, node: BaseNode) -> ProcessWrapper:
        """Return a coroutine wrapper that enforces idempotency without mutating the node."""

        async def wrapper(context: ExecutionContext, call_next: ProcessFn) -> Any:
            key = self._resolve_key(context)

            if key is None:
                return await call_next(context)

            record = await self.config.store.get(key)
            if record is not None:
                return record.resolve_result

            result = await call_next(context)
            record = IdempotencyRecord(
                process_result=_safe_copy(result),
                resolve_result=_safe_copy(result),
                ctx_snapshot=_safe_copy(context.snapshot()),
            )
            await self.config.store.set(key, record)
            return result

        return wrapper

    def __call__(self, node: BaseNode) -> BaseNode:
        """Configuration objects should not be invoked directly."""
        raise TypeError(
            "IdempotencyPolicy no longer mutates nodes directly; assign it via NodeConfig(idempotency=...) instead."
        )

    def _resolve_key(self, context: ExecutionContext) -> Hashable | None:
        """Resolve the idempotency key from context using configured resolver or field."""
        resolver = self.config.key_resolver
        if resolver is not None:
            key = resolver(context)
        else:
            key = getattr(context.state, self.config.key_field, None)
            if key is None and context.inputs is not None and context.inputs.content is not None:
                if isinstance(context.inputs.content, Mapping):
                    key = context.inputs.content.get(self.config.key_field)
        if key is None:
            return None
        if not isinstance(key, Hashable):
            raise TypeError("idempotency key must be hashable")
        return key
