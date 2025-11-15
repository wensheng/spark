"""Task metadata, dependency scheduling, and campaign tracking."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Deque, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spark.nodes.types import NodeMessage


@dataclass(slots=True)
class TaskBatchResult:
    """Aggregate result for scheduled task execution."""

    completed: dict[str, Any] = field(default_factory=dict)
    failed: dict[str, Exception] = field(default_factory=dict)

    def raise_for_errors(self) -> None:
        """Raise the first error if any tasks failed."""

        if not self.failed:
            return
        task_id, error = next(iter(self.failed.items()))
        raise RuntimeError(
            f"{len(self.failed)} task(s) failed; first failure from task '{task_id}'"
        ) from error


class TaskType(StrEnum):
    """type of the task"""

    ONE_OFF = "oneoff"

    LONG_RUNNING = "longrunning"

    STREAMING = "streaming"

    RESUMABLE = "resumable"
    """resumable long running task, can be resumed from the last checkpoint"""


class Budget(BaseModel):
    """budget of the task"""

    max_tokens: int = 0
    """max tokens of the task, 0 means unlimited"""

    max_seconds: int = 0
    """max seconds of the task, 0 means unlimited"""

    max_cost: float = 0
    """max cost of the task, 0 means unlimited"""


class CampaignInfo(BaseModel):
    """Metadata describing a campaign that a task belongs to."""

    campaign_id: str
    """Unique identifier for the campaign."""

    name: str | None = None
    owner: str | None = None
    description: str | None = None

    budget: Budget | None = None
    """Optional aggregate budget for all tasks under this campaign."""

    sla_seconds: int | None = None
    """Optional SLA target for the campaign."""


class Task(BaseModel):
    """
    A task is a unit of work that can be executed by a graph.
    """

    model_config = ConfigDict(extra='allow')

    task_id: str | None = None

    type: TaskType = TaskType.ONE_OFF
    """The type of the task."""

    inputs: NodeMessage = Field(default_factory=NodeMessage, description="The inputs of the task.")

    input_schema: dict[str, Any] = Field(default_factory=dict, description="The input schema of the task.")

    error: dict | None = None
    """The error of the task."""

    budget: Budget = Field(default_factory=lambda: Budget())
    """The budget of the task."""

    correlation_id: str | None = None
    """The correlation id of the task."""

    depends_on: list[str] = Field(default_factory=list, description="Task IDs that must complete before this task runs.")

    priority: int = 0
    """Higher values run earlier when multiple tasks are ready."""

    campaign: CampaignInfo | None = Field(default=None, description="Campaign metadata for grouped budgets.")

    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata for schedulers.")
    resume_from: str | None = Field(default=None, description="Checkpoint identifier to resume from.")

    @model_validator(mode="after")
    def validate_dependencies(self) -> "Task":
        """Ensure tasks supply IDs when dependencies are declared."""
        if self.depends_on and not self.task_id:
            raise ValueError("Task with dependencies must set task_id.")
        return self

    def is_ready(self, completed_ids: set[str] | None = None) -> bool:
        """Return True if dependencies are satisfied."""
        if not self.depends_on:
            return True
        completed = completed_ids or set()
        return all(dep in completed for dep in self.depends_on)


class TaskDependencyError(RuntimeError):
    """Raised when attempting to schedule a task whose dependencies are not met."""


class CampaignBudgetError(RuntimeError):
    """Raised when campaign budget limits are exceeded."""


class TaskScheduler:
    """Simple scheduler that enforces dependencies, priorities, and campaign budgets."""

    def __init__(
        self,
        tasks: Iterable[Task] | None = None,
        *,
        completed: Iterable[str] | None = None,
        concurrency_limit: int | None = None,
    ) -> None:
        self._tasks: dict[str, Task] = {}
        self._ready: Deque[str] = deque()
        self._inflight: set[str] = set()
        self._completed: set[str] = set(completed or [])
        self._concurrency_limit = concurrency_limit
        self._campaign_usage: dict[str, dict[str, float]] = {}
        self._campaign_budgets: dict[str, Budget] = {}
        if tasks:
            for task in tasks:
                self.add_task(task)

    def add_task(self, task: Task) -> None:
        """Register a task with the scheduler."""
        if not task.task_id:
            raise ValueError("Task must have task_id to be scheduled.")
        self._tasks[task.task_id] = task
        if task.campaign and task.campaign.budget:
            self._campaign_budgets.setdefault(task.campaign.campaign_id, task.campaign.budget)
        self._maybe_enqueue(task)

    def _maybe_enqueue(self, task: Task) -> None:
        if task.task_id in self._completed or task.task_id in self._inflight:
            return
        if task.is_ready(self._completed) and task.task_id not in self._ready:
            self._ready.append(task.task_id)

    def acquire_next_task(self) -> Task | None:
        """Return the next ready task (respecting concurrency limit)."""
        if self._concurrency_limit and len(self._inflight) >= self._concurrency_limit:
            return None
        while self._ready:
            # Use highest priority task among ready ones
            ready_ids = list(self._ready)
            ready_ids.sort(key=lambda task_id: -self._tasks[task_id].priority)
            next_id = ready_ids[0]
            self._ready = deque([task_id for task_id in ready_ids[1:]])
            if next_id in self._completed or next_id in self._inflight:
                continue
            task = self._tasks[next_id]
            self._inflight.add(next_id)
            return task
        return None

    def mark_completed(self, task_id: str) -> None:
        """Mark a task as completed and update dependency graph."""
        self._inflight.discard(task_id)
        self._completed.add(task_id)
        for pending in self._tasks.values():
            self._maybe_enqueue(pending)

    def mark_failed(self, task_id: str) -> None:
        """Remove task from inflight without marking complete."""
        self._inflight.discard(task_id)

    def record_campaign_usage(
        self,
        task: Task,
        *,
        tokens: int = 0,
        seconds: float = 0,
        cost: float = 0.0,
    ) -> None:
        """Track campaign resource consumption for guardrails."""
        if not task.campaign:
            return
        campaign_id = task.campaign.campaign_id
        usage = self._campaign_usage.setdefault(campaign_id, {'tokens': 0, 'seconds': 0.0, 'cost': 0.0})
        budget = self._campaign_budgets.get(campaign_id)

        if budget and budget.max_tokens and usage['tokens'] + tokens > budget.max_tokens:
            raise CampaignBudgetError(
                f"Campaign {campaign_id} exceeded token budget ({usage['tokens'] + tokens} > {budget.max_tokens})"
            )
        if budget and budget.max_seconds and usage['seconds'] + seconds > budget.max_seconds:
            raise CampaignBudgetError(
                f"Campaign {campaign_id} exceeded runtime budget ({usage['seconds'] + seconds:.2f} > {budget.max_seconds})"
            )
        if budget and budget.max_cost and usage['cost'] + cost > budget.max_cost:
            raise CampaignBudgetError(
                f"Campaign {campaign_id} exceeded cost budget ({usage['cost'] + cost:.2f} > {budget.max_cost})"
            )

        usage['tokens'] += tokens
        usage['seconds'] += seconds
        usage['cost'] += cost

    @property
    def pending(self) -> list[str]:
        """Return IDs of tasks that have not completed."""
        return [task_id for task_id in self._tasks if task_id not in self._completed]

    @property
    def completed(self) -> set[str]:
        return set(self._completed)

    @property
    def inflight(self) -> set[str]:
        return set(self._inflight)
