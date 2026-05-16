"""Async in-process actor runtime."""

from __future__ import annotations

import asyncio
import inspect
import logging
import multiprocessing as mp
import pickle
import queue
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn, cast
from uuid import uuid4

from ..actor.address import ActorAddress
from ..actor.base import Actor, ActorContext, _disable_actor_auto_start
from ..core.actor_spec import ActorExecution, ActorSpec
from ..core.exceptions import ActorNotFound, ActorTimeout, InvalidActorSpecError, MessageDeliveryError
from ..core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from ..core.mailbox_policy import MailboxPolicy
from ..core.messages import (
    ActorExited,
    ActorExitRequest,
    ActorStatus,
    CancellationRequest,
    ChildActorExited,
    ChildActorRestarted,
    CommonStatusFields,
    DeadLetter,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
    WakeupMessage,
    WatchMessage,
)
from ..persistence.journal import DurableTimer, Journal
from .diagnostics import ActorDiagnostics, RuntimeDiagnostics
from .events import RuntimeEvent
from .registry import ActorRecord, ActorRegistry
from .results import DeliveryResult

logger = logging.getLogger(__name__)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_control_payload(payload: Any) -> bool:
    return isinstance(
        payload,
        (
            ActorExited,
            ActorExitRequest,
            CancellationRequest,
            ChildActorExited,
            ChildActorRestarted,
            StatusRequest,
            WakeupMessage,
            WatchMessage,
        ),
    )


def _resolve_deadline(*, ttl: float | None = None, deadline: datetime | None = None) -> datetime | None:
    if ttl is not None and deadline is not None:
        raise ValueError("ttl and deadline are mutually exclusive")
    if ttl is None:
        return deadline
    if ttl < 0:
        raise ValueError("ttl must be >= 0")
    return datetime.now(tz=UTC) + timedelta(seconds=ttl)


@dataclass(slots=True)
class AsyncMailbox:
    """Two-lane async mailbox owned by one actor."""

    actor_id: ActorId
    policy: MailboxPolicy = field(default_factory=MailboxPolicy.unbounded)
    control_queue: asyncio.Queue[Envelope] = field(default_factory=asyncio.Queue)
    user_queue: asyncio.Queue[Envelope] = field(init=False)
    _available: asyncio.Event = field(init=False)
    _enqueued_at: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        max_size = 0 if self.policy.max_size is None else self.policy.max_size
        self.user_queue = asyncio.Queue(maxsize=max_size)
        self._available = asyncio.Event()

    async def enqueue(self, envelope: Envelope, *, control: bool = False) -> tuple[bool, str | None, Envelope | None]:
        if control:
            self.control_queue.put_nowait(envelope)
            self._enqueued_at[envelope.message_id] = asyncio.get_running_loop().time()
            self._available.set()
            return True, None, None

        if self.policy.max_size is None:
            self.user_queue.put_nowait(envelope)
            self._enqueued_at[envelope.message_id] = asyncio.get_running_loop().time()
            self._available.set()
            return True, None, None

        if not self.user_queue.full():
            if self.policy.overflow == "block":
                await self.user_queue.put(envelope)
            else:
                self.user_queue.put_nowait(envelope)
            self._enqueued_at[envelope.message_id] = asyncio.get_running_loop().time()
            self._available.set()
            return True, None, None

        reason = "mailbox full"
        if self.policy.overflow == "block":
            await self.user_queue.put(envelope)
            self._enqueued_at[envelope.message_id] = asyncio.get_running_loop().time()
            self._available.set()
            return True, None, None
        if self.policy.overflow == "drop_oldest":
            dropped = self.user_queue.get_nowait()
            self.user_queue.task_done()
            self._enqueued_at.pop(dropped.message_id, None)
            self.user_queue.put_nowait(envelope)
            self._enqueued_at[envelope.message_id] = asyncio.get_running_loop().time()
            self._available.set()
            return True, reason, dropped
        if self.policy.overflow in {"reject", "drop_newest", "dead_letter"}:
            return False, reason, envelope
        return False, reason, envelope

    async def get(self) -> tuple[Envelope, str]:
        while True:
            if not self.control_queue.empty():
                envelope = await self.control_queue.get()
                self._enqueued_at.pop(envelope.message_id, None)
                return envelope, "control"
            if not self.user_queue.empty():
                envelope = await self.user_queue.get()
                self._enqueued_at.pop(envelope.message_id, None)
                return envelope, "user"
            self._available.clear()
            await self._available.wait()

    def task_done(self, lane: str) -> None:
        if lane == "control":
            self.control_queue.task_done()
        else:
            self.user_queue.task_done()

    def size(self) -> int:
        return self.control_queue.qsize() + self.user_queue.qsize()

    def user_size(self) -> int:
        return self.user_queue.qsize()

    def pending(self) -> tuple[Envelope, ...]:
        return tuple(getattr(self.control_queue, "_queue", ())) + tuple(getattr(self.user_queue, "_queue", ()))

    def oldest_age(self, now: float) -> float | None:
        if not self._enqueued_at:
            return None
        return max(0.0, now - min(self._enqueued_at.values()))


@dataclass(slots=True)
class AsyncExternalInbox:
    """Async mailbox for code outside the actor registry."""

    actor_id: ActorId
    address: ActorAddress
    queue: asyncio.Queue[Envelope] = field(default_factory=asyncio.Queue)

    def enqueue(self, envelope: Envelope) -> None:
        self.queue.put_nowait(envelope)

    async def receive(self, timeout: float | None = None) -> Envelope | None:
        try:
            if timeout is None:
                return await self.queue.get()
            async with asyncio.timeout(timeout):
                return await self.queue.get()
        except TimeoutError:
            return None

    def has_pending(self) -> bool:
        return not self.queue.empty()


@dataclass(frozen=True, slots=True)
class _ScheduledWakeup:
    actor_id: ActorId
    wakeup: WakeupMessage
    persistence_id: str | None = None
    timer_id: str | None = None


@dataclass(slots=True)
class AsyncActorCell:
    """Runtime state owned by one async actor."""

    actor: Actor
    address: ActorAddress
    incarnation: ActorIncarnation
    parent_id: ActorId | None
    mailbox: AsyncMailbox
    spec: ActorSpec | None = None
    restart_timestamps: list[float] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    running: bool = False
    stopped: bool = False
    started_at: float = 0.0
    processed_count: int = 0
    failure_count: int = 0
    restart_count: int = 0
    processing_latency_total: float = 0.0


@dataclass(slots=True)
class ExecutorActorCell:
    """Runtime state for one stateless thread/process executor actor."""

    actor_class: type[Actor]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    execution: ActorExecution
    address: ActorAddress
    incarnation: ActorIncarnation
    parent_id: ActorId | None
    mailbox_depth: int = 0
    running: bool = False
    active: bool = True
    stopped: bool = False
    started_at: float = 0.0
    processed_count: int = 0
    failure_count: int = 0
    restart_count: int = 0
    processing_latency_total: float = 0.0
    input_queue: queue.Queue[Envelope | None] | Any | None = None
    result_queue: Any | None = None
    thread: threading.Thread | None = None
    process: Any | None = None
    reader_task: asyncio.Task[None] | None = None


RuntimeActorCell = AsyncActorCell | ExecutorActorCell


@dataclass(slots=True)
class _WatchState:
    read: set[int] = field(default_factory=set)
    write: set[int] = field(default_factory=set)


class _ExecutorActorProxy(Actor):
    """Registry placeholder for executor actors whose instance lives elsewhere."""

    __spark_auto_start__ = False

    def process(self, message: Any) -> None:
        return None


