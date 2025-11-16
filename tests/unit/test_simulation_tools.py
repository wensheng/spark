"""Tests for simulation tool adapters and registries."""

from __future__ import annotations

import asyncio
import json
from argparse import Namespace

from spark.kit import spec_cli
from spark.kit.simulation import SimulationRunner
from spark.nodes.spec import (
    GraphSpec,
    MissionSimulationSpec,
    MissionSpec,
    NodeSpec,
    SimulationToolOverrideSpec,
)
from spark.tools.registry import ToolRegistry
from spark.tools.simulation.adapters import SimulationToolAdapter, SimulationToolBundle
from spark.tools.simulation.registry import MockResourceRegistry


def test_simulation_tool_adapter_records_invocations():
    bundle = SimulationToolBundle(
        tool_name='mock_lookup',
        description='Return a canned value.',
        handler=lambda inputs: {'value': inputs.get('key', 'default')},
    )
    adapter = SimulationToolAdapter(bundle=bundle, latency_seconds=0.0)
    result = adapter()
    assert result['status'] == 'success'
    assert adapter.executions()[0].outputs == {'value': 'default'}


def test_mock_resource_registry_installs_tools():
    registry = MockResourceRegistry()
    registry.register_static_response(
        tool_name='mock_search',
        description='Returns a static payload.',
        response={'documents': []},
    )
    tool_registry = ToolRegistry()
    registry.install(tool_registry)
    tool = tool_registry.get_tool('mock_search')
    result = tool()
    assert 'documents' in result['content'][0]['text']
    records = registry.get_records('mock_search')
    assert len(records) == 1


def _build_simulation_mission() -> MissionSpec:
    graph = GraphSpec(
        id='sim.graph',
        start='agent',
        nodes=[
            NodeSpec(
                id='agent',
                type='Agent',
                config={
                    'model': {'provider': 'echo', 'model_id': 'echo', 'client_args': {}, 'streaming': False},
                    'tools': [{'name': 'mock_tool', 'source': 'tests.unit.simulation:mock'}],
                },
            )
        ],
        edges=[],
    )
    sim_spec = MissionSimulationSpec(
        enabled=True,
        tools=[
            SimulationToolOverrideSpec(
                name='mock_tool',
                static_response={'status': 'ok'},
            )
        ],
    )
    return MissionSpec(
        mission_id='sim.mission',
        version='1.0',
        graph=graph,
        simulation=sim_spec,
    )


def test_simulation_runner_executes_with_overrides():
    mission = _build_simulation_mission()
    runner = SimulationRunner(mission, import_policy='allow_all')
    result = asyncio.run(runner.run())
    assert 'mock_tool' in result.tool_records


def test_simulation_cli_runs(tmp_path, capsys):
    mission = _build_simulation_mission()
    mission_path = tmp_path / 'mission.json'
    mission_path.write_text(mission.model_dump_json(indent=2), encoding='utf-8')
    args = Namespace(
        mission=str(mission_path),
        inputs=None,
        simulation_config=None,
        import_policy='allow_all',
        format='json',
    )
    rc = spec_cli.cmd_simulation_run(args)
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out)
    assert 'mock_tool' in payload['tool_records']
