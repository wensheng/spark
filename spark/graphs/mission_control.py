"""Mission control helpers: declarative plans and guardrails."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional, Sequence

from spark.graphs.hooks import GraphLifecycleEvent
from spark.graphs.graph import Graph
from spark.nodes.nodes import Node


class PlanStepStatus(str, Enum):
    """Execution status for mission plan steps."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(slots=True)
class PlanStep:
    """Single step in a mission plan."""

    id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    depends_on: list[str] = field(default_factory=list)

    def is_ready(self, completed: set[str]) -> bool:
        """Return True if all dependencies have completed."""
        return all(dep in completed for dep in self.depends_on)


@dataclass
class MissionPlan:
    """Ordered set of plan steps that should be executed sequentially."""

    steps: list[PlanStep]

    def to_snapshot(self) -> list[dict[str, Any]]:
        """Serialize plan to a JSON-compatible list."""
        payload: list[dict[str, Any]] = []
        for step in self.steps:
            payload.append(
                {
                    "id": step.id,
                    "description": step.description,
                    "status": step.status.value,
                    "depends_on": list(step.depends_on),
                }
            )
        return payload

    def get_next_step(self) -> Optional[PlanStep]:
        """Return the next pending step whose dependencies are satisfied."""
        completed = {step.id for step in self.steps if step.status == PlanStepStatus.COMPLETED}
        for step in self.steps:
            if step.status == PlanStepStatus.PENDING and step.is_ready(completed):
                return step
        return None

    def get_active_step(self) -> Optional[PlanStep]:
        """Return the current in-progress step, if any."""
        for step in self.steps:
            if step.status == PlanStepStatus.IN_PROGRESS:
                return step
        return None

    def mark_completed(self, step: PlanStep | None = None) -> None:
        """Mark the specified step (or the active one) as completed."""
        target = step or self.get_active_step()
        if target:
            target.status = PlanStepStatus.COMPLETED


class PlanManager:
    """Registers lifecycle hooks to keep a mission plan in sync with graph execution."""

    def __init__(
        self,
        plan: MissionPlan,
        *,
        state_key: str = "mission_plan",
        auto_advance: bool = True,
    ) -> None:
        self.plan = plan
        self.state_key = state_key
        self.auto_advance = auto_advance

    def attach(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        """Attach lifecycle hooks to a graph."""
        graph.register_hook(GraphLifecycleEvent.BEFORE_RUN, self._before_run)
        graph.register_hook(GraphLifecycleEvent.BEFORE_ITERATION, self._before_iteration)
        graph.register_hook(GraphLifecycleEvent.ITERATION_COMPLETE, self._after_iteration)

    async def _persist(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        if getattr(graph, "_state_enabled", False):
            await graph.state.set(self.state_key, self.plan.to_snapshot())

    async def _before_run(self, ctx) -> None:
        await self._persist(ctx.graph)

    async def _before_iteration(self, ctx) -> None:
        if not self.auto_advance:
            return
        active = self.plan.get_active_step()
        if active is None:
            next_step = self.plan.get_next_step()
            if next_step:
                next_step.status = PlanStepStatus.IN_PROGRESS
                await self._persist(ctx.graph)

    async def _after_iteration(self, ctx) -> None:
        if not self.auto_advance:
            return
        active = self.plan.get_active_step()
        if active:
            active.status = PlanStepStatus.COMPLETED
            await self._persist(ctx.graph)


class GuardrailBreachError(RuntimeError):
    """Raised when a guardrail detects a budget violation."""


class Guardrail:
    """Base class for guardrails that respond to lifecycle events."""

    events: Iterable[GraphLifecycleEvent] = ()

    def attach(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        for event in self.events:
            graph.register_hook(event, self._handle_event)

    async def _handle_event(self, ctx) -> None:
        await self.handle(ctx)

    async def handle(self, ctx) -> None:  # pragma: no cover - override
        """Override in subclasses."""
        raise NotImplementedError


@dataclass
class BudgetGuardrailConfig:
    """Configuration for budget guardrails."""

    max_iterations: Optional[int] = None
    max_runtime_seconds: Optional[float] = None


class BudgetGuardrail(Guardrail):
    """Enforces iteration and runtime budgets."""

    events = (GraphLifecycleEvent.BEFORE_RUN, GraphLifecycleEvent.BEFORE_ITERATION)

    def __init__(self, config: BudgetGuardrailConfig) -> None:
        self.config = config
        self._start_time: float | None = None
        self._iteration_count = 0

    async def handle(self, ctx) -> None:
        event = ctx.metadata.get("event") if ctx.metadata else None
        if event == GraphLifecycleEvent.BEFORE_RUN.value or ctx.iteration_index == -1:
            self._start_time = time.time()
            self._iteration_count = 0
            return

        self._iteration_count += 1

        if self.config.max_iterations is not None and self._iteration_count > self.config.max_iterations:
            raise GuardrailBreachError(
                f"Iteration budget exceeded ({self._iteration_count} > {self.config.max_iterations})"
            )

        if self.config.max_runtime_seconds is not None and self._start_time is not None:
            runtime = time.time() - self._start_time
            if runtime > self.config.max_runtime_seconds:
                raise GuardrailBreachError(
                    f"Runtime budget exceeded ({runtime:.2f}s > {self.config.max_runtime_seconds}s)"
                )


class MissionControl:
    """High-level helper that wires plans and guardrails into graphs."""

    def __init__(
        self,
        plan: Optional[MissionPlan] = None,
        guardrails: Optional[Iterable[Guardrail]] = None,
    ) -> None:
        self.plan_manager = PlanManager(plan) if plan else None
        self.guardrails = list(guardrails or [])

    def attach(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        if self.plan_manager:
            self.plan_manager.attach(graph)
        for guardrail in self.guardrails:
            guardrail.attach(graph)


def spae_template(
    sense: Node,
    plan: Node,
    act: Node,
    evaluate: Node,
    *,
    initial_state: dict[str, Any] | None = None,
    plan_steps: Sequence[str] | None = None,
    guardrails: Iterable[Guardrail] | None = None,
) -> Graph:
    """Sense→Plan→Act→Evaluate mission template."""
    sense.goto(plan)
    plan.goto(act)
    act.goto(evaluate)
    graph = Graph(start=sense, initial_state=initial_state or {})

    plan_items = [
        PlanStep(id=f"step-{idx+1}", description=description)
        for idx, description in enumerate(plan_steps or ("Sense", "Plan", "Act", "Evaluate"))
    ]
    mission_plan = MissionPlan(plan_items)
    controller = MissionControl(plan=mission_plan, guardrails=guardrails)
    controller.attach(graph)
    return graph
