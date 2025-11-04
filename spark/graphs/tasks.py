"""
Tasks for the graphs.
"""

from typing import Any
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from spark.nodes.types import NodeMessage


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
