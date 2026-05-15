"""Tests for core exceptions."""

from spark.core.exceptions import (
    ActorAlreadyExists,
    ActorAlreadyStartedError,
    ActorNotFound,
    ActorNotStartedError,
    SyndicateError,
    ActorTimeout,
    InvalidActorSpecError,
    InvalidEnvelopeError,
    MessageDeliveryError,
    ServiceNotFoundError,
    SparkException,
    UnsupportedBackendError,
)


class TestSparkException:
    def test_spark_exception_creation(self) -> None:
        exc = SparkException("Test message")
        assert str(exc) == "Test message"
        assert isinstance(exc, Exception)


class TestActorNotFound:
    def test_actor_not_found_with_message(self) -> None:
        actor_id = "test-actor-123"
        exc = ActorNotFound(actor_id, "Custom not found message")
        assert exc.actor_id == actor_id
        assert str(exc) == "Custom not found message"

    def test_actor_not_found_default_message(self) -> None:
        actor_id = "test-actor-123"
        exc = ActorNotFound(actor_id)
        assert exc.actor_id == actor_id
        assert f"Actor {actor_id} not found" in str(exc)


class TestActorAlreadyExists:
    def test_actor_already_exists_with_message(self) -> None:
        actor_id = "test-actor-123"
        exc = ActorAlreadyExists(actor_id, "Custom exists message")
        assert exc.actor_id == actor_id
        assert str(exc) == "Custom exists message"

    def test_actor_already_exists_default_message(self) -> None:
        actor_id = "test-actor-123"
        exc = ActorAlreadyExists(actor_id)
        assert exc.actor_id == actor_id
        assert f"Actor {actor_id} already exists" in str(exc)


class TestActorContextErrors:
    def test_actor_not_started_error(self) -> None:
        exc = ActorNotStartedError("ExampleActor")
        assert exc.actor == "ExampleActor"
        assert "not started" in str(exc)

    def test_actor_already_started_error(self) -> None:
        exc = ActorAlreadyStartedError("actor-1")
        assert exc.actor_id == "actor-1"
        assert "already started" in str(exc)


class TestActorTimeout:
    def test_actor_timeout_with_message(self) -> None:
        exc = ActorTimeout("operation", 5.0, "Custom timeout message")
        assert exc.operation == "operation"
        assert exc.timeout == 5.0
        assert str(exc) == "Custom timeout message"

    def test_actor_timeout_default_message(self) -> None:
        exc = ActorTimeout("ask", 10.0)
        assert exc.operation == "ask"
        assert exc.timeout == 10.0
        assert "ask timed out after 10.0 seconds" in str(exc)


class TestMessageDeliveryError:
    def test_message_delivery_error_with_message(self) -> None:
        target = "test-target"
        reason = "destination unreachable"
        exc = MessageDeliveryError(target, reason, "Custom delivery error")
        assert exc.target == target
        assert exc.reason == reason
        assert str(exc) == "Custom delivery error"

    def test_message_delivery_error_default_message(self) -> None:
        target = "test-target"
        reason = "destination unreachable"
        exc = MessageDeliveryError(target, reason)
        assert exc.target == target
        assert exc.reason == reason
        assert f"Failed to deliver message to {target}: {reason}" in str(exc)


class TestMarkerExceptions:
    def test_marker_exceptions_inherit_from_spark_exception(self) -> None:
        exceptions = [
            SyndicateError("system"),
            UnsupportedBackendError("backend"),
            InvalidActorSpecError("spec"),
            InvalidEnvelopeError("envelope"),
        ]

        assert all(isinstance(exc, SparkException) for exc in exceptions)


class TestServiceNotFoundError:
    def test_service_not_found_without_available(self) -> None:
        exc = ServiceNotFoundError("missing_service")
        assert exc.service_name == "missing_service"
        assert exc.available_services == {}
        assert "Service 'missing_service' not found" in str(exc)

    def test_service_not_found_with_available(self) -> None:
        available = {
            "logging": "LoggingService",
            "metrics": "MetricsService",
            "tracing": "TracingService",
        }
        exc = ServiceNotFoundError("missing_service", available)

        assert exc.service_name == "missing_service"
        assert exc.available_services == available
        assert "Available services:" in str(exc)
        assert "logging" in str(exc)
        assert "metrics" in str(exc)
        assert "tracing" in str(exc)
