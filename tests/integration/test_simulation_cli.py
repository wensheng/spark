"""Integration tests for simulation CLI workflows."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from spark.nodes.spec import (
    GraphSpec,
    MissionSimulationSpec,
    MissionSpec,
    MissionStrategyBindingSpec,
    NodeSpec,
    ReasoningStrategySpec,
    SimulationToolOverrideSpec,
)


def _write_simulation_mission(path: Path) -> None:
    graph = GraphSpec(
        id='sim.graph',
        start='agent',
        nodes=[
            NodeSpec(
                id='agent',
                type='Agent',
                config={
                    'model': {'provider': 'echo', 'model_id': 'echo', 'client_args': {}, 'streaming': False},
                    'tools': [{'name': 'mock_tool', 'source': 'tests.integration.test_simulation_cli:mock'}],
                },
            )
        ],
        edges=[],
    )
    mission = MissionSpec(
        mission_id='sim.integration',
        version='1.0',
        graph=graph,
        strategies=[
            MissionStrategyBindingSpec(
                target='graph',
                reference='graph',
                strategy=ReasoningStrategySpec(type='plan_and_solve'),
            )
        ],
        simulation=MissionSimulationSpec(
            enabled=True,
            tools=[
                SimulationToolOverrideSpec(
                    name='mock_tool',
                    static_response={'status': 'ok'},
                )
            ],
        ),
    )
    path.write_text(mission.model_dump_json(indent=2), encoding='utf-8')


def test_simulation_run_cli(tmp_path):
    mission_path = tmp_path / 'mission.json'
    _write_simulation_mission(mission_path)
    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'spark.kit.spec_cli',
            'simulation-run',
            str(mission_path),
            '--import-policy',
            'allow_all',
            '--format',
            'json',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert 'mock_tool' in payload['tool_records']


def test_simulation_diff_cli(tmp_path):
    baseline = {
        'outputs': {'status': 'ok'},
        'policy_events': [],
        'tool_records': {'mock_tool': [{'outputs': {'status': 'ok'}}]},
    }
    candidate = {
        'outputs': {'status': 'changed'},
        'policy_events': [{'event': 'deny'}],
        'tool_records': {'mock_tool': []},
    }
    baseline_path = tmp_path / 'baseline.json'
    candidate_path = tmp_path / 'candidate.json'
    baseline_path.write_text(json.dumps(baseline), encoding='utf-8')
    candidate_path.write_text(json.dumps(candidate), encoding='utf-8')

    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'spark.kit.spec_cli',
            'simulation-diff',
            str(baseline_path),
            str(candidate_path),
            '--format',
            'json',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(proc.stdout)
    assert summary['outputs_equal'] is False
    assert summary['policy_events']['delta'] == 1


def mock(**_: dict) -> dict:
    """Placeholder tool referenced by simulation mission."""
    return {'status': 'real'}
