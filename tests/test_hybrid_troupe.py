import asyncio
import os
import threading
from time import perf_counter

import pytest

from spark import Actor, ActorAddress, ActorSpec, Syndicate
from spark.contrib.troupe import Troupe
from spark.core.exceptions import InvalidActorSpecError
from spark.core.message import Message


class StatelessEchoActor(Actor):
    async def process(self, message: Message) -> None:
        if message.sender is not None:
            await self.tell(
                (
                    message.content,
                    os.getpid(),
                    threading.get_ident(),
                    self.address,
                ),
                message.sender,
            )


class UnsupportedCreateActor(Actor):
    async def process(self, message: Message) -> None:
        await self.create_actor(StatelessEchoActor)
        if message.sender is not None:
            await self.tell("unreachable", message.sender)


class HybridProbeTroupe(Troupe):
    troupe_max_count = 3
    troupe_idle_count = 3

    async def process(self, message: Message) -> None:
        delay, label = message.content
        await asyncio.sleep(delay)
        if message.sender is not None:
            await self.tell(
                (
                    label,
                    self.address,
                    os.getpid(),
                    threading.get_ident(),
                ),
                message.sender,
            )


class SingleWorkerProbeTroupe(Troupe):
    troupe_max_count = 1
    troupe_idle_count = 1

    async def process(self, message: Message) -> None:
        delay, label = message.content
        await asyncio.sleep(delay)
        if message.sender is not None:
            await self.tell((label, self.address), message.sender)


@pytest.mark.asyncio
@pytest.mark.parametrize("execution", ["inprocess", "thread", "process"])
async def test_troupe_worker_execution_modes_process_jobs_in_parallel(execution: str) -> None:
    async with Syndicate(f"hybrid-troupe-{execution}") as system:
        troupe = await system.create_actor(HybridProbeTroupe, worker_execution=execution)

        warmups = await asyncio.gather(
            *(system.ask(troupe, (0.0, f"warm-{index}"), timeout=10.0) for index in range(3))
        )
        await asyncio.sleep(0.1)

        started_at = perf_counter()
        replies = await asyncio.gather(
            *(system.ask(troupe, (0.25, f"job-{index}"), timeout=10.0) for index in range(3))
        )
        elapsed = perf_counter() - started_at
        status = await system.ask(troupe, "troupe:status?", timeout=2.0)

    assert sorted(reply[0] for reply in replies) == ["job-0", "job-1", "job-2"]
    assert len({reply[1] for reply in warmups}) == 3
    assert len({reply[1] for reply in replies}) == 3
    assert elapsed < 0.8
    assert "Workers=3" in status
    assert f"Execution={execution}," in status
    if execution == "thread":
        assert len({reply[3] for reply in replies}) == 3
    elif execution == "process":
        assert len({reply[2] for reply in replies}) == 3
        assert all(reply[2] != os.getpid() for reply in replies)


@pytest.mark.asyncio
async def test_system_execution_resolves_to_selected_hybrid_backend() -> None:
    async with Syndicate("system-thread-default", backend="threaded") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=StatelessEchoActor, execution="system", stateless=True)
        )
        content, pid, thread_id, _address = await system.ask(actor, "hello", timeout=5.0)

    assert content == "hello"
    assert pid == os.getpid()
    assert thread_id != threading.get_ident()

    async with Syndicate("system-process-default", backend="process") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=StatelessEchoActor, execution="system", stateless=True)
        )
        content, pid, _thread_id, _address = await system.ask(actor, "hello", timeout=5.0)

    assert content == "hello"
    assert pid != os.getpid()


@pytest.mark.asyncio
async def test_executor_specs_must_be_marked_stateless() -> None:
    async with Syndicate("stateless-required") as system:
        with pytest.raises(InvalidActorSpecError):
            await system.create_actor_from_spec(
                ActorSpec(actor_class=StatelessEchoActor, execution="thread")
            )


@pytest.mark.asyncio
async def test_process_executor_rejects_non_picklable_payload() -> None:
    async with Syndicate("process-pickle-check") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=StatelessEchoActor, execution="process", stateless=True)
        )
        result = await system.tell(actor, lambda: None)

        assert result.success is False
        assert "pickl" in (result.reason or "")
        assert system.dead_letters


@pytest.mark.asyncio
@pytest.mark.parametrize("execution", ["thread", "process"])
async def test_executor_actors_reject_unsupported_actor_apis(execution: str) -> None:
    async with Syndicate(f"unsupported-api-{execution}") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=UnsupportedCreateActor, execution=execution, stateless=True)
        )
        await system.tell(actor, "go")

        deadline = asyncio.get_running_loop().time() + 5.0
        while not system.dead_letters and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)

        assert any("executor actors do not support create_actor" in letter.reason for letter in system.dead_letters)


@pytest.mark.asyncio
async def test_process_executor_shutdown_terminates_worker_process() -> None:
    async with Syndicate("process-shutdown") as system:
        actor = await system.create_actor_from_spec(
            ActorSpec(actor_class=StatelessEchoActor, execution="process", stateless=True)
        )
        _content, pid, _thread_id, _address = await system.ask(actor, "pid", timeout=5.0)

    assert not _pid_is_running(pid)


@pytest.mark.asyncio
async def test_process_troupe_requeues_work_when_worker_exits() -> None:
    async with Syndicate("process-troupe-requeue") as system:
        troupe = await system.create_actor(SingleWorkerProbeTroupe, worker_execution="process")
        pending = asyncio.create_task(system.ask(troupe, (5.0, "slow"), timeout=15.0))

        child_id = await _wait_for_child(system, troupe)
        await system.stop(ActorAddress(child_id))

        label, _worker_address = await pending

    assert label == "slow"


async def _wait_for_child(system: Syndicate, parent: ActorAddress):
    deadline = asyncio.get_running_loop().time() + 5.0
    while asyncio.get_running_loop().time() < deadline:
        children = system.backend.registry.children_of(parent.actor_id)
        if children:
            return children[0]
        await asyncio.sleep(0.05)
    raise AssertionError("timed out waiting for troupe worker")


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
