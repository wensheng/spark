"""Mission control helpers: declarative plans and guardrails."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
import inspect
from typing import Any, Awaitable, Callable, Iterable, Optional, Sequence

from spark.graphs.hooks import GraphLifecycleEvent
from spark.graphs.graph import Graph
from spark.nodes.nodes import Node
from spark.graphs.workspace import Workspace, WorkspacePolicy

try:  # Optional telemetry dependency
    from spark.telemetry import EventType
except ImportError:  # pragma: no cover - optional dep
    EventType = None


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

    @classmethod
    def from_snapshot(cls, snapshot: list[dict[str, Any]]) -> "MissionPlan":
        steps: list[PlanStep] = []
        for raw in snapshot:
            steps.append(
                PlanStep(
                    id=raw['id'],
                    description=raw.get('description', raw['id']),
                    status=PlanStepStatus(raw.get('status', PlanStepStatus.PENDING.value)),
                    depends_on=list(raw.get('depends_on') or []),
                )
            )
        return MissionPlan(steps)

    def render_text(self) -> str:
        """Return a human-readable view of the plan status."""

        symbols = {
            PlanStepStatus.PENDING: '[ ]',
            PlanStepStatus.IN_PROGRESS: '[>]',
            PlanStepStatus.COMPLETED: '[x]',
            PlanStepStatus.BLOCKED: '[!]',
        }
        lines = []
        for step in self.steps:
            icon = symbols.get(step.status, '[?]')
            deps = f" deps={','.join(step.depends_on)}" if step.depends_on else ''
            lines.append(f"{icon} {step.id}: {step.description}{deps}")
        return "\n".join(lines)

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

@dataclass(slots=True)
class PlanAdaptiveContext:
    """Context data for adaptive plan hooks."""

    graph: Graph
    plan: MissionPlan
    step: PlanStep
    event: str  # 'step_started' | 'step_completed'


class PlanManager:
    """Registers lifecycle hooks to keep a mission plan in sync with graph execution."""

    def __init__(
        self,
        plan: MissionPlan,
        *,
        state_key: str = "mission_plan",
        auto_advance: bool = True,
        telemetry_topic: str | None = None,
        adaptive_hook: Callable[[PlanAdaptiveContext], Awaitable[None] | None] | None = None,
    ) -> None:
        self.plan = plan
        self.state_key = state_key
        self.auto_advance = auto_advance
        self.telemetry_topic = telemetry_topic
        self.adaptive_hook = adaptive_hook

    def attach(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        """Attach lifecycle hooks to a graph."""
        graph.register_hook(GraphLifecycleEvent.BEFORE_RUN, self._before_run)
        graph.register_hook(GraphLifecycleEvent.BEFORE_ITERATION, self._before_iteration)
        graph.register_hook(GraphLifecycleEvent.ITERATION_COMPLETE, self._after_iteration)

    async def _emit_plan_snapshot(self, graph: "Graph") -> None:  # type: ignore[name-defined]
        snapshot = self.plan.to_snapshot()
        if getattr(graph, "_state_enabled", False):
            await graph.state.set(self.state_key, snapshot)
        if self.telemetry_topic:
            await graph.event_bus.publish(self.telemetry_topic, {'plan': snapshot})
        telemetry_manager = getattr(graph, '_telemetry_manager', None)
        if getattr(graph, '_telemetry_enabled', False) and telemetry_manager and EventType:
            telemetry_manager.record_event(
                type=EventType.GRAPH_PROGRESS,
                name='Mission plan updated',
                trace_id=getattr(telemetry_manager, 'current_trace_id', None),
                attributes={'plan': snapshot},
            )

    async def _before_run(self, ctx) -> None:
        await self._emit_plan_snapshot(ctx.graph)

    async def _before_iteration(self, ctx) -> None:
        if not self.auto_advance:
            return
        active = self.plan.get_active_step()
        if active is None:
            next_step = self.plan.get_next_step()
            if next_step:
                next_step.status = PlanStepStatus.IN_PROGRESS
                await self._emit_plan_snapshot(ctx.graph)
                await self._maybe_call_adaptive(ctx.graph, 'step_started', next_step)

    async def _after_iteration(self, ctx) -> None:
        if not self.auto_advance:
            return
        active = self.plan.get_active_step()
        if active:
            active.status = PlanStepStatus.COMPLETED
            await self._emit_plan_snapshot(ctx.graph)
            await self._maybe_call_adaptive(ctx.graph, 'step_completed', active)

    async def _maybe_call_adaptive(self, graph: "Graph", event: str, step: PlanStep) -> None:
        if not self.adaptive_hook:
            return
        ctx = PlanAdaptiveContext(graph=graph, plan=self.plan, step=step, event=event)
        result = self.adaptive_hook(ctx)
        if inspect.isawaitable(result):
            await result


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

    def __init__(self, config: BudgetGuardrailConfig, *, state_key: str = 'guardrail_budget') -> None:
        self.config = config
        self._start_time: float | None = None
        self._iteration_count = 0
        self._state_key = state_key

    async def handle(self, ctx) -> None:
        event = ctx.metadata.get("event") if ctx.metadata else None
        if event == GraphLifecycleEvent.BEFORE_RUN.value or ctx.iteration_index == -1:
            self._start_time = time.time()
            self._iteration_count = 0
            await self._persist_budget(ctx)
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
        await self._persist_budget(ctx)

    async def _persist_budget(self, ctx) -> None:
        if not getattr(ctx.graph, '_state_enabled', False):
            return
        runtime = None
        if self._start_time is not None:
            runtime = max(time.time() - self._start_time, 0.0)
        payload = {
            'max_iterations': self.config.max_iterations,
            'iteration_count': self._iteration_count,
            'max_runtime_seconds': self.config.max_runtime_seconds,
            'elapsed_seconds': runtime,
        }
        await ctx.graph.state.set(self._state_key, payload)


class MissionControl:
    """High-level helper that wires plans and guardrails into graphs."""

    def __init__(
        self,
        plan: Optional[MissionPlan] = None,
        guardrails: Optional[Iterable[Guardrail]] = None,
        plan_telemetry_topic: str | None = None,
        plan_adaptive_hook: Callable[[PlanAdaptiveContext], Awaitable[None] | None] | None = None,
    ) -> None:
        self.plan_manager = (
            PlanManager(
                plan,
                telemetry_topic=plan_telemetry_topic,
                adaptive_hook=plan_adaptive_hook,
            )
            if plan
            else None
        )
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
    workspace: Workspace | None = None,
    workspace_config: dict[str, Any] | None = None,
) -> Graph:
    """Sense→Plan→Act→Evaluate mission template."""
    sense.goto(plan)
    plan.goto(act)
    act.goto(evaluate)
    workspace_obj = workspace or _build_workspace_from_config(workspace_config)
    graph = Graph(start=sense, initial_state=initial_state or {}, workspace=workspace_obj)

    plan_items = [
        PlanStep(id=f"step-{idx+1}", description=description)
        for idx, description in enumerate(plan_steps or ("Sense", "Plan", "Act", "Evaluate"))
    ]
    mission_plan = MissionPlan(plan_items)
    controller = MissionControl(plan=mission_plan, guardrails=guardrails)
    controller.attach(graph)
    return graph


def _build_workspace_from_config(config: dict[str, Any] | None) -> Workspace | None:
    if not config:
        return None
    payload = dict(config)
    policy_payload = payload.get('policy')
    if policy_payload is not None and not isinstance(policy_payload, WorkspacePolicy):
        payload['policy'] = WorkspacePolicy(**policy_payload)
    return Workspace(**payload)
