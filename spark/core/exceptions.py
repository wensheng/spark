"""Core exceptions for Spark actor framework."""

from typing import Any


class SparkException(Exception):
    """Base exception for all Spark framework errors."""


class NoActiveNodeContext(SparkException):
    """Raised when a node has no active per-run context."""


class ActorNotFound(SparkException):
    """Raised when an actor cannot be found."""

    def __init__(self, actor_id: Any, message: str | None = None) -> None:
        self.actor_id = actor_id
        super().__init__(message or f"Actor {actor_id} not found")


class ActorAlreadyExists(SparkException):
    """Raised when trying to create an actor that already exists."""

    def __init__(self, actor_id: Any, message: str | None = None) -> None:
        self.actor_id = actor_id
        super().__init__(message or f"Actor {actor_id} already exists")


class ActorTimeout(SparkException):
    """Raised when an actor operation times out."""

    def __init__(self, operation: str, timeout: float, message: str | None = None) -> None:
        self.operation = operation
        self.timeout = timeout
        super().__init__(message or f"{operation} timed out after {timeout} seconds")


class MessageDeliveryError(SparkException):
    """Raised when a message cannot be delivered."""

    def __init__(self, target: Any, reason: str, message: str | None = None) -> None:
        self.target = target
        self.reason = reason
        super().__init__(message or f"Failed to deliver message to {target}: {reason}")


class ActorNotStartedError(SparkException):
    """Raised when actor runtime helpers are used before context binding."""

    def __init__(self, actor: Any, message: str | None = None) -> None:
        self.actor = actor
        super().__init__(message or f"Actor {actor} is not started")


class ActorAlreadyStartedError(SparkException):
    """Raised when an actor is bound to runtime context more than once."""

    def __init__(self, actor_id: Any, message: str | None = None) -> None:
        self.actor_id = actor_id
        super().__init__(message or f"Actor {actor_id} is already started")


class SyndicateError(SparkException):
    """Raised for actor system-level errors."""

    ...


class ActorSystemStartupError(SyndicateError):
    """Raised when the actor system fails to start."""

    ...


class ActorSystemShutdownError(SyndicateError):
    """Raised when the actor system fails to shut down."""

    ...


class UnsupportedBackendError(SparkException):
    """Raised when requesting an unsupported backend type."""

    ...


class InvalidActorSpecError(SparkException):
    """Raised when an invalid actor specification is provided."""

    ...


class InvalidEnvelopeError(SparkException):
    """Raised when an invalid envelope is encountered."""

    ...


class ServiceNotFoundError(SparkException):
    """Raised when a requested service is not available."""

    def __init__(self, service_name: str, available_services: dict[str, Any] | None = None) -> None:
        self.service_name = service_name
        self.available_services = available_services or {}
        super().__init__(
            f"Service '{service_name}' not found. Available services: {list(self.available_services.keys())}"
        )
