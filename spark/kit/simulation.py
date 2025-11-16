"""Mission simulation harness."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable

from spark.kit.loader import SpecLoader
from spark.nodes.spec import MissionSimulationSpec, MissionSpec, SimulationToolOverrideSpec
from spark.tools.simulation.adapters import ToolExecutionRecord
from spark.tools.simulation.registry import MockResourceRegistry
from spark.utils.import_utils import import_from_ref


@dataclass(slots=True)
class SimulationRunResult:
    """Aggregate result of a simulation run."""

    outputs: Any
    policy_events: list[dict[str, Any]] = field(default_factory=list)
    tool_records: dict[str, list[ToolExecutionRecord]] = field(default_factory=dict)


class SimulationRunner:
    """Load a mission spec and execute it using simulation tool overrides."""

    def __init__(self, mission: MissionSpec, *, import_policy: str = 'safe') -> None:
        self.mission = mission
        self._import_policy = import_policy
        self._loader = SpecLoader(import_policy=import_policy, simulation_mode=True)

    async def run(
        self,
        *,
        inputs: dict[str, Any] | None = None,
        simulation_override: MissionSimulationSpec | None = None,
    ) -> SimulationRunResult:
        """Execute the mission graph with simulation hooks."""

        graph = self._loader.load_graph(self.mission.graph)
        sim_spec = simulation_override or self.mission.simulation
        registry = None
        if sim_spec and sim_spec.enabled:
            registry = self._configure_simulation(graph, sim_spec)

        graph_inputs = inputs or {}
        outputs = await graph.run(graph_inputs)
        policy_events = []
        try:
            policy_events = await graph.state.get('policy_events', [])
        except Exception:
            policy_events = []

        records: dict[str, list[ToolExecutionRecord]] = {}
        if registry:
            for tool_name in registry.list_tools():
                records[tool_name] = registry.get_records(tool_name)

        normalized_output = outputs.model_dump() if hasattr(outputs, 'model_dump') else outputs
        return SimulationRunResult(outputs=normalized_output, policy_events=policy_events, tool_records=records)

    def _configure_simulation(self, graph, sim_spec: MissionSimulationSpec) -> MockResourceRegistry:
        registry = MockResourceRegistry()
        self._register_tool_overrides(registry, sim_spec.tools)
        if not registry.list_tools():
            return registry
        for node in graph.nodes:
            tool_registry = getattr(node, 'tool_registry', None)
            if tool_registry:
                registry.install(tool_registry, latency_seconds=sim_spec.latency_seconds)
        return registry

    def _register_tool_overrides(
        self,
        registry: MockResourceRegistry,
        overrides: Iterable[SimulationToolOverrideSpec],
    ) -> None:
        for override in overrides:
            if override.handler:
                handler = import_from_ref(override.handler)
                registry.register(
                    tool_name=override.name,
                    description=override.description or f"Simulation override for {override.name}",
                    handler=handler,
                    parameters=override.parameters,
                    response_schema=override.response_schema,
                )
            else:
                registry.register_static_response(
                    tool_name=override.name,
                    description=override.description or f"Simulation response for {override.name}",
                    response=override.static_response,
                    parameters=override.parameters,
                    response_schema=override.response_schema,
                )
