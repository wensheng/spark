"""Tests for identity and envelope contracts."""

import pickle
from datetime import UTC, datetime, timedelta

import pytest

from spark.actor import ActorAddress
from spark.core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId


class TestSyndicateId:
    def test_syndicate_id_creation(self) -> None:
        sys_id = SyndicateId()
        assert isinstance(sys_id.uuid, str)
        assert len(sys_id.uuid) == 36

    def test_syndicate_id_from_name_is_deterministic(self) -> None:
        assert SyndicateId.from_name("test-system") == SyndicateId.from_name("test-system")
        assert SyndicateId.from_name("system-a") != SyndicateId.from_name("system-b")

    def test_syndicate_id_string_representation(self) -> None:
        sys_id = SyndicateId.from_name("test")
        assert str(sys_id) == f"System({sys_id.uuid[:8]})"


class TestActorId:
    def test_actor_id_creation(self) -> None:
        sys_id = SyndicateId()
        actor_id = ActorId(syndicate_id=sys_id)

        assert actor_id.syndicate_id == sys_id
        assert isinstance(actor_id.actor_id, str)
        assert len(actor_id.actor_id) == 36

    def test_actor_id_equality_is_logical_identity_only(self) -> None:
        sys_id = SyndicateId()
        actor_id = ActorId(syndicate_id=sys_id)
        same_actor = ActorId(syndicate_id=sys_id, actor_id=actor_id.actor_id)

        assert actor_id == same_actor
        assert hash(actor_id) == hash(same_actor)

    def test_actor_incarnation_tracks_restart_generation(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        incarnation = ActorIncarnation(actor_id=actor_id)
        next_incarnation = incarnation.next_generation()

        assert incarnation.actor_id == next_incarnation.actor_id
        assert incarnation.generation == 0
        assert next_incarnation.generation == 1
        assert actor_id == next_incarnation.actor_id

    def test_actor_id_string_representation(self) -> None:
        sys_id = SyndicateId.from_name("test")
        actor_id = ActorId(syndicate_id=sys_id, actor_id="test-actor-123456")
        expected = f"Actor({sys_id.uuid[:8]}:{actor_id.actor_id[:8]})"
        assert str(actor_id) == expected


class TestActorAddress:
    def test_address_equality_hashing_and_pickle(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        address = ActorAddress(actor_id)
        restored = pickle.loads(pickle.dumps(address))

        assert restored == address
        assert hash(restored) == hash(address)
        assert restored.actor_id == actor_id
        assert str(address).startswith("ActorAddr-")


class TestEnvelope:
    def test_envelope_creation(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        envelope = Envelope(target=actor_id, payload="test message")

        assert envelope.message_id
        assert envelope.target == actor_id
        assert envelope.payload == "test message"
        assert envelope.sender is None
        assert envelope.headers == {}
        assert envelope.correlation_id == envelope.message_id
        assert envelope.trace_id

    def test_envelope_headers_are_copied_and_read_only(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        headers = {"route": "local"}
        envelope = Envelope(target=actor_id, payload="test", headers=headers)

        headers["route"] = "remote"
        headers["new"] = "ignored"

        assert envelope.headers == {"route": "local"}
        with pytest.raises(TypeError):
            envelope.headers["route"] = "mutated"  # type: ignore[index]

    def test_envelope_with_sender(self) -> None:
        sys_id = SyndicateId()
        sender_id = ActorId(syndicate_id=sys_id)
        target_id = ActorId(syndicate_id=sys_id)

        envelope = Envelope(target=target_id, payload="test").with_sender(sender_id)

        assert envelope.sender == sender_id
        assert envelope.target == target_id

    def test_envelope_deadline(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        deadline = datetime.now(tz=UTC) + timedelta(seconds=5)
        envelope = Envelope(target=actor_id, payload="test", deadline=deadline)

        assert envelope.deadline == deadline
        assert not envelope.is_expired

    def test_envelope_rejects_naive_deadline(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())

        with pytest.raises(ValueError, match="timezone-aware"):
            Envelope(target=actor_id, payload="test", deadline=datetime.now())

    def test_envelope_is_expired(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        future = datetime.now(tz=UTC) + timedelta(seconds=5)
        past = datetime.now(tz=UTC) - timedelta(seconds=5)

        assert not Envelope(target=actor_id, payload="test", deadline=future).is_expired
        assert Envelope(target=actor_id, payload="test", deadline=past).is_expired

    def test_envelope_with_deadline_preserves_metadata(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        envelope = Envelope(target=actor_id, payload="test", headers={"x": "y"})

        new_envelope = envelope.with_deadline(timedelta(seconds=10))

        assert new_envelope.deadline is not None
        assert new_envelope.payload == envelope.payload
        assert new_envelope.message_id == envelope.message_id
        assert new_envelope.target == actor_id
        assert new_envelope.headers == {"x": "y"}

    def test_envelope_string_representation(self) -> None:
        actor_id = ActorId(syndicate_id=SyndicateId())
        envelope = Envelope(target=actor_id, payload="test")

        assert str(envelope).startswith("Envelope(")
        assert str(envelope).endswith(")")
