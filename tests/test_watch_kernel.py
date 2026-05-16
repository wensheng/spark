"""Unit tests for the async backend's fd-watching state machinery."""

import asyncio
import os
from typing import Any

import pytest

from spark import Actor, Syndicate, WatchMessage
from spark.core.message import Message


class WatchSetterActor(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Message] = []

    async def process(self, message: Message) -> None:
        self.calls.append(message)
        if isinstance(message.content, tuple) and len(message.content) == 2:
            read, write = message.content
            await self.watch(read=read, write=write)


@pytest.fixture
def pipe_pair():
    r, w = os.pipe()
    yield r, w
    for fd in (r, w):
        try:
            os.close(fd)
        except OSError:
            pass


class TestBackendSetWatch:
    @pytest.mark.asyncio
    async def test_set_watch_records_state(self, pipe_pair) -> None:
        r, _ = pipe_pair
        async with Syndicate("async-watch-state") as system:
            actor = await system.create_actor(WatchSetterActor)
            await system.tell(([r], []), actor)
            await asyncio.sleep(0)

            backend = system.backend
            assert backend._watches[actor.actor_id].read == {r}
            assert backend._watches[actor.actor_id].write == set()
            assert backend._fd_owner[r] == actor.actor_id

    @pytest.mark.asyncio
    async def test_set_watch_replaces(self, pipe_pair) -> None:
        r, w = pipe_pair
        async with Syndicate("async-watch-replace") as system:
            actor = await system.create_actor(WatchSetterActor)
            await system.tell(([r], []), actor)
            await asyncio.sleep(0)
            await system.tell(([w], []), actor)
            await asyncio.sleep(0)

            backend = system.backend
            assert backend._watches[actor.actor_id].read == {w}
            assert r not in backend._fd_owner
            assert backend._fd_owner[w] == actor.actor_id

    @pytest.mark.asyncio
    async def test_set_watch_empty_clears(self, pipe_pair) -> None:
        r, _ = pipe_pair
        async with Syndicate("async-watch-clear") as system:
            actor = await system.create_actor(WatchSetterActor)
            await system.tell(([r], []), actor)
            await asyncio.sleep(0)
            await system.tell(([], []), actor)
            await asyncio.sleep(0)

            backend = system.backend
            assert actor.actor_id not in backend._watches or not backend._watches[actor.actor_id].read
            assert r not in backend._fd_owner

    @pytest.mark.asyncio
    async def test_set_watch_collision_raises(self, pipe_pair) -> None:
        r, _ = pipe_pair
        async with Syndicate("async-watch-collision") as system:
            actor1 = await system.create_actor(WatchSetterActor)
            await system.tell(([r], []), actor1)
            await asyncio.sleep(0)

            actor2 = await system.create_actor(WatchSetterActor)
            with pytest.raises(ValueError, match="already watched"):
                system.backend.watch(actor2.actor_id, read=(r,), write=())
            assert system.backend._fd_owner[r] == actor1.actor_id

    @pytest.mark.asyncio
    async def test_stop_actor_clears_watch(self, pipe_pair) -> None:
        r, _ = pipe_pair
        async with Syndicate("async-watch-stop") as system:
            actor = await system.create_actor(WatchSetterActor)
            await system.tell(([r], []), actor)
            await asyncio.sleep(0)
            assert r in system.backend._fd_owner

            await system.stop(actor)

            assert r not in system.backend._fd_owner
            assert actor.actor_id not in system.backend._watches


async def backend_set_watch(system, actor_id, *, read=(), write=()):
    await system.backend.watch(actor_id, read=read, write=write)


class WatchObserver(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.received: list[Any] = []

    async def process(self, message: Message):
        self.received.append(message.content)


def _get_observer(system: Syndicate, addr: Any) -> WatchObserver:
    return system.backend.registry.get(addr.actor_id).actor  # type: ignore[return-value]


class TestBackendWatchDelivery:
    @pytest.mark.asyncio
    async def test_read_ready_delivers_watchmessage(self) -> None:
        r, w = os.pipe()
        try:
            async with Syndicate("async-watch-read") as system:
                addr = await system.create_actor(WatchObserver)
                observer = _get_observer(system, addr)
                system.backend.watch(addr.actor_id, read=(r,), write=())
                os.write(w, b"x")

                deadline = asyncio.get_event_loop().time() + 1.0
                while not observer.received and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.05)

                assert any(
                    isinstance(m, WatchMessage) and r in m.ready_read
                    for m in observer.received
                )
        finally:
            for fd in (r, w):
                try:
                    os.close(fd)
                except OSError:
                    pass

    @pytest.mark.asyncio
    async def test_write_ready_delivers_watchmessage(self) -> None:
        r, w = os.pipe()
        try:
            async with Syndicate("async-watch-write") as system:
                addr = await system.create_actor(WatchObserver)
                observer = _get_observer(system, addr)
                system.backend.watch(addr.actor_id, read=(), write=(w,))

                deadline = asyncio.get_event_loop().time() + 1.0
                while not observer.received and asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.05)

                assert any(
                    isinstance(m, WatchMessage) and w in m.ready_write
                    for m in observer.received
                )
        finally:
            for fd in (r, w):
                try:
                    os.close(fd)
                except OSError:
                    pass

    @pytest.mark.asyncio
    async def test_no_watchmessage_after_clear(self) -> None:
        r, w = os.pipe()
        try:
            async with Syndicate("async-watch-noclear") as system:
                addr = await system.create_actor(WatchObserver)
                observer = _get_observer(system, addr)
                system.backend.watch(addr.actor_id, read=(r,), write=())
                system.backend._clear_watch(addr.actor_id)
                os.write(w, b"x")

                await asyncio.sleep(0.1)
                assert not any(
                    isinstance(m, WatchMessage) for m in observer.received
                )
        finally:
            for fd in (r, w):
                try:
                    os.close(fd)
                except OSError:
                    pass
