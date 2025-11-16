"""Placeholder tools used when loading missions in simulation mode."""

from __future__ import annotations

from typing import Any

from spark.tools.types import BaseTool, ToolSpec


class PlaceholderTool(BaseTool):
    """Stub tool that stands in for real implementations during simulation."""

    def __init__(self, tool_name: str) -> None:
        super().__init__()
        self._tool_name = tool_name

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def tool_type(self) -> str:
        return 'simulation_placeholder'

    @property
    def tool_spec(self) -> ToolSpec:
        return {
            'name': self._tool_name,
            'description': 'Simulation placeholder tool.',
            'parameters': {'json': {'type': 'object', 'properties': {}, 'required': []}},
        }

    @property
    def supports_hot_reload(self) -> bool:
        return True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(
            f"Tool '{self._tool_name}' is a simulation placeholder and cannot be invoked outside the harness."
        )
