"""Async in-process actor runtime."""

from __future__ import annotations

import asyncio
import inspect
import multiprocessing as mp
import pickle
import queue
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast

from ..actor.address import ActorAddress
from ..actor.base import Actor, ActorContext, _disable_actor_auto_start
from ..core.actor_spec import ActorExecution, ActorSpec
from ..core.exceptions import ActorNotFound, ActorTimeout, InvalidActorSpecError, MessageDeliveryError
from ..core.identity import ActorId, ActorIncarnation, Envelope, SyndicateId
from ..core.messages import (
    ActorExitRequest,
    ActorStatus,
    ChildActorExited,
    CommonStatusFields,
    DeadLetter,
    PendingMessage,
    PendingWakeup,
    StatusRequest,
    SystemStatus,
    WakeupMessage,
    WatchMessage,
)
from .diagnostics import ActorDiagnostics, RuntimeDiagnostics
from .registry import ActorRecord, ActorRegistry
from .results import DeliveryResult


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(slots=True)
class AsyncMailbox:
    """Async FIFO queue owned by one actor."""

    actor_id: ActorId
    queue: asyncio.Queue[Envelope] = field(default_factory=asyncio.Queue)

    def enqueue(self, envelope: Envelope) -> None:
        self.queue.put_nowait(envelope)

    def size(self) -> int:
        return self.queue.qsize()

    def pending(self) -> tuple[Envelope, ...]:
        return tuple(getattr(self.queue, "_queue", ()))


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


@dataclass(slots=True)
class AsyncActorCell:
    """Runtime state owned by one async actor."""

    actor: Actor
    address: ActorAddress
    incarnation: ActorIncarnation
    parent_id: ActorId | None
    mailbox: AsyncMailbox
    task: asyncio.Task[None] | None = None
    running: bool = False
    stopped: bool = False


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
        parent: ActorAddress | None,
    ) -> None:
        self.actor_id = actor_id
        self.address = address
        self.parent = parent

    async def ask(self, target: ActorAddress, message: Any, timeout: float | None = None) -> Any:
        self._unsupported("ask")

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        self._unsupported("create_actor")

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        self._unsupported("create_actor_from_spec")

    def schedule_after(self, delay: float, payload: Any = None) -> None:
        self._unsupported("schedule_after")

    async def watch(self, *, read: Iterable[int] = (), write: Iterable[int] = ()) -> None:
        self._unsupported("watch")

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
        parent: ActorAddress | None,
        owner_loop: asyncio.AbstractEventLoop,
        deliver: Callable[[Envelope], Awaitable[DeliveryResult]],
        started: Callable[[ActorId], Awaitable[None]],
        finished: Callable[[ActorId], Awaitable[None]],
        failed: Callable[[ActorId, Envelope, str], Awaitable[None]],
    ) -> None:
        super().__init__(actor_id, address, parent)
        self._owner_loop = owner_loop
        self._deliver = deliver
        self._started = started
        self._finished = finished
        self._failed = failed

    async def tell(self, target: ActorAddress, message: Any) -> None:
        await self._run_on_owner_loop(
            self._deliver(
                Envelope(
                    target=target.actor_id,
                    payload=message,
                    sender=self.actor_id,
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
        parent: ActorAddress | None,
        result_queue: Any,
    ) -> None:
        super().__init__(actor_id, address, parent)
        self._result_queue = result_queue

    async def tell(self, target: ActorAddress, message: Any) -> None:
        envelope = Envelope(target=target.actor_id, payload=message, sender=self.actor_id)
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
    input_queue: queue.Queue[Envelope | None],
    owner_loop: asyncio.AbstractEventLoop,
    deliver: Callable[[Envelope], Awaitable[DeliveryResult]],
    started: Callable[[ActorId], Awaitable[None]],
    finished: Callable[[ActorId], Awaitable[None]],
    failed: Callable[[ActorId, Envelope, str], Awaitable[None]],
) -> None:
    address = ActorAddress(actor_id)
    parent = ActorAddress(parent_id) if parent_id is not None else None
    context = _ThreadExecutorActorContext(actor_id, address, parent, owner_loop, deliver, started, finished, failed)
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
    input_queue: Any,
    result_queue: Any,
) -> None:
    asyncio.run(_process_actor_loop(actor_class, args, kwargs, actor_id, parent_id, input_queue, result_queue))


