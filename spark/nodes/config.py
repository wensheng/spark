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
    TimeoutPolicy,
    RateLimiterPolicy,
    CircuitBreakerPolicy,
    IdempotencyPolicy,
    # Keep these if they are used as config objects within the Policy classes
    # or if there's a reason NodeConfig needs to expose them directly for other purposes
    # For now, remove them as they are encapsulated by the Policy objects
    Rate,
    CircuitBreaker,
    IdempotencyConfig,
)


class NodeConfig(BaseModel):
    """
    Configuration for a Node instance, capturing policies for retry, timeout,
    rate limiting, circuit breaking, and idempotency, along with other settings.
    """

    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: str | None = None
    description: str | None = None

    live: bool = False
    """Whether the node is live; live nodes run continuously until stopped"""

    initial_state: NodeState = Field(default_factory=default_node_state)
    
    # Policies for resilience and control
    retry: RetryPolicy | None = None # Keep as is
    timeout: TimeoutPolicy | None = None # Changed from float to TimeoutPolicy
    rate_limiter: RateLimiterPolicy | None = None # New field, replaces rate_limit, resource_key, registry
    circuit_breaker: CircuitBreakerPolicy | None = None # New field, replaces breaker_key, circuit_breaker, registry
    idempotency: IdempotencyPolicy | None = None # Changed from IdempotencyConfig to IdempotencyPolicy

    redact_keys: Set[str] | None = None
    event_sink: EventSink | None = None
    
    validators: tuple[Callable[[Mapping[str, Any]], None | str], ...] = ()
    human_policy: HumanInLoopPolicy | None = None

    pre_process_hooks: list[Callable[[ExecutionContext], None]] = Field(default_factory=list)
    """Pre-process hook to be called before the process method."""

    post_process_hooks: list[Callable[[ExecutionContext], None]] = Field(default_factory=list)
    """Post-process hook to be called after the process method."""

    keep_in_state: list[str] = Field(default_factory=list)
    """List of input keys to keep in the state."""