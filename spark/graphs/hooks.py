"""Graph lifecycle hooks and context definitions."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Coroutine, Optional, Protocol

if False:  # pragma: no cover - for type checking without import cycles
    from spark.graphs.graph import Graph
    from spark.graphs.tasks import Task
    from spark.nodes.types import NodeMessage


class GraphLifecycleEvent(str, Enum):
    """Supported lifecycle hook events for Graph execution."""

    BEFORE_RUN = "before_run"
    AFTER_RUN = "after_run"
    BEFORE_ITERATION = "before_iteration"
    AFTER_ITERATION = "after_iteration"
    PLAN_GENERATED = "plan_generated"
    ITERATION_COMPLETE = "iteration_complete"


@dataclass(slots=True)
class GraphLifecycleContext:
    """Context passed to lifecycle hooks."""

    graph: "Graph"
    task: "Task"
    iteration_index: int = -1
    last_output: Optional["NodeMessage"] = None
    metadata: dict[str, Any] = field(default_factory=dict)


HookFn = Callable[[GraphLifecycleContext], Awaitable[None] | None]


def ensure_coroutine(fn: HookFn, context: GraphLifecycleContext) -> Coroutine[Any, Any, Any]:
    """Wrap sync hooks in a coroutine so Graph can await uniformly."""

    async def _runner():
        result = fn(context)
        if inspect.isawaitable(result):
            await result

    return _runner()
