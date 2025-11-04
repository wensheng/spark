"""
Exceptions for the Spark framework.
"""

from typing import Any
import copy

from spark.nodes.base import SparkError
from spark.nodes.types import ExecutionContext


class NodeTimeoutError(SparkError):
    """Raised when a node stage exceeds its configured timeout."""

    def __init__(self, node: Any, stage: str, timeout: float | None) -> None:
        """Initialize the NodeTimeoutError."""
        self.node = node
        self.stage = stage
        self.timeout = timeout
        timeout_msg = f" after {timeout} seconds" if timeout is not None else ''
        super().__init__(f"Node {node.__class__.__name__} {stage} stage timed out{timeout_msg}.")


class NodeExecutionError(SparkError):
    """Structured error wrapper for node execution."""

    def __init__(
        self, *, kind: str, node: Any, stage: str, original: BaseException, ctx_snapshot: ExecutionContext | None = None
    ):
        """Initialize the NodeExecutionError."""
        self.kind = kind
        self.node_name = getattr(node, 'name', node.__class__.__name__)
        self.stage = stage
        self.original = original
        self.ctx_snapshot: ExecutionContext | None = None
        if ctx_snapshot:
            self.ctx_snapshot = copy.deepcopy(ctx_snapshot)
        super().__init__(f"[{self.kind}] node={self.node_name} stage={self.stage}: {original}")

    def __repr__(self) -> str:
        """Return a string representation of the error."""
        return (
            f"NodeExecutionError(kind={self.kind!r}, node_name={self.node_name!r}, "
            f"stage={self.stage!r}, original={self.original!r})"
        )


class ContextValidationError(SparkError):
    """Raised when node context fails contract or custom validation."""

    def __init__(self, node: Any, message: str, *, errors: Any | None = None):
        """Initialize the ContextValidationError."""
        self.node = node
        self.node_name = getattr(node, 'name', node.__class__.__name__)
        self.errors = errors
        super().__init__(f"{self.node_name}: {message}")


class CircuitBreakerOpenError(SparkError):
    """Raised when circuit breaker is open and execution is short-circuited."""

    def __init__(self, *, key: str, retry_after: float | None = None) -> None:
        """Initialize the CircuitBreakerOpenError."""
        self.key = key
        self.retry_after = retry_after
        message = f'circuit breaker {key!r} is open'
        if retry_after is not None:
            message += f'; retry after {retry_after:.2f}s'
        super().__init__(message)
