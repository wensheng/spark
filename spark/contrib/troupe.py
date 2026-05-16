"""Async actor pool/router pattern."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from ..actor.address import ActorAddress
from ..actor.base import Actor
from ..core.actor_spec import ActorExecution, ActorSpec
from ..core.identity import Envelope
from ..core.message import Message
from ..core.messages import ActorExitRequest, ChildActorExited, SyndicateMessage, WakeupMessage

DISMISS_EXTRA_PERIOD = 2.0


class UpdateTroupeSettings:
    """Message used to adjust a troupe's pool size."""

    def __init__(
        self,
        max_count: int | None = None,
        idle_count: int | None = None,
        worker_execution: ActorExecution | None = None,
    ) -> None:
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive")
        if idle_count is not None and idle_count <= 0:
            raise ValueError("idle_count must be positive")
        if worker_execution is not None and worker_execution not in {"inprocess", "thread", "process", "system"}:
            raise ValueError("worker_execution must be one of inprocess, thread, process, or system")
        self.max_count = max_count
        self.idle_count = idle_count
        self.worker_execution = worker_execution


@dataclass(frozen=True, slots=True)
class GetTroupeStatus:
    """Request structured actor-pool status."""


@dataclass(frozen=True, slots=True)
class TroupeStatus:
    """Structured actor-pool status."""

    idle_count: int
    max_count: int
    worker_execution: ActorExecution
    worker_count: int
    idle_worker_count: int
    pending_count: int
    max_pending: int | None = None


class _TroupeMemberReady:
    __slots__ = ("ident_done",)

    def __init__(self, work_ident: int) -> None:
        self.ident_done = work_ident


class _TroupeWork:
    __slots__ = ("message", "orig_sender", "troupe_mgr", "ident")

    def __init__(self, message: Any, orig_sender: ActorAddress | None, troupe_mgr: ActorAddress) -> None:
        self.message = message
        self.orig_sender = orig_sender
        self.troupe_mgr = troupe_mgr
        self.ident = -1


class _TroupeManager:
    def __init__(
        self,
        mgr_addr: ActorAddress,
        idle_count: int,
        max_count: int,
        worker_execution: ActorExecution,
        max_pending: int | None = None,
    ) -> None:
        self.mgr_addr = mgr_addr
        self.idle_count = idle_count
        self.max_count = max_count
        self.worker_execution = worker_execution
        self.max_pending = max_pending
        self.workers: list[ActorAddress] = []
        self.idle_workers: list[ActorAddress] = []
        self.extra_workers: list[ActorAddress] = []
        self.pending_work: list[_TroupeWork] = []
        self.handling_work: dict[int, tuple[ActorAddress, _TroupeWork]] = {}
        self.pending_dismissal = False
        self.work_ident = 0

    def assign_ready(
        self,
        ready: _TroupeMemberReady,
        worker: ActorAddress,
    ) -> tuple[list[tuple[ActorAddress, _TroupeWork]], bool]:
        if ready.ident_done >= 0:
            self.handling_work.pop(ready.ident_done, None)
        if self.pending_work:
            work = self.pending_work.pop(0)
            self.handling_work[work.ident] = (worker, work)
            return [(worker, work)], False
        if len(self.workers) > self.idle_count and len(self.idle_workers) >= self.idle_count:
            schedule = not self.pending_dismissal
            self.pending_dismissal = True
            self.extra_workers.append(worker)
            return [], schedule
        self.idle_workers.append(worker)
        return [], False

    def assign_work(self, payload: Any, sender: ActorAddress | None) -> list[tuple[ActorAddress | None, _TroupeWork]]:
        work = payload if isinstance(payload, _TroupeWork) else _TroupeWork(payload, sender, self.mgr_addr)
        if work.ident < 0:
            work.ident = self.work_ident
            self.work_ident = (self.work_ident + 1) & 0xFFFFFFFF
        worker = self.idle_workers.pop(0) if self.idle_workers else None
        if worker is None and self.extra_workers:
            worker = self.extra_workers.pop(0)
        if worker is not None:
            self.handling_work[work.ident] = (worker, work)
            return [(worker, work)]
        if len(self.workers) < self.max_count:
            return [(None, work)]
        if self.max_pending is not None and len(self.pending_work) >= self.max_pending:
            raise RuntimeError("actor pool pending queue full")
        self.pending_work.append(work)
        return []

    def add_worker(self, worker: ActorAddress, work: _TroupeWork) -> None:
        if worker not in self.workers:
            self.workers.append(worker)
        self.handling_work[work.ident] = (worker, work)

    def worker_exited(self, worker: ActorAddress) -> _TroupeWork | None:
        for group in (self.workers, self.idle_workers, self.extra_workers):
            try:
                group.remove(worker)
            except ValueError:
                pass
        for assigned, work in list(self.handling_work.values()):
            if assigned == worker:
                self.handling_work.pop(work.ident, None)
                self.pending_work.append(work)
                return work
        return None

    def extras_for_dismissal(self) -> list[ActorAddress]:
        extras = list(self.extra_workers)
        self.extra_workers.clear()
        self.pending_dismissal = False
        return extras

    def status(self) -> str:
        return (
            f"Idle={self.idle_count}, Max={self.max_count}, "
            f"Execution={self.worker_execution}, "
            f"Workers={len(self.workers)}, IdleWorkers={len(self.idle_workers)}, "
            f"Pending={len(self.pending_work)}"
        )

    def structured_status(self) -> TroupeStatus:
        return TroupeStatus(
            idle_count=self.idle_count,
            max_count=self.max_count,
            worker_execution=self.worker_execution,
            worker_count=len(self.workers),
            idle_worker_count=len(self.idle_workers),
            pending_count=len(self.pending_work),
            max_pending=self.max_pending,
        )


