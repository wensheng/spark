"""Tests for core control messages."""

import pytest

from spark.core.actor_spec import ActorSpec
from spark.core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from spark.core.messages import (
    ActorCreateRequest,
    ActorCreateResponse,
    ActorExited,
    ActorExitRequest,
    ActorStatus,
    SyndicateMessage,
    ChildActorExited,
    CommonStatusFields,
    FederationAttendee,
    DeadLetter,
    LoadedSourceInfo,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
    SystemShutdown,
    WakeupMessage,
    WakeupRequest,
    WatchMessage,
)


class TestSystemShutdown:
    def test_system_shutdown_creation(self) -> None:
        sender = ActorId(SyndicateId())
        msg = SystemShutdown(sender=sender)
        assert msg.sender == sender

    def test_system_shutdown_no_sender(self) -> None:
        msg = SystemShutdown()
        assert msg.sender is None


class TestActorExitRequest:
    def test_actor_exit_request_creation(self) -> None:
        msg = ActorExitRequest(reason="test reason")
        assert msg.reason == "test reason"

    def test_actor_exit_request_default_reason(self) -> None:
        msg = ActorExitRequest()
        assert msg.reason == "actor requested to exit"


class TestActorExited:
    def test_actor_exited_creation(self) -> None:
        actor_id = ActorId(SyndicateId())
        incarnation = ActorIncarnation(actor_id=actor_id, generation=2)
        msg = ActorExited(
            actor_id=actor_id,
            incarnation=incarnation,
            exit_code=1,
            reason="test exit",
        )

        assert msg.actor_id == actor_id
        assert msg.incarnation == incarnation
        assert msg.exit_code == 1
        assert msg.reason == "test exit"

    def test_actor_exited_defaults(self) -> None:
        actor_id = ActorId(SyndicateId())
        msg = ActorExited(actor_id=actor_id)

        assert msg.actor_id == actor_id
        assert msg.incarnation is None
        assert msg.exit_code == 0
        assert msg.reason == "actor exited"


class TestChildActorExited:
    def test_child_actor_exited_creation(self) -> None:
        child_id = ActorId(SyndicateId())
        parent_id = ActorId(SyndicateId())
        child_incarnation = ActorIncarnation(actor_id=child_id)
        msg = ChildActorExited(
            child_id=child_id,
            parent_id=parent_id,
            child_incarnation=child_incarnation,
            exit_code=2,
            reason="child test exit",
        )

        assert msg.child_id == child_id
        assert msg.parent_id == parent_id
        assert msg.child_incarnation == child_incarnation
        assert msg.exit_code == 2
        assert msg.reason == "child test exit"

    def test_child_actor_exited_defaults(self) -> None:
        child_id = ActorId(SyndicateId())
        parent_id = ActorId(SyndicateId())
        msg = ChildActorExited(child_id=child_id, parent_id=parent_id)

        assert msg.child_id == child_id
        assert msg.parent_id == parent_id
        assert msg.child_incarnation is None
        assert msg.exit_code == 0
        assert msg.reason == "child actor exited"


class TestActorCreateMessages:
    def test_actor_create_request_creation(self) -> None:
        class TestActor:
            pass

        spec = ActorSpec(actor_class=TestActor, args=("name",), kwargs={"debug": True})
        parent_id = ActorId(SyndicateId())

        msg = ActorCreateRequest(
            actor_spec=spec,
            parent_id=parent_id,
            request_id="request-1",
        )

        assert msg.actor_spec == spec
        assert msg.parent_id == parent_id
        assert msg.request_id == "request-1"

    def test_actor_create_response_success(self) -> None:
        actor_id = ActorId(SyndicateId())
        msg = ActorCreateResponse(actor_id=actor_id, success=True, request_id="req")

        assert msg.actor_id == actor_id
        assert msg.success is True
        assert msg.error is None
        assert msg.request_id == "req"

    def test_actor_create_response_with_error(self) -> None:
        msg = ActorCreateResponse(success=False, error="Failed to create actor")

        assert msg.actor_id is None
        assert msg.success is False
        assert msg.error == "Failed to create actor"


class TestWakeupRequest:
    def test_wakeup_request_creation(self) -> None:
        actor_id = ActorId(SyndicateId())
        payload = {"data": "test"}

        msg = WakeupRequest(actor_id=actor_id, payload=payload)

        assert msg.actor_id == actor_id
        assert msg.payload == payload

    def test_wakeup_request_no_payload(self) -> None:
        actor_id = ActorId(SyndicateId())
        msg = WakeupRequest(actor_id=actor_id)
        assert msg.payload is None

    def test_wakeup_message_creation(self) -> None:
        msg = WakeupMessage(delay=1.5, payload="ready")
        assert msg.delay == 1.5
        assert msg.payload == "ready"


