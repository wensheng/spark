"""
Configuration for a Node instance, capturing timeouts, retry policy,
redaction, sink, and rate/circuit breaker options.
"""

from typing import Mapping, Set, Any, Callable, TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from spark.nodes.types import ExecutionContext, NodeState, default_node_state

if TYPE_CHECKING:
    from spark.nodes.human import HumanInLoopPolicy
else:  # pragma: no cover - runtime fallback for pydantic validation
    HumanInLoopPolicy = object  # type: ignore[assignment]

from spark.nodes.types import EventSink
from spark.nodes.policies import (
    RetryPolicy,
    Rate,
    RateLimiterRegistry,
    CircuitBreaker,
    CircuitBreakerRegistry,
    IdempotencyConfig,
)


class NodeConfig(BaseModel):
    """
    Configuration for a Node instance, capturing timeouts, retry policy,
    redaction, sink, and rate/circuit breaker options.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: str | None = None
    description: str | None = None

    live: bool = False
    """Whether the node is live, live nodes run continuously until stopped"""

    initial_state: NodeState = Field(default_factory=default_node_state)
    timeout: float | None = None
    retry: RetryPolicy | int | None = None
    redact_keys: Set[str] | None = None
    event_sink: EventSink | None = None
    # ctx_mode: str = "shared"
    resource_key: str | None = None
    rate_limit: Rate | None = None
    rate_limiter_registry: RateLimiterRegistry | None = None
    breaker_key: str | None = None
    circuit_breaker: CircuitBreaker | None = None
    circuit_breaker_registry: CircuitBreakerRegistry | None = None
    validators: tuple[Callable[[Mapping[str, Any]], None | str], ...] = ()
    idempotency: IdempotencyConfig | None = None
    human_policy: HumanInLoopPolicy | None = None

    pre_process_hooks: list[Callable[[ExecutionContext], None]] = Field(default_factory=list)
    """Pre-process hook to be called before the process method."""

    post_process_hooks: list[Callable[[ExecutionContext], None]] = Field(default_factory=list)
    """Post-process hook to be called after the process method."""

    keep_in_state: list[str] = Field(default_factory=list)
    """List of input keys to keep in the state."""
