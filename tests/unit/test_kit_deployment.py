"""
Tests for mission packaging + deployment helpers.
"""

from __future__ import annotations

import json

from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    MissionSpec,
    MissionPlanSpec,
    MissionPlanStepSpec,
    MissionStrategyBindingSpec,
    ReasoningStrategySpec,
)
from spark.graphs.state_schema import MissionStateModel
from spark.kit.deployment import MissionPackager, MissionDeployer, MissionPackageManifest


class SampleState(MissionStateModel):
    """Simple schema for packaging tests."""

    counter: int = 0


def _build_sample_mission() -> MissionSpec:
    graph = GraphSpec(
        id='mission.graph',
        start='entry',
        nodes=[NodeSpec(id='entry', type='Node')],
        edges=[],
    )
    plan = MissionPlanSpec(
        steps=[
            MissionPlanStepSpec(id='sense', description='collect'),
            MissionPlanStepSpec(id='act', description='act', depends_on=['sense']),
        ]
    )
    strategy = MissionStrategyBindingSpec(
        target='graph',
        reference='graph',
        strategy=ReasoningStrategySpec(type='plan_and_solve'),
    )
    return MissionSpec(
        mission_id='mission.testing',
        version='1.0',
        graph=graph,
        plan=plan,
        strategies=[strategy],
    )


def test_mission_packager_builds_manifest(tmp_path):
    mission = _build_sample_mission()
    packager = MissionPackager(tmp_path)
    package = packager.build_package(
        mission,
        package_id='pkg-001',
        schema_cls=SampleState,
        artifact_policy={'cleanup_on_success': True},
        notes='unit-test',
    )
    assert (package.path / 'mission.json').exists()
    assert (package.path / 'schema.json').exists()
    manifest = MissionPackager.load_manifest(package.path)
    assert isinstance(manifest, MissionPackageManifest)
    assert manifest.package_id == 'pkg-001'
    manifest_path = package.path / 'manifest.json'
    raw = json.loads(manifest_path.read_text())
    assert raw['notes'] == 'unit-test'


def test_mission_deployer_reports_status(tmp_path):
    mission = _build_sample_mission()
    packager = MissionPackager(tmp_path)
    package = packager.build_package(mission, package_id='pkg-002')
    report_path = tmp_path / 'report.json'
    deployer = MissionDeployer(import_policy='allow_all')
    report = deployer.deploy_package(
        package.path,
        environment_override='prod',
        workspace=tmp_path / 'workspace',
        write_report=report_path,
    )
    assert report.status == 'ready'
    assert report.environment == 'prod'
    assert report.graph_load_ok is True
    assert report_path.exists()
