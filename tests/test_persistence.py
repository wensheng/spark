"""Tests for opt-in persistent actors and hardened state backends."""

import asyncio

import pytest

from spark import ActorSpec, PersistentActor, SQLiteJournal, Syndicate
from spark.core.message import Message
from spark.core.messages import WakeupMessage
from spark.workflow.state_backend import JSONFileStateBackend, SQLiteStateBackend


class PersistentCounter(PersistentActor):
    __spark_auto_start__ = False

    def __init__(self, persistence_id: str) -> None:
        super().__init__(persistence_id)
        self.count = 0

    async def process(self, message: Message) -> int:
        if message.content == "snapshot":
            await self.save_snapshot()
            return self.count
        if isinstance(message.content, int):
            await self.persist({"delta": message.content})
        return self.count

    def apply_event(self, event: object) -> None:
        if isinstance(event, dict):
            self.count += int(event.get("delta", 0))

    def apply_snapshot(self, state: object) -> None:
        self.count = int(state)

    def snapshot_state(self) -> int:
        return self.count


class DurableTimerActor(PersistentActor):
    __spark_auto_start__ = False

    def __init__(self, persistence_id: str) -> None:
        super().__init__(persistence_id)
        self.fired = False

    async def process(self, message: Message) -> bool | str:
        if message.content == "schedule":
            self.schedule_after(0.2, "tick", durable=True, timer_id="tick")
            return "scheduled"
        if isinstance(message.content, WakeupMessage):
            await self.persist({"fired": True})
            return self.fired
        return self.fired

    def apply_event(self, event: object) -> None:
        if isinstance(event, dict) and event.get("fired") is True:
            self.fired = True


class TestPersistentActors:
    @pytest.mark.asyncio
    async def test_persistent_actor_replays_events_after_restart(self, tmp_path) -> None:
        journal_path = tmp_path / "spark-journal.sqlite"

        async with Syndicate("persistent-one", journal=SQLiteJournal(journal_path)) as system:
            counter = await system.create_actor_from_spec(ActorSpec(PersistentCounter, args=("counter",)))
            assert await system.ask(2, counter, timeout=1.0) == 2
            assert await system.ask(3, counter, timeout=1.0) == 5

        async with Syndicate("persistent-two", journal=SQLiteJournal(journal_path)) as system:
            counter = await system.create_actor_from_spec(ActorSpec(PersistentCounter, args=("counter",)))
            assert await system.ask(0, counter, timeout=1.0) == 5

    @pytest.mark.asyncio
    async def test_durable_timer_survives_system_restart(self, tmp_path) -> None:
        journal_path = tmp_path / "spark-timer.sqlite"

        async with Syndicate("timer-one", journal=SQLiteJournal(journal_path)) as system:
            timer = await system.create_actor_from_spec(ActorSpec(DurableTimerActor, args=("timer",)))
            assert await system.ask("schedule", timer, timeout=1.0) == "scheduled"

        async with Syndicate("timer-two", journal=SQLiteJournal(journal_path)) as system:
            timer = await system.create_actor_from_spec(ActorSpec(DurableTimerActor, args=("timer",)))
            await system.ask("status", timer, timeout=1.0)
            await asyncio.sleep(0.25)
            assert await system.ask("status", timer, timeout=1.0) is True

    @pytest.mark.asyncio
    async def test_persistent_actor_can_save_and_restore_snapshot(self, tmp_path) -> None:
        journal_path = tmp_path / "spark-snapshot.sqlite"

        async with Syndicate("snapshot-one", journal=SQLiteJournal(journal_path)) as system:
            counter = await system.create_actor_from_spec(ActorSpec(PersistentCounter, args=("snapshot",)))
            assert await system.ask(4, counter, timeout=1.0) == 4
            assert await system.ask("snapshot", counter, timeout=1.0) == 4

        async with Syndicate("snapshot-two", journal=SQLiteJournal(journal_path)) as system:
            counter = await system.create_actor_from_spec(ActorSpec(PersistentCounter, args=("snapshot",)))
            assert await system.ask(0, counter, timeout=1.0) == 4


class TestStateBackendHardening:
    def test_sqlite_backend_rejects_unsafe_table_names(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="table_name"):
            SQLiteStateBackend(tmp_path / "state.sqlite", table_name="graph_state;drop")

    @pytest.mark.asyncio
    async def test_blob_ids_are_sanitized(self, tmp_path) -> None:
        backend = JSONFileStateBackend(tmp_path / "state.json")
        await backend.initialize()

        with pytest.raises(ValueError, match="blob_id"):
            async with backend.open_blob_writer(blob_id="../bad"):
                pass

    @pytest.mark.asyncio
    async def test_file_state_writes_atomically(self, tmp_path) -> None:
        path = tmp_path / "state.json"
        backend = JSONFileStateBackend(path)
        await backend.initialize()

        await backend.set("answer", 42)

        assert path.exists()
        assert not list(tmp_path.glob(".state.json.*"))

    @pytest.mark.asyncio
    async def test_sqlite_backend_close_releases_connection(self, tmp_path) -> None:
        backend = SQLiteStateBackend(tmp_path / "state.sqlite")
        await backend.initialize()
        await backend.set("answer", 42)

        await backend.close()

        with pytest.raises(RuntimeError, match="not initialized"):
            await backend.set("again", 1)
