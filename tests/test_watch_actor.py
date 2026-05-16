"""Tests for Actor.watch plumbing (async version)."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from spark import Actor, ActorAddress
from spark.core.exceptions import ActorNotStartedError
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message


@dataclass
class RecordingWatchContext:
    actor_id: ActorId
    address: ActorAddress
    syndicate_address: ActorAddress
    parent: ActorAddress | None = None
    watch_calls: list[tuple[tuple[int, ...], tuple[int, ...]]] = field(default_factory=list)

    def tell(self, message: Any, target: ActorAddress) -> None: ...
    async def tell_async(self, message: Any, target: ActorAddress) -> None: ...
    def ask(self, message: Any, target: ActorAddress, timeout: float | None = None) -> Any: ...
    async def ask_async(self, message: Any, target: ActorAddress, timeout: float | None = None) -> Any: ...
    def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        return ActorAddress(ActorId(self.actor_id.syndicate_id))

    def schedule_after(
        self,
        timeout: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None: ...
    async def persist_event(self, event: Any) -> None: ...
    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None: ...
    async def stop(self) -> None: ...
    async def syndicate_shutdown(self) -> None: ...

    async def watch(self, *, read=(), write=()) -> None:
        self.watch_calls.append((tuple(read), tuple(write)))


class WatchingActor(Actor):
    __spark_auto_start__ = False

    def __init__(self) -> None:
        super().__init__()
        self.received: list[Message] = []

    def process(self, message: Message) -> Any:
        self.received.append(message)
        return None


def _bound(actor: Actor, ctx: RecordingWatchContext) -> None:
    actor._bind_context(ctx)


class TestActorWatch:
    @pytest.mark.asyncio
    async def test_watch_unbound_raises(self) -> None:
        actor = WatchingActor()
        with pytest.raises(ActorNotStartedError):
            await actor.watch(read=[3])

    @pytest.mark.asyncio
    async def test_watch_delegates_to_context(self) -> None:
        sys_id = SyndicateId()
        actor_id = ActorId(sys_id)
        address = ActorAddress(actor_id)
        ctx = RecordingWatchContext(actor_id=actor_id, address=address, syndicate_address=address)
        actor = WatchingActor()
        _bound(actor, ctx)

        await actor.watch(read=[3, 4], write=[5])

        assert ctx.watch_calls == [((3, 4), (5,))]

    @pytest.mark.asyncio
    async def test_watch_empty_clears(self) -> None:
        sys_id = SyndicateId()
        actor_id = ActorId(sys_id)
        address = ActorAddress(actor_id)
        ctx = RecordingWatchContext(actor_id=actor_id, address=address, syndicate_address=address)
        actor = WatchingActor()
        _bound(actor, ctx)

        await actor.watch()

        assert ctx.watch_calls == [((), ())]