class TestStatusMessages:
    def test_status_request_creation(self) -> None:
        sender_id = ActorId(SyndicateId())
        msg = StatusRequest(sender_id=sender_id)
        assert msg.sender_id == sender_id

    def test_system_status_creation(self) -> None:
        syndicate_id = SyndicateId()
        msg = SystemStatus(
            syndicate_id=syndicate_id,
            admin_address="spark://admin",
            actor_count=10,
            uptime_seconds=120.5,
            backend_type="inprocess",
            capabilities={"max_actors": 100},
            in_shutdown=False,
        )
        assert msg.actor_count == 10
        assert msg.uptime_seconds == 120.5
        assert msg.backend_type == "inprocess"
        assert msg.syndicate_id == syndicate_id
        assert msg.capabilities == {"max_actors": 100}
        assert not msg.in_shutdown
        assert msg.common.messages_sent == 0

    def test_actor_status_creation(self) -> None:
        msg = ActorStatus(
            actor_address="spark://actor1",
            actor_class="MyActor",
            admin_address="spark://admin",
            parent_address="spark://parent",
            source_hash="abc123",
        )
        assert msg.actor_address == "spark://actor1"
        assert msg.actor_class == "MyActor"
        assert msg.admin_address == "spark://admin"
        assert msg.parent_address == "spark://parent"
        assert msg.source_hash == "abc123"
        assert msg.exiting is None

    def test_common_status_fields_defaults(self) -> None:
        common = CommonStatusFields()
        assert common.pending_messages == ()
        assert common.pending_wakeups == ()
        assert common.received_messages == ()
        assert common.child_actors == ()
        assert common.governor is None
        assert common.messages_sent == 0
        assert common.send_failures == 0
        assert common.messages_received == 0
        assert common.misc == {}
        assert common.pending_addr_counts == {}

    def test_pending_message(self) -> None:
        pm = PendingMessage(from_addr="a", to_addr="b", message="hello")
        assert pm.from_addr == "a"
        assert pm.to_addr == "b"
        assert pm.message == "hello"

    def test_pending_wakeup(self) -> None:
        pw = PendingWakeup(target="a", delay=5.0, payload="wake")
        assert pw.target == "a"
        assert pw.delay == 5.0
        assert pw.payload == "wake"

    def test_federation_attendee(self) -> None:
        ca = FederationAttendee(address="addr", valid_until="2024-01-01")
        assert ca.address == "addr"
        assert ca.valid_until == "2024-01-01"

    def test_loaded_source_info(self) -> None:
        ls = LoadedSourceInfo(source_hash="abc", source_info="mymod.py")
        assert ls.source_hash == "abc"
        assert ls.source_info == "mymod.py"


class TestDeadLetter:
    def test_dead_letter_creation(self) -> None:
        sys_id = SyndicateId()
        sender_id = ActorId(syndicate_id=sys_id)
        target_id = ActorId(syndicate_id=sys_id)
        original_envelope = Envelope(
            target=target_id,
            payload="test message",
            sender=sender_id,
        )

        dead_letter = DeadLetter(
            original_envelope=original_envelope,
            reason="target not found",
        )

        assert dead_letter.original_envelope == original_envelope
        assert dead_letter.reason == "target not found"
        assert dead_letter.timestamp is not None

    def test_dead_letter_custom_timestamp(self) -> None:
        target_id = ActorId(syndicate_id=SyndicateId())
        original_envelope = Envelope(target=target_id, payload="test")
        custom_timestamp = 1234567890.0

        dead_letter = DeadLetter(
            original_envelope=original_envelope,
            reason="reason",
            timestamp=custom_timestamp,
        )

        assert dead_letter.timestamp == custom_timestamp


class TestMessageInheritance:
    def test_all_messages_inherit_from_syndicate_message(self) -> None:
        actor_id = ActorId(SyndicateId())
        spec = ActorSpec(actor_class=object)
        messages = [
            SystemShutdown(),
            ActorExitRequest(),
            ActorExited(actor_id),
            ChildActorExited(actor_id, ActorId(SyndicateId())),
            ActorCreateRequest(spec),
            ActorCreateResponse(actor_id),
            WakeupRequest(actor_id),
            WakeupMessage(1.0),
            StatusRequest(),
            SystemStatus(SyndicateId(), "admin", 0, 0.0, "test"),
            ActorStatus("addr", "Cls", "admin"),
            DeadLetter(Envelope(target=actor_id, payload="test"), "test"),
            WatchMessage(),
        ]

        assert all(isinstance(msg, SyndicateMessage) for msg in messages)


class TestWatchMessage:
    def test_defaults(self) -> None:
        msg = WatchMessage()
        assert msg.ready_read == ()
        assert msg.ready_write == ()
        assert msg.failed == ()

    def test_carries_fd_groups(self) -> None:
        msg = WatchMessage(ready_read=(3,), ready_write=(4,), failed=(5,))
        assert msg.ready_read == (3,)
        assert msg.ready_write == (4,)
        assert msg.failed == (5,)