class Troupe(Actor):
    """Async native pool/router base class.

    Subclasses override ``process`` with the work handler. The first instance
    becomes a manager and routes application messages to child workers of the
    same class while preserving actor isolation.
    """

    troupe_max_count: int = 10
    troupe_idle_count: int = 2
    troupe_worker_execution: ActorExecution = "inprocess"
    troupe_max_pending: int | None = None

    def __init__(
        self,
        *,
        max_count: int | None = None,
        idle_count: int | None = None,
        worker_execution: ActorExecution | None = None,
        max_pending: int | None = None,
    ) -> None:
        super().__init__()
        self._cfg_max_count = max_count if max_count is not None else self.troupe_max_count
        self._cfg_idle_count = idle_count if idle_count is not None else self.troupe_idle_count
        self._cfg_worker_execution = worker_execution if worker_execution is not None else self.troupe_worker_execution
        self._cfg_max_pending = max_pending if max_pending is not None else self.troupe_max_pending
        self._troupe_mgr: _TroupeManager | None = None
        self._is_worker_for: ActorAddress | None = None
        self._work_ident = -1
        self.troupe_work_in_progress = False

    def troupe_worker_spec(self) -> ActorSpec:
        """Return the actor specification used when the manager creates workers."""
        worker_execution = (
            self._troupe_mgr.worker_execution if self._troupe_mgr is not None else self._cfg_worker_execution
        )
        return ActorSpec(
            actor_class=self.__class__,
            execution=worker_execution,
            stateless=worker_execution in {"thread", "process", "system"},
        )

    async def receive_envelope(self, envelope: Envelope) -> None:
        payload = envelope.payload
        is_work = isinstance(payload, _TroupeWork)
        is_worker = self._is_worker_for is not None
        undecided_system = self._troupe_mgr is None and isinstance(payload, SyndicateMessage)
        if is_worker or is_work or undecided_system:
            await self._run_worker(envelope, payload, is_work)
            return
        await self._run_manager(envelope, payload)

    async def _run_worker(self, envelope: Envelope, payload: Any, is_work: bool) -> None:
        was_in_progress = self.troupe_work_in_progress
        message = self._worker_message(envelope, payload, is_work)
        result = self.process(message)
        if inspect.isawaitable(result):
            await result
        if (is_work or was_in_progress) and not self.troupe_work_in_progress and self._is_worker_for is not None:
            await self.tell(_TroupeMemberReady(self._work_ident), self._is_worker_for)
            self._work_ident = -1

    def _worker_message(self, envelope: Envelope, payload: Any, is_work: bool) -> Message:
        if not is_work:
            return self._message_from_envelope(envelope)
        self._is_worker_for = payload.troupe_mgr
        self._work_ident = payload.ident
        inner = payload.message
        if isinstance(inner, Message):
            inner.sender = payload.orig_sender
            return inner
        return Message(content=inner, sender=payload.orig_sender)

    async def _run_manager(self, envelope: Envelope, payload: Any) -> None:
        if isinstance(payload, ActorExitRequest):
            return
        if self._troupe_mgr is None:
            assert self.address is not None
            self._troupe_mgr = _TroupeManager(
                self.address,
                self._cfg_idle_count,
                self._cfg_max_count,
                self._cfg_worker_execution,
                self._cfg_max_pending,
            )

        sender = ActorAddress(envelope.sender) if envelope.sender is not None else None
        if isinstance(payload, ChildActorExited):
            payload = self._troupe_mgr.worker_exited(ActorAddress(payload.child_id))
        elif isinstance(payload, _TroupeMemberReady):
            if sender is None:
                return
            sends, schedule = self._troupe_mgr.assign_ready(payload, sender)
            for ready_target, work in sends:
                await self.tell(work, ready_target)
            if schedule:
                self.schedule_after(DISMISS_EXTRA_PERIOD)
            return
        elif isinstance(payload, UpdateTroupeSettings):
            if payload.max_count is not None:
                self._troupe_mgr.max_count = payload.max_count
            if payload.idle_count is not None:
                self._troupe_mgr.idle_count = payload.idle_count
            if payload.worker_execution is not None:
                self._troupe_mgr.worker_execution = payload.worker_execution
                self._cfg_worker_execution = payload.worker_execution
            if sender is not None:
                await self.tell(
                    UpdateTroupeSettings(
                        self._troupe_mgr.max_count,
                        self._troupe_mgr.idle_count,
                        self._troupe_mgr.worker_execution,
                    ),
                    sender,
                )
            return
        elif isinstance(payload, GetTroupeStatus):
            if sender is not None:
                await self.tell(self._troupe_mgr.structured_status(), sender)
            return
        elif isinstance(payload, str) and await self._handle_command(payload, sender):
            return
        elif isinstance(payload, WakeupMessage):
            for extra in self._troupe_mgr.extras_for_dismissal():
                await self.tell(ActorExitRequest(), extra)
            return

        if payload is None:
            return
        for assigned_target, work in self._troupe_mgr.assign_work(payload, sender):
            if assigned_target is None:
                worker = await self.create_actor_from_spec(self.troupe_worker_spec())
                self._troupe_mgr.add_worker(worker, work)
                await self.tell(work, worker)
            else:
                await self.tell(work, assigned_target)

    async def _handle_command(self, command: str, sender: ActorAddress | None) -> bool:
        assert self._troupe_mgr is not None
        if command == "troupe:status?":
            if sender is not None:
                await self.tell(self._troupe_mgr.status(), sender)
            return True
        if command.startswith("troupe:set_max_count="):
            self._troupe_mgr.max_count = int(command.split("=", 1)[1])
            if sender is not None:
                await self.tell(f"Set troupe max_count to {self._troupe_mgr.max_count}", sender)
            return True
        if command.startswith("troupe:set_idle_count="):
            self._troupe_mgr.idle_count = int(command.split("=", 1)[1])
            if sender is not None:
                await self.tell(f"Set troupe idle_count to {self._troupe_mgr.idle_count}", sender)
            return True
        return False


ActorPool = Troupe