async def _process_actor_loop(
    actor_class: type[Actor],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    actor_id: ActorId,
    parent_id: ActorId | None,
    input_queue: Any,
    result_queue: Any,
) -> None:
    address = ActorAddress(actor_id)
    parent = ActorAddress(parent_id) if parent_id is not None else None
    context = _ProcessExecutorActorContext(actor_id, address, parent, result_queue)
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
        parent: ActorAddress | None,
    ) -> None:
        self.backend = backend
        self.actor_id = actor_id
        self.address = address
        self.parent = parent

    async def tell(self, target: ActorAddress, message: Any) -> None:
        await self.backend.tell(target, message, sender=self.actor_id)

    async def ask(self, target: ActorAddress, message: Any, timeout: float | None = None) -> Any:
        return await self.backend.ask(target, message, timeout=timeout, sender=self.actor_id)

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        return await self.backend.create_actor(actor_class, *args, parent_id=self.actor_id, **kwargs)

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        return await self.backend.create_actor_from_spec(spec, parent_id=self.actor_id)

    def schedule_after(self, delay: float, payload: Any = None) -> None:
        self.backend.schedule_after(self.actor_id, delay, payload)

    async def watch(self, *, read: Iterable[int] = (), write: Iterable[int] = ()) -> None:
        self.backend.watch(self.actor_id, read=tuple(read), write=tuple(write))

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

    async def tell(self, target: ActorAddress, message: Any) -> None:
        await self._backend.tell(target, message, sender=self._inbox.actor_id)

    async def ask(self, target: ActorAddress, message: Any, timeout: float | None = 5.0) -> Any:
        await self.tell(target, message)
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