class _ExecutorActorContext(ActorContext):
    """Restricted actor context for stateless executor workers."""

    def __init__(
        self,
        actor_id: ActorId,
        address: ActorAddress,
        syndicate_address: ActorAddress,
        parent: ActorAddress | None,
    ) -> None:
        self.actor_id = actor_id
        self.address = address
        self.syndicate_address = syndicate_address
        self.parent = parent

    async def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        self._unsupported("ask")

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        self._unsupported("create_actor")

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        self._unsupported("create_actor_from_spec")

    def schedule_after(
        self,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        self._unsupported("schedule_after")

    async def persist_event(self, event: Any) -> None:
        self._unsupported("persist_event")

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        self._unsupported("save_snapshot")

    async def watch(self, *, read: Iterable[int] = (), write: Iterable[int] = ()) -> None:
        self._unsupported("watch")

    async def link(self, target: ActorAddress) -> None:
        self._unsupported("link")

    async def monitor(self, target: ActorAddress) -> None:
        self._unsupported("monitor")

    async def stop(self) -> None:
        self._unsupported("stop")

    async def syndicate_shutdown(self) -> None:
        self._unsupported("syndicate_shutdown")

    def _unsupported(self, api: str) -> NoReturn:
        raise RuntimeError(f"executor actors do not support {api}; use an in-process actor for full actor runtime APIs")


class _ThreadExecutorActorContext(_ExecutorActorContext):
    def __init__(
        self,
        actor_id: ActorId,
        address: ActorAddress,
        syndicate_address: ActorAddress,
        parent: ActorAddress | None,
        owner_loop: asyncio.AbstractEventLoop,
        deliver: Callable[[Envelope], Awaitable[DeliveryResult]],
        started: Callable[[ActorId], Awaitable[None]],
        finished: Callable[[ActorId], Awaitable[None]],
        failed: Callable[[ActorId, Envelope, str], Awaitable[None]],
    ) -> None:
        super().__init__(actor_id, address, syndicate_address, parent)
        self._owner_loop = owner_loop
        self._deliver = deliver
        self._started = started
        self._finished = finished
        self._failed = failed

    async def tell(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        await self._run_on_owner_loop(
            self._deliver(
                Envelope(
                    target=target.actor_id,
                    payload=message,
                    sender=self.actor_id,
                    deadline=_resolve_deadline(ttl=ttl, deadline=deadline),
                    headers={} if headers is None else headers,
                    trace_id=trace_id,
                )
            )
        )

    async def report_started(self) -> None:
        await self._run_on_owner_loop(self._started(self.actor_id))

    async def report_finished(self) -> None:
        await self._run_on_owner_loop(self._finished(self.actor_id))

    async def report_failed(self, envelope: Envelope, reason: str) -> None:
        asyncio.run_coroutine_threadsafe(
            cast(Coroutine[Any, Any, None], self._failed(self.actor_id, envelope, reason)),
            self._owner_loop,
        )
        await asyncio.sleep(0)

    async def _run_on_owner_loop(self, awaitable: Awaitable[Any]) -> Any:
        future: Any = asyncio.run_coroutine_threadsafe(
            cast(Coroutine[Any, Any, Any], awaitable),
            self._owner_loop,
        )
        return await asyncio.wrap_future(future)


class _ProcessExecutorActorContext(_ExecutorActorContext):
    def __init__(
        self,
        actor_id: ActorId,
        address: ActorAddress,
        syndicate_address: ActorAddress,
        parent: ActorAddress | None,
        result_queue: Any,
    ) -> None:
        super().__init__(actor_id, address, syndicate_address, parent)
        self._result_queue = result_queue

    async def tell(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        envelope = Envelope(
            target=target.actor_id,
            payload=message,
            sender=self.actor_id,
            deadline=_resolve_deadline(ttl=ttl, deadline=deadline),
            headers={} if headers is None else headers,
            trace_id=trace_id,
        )
        try:
            payload = pickle.dumps(envelope)
        except Exception as exc:
            raise RuntimeError(f"process executor reply is not picklable: {exc}") from exc
        self._result_queue.put(_ProcessEvent(kind="reply", envelope=payload))

    def report_started(self) -> None:
        self._result_queue.put(_ProcessEvent(kind="started"))

    def report_finished(self) -> None:
        self._result_queue.put(_ProcessEvent(kind="finished"))

    def report_failed(self, envelope: Envelope, reason: str) -> None:
        self._result_queue.put(_ProcessEvent(kind="failure", envelope=pickle.dumps(envelope), reason=reason))


@dataclass(frozen=True, slots=True)
class _ProcessEvent:
    kind: str
    envelope: bytes | None = None
    reason: str | None = None


def _thread_actor_main(
    actor_class: type[Actor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    actor_id: ActorId,
    parent_id: ActorId | None,
    syndicate_address: ActorAddress,
    input_queue: queue.Queue[Envelope | None],
    owner_loop: asyncio.AbstractEventLoop,
    deliver: Callable[[Envelope], Awaitable[DeliveryResult]],
    started: Callable[[ActorId], Awaitable[None]],
    finished: Callable[[ActorId], Awaitable[None]],
    failed: Callable[[ActorId, Envelope, str], Awaitable[None]],
) -> None:
    asyncio.run(
        _thread_actor_loop(
            actor_class,
            args,
            kwargs,
            actor_id,
            parent_id,
            syndicate_address,
            input_queue,
            owner_loop,
            deliver,
            started,
            finished,
            failed,
        )
    )


async def _thread_actor_loop(
    actor_class: type[Actor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    actor_id: ActorId,
    parent_id: ActorId | None,
    syndicate_address: ActorAddress,
    input_queue: queue.Queue[Envelope | None],
    owner_loop: asyncio.AbstractEventLoop,
    deliver: Callable[[Envelope], Awaitable[DeliveryResult]],
    started: Callable[[ActorId], Awaitable[None]],
    finished: Callable[[ActorId], Awaitable[None]],
    failed: Callable[[ActorId, Envelope, str], Awaitable[None]],
) -> None:
    address = ActorAddress(actor_id)
    parent = ActorAddress(parent_id) if parent_id is not None else None
    context = _ThreadExecutorActorContext(
        actor_id,
        address,
        syndicate_address,
        parent,
        owner_loop,
        deliver,
        started,
        finished,
        failed,
    )
    with _disable_actor_auto_start():
        actor = actor_class(*args, **kwargs)
    actor._bind_context(context)
    try:
        await _maybe_await(actor.pre_start())
        while True:
            envelope = await asyncio.to_thread(input_queue.get)
            if envelope is None:
                break
            await context.report_started()
            try:
                if isinstance(envelope.payload, ActorExitRequest):
                    break
                await actor.receive_envelope(envelope)
            except Exception as exc:
                await context.report_failed(envelope, f"handler failed: {exc}")
                break
            finally:
                await context.report_finished()
    finally:
        await _maybe_await(actor.post_stop())


def _process_actor_main(
    actor_class: type[Actor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    actor_id: ActorId,
    parent_id: ActorId | None,
    syndicate_address: ActorAddress,
    input_queue: Any,
    result_queue: Any,
) -> None:
    asyncio.run(
        _process_actor_loop(
            actor_class,
            args,
            kwargs,
            actor_id,
            parent_id,
            syndicate_address,
            input_queue,
            result_queue,
        )
    )


async def _process_actor_loop(
    actor_class: type[Actor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    actor_id: ActorId,
    parent_id: ActorId | None,
    syndicate_address: ActorAddress,
    input_queue: Any,
    result_queue: Any,
) -> None:
    address = ActorAddress(actor_id)
    parent = ActorAddress(parent_id) if parent_id is not None else None
    context = _ProcessExecutorActorContext(actor_id, address, syndicate_address, parent, result_queue)
    with _disable_actor_auto_start():
        actor = actor_class(*args, **kwargs)
    actor._bind_context(context)
    try:
        await _maybe_await(actor.pre_start())
        while True:
            payload = await asyncio.to_thread(input_queue.get)
            if payload is None:
                break
            envelope = pickle.loads(payload)
            context.report_started()
            try:
                if isinstance(envelope.payload, ActorExitRequest):
                    break
                await actor.receive_envelope(envelope)
            except Exception as exc:
                context.report_failed(envelope, f"handler failed: {exc}")
                break
            finally:
                context.report_finished()
    finally:
        await _maybe_await(actor.post_stop())
        result_queue.put(_ProcessEvent(kind="stopped"))


class AsyncActorContext(ActorContext):
    """Actor context backed by ``AsyncInProcessBackend``."""

    def __init__(
        self,
        backend: AsyncInProcessBackend,
        actor_id: ActorId,
        address: ActorAddress,
        syndicate_address: ActorAddress,
        parent: ActorAddress | None,
    ) -> None:
        self.backend = backend
        self.actor_id = actor_id
        self.address = address
        self.syndicate_address = syndicate_address
        self.parent = parent

    async def tell(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        await self.backend.tell(
            message,
            target,
            sender=self.actor_id,
            ttl=ttl,
            deadline=deadline,
            headers=headers,
            trace_id=trace_id,
        )

    async def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        return await self.backend.ask(
            message,
            target,
            timeout=timeout,
            sender=self.actor_id,
            ttl=ttl,
            deadline=deadline,
        )

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        return await self.backend.create_actor(actor_class, *args, parent_id=self.actor_id, **kwargs)

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        return await self.backend.create_actor_from_spec(spec, parent_id=self.actor_id)

    def schedule_after(
        self,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        self.backend.schedule_after(self.actor_id, delay, payload, durable=durable, timer_id=timer_id)

    async def persist_event(self, event: Any) -> None:
        await self.backend.persist_event(self.actor_id, event)

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        await self.backend.save_snapshot(self.actor_id, state, sequence=sequence)

    async def watch(self, *, read: Iterable[int] = (), write: Iterable[int] = ()) -> None:
        self.backend.watch(self.actor_id, read=tuple(read), write=tuple(write))

    async def link(self, target: ActorAddress) -> None:
        await self.backend.link(self.address, target)

    async def monitor(self, target: ActorAddress) -> None:
        await self.backend.monitor(self.address, target)

    async def stop(self) -> None:
        await self.backend.stop_actor(self.actor_id)

    async def syndicate_shutdown(self) -> None:
        await self.backend.shutdown()


class AsyncExternalEndpoint:
    """Isolated async external endpoint for application tasks."""

    def __init__(self, backend: AsyncInProcessBackend, inbox: AsyncExternalInbox) -> None:
        self._backend = backend
        self._inbox = inbox

    @property
    def address(self) -> ActorAddress:
        return self._inbox.address

    async def tell(
        self,
        message: Any,
        target: ActorAddress,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> None:
        await self._backend.tell(message, target, sender=self._inbox.actor_id, ttl=ttl, deadline=deadline)

    async def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = 5.0,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        await self.tell(message, target, ttl=ttl, deadline=deadline)
        envelope = await self._inbox.receive(timeout)
        if envelope is None:
            raise ActorTimeout("ask", 5.0 if timeout is None else timeout)
        return envelope.payload

    async def receive(self, timeout: float | None = None) -> Any:
        envelope = await self._inbox.receive(timeout)
        return None if envelope is None else envelope.payload

    async def listen(self) -> AsyncIterator[Any]:
        while True:
            yield await self.receive()

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        return await self._backend.create_actor(actor_class, *args, **kwargs)

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        return await self._backend.create_actor_from_spec(spec)

    async def monitor(self, target: ActorAddress) -> None:
        await self._backend.monitor(self.address, target)


class AsyncInProcessBackend:
    """Task-owned async actor runtime."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        *,
        default_execution: ActorExecution = "inprocess",
        backend_type: str = "async-inprocess",
        dead_letter_capacity: int = 1024,
        event_capacity: int = 2048,
        journal: Journal | None = None,
    ) -> None:
        if dead_letter_capacity <= 0:
            raise ValueError("dead_letter_capacity must be positive")
        if event_capacity <= 0:
            raise ValueError("event_capacity must be positive")
        self.syndicate_id = syndicate_id
        self.default_execution = default_execution
        self.backend_type = backend_type
        self.registry = ActorRegistry()
        self._cells: dict[ActorId, RuntimeActorCell] = {}
        self._external: dict[ActorId, AsyncExternalInbox] = {}
        self._dead_letters: deque[DeadLetter] = deque(maxlen=dead_letter_capacity)
        self._late_replies: deque[DeadLetter] = deque(maxlen=dead_letter_capacity)
        self._lifecycle_failures: deque[DeadLetter] = deque(maxlen=dead_letter_capacity)
        self._events: deque[RuntimeEvent] = deque(maxlen=event_capacity)
        self._closed_external: dict[ActorId, str] = {}
        self._remote_sender: Callable[[Envelope], Awaitable[DeliveryResult]] | None = None
        self._journal = journal
        self._shutdown = False
        self._task_group: asyncio.TaskGroup | None = None
        self._watches: dict[ActorId, _WatchState] = {}
        self._fd_owner: dict[int, ActorId] = {}
        self._wakeups: dict[asyncio.TimerHandle, _ScheduledWakeup] = {}
        self._links: dict[ActorId, set[ActorId]] = {}
        self._monitors: dict[ActorId, set[ActorId]] = {}
        self._inbox = self._create_external_inbox()
        self.address = self._inbox.address
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started_at: float = 0.0
        self._no_active_callback: Callable[[], Any] | None = None
        self._no_active_check_handle: asyncio.Handle | None = None

    async def start(self) -> None:
        if self._task_group is not None:
            return
        self._loop = asyncio.get_running_loop()
        if self._journal is not None:
            initialize = getattr(self._journal, "initialize", None)
            if initialize is not None:
                await initialize()
        if self._started_at == 0.0:
            self._started_at = self._loop.time()
        self._task_group = asyncio.TaskGroup()
        await self._task_group.__aenter__()

    def set_remote_sender(
        self,
        sender: Callable[[Envelope], Awaitable[DeliveryResult]] | None,
    ) -> None:
        self._remote_sender = sender

    def set_no_active_callback(self, callback: Callable[[], Any] | None) -> None:
        """Install a callback fired when no running actor is active."""
        self._no_active_callback = callback

    async def create_actor(
        self,
        actor_class: type[Actor],
        *args: Any,
        parent_id: ActorId | None = None,
        **kwargs: Any,
    ) -> ActorAddress:
        return await self.create_actor_from_spec(
            ActorSpec(actor_class=actor_class, args=args, kwargs=kwargs),
            parent_id=parent_id,
        )

    async def create_actor_from_spec(
        self,
        spec: ActorSpec,
        parent_id: ActorId | None = None,
    ) -> ActorAddress:
        actor_type = self._validate_actor_spec(spec)
        execution = self._resolve_execution(spec.execution)
        if execution == "inprocess":
            return await self._create_inprocess_actor_from_spec(actor_type, spec, parent_id=parent_id)
        return await self._create_executor_actor_from_spec(actor_type, spec, execution, parent_id=parent_id)

    async def _create_inprocess_actor_from_spec(
        self,
        actor_type: type[Actor],
        spec: ActorSpec,
        parent_id: ActorId | None = None,
    ) -> ActorAddress:
        with _disable_actor_auto_start():
            actor = actor_type(*spec.args, **dict(spec.kwargs))
        return await self.start_actor(actor, parent_id=parent_id, _spec=spec)

    async def _create_executor_actor_from_spec(
        self,
        actor_type: type[Actor],
        spec: ActorSpec,
        execution: ActorExecution,
        parent_id: ActorId | None = None,
    ) -> ActorAddress:
        if execution not in {"thread", "process"}:
            raise InvalidActorSpecError(f"unsupported actor execution mode {execution!r}")
        if not spec.stateless:
            raise InvalidActorSpecError(f"actor execution={execution!r} requires ActorSpec.stateless=True")
        await self.start()
        actor_id = ActorId(syndicate_id=self.syndicate_id)
        address = ActorAddress(actor_id)
        cell = ExecutorActorCell(
            actor_class=actor_type,
            args=tuple(spec.args),
            kwargs=dict(spec.kwargs),
            execution=execution,
            address=address,
            incarnation=ActorIncarnation(actor_id),
            parent_id=parent_id,
        )
        proxy = _ExecutorActorProxy()
        self.registry.register(
            actor_id,
            ActorRecord(actor=proxy, address=address, incarnation=cell.incarnation, parent_id=parent_id),
        )
        self._cells[actor_id] = cell
        try:
            if execution == "thread":
                self._start_thread_executor(cell)
            else:
                self._start_process_executor(cell)
        except Exception:
            with suppress(ActorNotFound):
                self.registry.remove(actor_id)
            self._cells.pop(actor_id, None)
            raise
        cell.started_at = asyncio.get_running_loop().time()
        self._record_event("actor_started", actor_id=actor_id, execution=execution)
        self._schedule_no_active_check()
        return address

    async def start_actor(
        self,
        actor: Actor,
        parent_id: ActorId | None = None,
        *,
        _spec: ActorSpec | None = None,
    ) -> ActorAddress:
        await self.start()
        if not isinstance(actor, Actor):
            raise InvalidActorSpecError(f"actor must be an Actor instance, got {actor!r}")
        actor_id = ActorId(syndicate_id=self.syndicate_id)
        address = ActorAddress(actor_id)
        parent_address = ActorAddress(parent_id) if parent_id is not None else None
        mailbox_policy = _spec.mailbox_policy if _spec is not None else MailboxPolicy.unbounded()
        mailbox = AsyncMailbox(actor_id, policy=mailbox_policy)
        context = AsyncActorContext(self, actor_id, address, self.address, parent_address)
        actor._bind_context(context)
        cell = AsyncActorCell(
            actor=actor,
            address=address,
            incarnation=ActorIncarnation(actor_id),
            parent_id=parent_id,
            mailbox=mailbox,
            spec=_spec,
        )
        actor._set_activity_change_callback(self._schedule_no_active_check)
        self.registry.register(
            actor_id,
            ActorRecord(actor=actor, address=address, incarnation=cell.incarnation, parent_id=parent_id),
        )
        self._cells[actor_id] = cell
        try:
            await self._recover_persistent_actor(cell)
            await _maybe_await(actor.pre_start())
        except Exception as exc:
            cell.stopped = True
            actor._set_activity_change_callback(None)
            with suppress(ActorNotFound):
                self.registry.remove(actor_id)
            self._cells.pop(actor_id, None)
            self._record_lifecycle_failure(actor_id, f"pre_start failed: {exc}")
            raise

        assert self._task_group is not None
        cell.task = self._task_group.create_task(self._actor_loop(actor_id), name=f"spark-actor-{actor_id.actor_id}")
        cell.started_at = asyncio.get_running_loop().time()
        self._record_event("actor_started", actor_id=actor_id, execution="inprocess")
        self._schedule_no_active_check()
        return address

    async def tell(
        self,
        message: Any,
        target: ActorAddress,
        sender: ActorId | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> DeliveryResult:
        return await self.deliver(
            Envelope(
                target=target.actor_id,
                payload=message,
                sender=sender or self._inbox.actor_id,
                deadline=_resolve_deadline(ttl=ttl, deadline=deadline),
                headers={} if headers is None else headers,
                trace_id=trace_id,
            )
        )

    async def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        sender: ActorId | None = None,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        ask_timeout = timeout
        inbox = self._create_external_inbox()
        envelope = Envelope(
            target=target.actor_id,
            payload=message,
            sender=inbox.actor_id,
            deadline=_resolve_deadline(ttl=ttl, deadline=deadline),
        )
        completed = False
        try:
            result = await self.deliver(envelope)
            if not result.success:
                raise MessageDeliveryError(target, result.reason or "delivery failed")
            reply = await inbox.receive(ask_timeout)
            if reply is None:
                self._close_external_inbox(inbox.actor_id, "ask timed out")
                self._record_event("ask_timed_out", actor_id=target.actor_id, message_id=envelope.message_id)
                raise ActorTimeout("ask", 5.0 if ask_timeout is None else ask_timeout)
            completed = True
            return reply.payload
        except asyncio.CancelledError:
            self._close_external_inbox(inbox.actor_id, "ask cancelled")
            self._record_event("ask_cancelled", actor_id=target.actor_id, message_id=envelope.message_id)
            await self.deliver(
                Envelope(
                    target=target.actor_id,
                    payload=CancellationRequest(correlation_id=envelope.correlation_id or envelope.message_id),
                    sender=inbox.actor_id,
                )
            )
            raise
        finally:
            self._close_external_inbox(inbox.actor_id, "ask completed" if completed else "ask closed")

    async def ask_stream(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        sender: ActorId | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        max_replies: int | None = None,
    ) -> AsyncIterator[Any]:
        inbox = self._create_external_inbox()
        envelope = Envelope(
            target=target.actor_id,
            payload=message,
            sender=inbox.actor_id,
            deadline=_resolve_deadline(ttl=ttl, deadline=deadline),
        )
        try:
            result = await self.deliver(envelope)
            if not result.success:
                raise MessageDeliveryError(target, result.reason or "delivery failed")
            yielded = 0
            while max_replies is None or yielded < max_replies:
                reply = await inbox.receive(timeout)
                if reply is None:
                    break
                yielded += 1
                yield reply.payload
        finally:
            self._close_external_inbox(inbox.actor_id, "ask stream closed")

    async def receive(self, timeout: float | None = None) -> Any:
        envelope = await self._inbox.receive(timeout)
        return None if envelope is None else envelope.payload

    async def listen(self) -> AsyncIterator[Any]:
        while True:
            yield await self.receive()

    def create_endpoint(self) -> AsyncExternalEndpoint:
        return AsyncExternalEndpoint(self, self._create_external_inbox())

    def remove_endpoint(self, endpoint: AsyncExternalEndpoint) -> None:
        self._external.pop(endpoint.address.actor_id, None)

    async def deliver_envelope(self, envelope: Envelope) -> DeliveryResult:
        return await self.deliver(envelope)

    async def deliver(self, envelope: Envelope) -> DeliveryResult:
        if self._shutdown:
            self._record_dead_letter(envelope, "system is shut down")
            return DeliveryResult(success=False, reason="system is shut down")

        if envelope.target.syndicate_id != self.syndicate_id:
            if self._remote_sender is None:
                self._record_dead_letter(envelope, "remote route not found")
                return DeliveryResult(success=False, reason="remote route not found")
            result = await self._remote_sender(envelope)
            if not result.success:
                self._record_dead_letter(envelope, result.reason or "remote delivery failed")
            return result

        if envelope.is_expired:
            self._record_dead_letter(envelope, "message expired")
            return DeliveryResult(success=False, reason="message expired")

        external = self._external.get(envelope.target)
        if external is not None:
            if isinstance(envelope.payload, StatusRequest):
                await self._reply_system_status(envelope.sender)
                return DeliveryResult(success=True)
            external.enqueue(envelope)
            return DeliveryResult(success=True)
        if envelope.target in self._closed_external:
            reason = f"late reply: {self._closed_external[envelope.target]}"
            self._record_late_reply(envelope, reason)
            return DeliveryResult(success=False, reason=reason)

        cell = self._cells.get(envelope.target)
        if cell is None or cell.stopped or not self.registry.exists(envelope.target):
            self._record_dead_letter(envelope, "target not found")
            return DeliveryResult(success=False, reason="target not found")
        if envelope.target_incarnation is not None and envelope.target_incarnation != cell.incarnation:
            reason = "stale actor incarnation"
            self._record_dead_letter(envelope, reason)
            return DeliveryResult(success=False, reason=reason)
        if isinstance(cell, ExecutorActorCell):
            return await self._deliver_executor(cell, envelope)
        success, enqueue_reason, dropped = await cell.mailbox.enqueue(
            envelope, control=_is_control_payload(envelope.payload)
        )
        if dropped is not None:
            self._record_event(
                "mailbox_overflow",
                actor_id=envelope.target,
                message_id=dropped.message_id,
                reason=enqueue_reason,
            )
            self._record_dead_letter(dropped, enqueue_reason or "mailbox overflow")
        if not success:
            self._record_event(
                "mailbox_overflow",
                actor_id=envelope.target,
                message_id=envelope.message_id,
                reason=enqueue_reason,
            )
            return DeliveryResult(success=False, reason=enqueue_reason)
        self._record_event("message_enqueued", actor_id=envelope.target, message_id=envelope.message_id)
        self._schedule_no_active_check()
        return DeliveryResult(success=True)

    async def _deliver_executor(self, cell: ExecutorActorCell, envelope: Envelope) -> DeliveryResult:
        if isinstance(envelope.payload, StatusRequest):
            await self._reply_actor_status(cell, envelope.sender)
            return DeliveryResult(success=True)
        if isinstance(envelope.payload, ActorExitRequest):
            await self.stop_actor(cell.address.actor_id, reason=envelope.payload.reason)
            return DeliveryResult(success=True)
        try:
            if cell.execution == "thread":
                assert isinstance(cell.input_queue, queue.Queue)
                cell.input_queue.put_nowait(envelope)
            elif cell.execution == "process":
                if cell.input_queue is None:
                    raise RuntimeError("process executor is not started")
                process_queue: Any = cell.input_queue
                process_queue.put(pickle.dumps(envelope))
            else:
                raise RuntimeError(f"unsupported executor mode {cell.execution!r}")
        except Exception as exc:
            reason = f"executor delivery failed: {exc}"
            self._record_dead_letter(envelope, reason)
            return DeliveryResult(success=False, reason=reason)
        cell.mailbox_depth += 1
        self._record_event("message_enqueued", actor_id=envelope.target, message_id=envelope.message_id)
        self._schedule_no_active_check()
        return DeliveryResult(success=True)

    def schedule_after(
        self,
        actor_id: ActorId,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        persistence_id = self._actor_persistence_id(actor_id) if durable else None
        if durable and persistence_id is None:
            raise RuntimeError("durable timers require a persistent actor and configured journal")
        if durable and self._journal is None:
            raise RuntimeError("durable timers require a configured journal")
        due_time = time.time() + max(0.0, delay)
        resolved_timer_id = timer_id or uuid4().hex
        if durable:
            assert persistence_id is not None
            self._spawn_runtime_task(
                self._journal_upsert_timer(DurableTimer(persistence_id, resolved_timer_id, due_time, payload)),
                name=f"spark-durable-timer-save-{actor_id.actor_id}",
            )
        self._schedule_wakeup_handle(
            actor_id,
            delay,
            payload,
            persistence_id=persistence_id,
            timer_id=resolved_timer_id if durable else None,
        )

    def _schedule_wakeup_handle(
        self,
        actor_id: ActorId,
        delay: float,
        payload: Any = None,
        *,
        persistence_id: str | None = None,
        timer_id: str | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        wakeup = WakeupMessage(delay=delay, payload=payload)

        def fire() -> None:
            self._spawn_runtime_task(
                self._fire_wakeup(handle),
                name=f"spark-wakeup-{actor_id.actor_id}",
            )

        handle = loop.call_later(max(0.0, delay), fire)
        self._wakeups[handle] = _ScheduledWakeup(
            actor_id=actor_id,
            wakeup=wakeup,
            persistence_id=persistence_id,
            timer_id=timer_id,
        )

    async def _fire_wakeup(self, handle: asyncio.TimerHandle) -> None:
        scheduled = self._wakeups.pop(handle, None)
        if scheduled is None:
            return
        if scheduled.persistence_id is not None and scheduled.timer_id is not None and self._journal is not None:
            await self._journal.delete_timer(scheduled.persistence_id, scheduled.timer_id)
        await self.deliver(Envelope(target=scheduled.actor_id, payload=scheduled.wakeup))

    async def _journal_upsert_timer(self, timer: DurableTimer) -> None:
        if self._journal is None:
            return
        await self._journal.upsert_timer(timer)

    async def persist_event(self, actor_id: ActorId, event: Any) -> int:
        if self._journal is None:
            raise RuntimeError("persistent actors require a configured journal")
        persistence_id = self._actor_persistence_id(actor_id)
        if persistence_id is None:
            raise RuntimeError("actor does not declare a persistence_id")
        entry = await self._journal.append_event(persistence_id, event)
        self._record_event("journal_event_appended", actor_id=actor_id, message_id=None, sequence=str(entry.sequence))
        return entry.sequence

    async def save_snapshot(self, actor_id: ActorId, state: Any, *, sequence: int | None = None) -> None:
        if self._journal is None:
            raise RuntimeError("persistent actors require a configured journal")
        persistence_id = self._actor_persistence_id(actor_id)
        if persistence_id is None:
            raise RuntimeError("actor does not declare a persistence_id")
        resolved_sequence = sequence
        if resolved_sequence is None:
            events = await self._journal.read_events(persistence_id)
            resolved_sequence = events[-1].sequence if events else 0
        await self._journal.save_snapshot(persistence_id, resolved_sequence, state)
        self._record_event("journal_snapshot_saved", actor_id=actor_id, sequence=str(resolved_sequence))

    def _actor_persistence_id(self, actor_id: ActorId) -> str | None:
        cell = self._cells.get(actor_id)
        if not isinstance(cell, AsyncActorCell):
            return None
        value = getattr(cell.actor, "persistence_id", None)
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    async def _recover_persistent_actor(self, cell: AsyncActorCell) -> None:
        if self._journal is None:
            return
        persistence_id = self._actor_persistence_id(cell.address.actor_id)
        if persistence_id is None:
            return
        snapshot = await self._journal.load_snapshot(persistence_id)
        after_sequence = 0
        if snapshot is not None:
            apply_snapshot = getattr(cell.actor, "apply_snapshot", None)
            if apply_snapshot is not None:
                await _maybe_await(apply_snapshot(snapshot.state))
            after_sequence = snapshot.sequence
        apply_event = getattr(cell.actor, "apply_event", None)
        if apply_event is not None:
            for entry in await self._journal.read_events(persistence_id, after_sequence=after_sequence):
                await _maybe_await(apply_event(entry.event))
        on_recovered = getattr(cell.actor, "on_recovered", None)
        if on_recovered is not None:
            await _maybe_await(on_recovered())
        await self._restore_durable_timers(cell.address.actor_id, persistence_id)
        self._record_event("journal_replayed", actor_id=cell.address.actor_id, persistence_id=persistence_id)

    async def _restore_durable_timers(self, actor_id: ActorId, persistence_id: str) -> None:
        if self._journal is None:
            return
        for timer in await self._journal.list_timers(persistence_id):
            self._schedule_wakeup_handle(
                actor_id,
                max(0.0, timer.due_time - time.time()),
                timer.payload,
                persistence_id=timer.persistence_id,
                timer_id=timer.timer_id,
            )

    def watch(
        self,
        actor_id: ActorId,
        *,
        read: tuple[int, ...] = (),
        write: tuple[int, ...] = (),
    ) -> None:
        loop = asyncio.get_running_loop()
        new_read = set(read)
        new_write = set(write)
        all_new = new_read | new_write
        prior = self._watches.get(actor_id, _WatchState())
        prior_read = set(prior.read)
        prior_write = set(prior.write)

        for fd in all_new:
            owner = self._fd_owner.get(fd)
            if owner is not None and owner != actor_id:
                raise ValueError(f"fd {fd} already watched by actor {owner}")

        self._clear_watch(actor_id)
        installed: list[tuple[str, int]] = []
        try:
            for fd in new_read:
                loop.add_reader(fd, self._fd_ready, actor_id, fd, "read")
                installed.append(("read", fd))
            for fd in new_write:
                loop.add_writer(fd, self._fd_ready, actor_id, fd, "write")
                installed.append(("write", fd))
        except Exception:
            for mode, fd in installed:
                if mode == "read":
                    loop.remove_reader(fd)
                else:
                    loop.remove_writer(fd)
            self._restore_watch(actor_id, prior_read, prior_write)
            raise

        if all_new:
            self._watches[actor_id] = _WatchState(read=new_read, write=new_write)
            for fd in all_new:
                self._fd_owner[fd] = actor_id

    async def link(self, left: ActorAddress, right: ActorAddress) -> None:
        """Link two local actors for bidirectional fate sharing."""
        self._require_local_actor(left)
        self._require_local_actor(right)
        if left.actor_id == right.actor_id:
            return
        self._links.setdefault(left.actor_id, set()).add(right.actor_id)
        self._links.setdefault(right.actor_id, set()).add(left.actor_id)

    async def monitor(self, watcher: ActorAddress, target: ActorAddress) -> None:
        """Notify ``watcher`` when ``target`` exits."""
        self._require_local_deliverable(watcher, role="monitor watcher")
        self._require_local_actor(target)
        if watcher.actor_id == target.actor_id:
            return
        self._monitors.setdefault(target.actor_id, set()).add(watcher.actor_id)

    def _start_thread_executor(self, cell: ExecutorActorCell) -> None:
        loop = self._loop
        if loop is None:
            raise RuntimeError("backend event loop is not running")
        input_queue: queue.Queue[Envelope | None] = queue.Queue()
        cell.input_queue = input_queue
        thread = threading.Thread(
            target=_thread_actor_main,
            args=(
                cell.actor_class,
                cell.args,
                cell.kwargs,
                cell.address.actor_id,
                cell.parent_id,
                self.address,
                input_queue,
                loop,
                self.deliver,
                self._executor_started,
                self._executor_finished,
                self._executor_failed,
            ),
            name=f"spark-executor-thread-{cell.address.actor_id.actor_id[:8]}",
            daemon=True,
        )
        cell.thread = thread
        thread.start()

    def _start_process_executor(self, cell: ExecutorActorCell) -> None:
        ctx = mp.get_context("spawn")
        input_queue = ctx.Queue()
        result_queue = ctx.Queue()
        process = ctx.Process(
            target=_process_actor_main,
            args=(
                cell.actor_class,
                cell.args,
                cell.kwargs,
                cell.address.actor_id,
                cell.parent_id,
                self.address,
                input_queue,
                result_queue,
            ),
            name=f"spark-executor-process-{cell.address.actor_id.actor_id[:8]}",
            daemon=True,
        )
        cell.input_queue = input_queue
        cell.result_queue = result_queue
        process.start()
        cell.process = process
        assert self._task_group is not None
        cell.reader_task = self._task_group.create_task(
            self._process_result_loop(cell.address.actor_id),
            name=f"spark-executor-process-reader-{cell.address.actor_id.actor_id}",
        )

    async def _process_result_loop(self, actor_id: ActorId) -> None:
        try:
            while not self._shutdown:
                cell = self._cells.get(actor_id)
                if not isinstance(cell, ExecutorActorCell) or cell.stopped or cell.result_queue is None:
                    return
                event = await asyncio.to_thread(cell.result_queue.get)
                if not isinstance(event, _ProcessEvent):
                    continue
                if event.kind == "reply" and event.envelope is not None:
                    await self.deliver(pickle.loads(event.envelope))
                elif event.kind == "failure" and event.envelope is not None:
                    await self._executor_failed(
                        actor_id,
                        pickle.loads(event.envelope),
                        event.reason or "handler failed",
                    )
                elif event.kind == "started":
                    await self._executor_started(actor_id)
                elif event.kind == "finished":
                    await self._executor_finished(actor_id)
                elif event.kind == "stopped":
                    return
        except asyncio.CancelledError:
            pass

    async def _executor_started(self, actor_id: ActorId) -> None:
        cell = self._cells.get(actor_id)
        if not isinstance(cell, ExecutorActorCell) or cell.stopped:
            return
        cell.running = True
        cell.mailbox_depth = max(0, cell.mailbox_depth - 1)
        self._record_event("message_dequeued", actor_id=actor_id)
        self._schedule_no_active_check()

    async def _executor_finished(self, actor_id: ActorId) -> None:
        cell = self._cells.get(actor_id)
        if not isinstance(cell, ExecutorActorCell) or cell.stopped:
            return
        cell.running = False
        cell.processed_count += 1
        self._record_event("message_processed", actor_id=actor_id)
        self._schedule_no_active_check()

    async def _executor_failed(self, actor_id: ActorId, envelope: Envelope, reason: str) -> None:
        if actor_id not in self._cells:
            return
        cell = self._cells.get(actor_id)
        if isinstance(cell, ExecutorActorCell):
            cell.failure_count += 1
        self._record_dead_letter(envelope, reason)
        await self.stop_actor(actor_id, reason="handler failed")

    async def stop(self, target: ActorAddress) -> None:
        await self.stop_actor(target.actor_id)

    async def stop_actor(
        self,
        actor_id: ActorId,
        reason: str = "actor stopped",
        exit_code: int = 0,
        notify_parent: bool = True,
        notify_links: bool = True,
    ) -> None:
        cell = self._cells.get(actor_id)
        if cell is None or cell.stopped:
            return
        linked_actor_ids, monitor_actor_ids = self._remove_actor_relationships(actor_id)
        for child_id in list(self.registry.children_of(actor_id)):
            await self.stop_actor(child_id, reason="parent stopped", notify_parent=False)

        if isinstance(cell, ExecutorActorCell):
            await self._stop_executor_actor(cell, reason=reason)
            with suppress(ActorNotFound):
                self.registry.remove(actor_id)
            self._cells.pop(actor_id, None)
            self._schedule_no_active_check()
            self._record_event("actor_stopped", actor_id=actor_id, reason=reason)
            if notify_parent and cell.parent_id is not None:
                await self._notify_child_exited(cell, reason, exit_code)
            await self._notify_monitors_exited(monitor_actor_ids, cell, reason, exit_code)
            if notify_links:
                await self._stop_linked_actors(linked_actor_ids, reason, exit_code)
            return

        cell.stopped = True
        self._clear_watch(actor_id)
        for handle, scheduled in list(self._wakeups.items()):
            if scheduled.actor_id == actor_id:
                handle.cancel()
                self._wakeups.pop(handle, None)

        current = asyncio.current_task()
        if cell.task is not None and cell.task is not current:
            cell.task.cancel()
            with suppress(asyncio.CancelledError):
                await cell.task

        with suppress(ActorNotFound):
            self.registry.remove(actor_id)
        self._cells.pop(actor_id, None)
        try:
            await _maybe_await(cell.actor.post_stop())
        except Exception as exc:
            self._record_lifecycle_failure(cell.address.actor_id, f"post_stop failed: {exc}")
        finally:
            cell.actor._set_activity_change_callback(None)
            self._schedule_no_active_check()

        if notify_parent and cell.parent_id is not None:
            await self._notify_child_exited(cell, reason, exit_code)
        await self._notify_monitors_exited(monitor_actor_ids, cell, reason, exit_code)
        if notify_links:
            await self._stop_linked_actors(linked_actor_ids, reason, exit_code)
        self._record_event("actor_stopped", actor_id=actor_id, reason=reason)

    async def _stop_executor_actor(self, cell: ExecutorActorCell, reason: str) -> None:
        cell.stopped = True
        cell.active = False
        cell.running = False
        if cell.execution == "thread":
            if isinstance(cell.input_queue, queue.Queue):
                cell.input_queue.put_nowait(None)
            if cell.thread is not None and cell.thread.is_alive():
                await asyncio.to_thread(cell.thread.join, 2.0)
        elif cell.execution == "process":
            if cell.input_queue is not None:
                with suppress(Exception):
                    cell.input_queue.put(None)
            process = cell.process
            current = asyncio.current_task()
            if cell.reader_task is not None and cell.reader_task is not current:
                try:
                    await asyncio.wait_for(cell.reader_task, timeout=2.0)
                except (TimeoutError, asyncio.CancelledError):
                    cell.reader_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await cell.reader_task
            if process is not None and process.is_alive():
                await asyncio.to_thread(process.join, 2.0)
                if process.is_alive():
                    process.terminate()
                    await asyncio.to_thread(process.join, 2.0)
                if process.is_alive():
                    process.kill()
                    await asyncio.to_thread(process.join, 2.0)
            for q in (cell.input_queue, cell.result_queue):
                close = getattr(q, "close", None)
                if close is not None:
                    with suppress(Exception):
                        close()

    async def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        if self._no_active_check_handle is not None:
            self._no_active_check_handle.cancel()
            self._no_active_check_handle = None
        for actor_id in reversed(list(self._cells)):
            await self.stop_actor(actor_id, reason="system shutdown", notify_parent=False, notify_links=False)
        for handle in list(self._wakeups):
            handle.cancel()
            self._wakeups.pop(handle, None)
        for actor_id in list(self._watches):
            self._clear_watch(actor_id)
        if self._task_group is not None:
            await self._task_group.__aexit__(None, None, None)
            self._task_group = None
        if self._journal is not None:
            await self._journal.close()

    def diagnostics(self) -> RuntimeDiagnostics:
        now = asyncio.get_running_loop().time()
        actors = tuple(
            ActorDiagnostics(
                actor_id=actor_id,
                parent_id=cell.parent_id,
                child_count=len(self.registry.get(actor_id).children) if self.registry.exists(actor_id) else 0,
                mailbox_depth=cell.mailbox.size() if isinstance(cell, AsyncActorCell) else cell.mailbox_depth,
                oldest_message_age=cell.mailbox.oldest_age(now) if isinstance(cell, AsyncActorCell) else None,
                running=cell.running,
                stopped=cell.stopped,
                active=cell.actor.active if isinstance(cell, AsyncActorCell) else cell.active,
                processed_count=cell.processed_count,
                failure_count=cell.failure_count,
                restart_count=cell.restart_count,
                average_processing_latency=(
                    cell.processing_latency_total / cell.processed_count if cell.processed_count else 0.0
                ),
            )
            for actor_id, cell in self._cells.items()
        )
        dead_letter_summary: dict[str, int] = {}
        for letter in self._dead_letters:
            dead_letter_summary[letter.reason] = dead_letter_summary.get(letter.reason, 0) + 1
        return RuntimeDiagnostics(
            syndicate_id=self.syndicate_id,
            backend_type=self.backend_type,
            actor_count=len(self._cells),
            external_inbox_count=len(self._external),
            dead_letter_count=len(self._dead_letters),
            lifecycle_failure_count=len(self._lifecycle_failures),
            late_reply_count=len(self._late_replies),
            event_count=len(self._events),
            uptime_seconds=0.0 if self._started_at == 0.0 else max(0.0, now - self._started_at),
            dead_letter_summary=dead_letter_summary,
            actors=actors,
        )

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        return tuple(self._dead_letters)

    @property
    def late_replies(self) -> tuple[DeadLetter, ...]:
        return tuple(self._late_replies)

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)

    async def _actor_loop(self, actor_id: ActorId) -> None:
        cell = self._cells[actor_id]
        assert isinstance(cell, AsyncActorCell)
        try:
            while not cell.stopped and not self._shutdown:
                envelope, lane = await cell.mailbox.get()
                cell.running = True
                started_at = asyncio.get_running_loop().time()
                self._record_event("message_dequeued", actor_id=actor_id, message_id=envelope.message_id)
                try:
                    await self._handle_envelope(cell, envelope)
                finally:
                    elapsed = asyncio.get_running_loop().time() - started_at
                    cell.processed_count += 1
                    cell.processing_latency_total += elapsed
                    self._record_event(
                        "message_processed",
                        actor_id=actor_id,
                        message_id=envelope.message_id,
                        latency=f"{elapsed:.6f}",
                    )
                    cell.running = False
                    cell.mailbox.task_done(lane)
                    self._schedule_no_active_check()
        except asyncio.CancelledError:
            pass

    def active_actor_count(self) -> int:
        """Return the number of non-stopped actors marked active."""
        return sum(
            1
            for cell in self._cells.values()
            if not cell.stopped and (cell.actor.active if isinstance(cell, AsyncActorCell) else cell.active)
        )

    def running_actor_count(self) -> int:
        """Return the number of non-stopped actors currently processing a message."""
        return sum(1 for cell in self._cells.values() if not cell.stopped and cell.running)

    def _schedule_no_active_check(self) -> None:
        if self._no_active_callback is None or self._shutdown:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not loop:
            loop.call_soon_threadsafe(self._schedule_no_active_check)
            return
        if self._no_active_check_handle is not None and not self._no_active_check_handle.cancelled():
            return
        self._no_active_check_handle = loop.call_soon(self._run_no_active_check)

    def _spawn_runtime_task(self, awaitable: Awaitable[Any], *, name: str) -> asyncio.Task[Any]:
        coroutine = cast(Coroutine[Any, Any, Any], awaitable)
        if self._task_group is not None and not self._shutdown:
            return self._task_group.create_task(coroutine, name=name)
        return asyncio.create_task(coroutine, name=name)

    def _run_no_active_check(self) -> None:
        self._no_active_check_handle = None
        if self._no_active_callback is None or self._shutdown:
            return
        if self.running_actor_count() > 0 or self.active_actor_count() > 0:
            return
        result = self._no_active_callback()
        if inspect.isawaitable(result):
            self._spawn_runtime_task(cast(Coroutine[Any, Any, Any], result), name="spark-no-active-callback")

    async def _handle_envelope(self, cell: AsyncActorCell, envelope: Envelope) -> None:
        if envelope.target_incarnation is not None and envelope.target_incarnation != cell.incarnation:
            self._record_dead_letter(envelope, "stale actor incarnation")
            return
        if envelope.is_expired:
            self._record_dead_letter(envelope, "message expired")
            return
        if isinstance(envelope.payload, StatusRequest):
            await self._reply_actor_status(cell, envelope.sender)
            return
        if isinstance(envelope.payload, ActorExitRequest):
            await self.stop_actor(cell.address.actor_id, reason=envelope.payload.reason)
            return
        try:
            if isinstance(envelope.payload, ChildActorExited):
                await _maybe_await(
                    cell.actor.on_child_exited(ActorAddress(envelope.payload.child_id), envelope.payload.reason)
                )
            await cell.actor.receive_envelope(envelope)
        except Exception as exc:
            reason = f"handler failed: {exc}"
            cell.failure_count += 1
            self._record_dead_letter(envelope, reason)
            await self._supervise_failed_actor(cell, reason)

    async def _supervise_failed_actor(self, cell: AsyncActorCell, reason: str) -> None:
        strategy = cell.spec.supervisor_strategy if cell.spec is not None else None
        decision = "stop" if strategy is None else strategy.decision
        if decision == "resume":
            return
        if decision == "restart" and strategy is not None and cell.spec is not None:
            prior_restart_count = self._record_restart_attempt(cell)
            if prior_restart_count is not None:
                self._record_event(
                    "supervision_decision",
                    actor_id=cell.address.actor_id,
                    reason=reason,
                    decision="restart",
                )
                delay = strategy.restart_delay(prior_restart_count)
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._restart_actor(cell, reason)
                return
            self._record_event(
                "supervision_decision",
                actor_id=cell.address.actor_id,
                reason=reason,
                decision="stop",
                detail="restart limit exceeded",
            )
            self._record_lifecycle_failure(cell.address.actor_id, f"restart limit exceeded: {reason}")
            await self.stop_actor(
                cell.address.actor_id,
                reason=f"restart limit exceeded: {reason}",
                exit_code=1,
            )
            return
        if decision == "escalate":
            self._record_event(
                "supervision_decision",
                actor_id=cell.address.actor_id,
                reason=reason,
                decision="escalate",
            )
            await self.stop_actor(cell.address.actor_id, reason=f"escalated: {reason}", exit_code=1)
            return
        self._record_event("supervision_decision", actor_id=cell.address.actor_id, reason=reason, decision=decision)
        await self.stop_actor(cell.address.actor_id, reason=reason, exit_code=1)

    def _record_restart_attempt(self, cell: AsyncActorCell) -> int | None:
        assert cell.spec is not None
        strategy = cell.spec.supervisor_strategy
        loop = self._loop
        now = loop.time() if loop is not None else asyncio.get_running_loop().time()
        cell.restart_timestamps = [
            timestamp for timestamp in cell.restart_timestamps if now - timestamp <= strategy.period_seconds
        ]
        prior_restart_count = len(cell.restart_timestamps)
        if prior_restart_count >= strategy.max_restarts:
            return None
        cell.restart_timestamps.append(now)
        return prior_restart_count

    async def _restart_actor(self, old_cell: AsyncActorCell, reason: str) -> None:
        spec = old_cell.spec
        if spec is None:
            await self.stop_actor(old_cell.address.actor_id, reason=reason, exit_code=1)
            return
        actor_id = old_cell.address.actor_id
        old_incarnation = old_cell.incarnation
        new_incarnation = old_incarnation.next_generation()
        for child_id in list(self.registry.children_of(actor_id)):
            await self.stop_actor(child_id, reason="parent restarted", notify_parent=False)
        self._clear_watch(actor_id)
        for handle, scheduled in list(self._wakeups.items()):
            if scheduled.actor_id == actor_id:
                handle.cancel()
                self._wakeups.pop(handle, None)

        old_cell.stopped = True
        old_cell.actor._set_activity_change_callback(None)
        try:
            await _maybe_await(old_cell.actor.post_stop())
        except Exception as exc:
            self._record_lifecycle_failure(actor_id, f"post_stop failed during restart: {exc}")

        actor_type = self._validate_actor_spec(spec)
        with _disable_actor_auto_start():
            new_actor = actor_type(*spec.args, **dict(spec.kwargs))
        parent_address = ActorAddress(old_cell.parent_id) if old_cell.parent_id is not None else None
        context = AsyncActorContext(self, actor_id, old_cell.address, self.address, parent_address)
        new_actor._bind_context(context)
        new_cell = AsyncActorCell(
            actor=new_actor,
            address=old_cell.address,
            incarnation=new_incarnation,
            parent_id=old_cell.parent_id,
            mailbox=old_cell.mailbox,
            spec=spec,
            restart_timestamps=list(old_cell.restart_timestamps),
            restart_count=old_cell.restart_count + 1,
        )
        new_actor._set_activity_change_callback(self._schedule_no_active_check)
        self._cells[actor_id] = new_cell
        record = self.registry.get(actor_id)
        record.actor = new_actor
        record.incarnation = new_incarnation
        try:
            await self._recover_persistent_actor(new_cell)
            await _maybe_await(new_actor.pre_start())
        except Exception as exc:
            new_cell.stopped = True
            new_actor._set_activity_change_callback(None)
            with suppress(ActorNotFound):
                self.registry.remove(actor_id)
            self._cells.pop(actor_id, None)
            self._record_lifecycle_failure(actor_id, f"pre_start failed during restart: {exc}")
            if old_cell.parent_id is not None:
                await self._notify_child_exited(new_cell, "pre_start failed during restart", 1)
            return

        assert self._task_group is not None
        new_cell.task = self._task_group.create_task(
            self._actor_loop(actor_id),
            name=f"spark-actor-{actor_id.actor_id}",
        )
        new_cell.started_at = asyncio.get_running_loop().time()
        self._schedule_no_active_check()
        self._record_event(
            "actor_restarted",
            actor_id=actor_id,
            reason=reason,
            old_generation=str(old_incarnation.generation),
            new_generation=str(new_incarnation.generation),
        )
        logger.info("spark actor restarted actor=%s generation=%s", actor_id, new_incarnation.generation)
        await self._notify_child_restarted(new_cell, old_incarnation, reason)

    async def _reply_system_status(self, sender_id: ActorId | None) -> None:
        if sender_id is None:
            return
        pending_wakeups = tuple(
            PendingWakeup(
                target=str(actor_id),
                delay=max(0.0, handle.when() - asyncio.get_running_loop().time()),
                payload=str(wakeup.payload),
            )
            for handle, scheduled in self._wakeups.items()
            for actor_id, wakeup in ((scheduled.actor_id, scheduled.wakeup),)
            if not handle.cancelled()
        )
        pending_messages: list[PendingMessage] = []
        for cell in self._cells.values():
            if not isinstance(cell, AsyncActorCell):
                continue
            for envelope in cell.mailbox.pending():
                pending_messages.append(
                    PendingMessage(
                        from_addr=str(envelope.sender or ""),
                        to_addr=str(envelope.target),
                        message=str(envelope.payload),
                    )
                )
        status = SystemStatus(
            syndicate_id=self.syndicate_id,
            admin_address=str(self.address),
            actor_count=len(self._cells),
            uptime_seconds=self.diagnostics().uptime_seconds,
            backend_type=self.backend_type,
            common=CommonStatusFields(
                pending_messages=tuple(pending_messages),
                pending_wakeups=pending_wakeups,
                messages_received=sum(cell.processed_count for cell in self._cells.values()),
                send_failures=len(self._dead_letters),
                misc={
                    "runtime_events": str(len(self._events)),
                    "late_replies": str(len(self._late_replies)),
                },
            ),
            in_shutdown=self._shutdown,
        )
        await self.deliver(Envelope(target=sender_id, payload=status))

    async def _reply_actor_status(self, cell: RuntimeActorCell, sender_id: ActorId | None) -> None:
        if sender_id is None:
            return
        if isinstance(cell, AsyncActorCell):
            pending_messages = tuple(
                PendingMessage(
                    from_addr=str(envelope.sender or ""),
                    to_addr=str(envelope.target),
                    message=str(envelope.payload),
                )
                for envelope in cell.mailbox.pending()
            )
            pending_wakeups = tuple(
                PendingWakeup(
                    target=str(actor_id),
                    delay=max(0.0, handle.when() - asyncio.get_running_loop().time()),
                    payload=str(wakeup.payload),
                )
                for handle, scheduled in self._wakeups.items()
                for actor_id, wakeup in ((scheduled.actor_id, scheduled.wakeup),)
                if actor_id == cell.address.actor_id and not handle.cancelled()
            )
            actor_class_name = cell.actor.__class__.__name__
            processed_count = cell.processed_count
            failure_count = cell.failure_count
            restart_count = cell.restart_count
        else:
            pending_messages = ()
            pending_wakeups = ()
            actor_class_name = cell.actor_class.__name__
            processed_count = cell.processed_count
            failure_count = cell.failure_count
            restart_count = cell.restart_count
        children = (
            tuple(
                str(self.registry.get(child_id).address)
                for child_id in self.registry.children_of(cell.address.actor_id)
            )
            if self.registry.exists(cell.address.actor_id)
            else ()
        )
        status = ActorStatus(
            actor_address=str(cell.address),
            actor_class=actor_class_name,
            admin_address=str(self.address),
            parent_address=str(cell.parent_id) if cell.parent_id is not None else None,
            common=CommonStatusFields(
                pending_messages=pending_messages,
                pending_wakeups=pending_wakeups,
                child_actors=children,
                messages_received=processed_count,
                send_failures=failure_count,
                misc={"restart_count": str(restart_count)},
            ),
        )
        await self.deliver(Envelope(target=sender_id, payload=status))

    def _require_local_actor(self, address: ActorAddress) -> RuntimeActorCell:
        actor_id = address.actor_id
        if actor_id.syndicate_id != self.syndicate_id:
            raise MessageDeliveryError(address, "remote actors are not supported for local supervision links")
        cell = self._cells.get(actor_id)
        if cell is None or cell.stopped or not self.registry.exists(actor_id):
            raise MessageDeliveryError(address, "target not found")
        return cell

    def _require_local_deliverable(self, address: ActorAddress, *, role: str) -> None:
        actor_id = address.actor_id
        if actor_id.syndicate_id != self.syndicate_id:
            raise MessageDeliveryError(address, f"remote actors are not supported as {role}")
        if actor_id in self._external:
            return
        self._require_local_actor(address)

    def _remove_actor_relationships(self, actor_id: ActorId) -> tuple[set[ActorId], set[ActorId]]:
        linked_actor_ids = self._links.pop(actor_id, set())
        for linked_actor_id in linked_actor_ids:
            peers = self._links.get(linked_actor_id)
            if peers is None:
                continue
            peers.discard(actor_id)
            if not peers:
                self._links.pop(linked_actor_id, None)

        monitor_actor_ids = self._monitors.pop(actor_id, set())
        for target_id, watcher_ids in list(self._monitors.items()):
            watcher_ids.discard(actor_id)
            if not watcher_ids:
                self._monitors.pop(target_id, None)
        return linked_actor_ids, monitor_actor_ids

    async def _notify_monitors_exited(
        self,
        monitor_actor_ids: set[ActorId],
        cell: RuntimeActorCell,
        reason: str,
        exit_code: int,
    ) -> None:
        if not monitor_actor_ids:
            return
        payload = ActorExited(
            actor_id=cell.address.actor_id,
            incarnation=cell.incarnation,
            exit_code=exit_code,
            reason=reason,
        )
        for monitor_actor_id in monitor_actor_ids:
            if monitor_actor_id == cell.address.actor_id:
                continue
            if monitor_actor_id not in self._external and not self.registry.exists(monitor_actor_id):
                continue
            await self.deliver(
                Envelope(
                    target=monitor_actor_id,
                    payload=payload,
                    sender=cell.address.actor_id,
                )
            )

    async def _stop_linked_actors(
        self,
        linked_actor_ids: set[ActorId],
        reason: str,
        exit_code: int,
    ) -> None:
        for linked_actor_id in linked_actor_ids:
            if linked_actor_id not in self._cells:
                continue
            await self.stop_actor(
                linked_actor_id,
                reason=f"linked actor exited: {reason}",
                exit_code=exit_code,
            )

    async def _notify_child_exited(self, child_cell: RuntimeActorCell, reason: str, exit_code: int) -> None:
        parent_id = child_cell.parent_id
        if parent_id is None or not self.registry.exists(parent_id):
            return
        await self.deliver(
            Envelope(
                target=parent_id,
                payload=ChildActorExited(
                    child_id=child_cell.address.actor_id,
                    parent_id=parent_id,
                    child_incarnation=child_cell.incarnation,
                    exit_code=exit_code,
                    reason=reason,
                ),
                sender=child_cell.address.actor_id,
            )
        )

    async def _notify_child_restarted(
        self,
        child_cell: AsyncActorCell,
        old_incarnation: ActorIncarnation,
        reason: str,
    ) -> None:
        parent_id = child_cell.parent_id
        if parent_id is None or not self.registry.exists(parent_id):
            return
        await self.deliver(
            Envelope(
                target=parent_id,
                payload=ChildActorRestarted(
                    child_id=child_cell.address.actor_id,
                    parent_id=parent_id,
                    old_incarnation=old_incarnation,
                    new_incarnation=child_cell.incarnation,
                    reason=reason,
                ),
                sender=child_cell.address.actor_id,
            )
        )

    def _fd_ready(self, actor_id: ActorId, fd: int, mode: str) -> None:
        payload = WatchMessage(ready_read=(fd,)) if mode == "read" else WatchMessage(ready_write=(fd,))
        self._spawn_runtime_task(
            self.deliver(Envelope(target=actor_id, payload=payload)),
            name=f"spark-fd-ready-{actor_id.actor_id}",
        )

    def _clear_watch(self, actor_id: ActorId) -> None:
        loop = asyncio.get_running_loop()
        watch = self._watches.pop(actor_id, None)
        if watch is None:
            return
        for fd in watch.read:
            loop.remove_reader(fd)
            self._fd_owner.pop(fd, None)
        for fd in watch.write:
            loop.remove_writer(fd)
            self._fd_owner.pop(fd, None)

    def _restore_watch(self, actor_id: ActorId, read: set[int], write: set[int]) -> None:
        if read or write:
            self.watch(actor_id, read=tuple(read), write=tuple(write))

    def _create_external_inbox(self) -> AsyncExternalInbox:
        actor_id = ActorId(self.syndicate_id)
        inbox = AsyncExternalInbox(actor_id=actor_id, address=ActorAddress(actor_id))
        self._external[actor_id] = inbox
        return inbox

    def _close_external_inbox(self, actor_id: ActorId, reason: str) -> None:
        self._external.pop(actor_id, None)
        self._closed_external.setdefault(actor_id, reason)
        max_closed = self._dead_letters.maxlen
        if max_closed is not None:
            while len(self._closed_external) > max_closed:
                self._closed_external.pop(next(iter(self._closed_external)))

    def _record_dead_letter(self, envelope: Envelope, reason: str) -> None:
        self._dead_letters.append(DeadLetter(original_envelope=envelope, reason=reason))
        self._record_event(
            "delivery_failed",
            actor_id=envelope.target,
            message_id=envelope.message_id,
            reason=reason,
        )
        logger.warning("spark delivery failed target=%s reason=%s", envelope.target, reason)

    def _record_late_reply(self, envelope: Envelope, reason: str) -> None:
        self._late_replies.append(DeadLetter(original_envelope=envelope, reason=reason))
        self._record_event("late_reply", actor_id=envelope.target, message_id=envelope.message_id, reason=reason)

    def _record_lifecycle_failure(self, actor_id: ActorId, reason: str) -> None:
        failure = DeadLetter(original_envelope=Envelope(target=actor_id, payload=None), reason=reason)
        self._lifecycle_failures.append(failure)
        self._dead_letters.append(failure)
        self._record_event("lifecycle_failed", actor_id=actor_id, reason=reason)
        logger.warning("spark lifecycle failed actor=%s reason=%s", actor_id, reason)

    def _record_event(
        self,
        kind: str,
        *,
        actor_id: ActorId | None = None,
        message_id: str | None = None,
        reason: str | None = None,
        **fields: str,
    ) -> None:
        self._events.append(
            RuntimeEvent(
                kind=kind,
                syndicate_id=self.syndicate_id,
                actor_id=actor_id,
                message_id=message_id,
                reason=reason,
                fields=fields,
            )
        )

    def _validate_actor_spec(self, spec: ActorSpec) -> type[Actor]:
        actor_class = spec.actor_class
        if not isinstance(actor_class, type) or not issubclass(actor_class, Actor):
            raise InvalidActorSpecError(f"actor_class must be an Actor subclass, got {actor_class!r}")
        if spec.execution not in {"inprocess", "thread", "process", "system"}:
            raise InvalidActorSpecError(f"unsupported actor execution mode {spec.execution!r}")
        return actor_class

    def _resolve_execution(self, execution: ActorExecution) -> ActorExecution:
        if execution == "system":
            return self.default_execution
        return execution
