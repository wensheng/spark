"""Capability helpers that extend :class:`Node` behaviours."""

import asyncio
from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TYPE_CHECKING

from spark.nodes.types import _safe_copy
from spark.nodes.config import NodeConfig
from spark.nodes.policies import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    IdempotencyRecord,
    IdempotencyConfig,
    NodeTimeoutError,
    Rate,
    RateLimiterRegistry,
    RetryPolicy,
)

if TYPE_CHECKING:  # pragma: no cover - for type checking only
    from spark.nodes.nodes import Node, ExecutionContext


_GLOBAL_RATE_REGISTRY = RateLimiterRegistry()
_GLOBAL_BREAKER_REGISTRY = CircuitBreakerRegistry()


# ---------------------------------------------------------------------------
# Retry & timeout capabilities


@dataclass(slots=True)
class RetryCapability:
    """Capability for handling retry logic with configurable policies."""

    policy: RetryPolicy

    def should_retry(self, error: BaseException, attempt_index: int) -> bool:
        """Check if a retry should be attempted based on error and attempt count."""
        if not self.policy.is_retryable_exception(error):
            return False
        return self.policy.allows_retry(attempt_index)

    def get_delay(self, attempt_index: int) -> float:
        """Get the delay duration for the next retry attempt."""
        return self.policy.get_delay(attempt_index)


