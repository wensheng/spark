"""Tests for the base actor API."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from spark.actor import Actor, ActorAddress
from spark.core.exceptions import ActorAlreadyStartedError, ActorNotStartedError
from spark.core.identity import ActorId, Envelope, SyndicateId
from spark.core.message import Message


class RecordingActor(Actor):
    __spark_auto_start__ = False

    def __init__(self) -> None:
        super().__init__()
        self.received: list[Message] = []

    def process(self, message: Message) -> None:
        self.received.append(message)


@dataclass
class RecordingContext:
    actor_id: ActorId
    address: ActorAddress
    syndicate_address: ActorAddress
    parent: ActorAddress | None = None
    sent: list[tuple[ActorAddress, Any]] = field(default_factory=list)
    wakeups: list[tuple[float, Any]] = field(default_factory=list)

    async def tell(self, message: Any, target: ActorAddress) -> None:
        self.sent.append((target, message))

    async def ask(self, message: Any, target: ActorAddress, timeout: float | None = None) -> Any:
        self.sent.append((target, message))
        return {"target": target, "message": message, "timeout": timeout}

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        child_id = ActorId(syndicate_id=self.actor_id.syndicate_id)
        return ActorAddress(child_id)

    def schedule_after(
        self,
        timeout: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        self.wakeups.append((timeout, payload))

    async def persist_event(self, event: Any) -> None:
        return None

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def watch(self, *, read=(), write=()) -> None:
        pass

    async def syndicate_shutdown(self) -> None:
        pass


class TestActorBase:
    def test_user_actor_only_needs_process(self) -> None:
        actor = RecordingActor()

        assert actor.actor_id is None
        assert actor.actor_address is None
        assert actor.address is None
        assert actor.active is True

    def test_activity_state_defaults_to_active_and_can_change(self) -> None:
        actor = RecordingActor()
        changes: list[bool] = []
        actor._set_activity_change_callback(lambda: changes.append(actor.active))

        assert actor.active is True

        actor.active = True
        assert changes == []

        actor.deactivate()
        assert actor.active is False
        assert changes == [False]

        actor.active = False
        assert changes == [False]

        actor.activate()
        assert actor.active is True
        assert changes == [False, True]

    @pytest.mark.asyncio
    async def test_unbound_runtime_methods_raise_clear_error(self) -> None:
        actor = RecordingActor()
        target = ActorAddress(ActorId(SyndicateId()))

        with pytest.raises(ActorNotStartedError):
            await actor.tell("hello", target)
        with pytest.raises(ActorNotStartedError):
            await actor.ask("hello", target)
        with pytest.raises(ActorNotStartedError):
            await actor.create_actor(RecordingActor)
        with pytest.raises(ActorNotStartedError):
            actor.schedule_after(1.0)
        with pytest.raises(ActorNotStartedError):
            await actor.stop()

    def test_context_binding_exposes_runtime_properties(self) -> None:
        actor_id = ActorId(SyndicateId())
        address = ActorAddress(actor_id)
        context = RecordingContext(actor_id=actor_id, address=address, syndicate_address=address)
        actor = RecordingActor()

        actor._bind_context(context)

        assert actor.actor_id == actor_id
        assert actor.actor_address == context.address
        assert actor.address == context.address

    def test_context_binding_can_only_happen_once(self) -> None:
        actor_id = ActorId(SyndicateId())
        address = ActorAddress(actor_id)
        context = RecordingContext(actor_id=actor_id, address=address, syndicate_address=address)
        actor = RecordingActor()

        actor._bind_context(context)

        with pytest.raises(ActorAlreadyStartedError):
            actor._bind_context(context)

    @pytest.mark.asyncio
    async def test_runtime_methods_delegate_to_context(self) -> None:
        actor_id = ActorId(SyndicateId())
        address = ActorAddress(actor_id)
        context = RecordingContext(actor_id=actor_id, address=address, syndicate_address=address)
        target = ActorAddress(ActorId(SyndicateId()))
        actor = RecordingActor()
        actor._bind_context(context)

        await actor.tell("hello", target)
        response = await actor.ask("question", target, timeout=2.0)
        child = await actor.create_actor(RecordingActor)
        actor.schedule_after(3.0, payload="wake")
        await actor.stop()

        assert context.sent == [(target, "hello"), (target, "question")]
        assert response == {"target": target, "message": "question", "timeout": 2.0}
        assert child.actor_id.syndicate_id == actor_id.syndicate_id
        assert context.wakeups == [(3.0, "wake")]

    @pytest.mark.asyncio
    async def test_receive_envelope_converts_sender_to_address(self) -> None:
        sys_id = SyndicateId()
        sender = ActorId(syndicate_id=sys_id)
        target = ActorId(syndicate_id=sys_id)
        actor = RecordingActor()

        await actor.receive_envelope(Envelope(target=target, payload="hello", sender=sender))

        assert len(actor.received) == 1
        assert actor.received[0].content == "hello"
        assert actor.received[0].sender == ActorAddress(sender)

    def test_lifecycle_hooks_are_optional_noops(self) -> None:
        actor = RecordingActor()

        assert actor.pre_start() is None
        assert actor.post_stop() is None
        assert actor.on_child_exited(ActorAddress(ActorId(SyndicateId())), "done") is None
