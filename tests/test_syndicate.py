import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

import spark.system.syndicate as syndicate_module
from spark import (
    Actor,
    ActorAddress,
    ActorExited,
    ActorExitRequest,
    ActorSpec,
    CancellationRequest,
    ChildActorExited,
    ChildActorRestarted,
    MailboxPolicy,
    SupervisorStrategy,
    Syndicate,
    SyndicateId,
    WatchMessage,
    get_existing_global_syndicate,
    get_global_syndicate,
    shutdown_global_syndicate,
)
from spark.core.exceptions import ActorTimeout, MessageDeliveryError, SyndicateError
from spark.core.identity import ActorId, Envelope
from spark.core.message import Message
from spark.core.messages import WakeupMessage


class EchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(f"echo:{message.content}", message.sender)


class SlowOrderedActor(Actor):
    async def process(self, message: Message) -> None:
        index, delay = message.content
        await asyncio.sleep(delay)
        if message.sender is not None:
            await self.tell(index, message.sender)


class WakeupActor(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.requester: ActorAddress | None = None

    async def process(self, message: Message) -> None:
        if message.content == "start" and message.sender is not None:
            self.requester = message.sender
            self.schedule_after(0.01, "ready")
        elif isinstance(message.content, WakeupMessage) and self.requester is not None:
            await self.tell(message.content.payload, self.requester)


class ChildActor(Actor):
    async def process(self, message: Message) -> None:
        return None


class ParentActor(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.requester: ActorAddress | None = None

    async def process(self, message: Message) -> None:
        if message.content == "start" and message.sender is not None:
            self.requester = message.sender
            child = await self.create_actor(ChildActor)
            await self.tell(ActorExitRequest("done"), child)
        elif isinstance(message.content, ChildActorExited) and self.requester is not None:
            await self.tell(message.content.reason, self.requester)


class WatchActor(Actor):
    def __init__(self, fd: int) -> None:
        super().__init__()
        self.fd = fd
        self.requester: ActorAddress | None = None

    async def process(self, message: Message) -> None:
        if message.content == "arm" and message.sender is not None:
            self.requester = message.sender
            await self.watch(read=(self.fd,))
        elif isinstance(message.content, WatchMessage) and self.requester is not None:
            await self.tell(("read", message.content.ready_read), self.requester)


class DirectEchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(f"direct:{message.content}", message.sender)


class SystemInboxEmitter(Actor):
    async def process(self, message: Message) -> None:
        if message.content == "emit":
            await self.tell("owned-system")


class DeactivatingReturnActor(Actor):
    async def process(self, message: Message) -> str:
        self.deactivate()
        return f"inactive:{message.content}"


class ReactivatingReturnActor(Actor):
    async def process(self, message: Message) -> str:
        self.deactivate()
        self.activate()
        return f"active:{message.content}"


class ReturnActor(Actor):
    async def process(self, message: Message) -> str:
        return f"run:{message.content}"


class NoReplyDeactivatingActor(Actor):
    async def process(self, message: Message) -> None:
        self.deactivate()


class SlowReturnActor(Actor):
    async def process(self, message: Message) -> str:
        await asyncio.sleep(1.0)
        return f"slow:{message.content}"


@pytest.fixture
def clean_global_syndicate():
    shutdown_global_syndicate()
    yield
    shutdown_global_syndicate()


async def _wait_for_global_shutdown(timeout: float = 1.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if syndicate_module._global_syndicate is None:
            return
        await asyncio.sleep(0.01)
    assert syndicate_module._global_syndicate is None


async def _wait_until(condition: Callable[[], bool], timeout: float = 1.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    assert condition()


@pytest.mark.asyncio
async def test_create_tell_ask_and_receive() -> None:
    async with Syndicate("async-basic") as system:
        actor = await system.create_actor(EchoActor)
        await system.tell("hello", actor)
        assert await system.receive(timeout=1.0) == "echo:hello"
        assert await system.ask("question", actor) == "echo:question"


@pytest.mark.asyncio
async def test_actor_processes_one_message_at_a_time_in_fifo_order() -> None:
    async with Syndicate("async-ordering") as system:
        actor = await system.create_actor(SlowOrderedActor)
        for index in range(5):
            await system.tell((index, 0.01 if index == 0 else 0.0), actor)
        replies = [await system.receive(timeout=1.0) for _ in range(5)]
        assert replies == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_wakeup_child_exit_dead_letter_and_endpoint() -> None:
    async with Syndicate("async-runtime") as system:
        wakeup = await system.create_actor(WakeupActor)
        await system.tell("start", wakeup)
        assert await system.receive(timeout=1.0) == "ready"

        parent = await system.create_actor(ParentActor)
        await system.tell("start", parent)
        assert await system.receive(timeout=1.0) == "done"

        missing = ActorAddress(ActorId(SyndicateId.from_name("async-runtime")))
        await system.tell("lost", missing)
        assert system.dead_letters[-1].reason == "target not found"
        with pytest.raises(MessageDeliveryError, match="target not found"):
            await system.ask("lost", missing)

        async with system.endpoint() as endpoint:
            actor = await endpoint.create_actor(EchoActor)
            await endpoint.tell("private", actor)
            assert await endpoint.receive(timeout=1.0) == "echo:private"
            assert await system.receive(timeout=0.05) is None


@pytest.mark.asyncio
async def test_ask_timeout() -> None:
    class SilentActor(Actor):
        async def process(self, message: Message) -> None:
            return None

    async with Syndicate("async-timeout") as system:
        actor = await system.create_actor(SilentActor)
        with pytest.raises(ActorTimeout):
            await system.ask("hello", actor, timeout=0.01)


@pytest.mark.asyncio
async def test_fd_watch_uses_event_loop_reader() -> None:
    read_fd, write_fd = os.pipe()
    try:
        async with Syndicate("async-watch") as system:
            actor = await system.create_actor(WatchActor, read_fd)
            await system.tell("arm", actor)
            await asyncio.sleep(0)
            os.write(write_fd, b"x")
            assert await system.receive(timeout=1.0) == ("read", (read_fd,))
    finally:
        for fd in (read_fd, write_fd):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_remote_ask_uses_asyncio_tcp_streams() -> None:
    async with (
        Syndicate("remote-left", remote=True, transport_codec="trusted-pickle") as left,
        Syndicate("remote-right", remote=True, transport_codec="trusted-pickle") as right,
    ):
        assert left.remote_address is not None
        assert right.remote_address is not None
        await left.connect(right.syndicate_id, *right.remote_address)
        await right.connect(left.syndicate_id, *left.remote_address)
        remote_actor = await right.create_actor(EchoActor)
        assert await left.ask("hello", remote_actor, timeout=2.0) == "echo:hello"


@pytest.mark.asyncio
async def test_threaded_and_process_backends_are_hybrid_execution_modes() -> None:
    async with Syndicate("threaded-hybrid", backend="threaded") as threaded:
        assert threaded.diagnostics().backend_type == "async-hybrid-threaded"
        actor = await threaded.create_actor_from_spec(
            ActorSpec(actor_class=EchoActor, execution="system", stateless=True)
        )
        assert await threaded.ask("hello", actor, timeout=2.0) == "echo:hello"

    async with Syndicate("process-hybrid", backend="process") as process:
        assert process.diagnostics().backend_type == "async-hybrid-process"


def test_direct_constructor_auto_starts_actor_in_global_syndicate(clean_global_syndicate) -> None:
    actor = DirectEchoActor()
    system = get_global_syndicate()

    assert actor.actor_id is not None
    assert actor.actor_address is not None
    assert actor.address is not None
    assert actor.actor_id.syndicate_id == system.syndicate_id


@pytest.mark.asyncio
async def test_direct_constructor_actor_receives_via_global_syndicate(clean_global_syndicate) -> None:
    actor = DirectEchoActor()
    system = get_global_syndicate()

    assert actor.address is not None
    assert await system.ask("hello", actor.address, timeout=1.0) == "direct:hello"


def test_actor_can_opt_out_of_constructor_auto_start(clean_global_syndicate) -> None:
    class ManualActor(Actor):
        __spark_auto_start__ = False

        async def process(self, message: Message) -> None:
            return None

    actor = ManualActor()

    assert actor.actor_id is None
    assert actor.actor_address is None
    assert actor.address is None


@pytest.mark.asyncio
async def test_explicit_create_actor_suppresses_constructor_auto_start(clean_global_syndicate) -> None:
    async with Syndicate("explicit-no-global-leak") as system:
        actor = await system.create_actor(DirectEchoActor)

        assert actor.actor_id.syndicate_id == system.syndicate_id
        assert syndicate_module._global_syndicate is None


def test_global_syndicate_reuses_matching_config_and_rejects_conflicts(clean_global_syndicate) -> None:
    first = get_global_syndicate("same-global")

    assert get_global_syndicate("same-global") is first
    with pytest.raises(SyndicateError):
        get_global_syndicate("different-global")


def test_get_existing_global_syndicate_does_not_create(clean_global_syndicate) -> None:
    assert get_existing_global_syndicate() is None
    assert syndicate_module._global_syndicate is None

    system = get_global_syndicate("existing-global")

    assert get_existing_global_syndicate() is system

    shutdown_global_syndicate()

    assert get_existing_global_syndicate() is None


def test_shutdown_global_syndicate_allows_fresh_default(clean_global_syndicate) -> None:
    first = get_global_syndicate("first-global")

    shutdown_global_syndicate()
    second = get_global_syndicate("second-global")

    assert second is not first
    assert second.syndicate_id != first.syndicate_id


@pytest.mark.asyncio
async def test_get_global_syndicate_replaces_stale_context_managed_default(clean_global_syndicate) -> None:
    first = get_global_syndicate()
    first_id = first.syndicate_id

    async with first:
        assert first.active is True

    assert first.active is False

    second = get_global_syndicate()

    assert second is not first
    assert second.active is True
    assert second.syndicate_id != first_id
    await second.tell("ping", second.address)
    assert await second.receive(timeout=1.0) == "ping"


@pytest.mark.asyncio
async def test_omitted_target_tell_and_ask_use_global_inbox(clean_global_syndicate) -> None:
    actor = DirectEchoActor()
    system = get_global_syndicate()

    await actor.tell("from-actor")
    assert await system.receive(timeout=1.0) == "from-actor"

    await system.tell("from-system")
    assert await system.receive(timeout=1.0) == "from-system"

    with pytest.raises(ActorTimeout):
        await actor.ask("no-responder", timeout=0.01)
    assert await system.receive(timeout=1.0) == "no-responder"


@pytest.mark.asyncio
async def test_actor_omitted_target_uses_owning_syndicate_inbox() -> None:
    async with Syndicate("explicit-owner") as system:
        actor = await system.create_actor(SystemInboxEmitter)

        await system.tell("emit", actor)

        assert await system.receive(timeout=1.0) == "owned-system"


@pytest.mark.asyncio
async def test_global_syndicate_shuts_down_when_no_actors_are_active(clean_global_syndicate) -> None:
    actor = DeactivatingReturnActor()
    system = get_global_syndicate()

    assert actor.address is not None
    assert await system.ask("done", actor.address, timeout=1.0) == "inactive:done"
    assert actor.active is False

    await _wait_for_global_shutdown()
    fresh = get_global_syndicate()
    assert fresh is not system
    assert fresh.syndicate_id != system.syndicate_id


@pytest.mark.asyncio
async def test_global_syndicate_stays_running_when_any_actor_is_active(clean_global_syndicate) -> None:
    inactive_actor = DeactivatingReturnActor()
    active_actor = DirectEchoActor()
    system = get_global_syndicate()

    assert inactive_actor.address is not None
    assert active_actor.address is not None
    assert await system.ask("done", inactive_actor.address, timeout=1.0) == "inactive:done"
    await asyncio.sleep(0.05)

    assert inactive_actor.active is False
    assert active_actor.active is True
    assert syndicate_module._global_syndicate is system


@pytest.mark.asyncio
async def test_actor_run_keeps_active_actor_bound_across_global_idle_check(clean_global_syndicate) -> None:
    actor = ReturnActor()
    system = get_global_syndicate()

    assert await actor.run("Spark") == "run:Spark"
    assert actor.active is True

    await asyncio.sleep(0.05)
    assert syndicate_module._global_syndicate is system
    assert await actor.run("again") == "run:again"


@pytest.mark.asyncio
async def test_actor_run_completes_when_process_returns_none(clean_global_syndicate) -> None:
    actor = NoReplyDeactivatingActor()

    assert await actor.run("Spark") is None
    assert actor.active is False

    await _wait_for_global_shutdown()
    assert syndicate_module._global_syndicate is None


@pytest.mark.asyncio
async def test_actor_run_preserves_active_state_when_cancelled(clean_global_syndicate) -> None:
    actor = SlowReturnActor()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(actor.run("Spark"), timeout=0.01)

    assert actor.active is True


@pytest.mark.asyncio
async def test_actor_run_on_stale_global_actor_fails_immediately(clean_global_syndicate) -> None:
    actor = ReturnActor()

    assert await actor.run("Spark") == "run:Spark"

    shutdown_global_syndicate()

    with pytest.raises(SyndicateError, match="stopped global Syndicate"):
        await actor.run("again")


@pytest.mark.asyncio
async def test_actor_reactivation_prevents_global_shutdown(clean_global_syndicate) -> None:
    actor = ReactivatingReturnActor()
    system = get_global_syndicate()

    assert actor.address is not None
    assert await system.ask("again", actor.address, timeout=1.0) == "active:again"
    await asyncio.sleep(0.05)

    assert actor.active is True
    assert syndicate_module._global_syndicate is system


@pytest.mark.asyncio
async def test_explicit_syndicate_does_not_shutdown_when_actor_deactivates() -> None:
    async with Syndicate("explicit-inactive-no-shutdown") as system:
        actor = await system.create_actor(DeactivatingReturnActor)

        assert await system.ask("done", actor, timeout=1.0) == "inactive:done"
        await asyncio.sleep(0.05)

        assert system.backend.registry.exists(actor.actor_id)
        assert system.backend._shutdown is False


@pytest.mark.asyncio
async def test_bounded_mailbox_rejects_overflow_and_control_lane_stays_available() -> None:
    class HoldingActor(Actor):
        release = asyncio.Event()
        processed: list[str] = []

        async def process(self, message: Message) -> None:
            if message.content == "hold":
                await type(self).release.wait()
                return
            type(self).processed.append(str(message.content))

    HoldingActor.release = asyncio.Event()
    HoldingActor.processed = []

    async with Syndicate("mailbox-overflow") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(
                actor_class=HoldingActor,
                mailbox_policy=MailboxPolicy(max_size=1, overflow="reject"),
            )
        )

        assert (await system.tell("hold", actor)).success
        await _wait_until(lambda: system.backend.running_actor_count() == 1)
        assert (await system.tell("queued", actor)).success
        overflow = await system.tell("overflow", actor)
        assert overflow.success is False
        assert overflow.reason == "mailbox full"

        exit_result = await system.tell(ActorExitRequest("control stop"), actor)
        HoldingActor.release.set()
        await _wait_until(lambda: not system.backend.registry.exists(actor.actor_id))

        assert exit_result.success
        assert any(letter.original_envelope.payload == "overflow" for letter in system.dead_letters)
        assert HoldingActor.processed == []


@pytest.mark.asyncio
async def test_drop_oldest_mailbox_policy_keeps_newest_message() -> None:
    class HoldingActor(Actor):
        release = asyncio.Event()
        processed: list[str] = []

        async def process(self, message: Message) -> None:
            if message.content == "hold":
                await type(self).release.wait()
                return
            type(self).processed.append(str(message.content))

    HoldingActor.release = asyncio.Event()
    HoldingActor.processed = []

    async with Syndicate("mailbox-drop-oldest") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(
                actor_class=HoldingActor,
                mailbox_policy=MailboxPolicy(max_size=1, overflow="drop_oldest"),
            )
        )

        await system.tell("hold", actor)
        await _wait_until(lambda: system.backend.running_actor_count() == 1)
        assert (await system.tell("old", actor)).success
        assert (await system.tell("new", actor)).success

        HoldingActor.release.set()
        await _wait_until(lambda: HoldingActor.processed == ["new"])

        assert any(letter.original_envelope.payload == "old" for letter in system.dead_letters)


@pytest.mark.asyncio
async def test_send_deadline_expires_before_delivery() -> None:
    class RecordingActor(Actor):
        processed: list[str] = []

        async def process(self, message: Message) -> None:
            type(self).processed.append(str(message.content))

    RecordingActor.processed = []

    async with Syndicate("mailbox-deadline") as system:
        actor = await system.create_actor(RecordingActor)
        past = datetime.now(tz=UTC) - timedelta(seconds=1)

        result = await system.tell("expired", actor, deadline=past)

        assert result.success is False
        assert result.reason == "message expired"
        await asyncio.sleep(0.01)
        assert RecordingActor.processed == []


@pytest.mark.asyncio
async def test_ask_timeout_classifies_late_reply_outside_dead_letters() -> None:
    class SlowReplyActor(Actor):
        async def process(self, message: Message) -> str:
            await asyncio.sleep(0.05)
            return "late"

    async with Syndicate("late-reply") as system:
        actor = await system.create_actor(SlowReplyActor)

        with pytest.raises(ActorTimeout):
            await system.ask("work", actor, timeout=0.01)
        await _wait_until(lambda: len(system.late_replies) == 1)

        assert system.late_replies[0].original_envelope.payload == "late"
        assert not any(letter.original_envelope.payload == "late" for letter in system.dead_letters)


@pytest.mark.asyncio
async def test_cancelled_ask_sends_best_effort_cancellation() -> None:
    class CancellableActor(Actor):
        async def process(self, message: Message) -> str | None:
            if message.content == "work":
                await asyncio.sleep(0.05)
                return "done"
            if isinstance(message.content, CancellationRequest):
                await self.tell(("cancelled", message.content.correlation_id))
            return None

    async with Syndicate("ask-cancellation") as system:
        actor = await system.create_actor(CancellableActor)
        pending = asyncio.create_task(system.ask("work", actor, timeout=1.0))
        await asyncio.sleep(0)

        pending.cancel()

        with pytest.raises(asyncio.CancelledError):
            await pending
        cancellation = await system.receive(timeout=1.0)

        assert cancellation[0] == "cancelled"


@pytest.mark.asyncio
async def test_ask_stream_yields_multiple_replies() -> None:
    class StreamActor(Actor):
        async def process(self, message: Message) -> None:
            if message.sender is None:
                return
            for index in range(3):
                await self.tell(index, message.sender)

    async with Syndicate("ask-stream") as system:
        actor = await system.create_actor(StreamActor)

        replies = [reply async for reply in system.ask_stream("go", actor, timeout=0.1, max_replies=3)]

        assert replies == [0, 1, 2]


@pytest.mark.asyncio
async def test_dead_letters_are_bounded_by_ring_capacity() -> None:
    async with Syndicate("dead-letter-ring", dead_letter_capacity=2) as system:
        missing = ActorAddress(ActorId(system.syndicate_id))

        await system.tell("first", missing)
        await system.tell("second", missing)
        await system.tell("third", missing)

        assert [letter.original_envelope.payload for letter in system.dead_letters] == ["second", "third"]


@pytest.mark.asyncio
async def test_supervisor_restart_preserves_address_and_bumps_incarnation() -> None:
    class RestartableActor(Actor):
        starts = 0
        stops = 0

        async def pre_start(self) -> None:
            type(self).starts += 1

        async def post_stop(self) -> None:
            type(self).stops += 1

        async def process(self, message: Message) -> tuple[str, int] | None:
            if message.content == "boom":
                raise RuntimeError("boom")
            if message.content == "ping":
                return ("pong", type(self).starts)
            return None

    async with Syndicate("supervision-restart") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(
                actor_class=RestartableActor,
                supervisor_strategy=SupervisorStrategy.restart(max_restarts=1),
            )
        )
        old_incarnation = system.backend.registry.get(actor.actor_id).incarnation

        await system.tell("boom", actor)
        await _wait_until(
            lambda: system.backend.registry.get(actor.actor_id).incarnation.generation == old_incarnation.generation + 1
        )

        new_incarnation = system.backend.registry.get(actor.actor_id).incarnation
        assert new_incarnation.actor_id == old_incarnation.actor_id == actor.actor_id
        assert new_incarnation.generation == old_incarnation.generation + 1
        assert await system.ask("ping", actor, timeout=1.0) == ("pong", 2)
        assert RestartableActor.stops == 1


@pytest.mark.asyncio
async def test_parent_receives_child_restarted_notification() -> None:
    class FailingChild(Actor):
        async def process(self, message: Message) -> None:
            if message.content == "boom":
                raise RuntimeError("child exploded")

    class RestartParent(Actor):
        def __init__(self) -> None:
            super().__init__()
            self.requester: ActorAddress | None = None

        async def process(self, message: Message) -> None:
            if message.content == "start" and message.sender is not None:
                self.requester = message.sender
                child = await self.create_actor_from_spec(
                    ActorSpec(
                        actor_class=FailingChild,
                        supervisor_strategy=SupervisorStrategy.restart(max_restarts=1),
                    )
                )
                await self.tell("boom", child)
            elif isinstance(message.content, ChildActorRestarted) and self.requester is not None:
                await self.tell(
                    (
                        "restarted",
                        message.content.old_incarnation.generation,
                        message.content.new_incarnation.generation,
                        message.content.reason,
                    ),
                    self.requester,
                )

    async with Syndicate("supervision-parent-restart") as system:
        parent = await system.create_actor(RestartParent)

        await system.tell("start", parent)

        reply = await system.receive(timeout=1.0)
        assert reply[:3] == ("restarted", 0, 1)
        assert "handler failed: child exploded" in reply[3]


@pytest.mark.asyncio
async def test_parent_on_child_exited_hook_runs_for_child_exit() -> None:
    class HookChild(Actor):
        async def process(self, message: Message) -> None:
            return None

    class HookParent(Actor):
        def __init__(self) -> None:
            super().__init__()
            self.requester: ActorAddress | None = None
            self.hook_reason: str | None = None

        async def on_child_exited(self, child: ActorAddress, reason: str) -> None:
            self.hook_reason = reason

        async def process(self, message: Message) -> None:
            if message.content == "start" and message.sender is not None:
                self.requester = message.sender
                child = await self.create_actor(HookChild)
                await self.tell(ActorExitRequest("hooked"), child)
            elif isinstance(message.content, ChildActorExited) and self.requester is not None:
                await self.tell((self.hook_reason, message.content.reason), self.requester)

    async with Syndicate("supervision-child-hook") as system:
        parent = await system.create_actor(HookParent)

        await system.tell("start", parent)

        assert await system.receive(timeout=1.0) == ("hooked", "hooked")


@pytest.mark.asyncio
async def test_system_monitor_receives_actor_exited_notification() -> None:
    class MonitoredActor(Actor):
        async def process(self, message: Message) -> None:
            return None

    async with Syndicate("supervision-monitor") as system:
        actor = await system.create_actor(MonitoredActor)

        await system.monitor(actor)
        await system.stop(actor)

        notification = await system.receive(timeout=1.0)
        assert isinstance(notification, ActorExited)
        assert notification.actor_id == actor.actor_id
        assert notification.reason == "actor stopped"


@pytest.mark.asyncio
async def test_actor_monitor_receives_actor_exited_notification() -> None:
    class MonitoredActor(Actor):
        async def process(self, message: Message) -> None:
            return None

    class MonitorActor(Actor):
        def __init__(self) -> None:
            super().__init__()
            self.requester: ActorAddress | None = None
            self.target: ActorAddress | None = None

        async def process(self, message: Message) -> None:
            if message.content == "start" and message.sender is not None:
                self.requester = message.sender
                self.target = await self.create_actor(MonitoredActor)
                await self.monitor(self.target)
                await self.tell(ActorExitRequest("watched"), self.target)
            elif isinstance(message.content, ActorExited) and self.requester is not None:
                await self.tell((message.content.actor_id, message.content.reason), self.requester)

    async with Syndicate("supervision-actor-monitor") as system:
        watcher = await system.create_actor(MonitorActor)

        await system.tell("start", watcher)

        actor_id, reason = await system.receive(timeout=1.0)
        assert reason == "watched"
        assert isinstance(actor_id, ActorId)


@pytest.mark.asyncio
async def test_link_stops_peer_when_actor_exits() -> None:
    class LinkedActor(Actor):
        async def process(self, message: Message) -> None:
            return None

    async with Syndicate("supervision-link") as system:
        left = await system.create_actor(LinkedActor)
        right = await system.create_actor(LinkedActor)

        await system.link(left, right)
        await system.stop(left)

        assert not system.backend.registry.exists(left.actor_id)
        await _wait_until(lambda: not system.backend.registry.exists(right.actor_id))


@pytest.mark.asyncio
async def test_restart_limit_exhaustion_stops_actor() -> None:
    class AlwaysCrashesActor(Actor):
        async def process(self, message: Message) -> str | None:
            if message.content == "boom":
                raise RuntimeError("boom")
            return "alive"

    async with Syndicate("supervision-limit") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(
                actor_class=AlwaysCrashesActor,
                supervisor_strategy=SupervisorStrategy.restart(max_restarts=1),
            )
        )

        await system.tell("boom", actor)
        await _wait_until(lambda: system.backend.registry.get(actor.actor_id).incarnation.generation == 1)
        await system.tell("boom", actor)
        await _wait_until(lambda: not system.backend.registry.exists(actor.actor_id))

        with pytest.raises(MessageDeliveryError, match="target not found"):
            await system.ask("ping", actor, timeout=0.1)
        assert any("restart limit exceeded" in letter.reason for letter in system.dead_letters)