@dataclass(slots=True)
class TimeoutCapability:
    """Capability for enforcing execution timeouts on node operations."""

    timeout: float

    async def run(self, node: "Node", coro: Awaitable[Any]) -> Any:
        """Execute a coroutine with timeout enforcement."""
        try:
            return await asyncio.wait_for(coro, timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise NodeTimeoutError(node, "execute", self.timeout) from exc


# ---------------------------------------------------------------------------
# Rate limiting capability


@dataclass(slots=True)
class RateLimitConfig:
    """Configuration for rate limiting a specific resource."""

    resource_key: str
    rate: Rate
    registry: RateLimiterRegistry | None = None


@dataclass(slots=True)
class RateLimitCapability:
    """Capability for enforcing rate limits on resource access."""

    config: RateLimitConfig
    _default_registry: RateLimiterRegistry = field(default=_GLOBAL_RATE_REGISTRY, init=False)

    async def acquire(self) -> Any:
        """Acquire a rate limit token for the configured resource."""
        registry = self.config.registry or self._default_registry
        return await registry.acquire(self.config.resource_key, self.config.rate)

    def release(self, bucket: Any) -> None:
        """Release a rate limit token back to the registry."""
        release = getattr(bucket, "release", None)
        if callable(release):
            release()


# ---------------------------------------------------------------------------
# Circuit breaker capability


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern implementation."""

    key: str
    breaker: CircuitBreaker
    registry: CircuitBreakerRegistry | None = None


@dataclass(slots=True)
class CircuitBreakerCapability:
    """Capability for implementing circuit breaker pattern to prevent cascading failures."""

    config: CircuitBreakerConfig
    _default_registry: CircuitBreakerRegistry = field(default=_GLOBAL_BREAKER_REGISTRY, init=False)

    async def acquire_state(self) -> Any:
        """Acquire circuit breaker state and check if operation is allowed."""
        registry = self.config.registry or self._default_registry
        state = await registry.get(self.config.key, self.config.breaker)
        await state.allow()
        return state

    async def record_success(self, state: Any) -> None:
        """Record a successful operation to the circuit breaker state."""
        await state.record_success()

    async def record_failure(self, state: Any) -> None:
        """Record a failed operation to the circuit breaker state."""
        await state.record_failure()


# ---------------------------------------------------------------------------
# Idempotency capability


@dataclass(slots=True)
class IdempotencyReplay:
    """Result of idempotency check indicating whether operation was reused."""

    reused: bool
    key: Hashable | None
    snapshot: Mapping[str, Any] | None = None
    output: Mapping[str, Any] | None = None
    flag: Any | None = None


@dataclass(slots=True)
class IdempotencyCapability:
    """Capability for ensuring operation idempotency through replay detection."""

    config: IdempotencyConfig
    _pending_key: Hashable | None = None

    def _resolve_key(self, context: "ExecutionContext") -> Hashable | None:
        """Resolve the idempotency key from context using configured resolver or field."""
        resolver = self.config.key_resolver
        if resolver is not None:
            key = resolver(context)
        else:
            key = getattr(context.state, self.config.key_field)
            if key is None and context.inputs is not None and context.inputs.content is not None:
                # Type check: inputs can be a list or a mapping
                if isinstance(context.inputs.content, Mapping):
                    key = context.inputs.content.get(self.config.key_field)
                else:
                    key = None
        if key is None:
            return None
        if not isinstance(key, Hashable):
            raise TypeError("idempotency key must be hashable")
        return key

        # Attempt to adapt legacy records to core snapshot usage.

    async def before_attempt(
        self,
        context: "ExecutionContext",
        attempt_index: int,
    ) -> IdempotencyReplay:
        """Check for existing idempotency record before attempting operation."""
        key = self._resolve_key(context)
        if key is None:
            self._pending_key = None
            return IdempotencyReplay(reused=False, key=None)

        self._pending_key = key
        if attempt_index > 0:
            return IdempotencyReplay(reused=False, key=key)

        record = await self.config.store.get(key)
        if record is None:
            return IdempotencyReplay(reused=False, key=key)

        snapshot = _safe_copy(record.ctx_snapshot)
        output = record.resolve_result if isinstance(record.resolve_result, Mapping) else {}
        flag = record.flag
        return IdempotencyReplay(
            reused=True,
            key=key,
            snapshot=snapshot,
            output=output,
            flag=flag,
        )

    async def after_success(
        self,
        context: "ExecutionContext",
        output: Mapping[str, Any],
        flag: Any | None,
        reused: bool,
    ) -> None:
        """Store idempotency record after successful operation completion."""
        if reused:
            self._pending_key = None
            return
        key = self._pending_key
        if key is None:
            return
        record = IdempotencyRecord(
            process_result=None,
            resolve_result=_safe_copy(output),
            ctx_snapshot=_safe_copy(dict(context.state)),
            flag=flag,
        )
        await self.config.store.set(key, record)
        self._pending_key = None

    def reset(self) -> None:
        """Reset the pending idempotency key state."""
        self._pending_key = None


# ---------------------------------------------------------------------------
# Aggregated capability suite


@dataclass(slots=True)
class AttemptState:
    """State tracking for a single execution attempt across all capabilities."""

    rate_bucket: Any | None = None
    breaker_state: Any | None = None
    idempotency: IdempotencyReplay | None = None


@dataclass(slots=True)
class CapabilitySuite:
    """Aggregated suite of capabilities for comprehensive node behavior control."""

    retry: RetryCapability | None = None
    timeout: TimeoutCapability | None = None
    rate_limit: RateLimitCapability | None = None
    circuit_breaker: CircuitBreakerCapability | None = None
    idempotency: IdempotencyCapability | None = None

    @classmethod
    def from_config(cls, config: NodeConfig) -> "CapabilitySuite":
        """Create a capability suite from a configuration object."""
        # Handle retry: convert int to RetryPolicy if needed
        retry_cap = None
        if config and config.retry:
            if isinstance(config.retry, RetryPolicy):
                retry_cap = RetryCapability(config.retry)
            elif isinstance(config.retry, int):
                # TODO: Convert int to RetryPolicy - need to import/create default policy
                retry_cap = None  # type: ignore[assignment]

        timeout_cap = TimeoutCapability(config.timeout) if config and config.timeout else None

        # Handle rate_limit: convert Rate to RateLimitConfig if needed
        rate_cap = None
        if config and config.rate_limit:
            # config.rate_limit is Rate, but we need RateLimitConfig
            rate_config = RateLimitConfig(
                resource_key=config.resource_key or "default",
                rate=config.rate_limit,
                registry=config.rate_limiter_registry,
            )
            rate_cap = RateLimitCapability(rate_config)

        # Handle circuit_breaker: convert CircuitBreaker to CircuitBreakerConfig if needed
        breaker_cap = None
        if config and config.circuit_breaker:
            breaker_config = CircuitBreakerConfig(
                key=config.breaker_key or "default",
                breaker=config.circuit_breaker,
                registry=config.circuit_breaker_registry,
            )
            breaker_cap = CircuitBreakerCapability(breaker_config)

        idempotency_cap = IdempotencyCapability(config.idempotency) if config and config.idempotency else None
        return cls(
            retry=retry_cap,
            timeout=timeout_cap,
            rate_limit=rate_cap,
            circuit_breaker=breaker_cap,
            idempotency=idempotency_cap,
        )

    async def before_attempt(
        self,
        context: "ExecutionContext",
        attempt_index: int,
    ) -> AttemptState:
        """Prepare all capabilities before attempting an operation."""
        state = AttemptState()
        if self.rate_limit is not None:
            state.rate_bucket = await self.rate_limit.acquire()
        if self.circuit_breaker is not None:
            state.breaker_state = await self.circuit_breaker.acquire_state()
        if self.idempotency is not None:
            state.idempotency = await self.idempotency.before_attempt(context, attempt_index)
        return state

    async def after_success(
        self,
        context: "ExecutionContext",
        output: Mapping[str, Any],
        flag: Any | None,
        attempt_state: AttemptState,
        reused: bool,
    ) -> None:
        """Handle successful operation completion across all capabilities."""
        if attempt_state.rate_bucket is not None and self.rate_limit is not None:
            self.rate_limit.release(attempt_state.rate_bucket)
        if attempt_state.breaker_state is not None and self.circuit_breaker is not None:
            await self.circuit_breaker.record_success(attempt_state.breaker_state)
        if self.idempotency is not None:
            await self.idempotency.after_success(context, output, flag, reused)

    async def after_failure(
        self,
        attempt_state: AttemptState,
    ) -> None:
        """Handle failed operation across all capabilities."""
        if attempt_state.rate_bucket is not None and self.rate_limit is not None:
            self.rate_limit.release(attempt_state.rate_bucket)
        if attempt_state.breaker_state is not None and self.circuit_breaker is not None:
            await self.circuit_breaker.record_failure(attempt_state.breaker_state)
        if self.idempotency is not None:
            self.idempotency.reset()

    def should_retry(self, error: BaseException, attempt_index: int) -> bool:
        """Check if operation should be retried based on error and attempt count."""
        if self.retry is None:
            return False
        return self.retry.should_retry(error, attempt_index)

    def retry_delay(self, attempt_index: int) -> float:
        """Get the delay duration for the next retry attempt."""
        if self.retry is None:
            return 0.0
        return self.retry.get_delay(attempt_index)

    async def execute(
        self,
        node: "Node",
        func: Callable[["ExecutionContext"], Awaitable[Any]],
        context: "ExecutionContext",
    ) -> Any:
        """Execute a function with timeout enforcement if configured."""
        coro = func(context)
        if self.timeout is None:
            return await coro
        return await self.timeout.run(node, coro)