class AsyncInProcessBackend:
    """Task-owned async actor runtime."""

    def __init__(
        self,
        syndicate_id: SyndicateId,
        *,
        default_execution: ActorExecution = "inprocess",
        backend_type: str = "async-inprocess",
    ) -> None:
        self.syndicate_id = syndicate_id
        self.default_execution = default_execution
        self.backend_type = backend_type
        self.registry = ActorRegistry()
        self._cells: dict[ActorId, RuntimeActorCell] = {}
        self._external: dict[ActorId, AsyncExternalInbox] = {}
        self._dead_letters: list[DeadLetter] = []
        self._remote_sender: Callable[[Envelope], Awaitable[DeliveryResult]] | None = None
        self._shutdown = False
        self._task_group: asyncio.TaskGroup | None = None
        self._watches: dict[ActorId, _WatchState] = {}
        self._fd_owner: dict[int, ActorId] = {}
        self._wakeups: dict[asyncio.TimerHandle, tuple[ActorId, WakeupMessage]] = {}
        self._inbox = self._create_external_inbox()
        self.address = self._inbox.address
        self._loop: asyncio.AbstractEventLoop | None = None
        self._no_active_callback: Callable[[], Any] | None = None
        self._no_active_check_handle: asyncio.Handle | None = None

    async def start(self) -> None:
        if self._task_group is not None:
            return
        self._loop = asyncio.get_running_loop()
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
        return await self.start_actor(actor, parent_id=parent_id)

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
        self._schedule_no_active_check()
        return address

    async def start_actor(self, actor: Actor, parent_id: ActorId | None = None) -> ActorAddress:
        await self.start()
        if not isinstance(actor, Actor):
            raise InvalidActorSpecError(f"actor must be an Actor instance, got {actor!r}")
        actor_id = ActorId(syndicate_id=self.syndicate_id)
        address = ActorAddress(actor_id)
        parent_address = ActorAddress(parent_id) if parent_id is not None else None
        mailbox = AsyncMailbox(actor_id)
        context = AsyncActorContext(self, actor_id, address, parent_address)
        actor._bind_context(context)
        cell = AsyncActorCell(
            actor=actor,
            address=address,
            incarnation=ActorIncarnation(actor_id),
            parent_id=parent_id,
            mailbox=mailbox,
        )
        actor._set_activity_change_callback(self._schedule_no_active_check)
        self.registry.register(
            actor_id,
            ActorRecord(actor=actor, address=address, incarnation=cell.incarnation, parent_id=parent_id),
        )
        self._cells[actor_id] = cell
        try:
            await _maybe_await(actor.pre_start())
        except Exception:
            await self.stop_actor(actor_id, reason="pre_start failed", notify_parent=False)
            raise

        assert self._task_group is not None
        cell.task = self._task_group.create_task(self._actor_loop(actor_id), name=f"spark-actor-{actor_id.actor_id}")
        self._schedule_no_active_check()
        return address

    async def tell(self, target: ActorAddress, message: Any, sender: ActorId | None = None) -> DeliveryResult:
        return await self.deliver(
            Envelope(
                target=target.actor_id,
                payload=message,
                sender=sender or self._inbox.actor_id,
            )
        )

    async def ask(
        self,
        target: ActorAddress,
        message: Any,
        timeout: float | None = None,
        sender: ActorId | None = None,
    ) -> Any:
        ask_timeout = timeout
        inbox = self._create_external_inbox()
        try:
            result = await self.deliver(Envelope(target=target.actor_id, payload=message, sender=inbox.actor_id))
            if not result.success:
                raise MessageDeliveryError(target, result.reason or "delivery failed")
            envelope = await inbox.receive(ask_timeout)
            if envelope is None and ask_timeout:
                raise ActorTimeout("ask", ask_timeout)
            return envelope.payload
        finally:
            self._external.pop(inbox.actor_id, None)

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

        cell = self._cells.get(envelope.target)
        if cell is None or cell.stopped or not self.registry.exists(envelope.target):
            self._record_dead_letter(envelope, "target not found")
            return DeliveryResult(success=False, reason="target not found")
        if isinstance(cell, ExecutorActorCell):
            return await self._deliver_executor(cell, envelope)
        cell.mailbox.enqueue(envelope)
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
        self._schedule_no_active_check()
        return DeliveryResult(success=True)

    def schedule_after(self, actor_id: ActorId, delay: float, payload: Any = None) -> None:
        loop = asyncio.get_running_loop()
        wakeup = WakeupMessage(delay=delay, payload=payload)

        def fire() -> None:
            self._wakeups.pop(handle, None)
            asyncio.create_task(self.deliver(Envelope(target=actor_id, payload=wakeup)))

        handle = loop.call_later(max(0.0, delay), fire)
        self._wakeups[handle] = (actor_id, wakeup)

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
        self._schedule_no_active_check()

    async def _executor_finished(self, actor_id: ActorId) -> None:
        cell = self._cells.get(actor_id)
        if not isinstance(cell, ExecutorActorCell) or cell.stopped:
            return
        cell.running = False
        self._schedule_no_active_check()

    async def _executor_failed(self, actor_id: ActorId, envelope: Envelope, reason: str) -> None:
        if actor_id not in self._cells:
            return
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
    ) -> None:
        cell = self._cells.get(actor_id)
        if cell is None or cell.stopped:
            return
        for child_id in list(self.registry.children_of(actor_id)):
            await self.stop_actor(child_id, reason="parent stopped", notify_parent=False)

        if isinstance(cell, ExecutorActorCell):
            await self._stop_executor_actor(cell, reason=reason)
            with suppress(ActorNotFound):
                self.registry.remove(actor_id)
            self._cells.pop(actor_id, None)
            self._schedule_no_active_check()
            if notify_parent and cell.parent_id is not None:
                await self._notify_child_exited(cell, reason, exit_code)
            return

        cell.stopped = True
        self._clear_watch(actor_id)
        for handle, (target, _wakeup) in list(self._wakeups.items()):
            if target == actor_id:
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
        finally:
            cell.actor._set_activity_change_callback(None)
            self._schedule_no_active_check()

        if notify_parent and cell.parent_id is not None:
            await self._notify_child_exited(cell, reason, exit_code)

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
            await self.stop_actor(actor_id, reason="system shutdown", notify_parent=False)
        for handle in list(self._wakeups):
            handle.cancel()
            self._wakeups.pop(handle, None)
        for actor_id in list(self._watches):
            self._clear_watch(actor_id)
        if self._task_group is not None:
            await self._task_group.__aexit__(None, None, None)
            self._task_group = None

    def diagnostics(self) -> RuntimeDiagnostics:
        actors = tuple(
            ActorDiagnostics(
                actor_id=actor_id,
                parent_id=cell.parent_id,
                child_count=len(self.registry.get(actor_id).children) if self.registry.exists(actor_id) else 0,
                mailbox_depth=cell.mailbox.size() if isinstance(cell, AsyncActorCell) else cell.mailbox_depth,
                running=cell.running,
                stopped=cell.stopped,
                active=cell.actor.active if isinstance(cell, AsyncActorCell) else cell.active,
            )
            for actor_id, cell in self._cells.items()
        )
        return RuntimeDiagnostics(
            syndicate_id=self.syndicate_id,
            backend_type=self.backend_type,
            actor_count=len(self._cells),
            external_inbox_count=len(self._external),
            dead_letter_count=len(self._dead_letters),
            actors=actors,
        )

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        return tuple(self._dead_letters)

    async def _actor_loop(self, actor_id: ActorId) -> None:
        cell = self._cells[actor_id]
        assert isinstance(cell, AsyncActorCell)
        try:
            while not cell.stopped and not self._shutdown:
                envelope = await cell.mailbox.queue.get()
                cell.running = True
                try:
                    await self._handle_envelope(cell, envelope)
                finally:
                    cell.running = False
                    cell.mailbox.queue.task_done()
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

    def _run_no_active_check(self) -> None:
        self._no_active_check_handle = None
        if self._no_active_callback is None or self._shutdown:
            return
        if self.running_actor_count() > 0 or self.active_actor_count() > 0:
            return
        result = self._no_active_callback()
        if inspect.isawaitable(result):
            asyncio.create_task(cast(Coroutine[Any, Any, Any], result))

    async def _handle_envelope(self, cell: AsyncActorCell, envelope: Envelope) -> None:
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
            await cell.actor.receive_envelope(envelope)
        except Exception as exc:
            self._record_dead_letter(envelope, f"handler failed: {exc}")
            await self.stop_actor(cell.address.actor_id, reason="handler failed")

    async def _reply_system_status(self, sender_id: ActorId | None) -> None:
        if sender_id is None:
            return
        pending_wakeups = tuple(
            PendingWakeup(
                target=str(actor_id),
                delay=max(0.0, handle.when() - asyncio.get_running_loop().time()),
                payload=str(wakeup.payload),
            )
            for handle, (actor_id, wakeup) in self._wakeups.items()
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
            uptime_seconds=0.0,
            backend_type=self.backend_type,
            common=CommonStatusFields(
                pending_messages=tuple(pending_messages),
                pending_wakeups=pending_wakeups,
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
                for handle, (actor_id, wakeup) in self._wakeups.items()
                if actor_id == cell.address.actor_id and not handle.cancelled()
            )
            actor_class_name = cell.actor.__class__.__name__
        else:
            pending_messages = ()
            pending_wakeups = ()
            actor_class_name = cell.actor_class.__name__
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
            ),
        )
        await self.deliver(Envelope(target=sender_id, payload=status))

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

    def _fd_ready(self, actor_id: ActorId, fd: int, mode: str) -> None:
        payload = WatchMessage(ready_read=(fd,)) if mode == "read" else WatchMessage(ready_write=(fd,))
        asyncio.create_task(self.deliver(Envelope(target=actor_id, payload=payload)))

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

    def _record_dead_letter(self, envelope: Envelope, reason: str) -> None:
        self._dead_letters.append(DeadLetter(original_envelope=envelope, reason=reason))

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
