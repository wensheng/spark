"""Tests for MissionPlan visualization and CLI helpers."""

from __future__ import annotations

import json
from argparse import Namespace

from spark.graphs.mission_control import MissionPlan, PlanStep, PlanStepStatus
from spark.kit import spec_cli


def test_mission_plan_render_text():
    plan = MissionPlan(
        steps=[
            PlanStep(id='prep', description='Prepare', status=PlanStepStatus.COMPLETED),
            PlanStep(id='execute', description='Execute work', status=PlanStepStatus.IN_PROGRESS),
            PlanStep(id='verify', description='Verify output', status=PlanStepStatus.PENDING, depends_on=['execute']),
        ]
    )
    rendered = plan.render_text()
    assert '[x] prep' in rendered
    assert '[>]' in rendered
    assert 'deps=execute' in rendered


def test_plan_render_cli(tmp_path, capsys):
    plan_snapshot = [
        {'id': 'prep', 'description': 'Prep', 'status': 'completed'},
        {'id': 'run', 'description': 'Run', 'status': 'pending'},
    ]
    path = tmp_path / 'plan.json'
    path.write_text(json.dumps(plan_snapshot), encoding='utf-8')
    args = Namespace(file=str(path))
    rc = spec_cli.cmd_plan_render(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert 'prep' in captured.out
