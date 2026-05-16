"""Async-first base actor API for Spark."""

from __future__ import annotations

import inspect
from abc import ABC, ABCMeta, abstractmethod
from collections.abc import Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Protocol

from ..core.actor_spec import ActorSpec
from ..core.exceptions import ActorAlreadyStartedError, ActorNotStartedError, SparkException, SyndicateError
from ..core.identity import ActorId, Envelope
from ..core.message import Message
from .address import ActorAddress

_auto_start_disabled_depth: ContextVar[int] = ContextVar("spark_actor_auto_start_disabled_depth", default=0)
_current_envelope: ContextVar[Envelope | None] = ContextVar("spark_current_envelope", default=None)
_RUN_REPLY_METADATA_KEY = "__spark_run_reply__"


@contextmanager
def _disable_actor_auto_start() -> Iterator[None]:
    """Temporarily disable implicit global-Syndicate registration."""
    token = _auto_start_disabled_depth.set(_auto_start_disabled_depth.get() + 1)
    try:
        yield
    finally:
        _auto_start_disabled_depth.reset(token)


class ActorContext(Protocol):
    """Async runtime operations exposed to a started actor."""

    actor_id: ActorId
    address: ActorAddress
    syndicate_address: ActorAddress
    parent: ActorAddress | None

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
        """Send a fire-and-forget message to another actor."""

    async def ask(
        self,
        message: Any,
        target: ActorAddress,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        """Send a message and await a reply."""

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a child actor."""

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        """Create a child actor from an explicit actor specification."""

    def schedule_after(
        self,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        """Schedule a wakeup message for this actor."""

    async def persist_event(self, event: Any) -> None:
        """Persist an event for a persistent actor."""

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        """Persist a snapshot for a persistent actor."""

    async def watch(self, *, read: Iterable[int] = (), write: Iterable[int] = ()) -> None:
        """Replace this actor's fd watch list."""

    async def link(self, target: ActorAddress) -> None:
        """Link this actor to another actor for bidirectional fate sharing."""

    async def monitor(self, target: ActorAddress) -> None:
        """Monitor another actor for one-way exit notification."""

    async def stop(self) -> None:
        """Stop this actor."""

    async def syndicate_shutdown(self) -> None:
        """Request shutdown of the entire syndicate."""


class ActorMeta(ABCMeta):
    """Metaclass that auto-starts directly constructed actor instances."""

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        instance = super().__call__(*args, **kwargs)
        if _auto_start_disabled_depth.get() == 0 and getattr(cls, "__spark_auto_start__", True):
            instance._auto_start_global_actor()
        return instance


class Actor(ABC, metaclass=ActorMeta):
    """Base class for async-first Spark actors."""

    __spark_auto_start__ = True

    def __init__(self) -> None:
        self._context: ActorContext | None = None
        self._active = True
        self._activity_change_callback: Callable[[], None] | None = None

    def _auto_start_global_actor(self) -> None:
        """Register direct actor instances with the process-wide Syndicate."""
        if self._context is not None:
            return
        from ..system.syndicate import _start_global_actor

        _start_global_actor(self)

    def _bind_context(self, context: ActorContext) -> None:
        """Bind this actor to its runtime context."""
        if self._context is not None:
            raise ActorAlreadyStartedError(self.actor_id)
        self._context = context

    def _set_activity_change_callback(self, callback: Callable[[], None] | None) -> None:
        """Install a runtime callback invoked when ``active`` changes."""
        self._activity_change_callback = callback

    @property
    def active(self) -> bool:
        """Return whether this actor is considered active."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        new_value = bool(value)
        if self._active == new_value:
            return
        self._active = new_value
        if self._activity_change_callback is not None:
            self._activity_change_callback()

    def activate(self) -> None:
        """Mark this actor active."""
        self.active = True

    def deactivate(self) -> None:
        """Mark this actor inactive."""
        self.active = False

    @property
    def actor_id(self) -> ActorId | None:
        """Return this actor's logical id once it has started."""
        return self._context.actor_id if self._context is not None else None

    @property
    def actor_address(self) -> ActorAddress | None:
        """Return this actor's public address once it has started."""
        return self._context.address if self._context is not None else None

    @property
    def address(self) -> ActorAddress | None:
        """Return this actor's public address once it has started."""
        return self.actor_address

    def _require_context(self) -> ActorContext:
        if self._context is None:
            raise ActorNotStartedError(self.__class__.__name__)
        return self._context

    async def tell(
        self,
        message: Any,
        target: ActorAddress | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
        headers: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Send a fire-and-forget message."""
        context = self._require_context()
        current = _current_envelope.get()
        if headers is None and current is not None:
            headers = dict(current.headers)
        if trace_id is None and current is not None:
            trace_id = current.trace_id
        if target is None:
            if ttl is None and deadline is None and headers is None and trace_id is None:
                await context.tell(message, context.syndicate_address)
            else:
                await context.tell(
                    message,
                    context.syndicate_address,
                    ttl=ttl,
                    deadline=deadline,
                    headers=headers,
                    trace_id=trace_id,
                )
            return
        if ttl is None and deadline is None and headers is None and trace_id is None:
            await context.tell(message, target)
        else:
            await context.tell(message, target, ttl=ttl, deadline=deadline, headers=headers, trace_id=trace_id)

    async def ask(
        self,
        message: Any,
        target: ActorAddress | None = None,
        timeout: float | None = None,
        *,
        ttl: float | None = None,
        deadline: datetime | None = None,
    ) -> Any:
        """Send a message and await a reply."""
        context = self._require_context()
        if target is None:
            if ttl is None and deadline is None:
                return await context.ask(message, context.syndicate_address, timeout)
            return await context.ask(message, context.syndicate_address, timeout, ttl=ttl, deadline=deadline)
        if ttl is None and deadline is None:
            return await context.ask(message, target, timeout)
        return await context.ask(message, target, timeout, ttl=ttl, deadline=deadline)

    async def create_actor(self, actor_class: type[Actor], *args: Any, **kwargs: Any) -> ActorAddress:
        """Create a child actor."""
        return await self._require_context().create_actor(actor_class, *args, **kwargs)

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        """Create a child actor from an explicit actor specification."""
        return await self._require_context().create_actor_from_spec(spec)

    def schedule_after(
        self,
        delay: float,
        payload: Any = None,
        *,
        durable: bool = False,
        timer_id: str | None = None,
    ) -> None:
        """Schedule a wakeup message after ``delay`` seconds."""
        self._require_context().schedule_after(delay, payload, durable=durable, timer_id=timer_id)

    async def persist_event(self, event: Any) -> None:
        """Persist an event for this actor when the runtime has a journal."""
        await self._require_context().persist_event(event)

    async def save_snapshot(self, state: Any, *, sequence: int | None = None) -> None:
        """Persist a snapshot for this actor when the runtime has a journal."""
        await self._require_context().save_snapshot(state, sequence=sequence)

    async def watch(
        self,
        *,
        read: Iterable[int] = (),
        write: Iterable[int] = (),
    ) -> None:
        """Replace this actor's fd watch list."""
        await self._require_context().watch(read=tuple(read), write=tuple(write))

    async def link(self, target: ActorAddress) -> None:
        """Link this actor to another actor for bidirectional fate sharing."""
        await self._require_context().link(target)

    async def monitor(self, target: ActorAddress) -> None:
        """Monitor another actor for one-way exit notification."""
        await self._require_context().monitor(target)

    async def stop(self) -> None:
        """Stop this actor."""
        await self._require_context().stop()

    async def syndicate_shutdown(self) -> None:
        """Request shutdown of the entire syndicate."""
        await self._require_context().syndicate_shutdown()

    @abstractmethod
    def process(self, message: Message) -> Any | Awaitable[Any]:
        """Handle an incoming message."""

    async def _process(self, message: Message) -> Any | Awaitable[Any]:
        """Wrap the process method to an async method."""
        result = self.process(message)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def receive_envelope(self, envelope: Envelope) -> None:
        """Normalize an envelope and dispatch it to ``process``."""
        token = _current_envelope.set(envelope)
        try:
            message = self._message_from_envelope(envelope)
            result = await self._process(message)
            force_reply = bool(message.metadata.get(_RUN_REPLY_METADATA_KEY))
            if (result is not None or force_reply) and message.sender is not None:
                await self.tell(result, message.sender)
        finally:
            _current_envelope.reset(token)

    async def run(self, payload: Any = None, timeout: float | None = 5.0) -> Any:
        """
        Called directly on an actor instance, but will raise if the actor is not running in the global syndicate.
        """
        context = self._require_context()
        if context.parent is not None:
            raise SparkException("Directly calling run() is only supported for actors running in the global syndicate.")
        was_active = self.active
        self.activate()
        try:
            message = Message(content=payload, metadata={_RUN_REPLY_METADATA_KEY: True})
            from ..system.syndicate import get_existing_global_syndicate

            syn = get_existing_global_syndicate()
            if syn is None or not syn.active or syn.syndicate_id != context.address.actor_id.syndicate_id:
                raise SyndicateError(
                    "direct actor is bound to a stopped global Syndicate; "
                    "create a new actor or use an explicit Syndicate"
                )
            return await syn.ask(message, context.address, timeout=timeout)
        finally:
            if not was_active and self.active:
                self.deactivate()

    @staticmethod
    def _message_from_envelope(envelope: Envelope) -> Message:
        sender = ActorAddress(envelope.sender) if envelope.sender is not None else None
        payload = envelope.payload
        if isinstance(payload, Message):
            payload.sender = sender
            return payload
        return Message(
            content=payload,
            sender=sender,
            id=envelope.message_id,
            correlation_id=envelope.correlation_id,
            metadata=dict(envelope.headers),
        )

    def pre_start(self) -> None | Awaitable[None]:
        """Called when the actor starts."""

    def post_stop(self) -> None | Awaitable[None]:
        """Called when the actor stops."""

    def on_child_exited(self, child: ActorAddress, reason: str) -> None | Awaitable[None]:
        """Called when a child actor exits."""

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.actor_id})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.actor_id})"
