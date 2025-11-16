"""Registry for simulation tools and mock resources."""

from __future__ import annotations

from typing import Any, Callable, Iterable

from spark.tools.registry import ToolRegistry

from .adapters import SimulationToolAdapter, SimulationToolBundle, ToolExecutionRecord


class MockResourceRegistry:
    """Track simulation bundles and export adapters for ToolRegistry."""

    def __init__(self) -> None:
        self._bundles: dict[str, SimulationToolBundle] = {}
        self._records: dict[str, list[ToolExecutionRecord]] = {}

    def register(
        self,
        *,
        tool_name: str,
        description: str,
        handler: Callable[[dict[str, Any]], Any],
        parameters: dict[str, Any] | None = None,
        response_schema: dict[str, Any] | None = None,
        runtime_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a simulation handler."""

        bundle = SimulationToolBundle(
            tool_name=tool_name,
            description=description,
            handler=handler,
            parameters=parameters or {'type': 'object', 'properties': {}, 'required': []},
            response_schema=response_schema,
            runtime_metadata=runtime_metadata or {},
        )
        self._bundles[tool_name] = bundle
        self._records.setdefault(tool_name, [])

    def register_static_response(
        self,
        *,
        tool_name: str,
        description: str,
        response: Any,
        parameters: dict[str, Any] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a simulation tool that always returns a static response."""

        def _handler(_: dict[str, Any]) -> Any:
            return response

        self.register(
            tool_name=tool_name,
            description=description,
            handler=_handler,
            parameters=parameters,
            response_schema=response_schema,
        )

    def install(self, registry: ToolRegistry, *, latency_seconds: float = 0.0) -> list[str]:
        """Register adapters for all bundles with the provided ToolRegistry."""

        installed: list[str] = []
        for bundle in self._bundles.values():
            adapter = SimulationToolAdapter(
                bundle=bundle,
                latency_seconds=latency_seconds,
                records=self._records[bundle.tool_name],
            )
            registry.register_tool(adapter)
            installed.append(bundle.tool_name)
        return installed

    def list_tools(self) -> list[str]:
        """Return the names of registered simulation tools."""

        return sorted(self._bundles.keys())

    def get_records(self, tool_name: str) -> list[ToolExecutionRecord]:
        """Return execution records for a registered simulation tool."""

        if tool_name not in self._records:
            raise KeyError(f"Simulation tool '{tool_name}' is not registered.")
        return list(self._records[tool_name])
