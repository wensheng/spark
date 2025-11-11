"""
Base types for the Spark Node.
"""

import copy
import time
from abc import ABC
from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Optional, TypeVar, Generic, TYPE_CHECKING

from typing_extensions import TypedDict  # PEP 728, python 3.15 available > 4.10.0
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from spark.graphs.graph_state import GraphState


class NodeMessage(BaseModel):
    """payload to/from nodes/agents"""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    id: str | None = Field(default=None, coerce_numbers_to_str=True)
    type: Literal['json', 'text'] = 'text'
    content: Any = None

    raw: Any = None
    """raw output from (LLM) inside process method before parsing"""

    metadata: dict = Field(default_factory=dict)
    """metadata about the message"""

    extras: dict = Field(default_factory=dict)
    """additional metadata about the message"""

    state: dict[str, Any] | None = None


class NodeState(TypedDict, extra_items=Any):  # type: ignore[call-arg]
    """State of the node."""

    context_snapshot: dict[str, Any] | None
    processing: bool
    pending_inputs: deque[NodeMessage]
    process_count: int


# TypeVar for NodeState and its subclasses
TNodeState = TypeVar('TNodeState', bound=NodeState)


def default_node_state(**kwargs) -> NodeState:
    """Create a default node state."""
    state: NodeState = {
        'context_snapshot': None,
        'processing': False,
        'pending_inputs': deque(),
        'process_count': 0,
    }
    state.update(kwargs)  # type: ignore
    return state


def _safe_copy(value: Any) -> Any:
    """Best-effort deep copy used when snapshotting context for errors."""
    try:
        return copy.deepcopy(value)
    except Exception:
        try:
            return copy.copy(value)
        except Exception:
            return value


@dataclass(slots=True)
class ExecutionMetadata:
    """Timing and attempt metadata captured for each run."""

    attempt: int = 1
    started_at: float | None = None
    finished_at: float | None = None

    def mark_started(self, attempt: int) -> None:
        """Mark the execution as started."""
        self.attempt = attempt
        self.started_at = time.perf_counter()
        self.finished_at = None

    def mark_finished(self) -> None:
        """Mark the execution as finished."""
        self.finished_at = time.perf_counter()

    @property
    def duration(self) -> float | None:
        """Get the duration of the execution."""
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def as_dict(self) -> dict[str, Any]:
        """Convert the execution metadata to a dictionary."""
        return {
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
        }


@dataclass(slots=True)
class ExecutionContext(Generic[TNodeState]):
    """
    Execution context for the node.process method.

    This context is passed to the node.process method.
    It contains the inputs, state, and metadata for the node.
    The state is from _state from the node
    The state can be changed by pre_process_hooks and post_process_hooks.
    The metadata is used to capture the execution metadata.
    The inputs are the inputs to the node.
    The graph_state is the global state shared across all nodes in the graph.
    """

    inputs: NodeMessage = field(default_factory=NodeMessage)
    state: TNodeState = field(default_factory=default_node_state)  # type: ignore[assignment]
    metadata: ExecutionMetadata = field(default_factory=ExecutionMetadata)
    outputs: Any | None = None
    graph_state: Optional['GraphState'] = None

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the current state for diagnostics."""

        return _safe_copy(self.state)

    def fork(self) -> "ExecutionContext[TNodeState]":
        """Produce a copy suitable for branch execution."""

        return ExecutionContext(
            inputs=_safe_copy(self.inputs),
            state=_safe_copy(self.state),
            metadata=replace(self.metadata),
            outputs=_safe_copy(self.outputs),
            graph_state=self.graph_state,
        )


class EventSink(ABC):
    """Abstract interface for recording structured node lifecycle events."""

    async def emit(self, event: dict) -> None:  # pragma: no cover - interface
        """Emit an event."""
        raise NotImplementedError


class NullEventSink(EventSink):
    """No-op sink used when observability is disabled."""

    async def emit(self, event: dict) -> None:  # pragma: no cover - intentional noop
        return None