@pytest.mark.asyncio
async def test_stale_target_incarnation_is_rejected_after_restart() -> None:
    class RestartableActor(Actor):
        processed: list[str] = []

        async def process(self, message: Message) -> None:
            if message.content == "boom":
                raise RuntimeError("boom")
            type(self).processed.append(str(message.content))

    async with Syndicate("supervision-stale-incarnation") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(
                actor_class=RestartableActor,
                supervisor_strategy=SupervisorStrategy.restart(max_restarts=1),
            )
        )
        old_incarnation = system.backend.registry.get(actor.actor_id).incarnation

        boom_result = await system.backend.deliver(
            Envelope(target=actor.actor_id, payload="boom", target_incarnation=old_incarnation)
        )
        stale_result = await system.backend.deliver(
            Envelope(target=actor.actor_id, payload="stale", target_incarnation=old_incarnation)
        )

        assert boom_result.success
        assert stale_result.success
        await _wait_until(lambda: system.backend.registry.get(actor.actor_id).incarnation.generation == 1)
        await _wait_until(
            lambda: any(
                letter.original_envelope.payload == "stale" and letter.reason == "stale actor incarnation"
                for letter in system.dead_letters
            )
        )
        assert RestartableActor.processed == []


@pytest.mark.asyncio
async def test_resume_strategy_keeps_actor_running_after_handler_failure() -> None:
    class ResumeActor(Actor):
        def __init__(self) -> None:
            super().__init__()
            self.failed_once = False

        async def process(self, message: Message) -> tuple[str, bool] | None:
            if message.content == "boom":
                self.failed_once = True
                raise RuntimeError("resume me")
            if message.content == "ping":
                return ("alive", self.failed_once)
            return None

    async with Syndicate("supervision-resume") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=ResumeActor, supervisor_strategy=SupervisorStrategy.resume())
        )
        incarnation = system.backend.registry.get(actor.actor_id).incarnation

        await system.tell("boom", actor)
        await _wait_until(lambda: any("resume me" in letter.reason for letter in system.dead_letters))

        assert system.backend.registry.get(actor.actor_id).incarnation == incarnation
        assert await system.ask("ping", actor, timeout=1.0) == ("alive", True)


