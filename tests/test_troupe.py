"""Tests for the Troupe base class (spark.contrib.troupe)."""

import asyncio

import pytest
import pytest_asyncio

from spark import ActorTimeout, Syndicate
from spark.contrib.troupe import (
    ActorPool,
    GetTroupeStatus,
    Troupe,
    TroupeStatus,
    UpdateTroupeSettings,
    _TroupeManager,
)


class Bee(Troupe):
    """One-shot worker: receives (delay, label), replies '<label> buzz'."""

    async def process(self, message):
        if isinstance(message.content, tuple) and message.sender is not None:
            delay, label = message.content
            if delay:
                await asyncio.sleep(delay)
            await self.tell(f"{label} buzz", message.sender)


class Colony(Troupe):
    """Multi-step worker: forwards to a Bee child and waits for the reply."""

    def __init__(self):
        super().__init__()
        self.hive = None
        self.askers: list = []

    async def process(self, message):
        content = message.content
        if isinstance(content, tuple):
            if self.hive is None:
                self.hive = await self.create_actor(Bee)
            self.askers.append(message.sender)
            await self.tell(content, self.hive)
            self.troupe_work_in_progress = True
        elif isinstance(content, str):
            target = self.askers.pop(0)
            await self.tell(content, target)
            self.troupe_work_in_progress = bool(self.askers)


@pytest_asyncio.fixture
async def system():
    async with Syndicate("async-troupe-test") as system:
        yield system


class TestSingleStepTroupe:
    @pytest.mark.asyncio
    async def test_simple_replies(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        items = [(0.0, "Fizz"), (0.0, "Honey"), (0.0, "Pollen"), (0.0, "Lily")]
        for it in items:
            await system.tell(it, bee)
        replies = []
        for _ in items:
            r = await system.receive(timeout=2.0)
            assert r is not None
            replies.append(r)
        assert sorted(replies) == ["Fizz buzz", "Honey buzz", "Lily buzz", "Pollen buzz"]


class TestMultiStepTroupe:
    @pytest.mark.asyncio
    async def test_colony_forwards_via_child(self, system: Syndicate) -> None:
        c = await system.create_actor(Colony)
        items = [(0.0, "Fizz"), (0.0, "Honey"), (0.0, "Pollen")]
        for it in items:
            await system.tell(it, c)
        replies = []
        for _ in items:
            replies.append(await system.receive(timeout=2.0))
        assert sorted(replies) == ["Fizz buzz", "Honey buzz", "Pollen buzz"]


class TestTroupeStatus:
    @pytest.mark.asyncio
    async def test_status_string_format(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        r = await system.ask("troupe:status?", bee, timeout=2.0)
        assert isinstance(r, str)
        assert "Idle=2," in r
        assert "Max=10," in r

    @pytest.mark.asyncio
    async def test_set_max_count_string(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        r = await system.ask("troupe:set_max_count=5", bee, timeout=2.0)
        assert r == "Set troupe max_count to 5"
        r = await system.ask("troupe:status?", bee, timeout=2.0)
        assert "Max=5," in r

    @pytest.mark.asyncio
    async def test_set_max_count_string_bad_value_records_dead_letter(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        with pytest.raises(ActorTimeout):
            await system.ask("troupe:set_max_count=nine", bee, timeout=2.0)
        assert len(system.dead_letters) >= 1

    @pytest.mark.asyncio
    async def test_set_idle_count_string(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        r = await system.ask("troupe:set_idle_count=3", bee, timeout=2.0)
        assert r == "Set troupe idle_count to 3"
        r = await system.ask("troupe:status?", bee, timeout=2.0)
        assert "Idle=3," in r

    @pytest.mark.asyncio
    async def test_update_troupe_settings_message(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        r = await system.ask(UpdateTroupeSettings(max_count=3, idle_count=1), bee, timeout=2.0)
        assert isinstance(r, UpdateTroupeSettings)
        assert r.max_count == 3
        assert r.idle_count == 1
        assert r.worker_execution == "inprocess"

    @pytest.mark.asyncio
    async def test_update_troupe_worker_execution_message(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee)
        r = await system.ask(UpdateTroupeSettings(worker_execution="thread"), bee, timeout=2.0)
        assert isinstance(r, UpdateTroupeSettings)
        assert r.worker_execution == "thread"
        status = await system.ask("troupe:status?", bee, timeout=2.0)
        assert "Execution=thread," in status

    @pytest.mark.asyncio
    async def test_constructor_kwargs_set_pool_sizes(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee, max_count=7, idle_count=3)
        r = await system.ask("troupe:status?", bee, timeout=2.0)
        assert "Max=7," in r
        assert "Idle=3," in r

    @pytest.mark.asyncio
    async def test_structured_status_message(self, system: Syndicate) -> None:
        bee = await system.create_actor(Bee, max_count=4, idle_count=1, max_pending=2)

        status = await system.ask(GetTroupeStatus(), bee, timeout=2.0)

        assert isinstance(status, TroupeStatus)
        assert status.max_count == 4
        assert status.idle_count == 1
        assert status.max_pending == 2


def test_actor_pool_alias_keeps_troupe_base() -> None:
    assert ActorPool is Troupe


class TestTroupeManagerBookkeeping:
    def test_new_work_returns_pending_when_at_max(self) -> None:
        from spark.actor.address import ActorAddress
        from spark.core.identity import ActorId, SyndicateId

        sys_id = SyndicateId()
        mgr = ActorAddress(ActorId(syndicate_id=sys_id))
        m = _TroupeManager(mgr, idle_count=1, max_count=1, worker_execution="inprocess")
        existing = ActorAddress(ActorId(syndicate_id=sys_id))
        m.workers.append(existing)
        sends = m.assign_work("payload-A", None)
        assert sends == []
        assert len(m.pending_work) == 1

    def test_pending_queue_can_be_bounded(self) -> None:
        from spark.actor.address import ActorAddress
        from spark.core.identity import ActorId, SyndicateId

        sys_id = SyndicateId()
        mgr = ActorAddress(ActorId(syndicate_id=sys_id))
        m = _TroupeManager(mgr, idle_count=1, max_count=1, worker_execution="inprocess", max_pending=1)
        existing = ActorAddress(ActorId(syndicate_id=sys_id))
        m.workers.append(existing)

        assert m.assign_work("payload-A", None) == []
        with pytest.raises(RuntimeError, match="pending queue full"):
            m.assign_work("payload-B", None)
