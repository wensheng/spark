import asyncio
import os

import pytest

import spark.system as system_module
from spark import (
    Actor,
    ActorAddress,
    ActorExitRequest,
    ActorSpec,
    ChildActorExited,
    Syndicate,
    SyndicateId,
    WatchMessage,
    get_existing_global_syndicate,
    get_global_syndicate,
    shutdown_global_syndicate,
)
from spark.core.exceptions import ActorTimeout, MessageDeliveryError, SyndicateError
from spark.core.identity import ActorId
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
        if system_module._global_syndicate is None:
            return
        await asyncio.sleep(0.01)
    assert system_module._global_syndicate is None


@pytest.mark.asyncio
async def test_create_tell_ask_and_receive() -> None:
    async with Syndicate("async-basic") as system:
        actor = await system.create_actor(EchoActor)
        await system.tell(actor, "hello")
        assert await system.receive(timeout=1.0) == "echo:hello"
        assert await system.ask(actor, "question") == "echo:question"


@pytest.mark.asyncio
async def test_actor_processes_one_message_at_a_time_in_fifo_order() -> None:
    async with Syndicate("async-ordering") as system:
        actor = await system.create_actor(SlowOrderedActor)
        for index in range(5):
            await system.tell(actor, (index, 0.01 if index == 0 else 0.0))
        replies = [await system.receive(timeout=1.0) for _ in range(5)]
        assert replies == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_wakeup_child_exit_dead_letter_and_endpoint() -> None:
    async with Syndicate("async-runtime") as system:
        wakeup = await system.create_actor(WakeupActor)
        await system.tell(wakeup, "start")
        assert await system.receive(timeout=1.0) == "ready"

        parent = await system.create_actor(ParentActor)
        await system.tell(parent, "start")
        assert await system.receive(timeout=1.0) == "done"

        missing = ActorAddress(ActorId(SyndicateId.from_name("async-runtime")))
        await system.tell(missing, "lost")
        assert system.dead_letters[-1].reason == "target not found"
        with pytest.raises(MessageDeliveryError, match="target not found"):
            await system.ask(missing, "lost")

        async with system.endpoint() as endpoint:
            actor = await endpoint.create_actor(EchoActor)
            await endpoint.tell(actor, "private")
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
            await system.ask(actor, "hello", timeout=0.01)


@pytest.mark.asyncio
async def test_fd_watch_uses_event_loop_reader() -> None:
    read_fd, write_fd = os.pipe()
    try:
        async with Syndicate("async-watch") as system:
            actor = await system.create_actor(WatchActor, read_fd)
            await system.tell(actor, "arm")
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
    async with Syndicate("remote-left", remote=True) as left, Syndicate("remote-right", remote=True) as right:
        assert left.remote_address is not None
        assert right.remote_address is not None
        await left.connect(right.syndicate_id, *right.remote_address)
        await right.connect(left.syndicate_id, *left.remote_address)
        remote_actor = await right.create_actor(EchoActor)
        assert await left.ask(remote_actor, "hello", timeout=2.0) == "echo:hello"


@pytest.mark.asyncio
async def test_threaded_and_process_backends_are_hybrid_execution_modes() -> None:
    async with Syndicate("threaded-hybrid", backend="threaded") as threaded:
        assert threaded.diagnostics().backend_type == "async-hybrid-threaded"
        actor = await threaded.create_actor_from_spec(
            ActorSpec(actor_class=EchoActor, execution="system", stateless=True)
        )
        assert await threaded.ask(actor, "hello", timeout=2.0) == "echo:hello"

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
    assert await system.ask(actor.address, "hello", timeout=1.0) == "direct:hello"


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
        assert system_module._global_syndicate is None


def test_global_syndicate_reuses_matching_config_and_rejects_conflicts(clean_global_syndicate) -> None:
    first = get_global_syndicate("same-global")

    assert get_global_syndicate("same-global") is first
    with pytest.raises(SyndicateError):
        get_global_syndicate("different-global")


def test_get_existing_global_syndicate_does_not_create(clean_global_syndicate) -> None:
    assert get_existing_global_syndicate() is None
    assert system_module._global_syndicate is None

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
    await second.tell(second.address, "ping")
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
async def test_global_syndicate_shuts_down_when_no_actors_are_active(clean_global_syndicate) -> None:
    actor = DeactivatingReturnActor()
    system = get_global_syndicate()

    assert actor.address is not None
    assert await system.ask(actor.address, "done", timeout=1.0) == "inactive:done"
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
    assert await system.ask(inactive_actor.address, "done", timeout=1.0) == "inactive:done"
    await asyncio.sleep(0.05)

    assert inactive_actor.active is False
    assert active_actor.active is True
    assert system_module._global_syndicate is system


@pytest.mark.asyncio
async def test_actor_run_keeps_active_actor_bound_across_global_idle_check(clean_global_syndicate) -> None:
    actor = ReturnActor()
    system = get_global_syndicate()

    assert await actor.run("Spark") == "run:Spark"
    assert actor.active is True

    await asyncio.sleep(0.05)
    assert system_module._global_syndicate is system
    assert await actor.run("again") == "run:again"


@pytest.mark.asyncio
async def test_actor_run_completes_when_process_returns_none(clean_global_syndicate) -> None:
    actor = NoReplyDeactivatingActor()

    assert await actor.run("Spark") is None
    assert actor.active is False

    await _wait_for_global_shutdown()
    assert system_module._global_syndicate is None


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
    assert await system.ask(actor.address, "again", timeout=1.0) == "active:again"
    await asyncio.sleep(0.05)

    assert actor.active is True
    assert system_module._global_syndicate is system


@pytest.mark.asyncio
async def test_explicit_syndicate_does_not_shutdown_when_actor_deactivates() -> None:
    async with Syndicate("explicit-inactive-no-shutdown") as system:
        actor = await system.create_actor(DeactivatingReturnActor)

        assert await system.ask(actor, "done", timeout=1.0) == "inactive:done"
        await asyncio.sleep(0.05)

        assert system.backend.registry.exists(actor.actor_id)
        assert system.backend._shutdown is False
