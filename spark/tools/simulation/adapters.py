"""Simulation tool adapters for mocking external systems."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from spark.tools.types import BaseTool, ToolResult, ToolSpec


@dataclass(slots=True)
class ToolExecutionRecord:
    """Record describing a simulated invocation."""

    tool_name: str
    tool_use_id: str | None
    inputs: dict[str, Any]
    outputs: Any
    status: str
    started_at: float
    completed_at: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SimulationToolBundle:
    """Bundle describing a simulated tool + behavior."""

    tool_name: str
    description: str
    handler: Callable[[dict[str, Any]], Any]
    parameters: dict[str, Any] = field(default_factory=lambda: {'type': 'object', 'properties': {}, 'required': []})
    response_schema: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] = field(default_factory=dict)


class SimulationToolAdapter(BaseTool):
    """Convert a handler into a mock tool that records requests/responses."""

    def __init__(
        self,
        *,
        bundle: SimulationToolBundle,
        latency_seconds: float = 0.0,
        records: list[ToolExecutionRecord] | None = None,
    ) -> None:
        super().__init__()
        self._bundle = bundle
        self._latency = max(0.0, latency_seconds)
        self._records: list[ToolExecutionRecord] = records if records is not None else []

    @property
    def tool_name(self) -> str:
        return self._bundle.tool_name

    @property
    def tool_type(self) -> str:
        return 'simulation'

    @property
    def supports_hot_reload(self) -> bool:
        """Allow overriding existing tools when installing adapters."""
        return True

    @property
    def tool_spec(self) -> ToolSpec:
        payload: ToolSpec = {
            'name': self._bundle.tool_name,
            'description': self._bundle.description,
            'parameters': {'json': self._bundle.parameters},
        }
        if self._bundle.response_schema:
            payload['response_schema'] = self._bundle.response_schema
        if self._bundle.runtime_metadata:
            payload['x_spark'] = dict(self._bundle.runtime_metadata)
        return payload

    def __call__(self, *args: Any, **kwargs: Any) -> ToolResult:
        """Invoke the simulation handler and record metadata."""

        inputs = kwargs or {}
        start = time.time()
        if self._latency:
            time.sleep(self._latency)
        result = self._bundle.handler(inputs)
        if isinstance(result, dict) and 'toolUseId' in result:
            payload: ToolResult = result  # type: ignore[assignment]
        else:
            payload: ToolResult = {
                'content': [{'text': str(result)}],
                'status': 'success',
                'toolUseId': f"{self.tool_name}-{int(start * 1000)}",
                'metadata': {},
            }
        record = ToolExecutionRecord(
            tool_name=self.tool_name,
            tool_use_id=payload['toolUseId'],
            inputs=dict(inputs),
            outputs=result,
            status=payload['status'],
            started_at=start,
            completed_at=time.time(),
            metadata=dict(payload.get('metadata') or {}),
        )
        self._records.append(record)
        return payload

    def executions(self) -> list[ToolExecutionRecord]:
        """Return the recorded history of invocations."""

        return list(self._records)