@pytest.mark.asyncio
async def test_escalate_strategy_stops_child_and_notifies_parent() -> None:
    class EscalatingChild(Actor):
        async def process(self, message: Message) -> None:
            if message.content == "boom":
                raise RuntimeError("escalated failure")

    class EscalationParent(Actor):
        def __init__(self) -> None:
            super().__init__()
            self.requester: ActorAddress | None = None

        async def process(self, message: Message) -> None:
            if message.content == "start" and message.sender is not None:
                self.requester = message.sender
                child = await self.create_actor_from_spec(
                    ActorSpec(
                        actor_class=EscalatingChild,
                        supervisor_strategy=SupervisorStrategy.escalate(),
                    )
                )
                await self.tell("boom", child)
            elif isinstance(message.content, ChildActorExited) and self.requester is not None:
                await self.tell((message.content.exit_code, message.content.reason), self.requester)

    async with Syndicate("supervision-escalate") as system:
        parent = await system.create_actor(EscalationParent)

        await system.tell("start", parent)

        exit_code, reason = await system.receive(timeout=1.0)
        assert exit_code == 1
        assert reason.startswith("escalated: handler failed: escalated failure")


@pytest.mark.asyncio
async def test_post_stop_failure_is_recorded_without_blocking_stop() -> None:
    class BadCleanupActor(Actor):
        async def process(self, message: Message) -> None:
            return None

        async def post_stop(self) -> None:
            raise RuntimeError("cleanup failed")

    async with Syndicate("supervision-cleanup-failure") as system:
        actor = await system.create_actor(BadCleanupActor)

        await system.stop(actor)

        assert system.diagnostics().lifecycle_failure_count == 1
        assert system.dead_letters[-1].reason == "post_stop failed: cleanup failed"


@pytest.mark.asyncio
async def test_failed_pre_start_does_not_call_post_stop() -> None:
    class BadStartActor(Actor):
        post_stop_called = False

        async def pre_start(self) -> None:
            raise RuntimeError("init failed")

        async def process(self, message: Message) -> None:
            return None

        async def post_stop(self) -> None:
            type(self).post_stop_called = True

    async with Syndicate("supervision-start-failure") as system:
        with pytest.raises(RuntimeError, match="init failed"):
            await system.create_actor(BadStartActor)

        assert BadStartActor.post_stop_called is False
        assert system.diagnostics().lifecycle_failure_count == 1
        assert system.dead_letters[-1].reason == "pre_start failed: init failed"
