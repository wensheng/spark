"""
Mission packaging and deployment helpers (Phase 7).

Provides utilities to bundle MissionSpec payloads with schema/artifact
metadata and to run lightweight deployment readiness checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from spark.nodes.spec import MissionSpec
from spark.graphs.state_schema import MissionStateModel
from spark.kit.analysis import GraphAnalyzer
from spark.kit.loader import SpecLoader
from spark.nodes.serde import load_mission_spec


class MissionPackageError(RuntimeError):
    """Raised when mission packaging fails."""


class MissionPackageManifest(BaseModel):
    """Metadata describing a packaged mission."""

    package_id: str
    mission_id: str
    mission_version: str
    mission_file: str
    schema_file: Optional[str] = None
    artifact_policy_file: Optional[str] = None
    deployment: Optional[dict[str, Any]] = None
    created_at: str
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class MissionPackage:
    """Represents a packaged mission on disk."""

    path: Path
    manifest: MissionPackageManifest


class MissionPackager:
    """Create mission packages for deployment."""

    def __init__(self, output_root: Path | str) -> None:
        self.output_root = Path(output_root)

    def build_package(
        self,
        mission: MissionSpec,
        *,
        package_id: str | None = None,
        schema_cls: Type[MissionStateModel] | None = None,
        artifact_policy: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> MissionPackage:
        """Render mission, schema, and manifest into a package directory."""

        package_id = package_id or f"{mission.mission_id.replace('.', '-')}-{mission.version}"
        package_dir = self.output_root / package_id
        package_dir.mkdir(parents=True, exist_ok=True)

        mission_file = package_dir / 'mission.json'
        mission_file.write_text(json.dumps(mission.model_dump(), ensure_ascii=False, indent=2), encoding='utf-8')

        schema_file: Path | None = None
        if schema_cls:
            payload = {
                'metadata': schema_cls.schema_metadata(),
                'json_schema': schema_cls.model_json_schema(),
            }
            schema_file = package_dir / 'schema.json'
            schema_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

        artifact_policy_file: Path | None = None
        if artifact_policy:
            artifact_policy_file = package_dir / 'artifact_policy.json'
            artifact_policy_file.write_text(json.dumps(artifact_policy, ensure_ascii=False, indent=2), encoding='utf-8')

        files = ['mission.json']
        if schema_file:
            files.append(schema_file.name)
        if artifact_policy_file:
            files.append(artifact_policy_file.name)
        manifest = MissionPackageManifest(
            package_id=package_id,
            mission_id=mission.mission_id,
            mission_version=mission.version,
            mission_file='mission.json',
            schema_file=str(schema_file.name) if schema_file else None,
            artifact_policy_file=str(artifact_policy_file.name) if artifact_policy_file else None,
            deployment=mission.deployment.model_dump() if mission.deployment else None,
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
            metadata={'files': files},
        )

        manifest_file = package_dir / 'manifest.json'
        manifest_file.write_text(manifest.model_dump_json(indent=2), encoding='utf-8')
        return MissionPackage(path=package_dir, manifest=manifest)

    @staticmethod
    def load_manifest(package_path: Path | str) -> MissionPackageManifest:
        """Load package manifest from disk."""
        package_path = Path(package_path)
        manifest_file = package_path / 'manifest.json'
        if not manifest_file.exists():
            raise MissionPackageError(f"manifest.json not found under {package_path}")
        return MissionPackageManifest.model_validate_json(manifest_file.read_text(encoding='utf-8'))


class DeploymentReport(BaseModel):
    """Outcome of a deployment readiness check."""

    environment: Optional[str] = None
    semantic_issues: list[str] = Field(default_factory=list)
    graph_load_ok: bool = False
    loader_error: Optional[str] = None
    status: str = 'blocked'
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionDeployer:
    """Run deployment readiness checks + manifest bookkeeping."""

    def __init__(self, *, import_policy: str = 'allow_all') -> None:
        self.loader = SpecLoader(import_policy=import_policy)

    def load_package(self, package_dir: Path | str) -> tuple[MissionSpec, MissionPackageManifest]:
        package_dir = Path(package_dir)
        manifest = MissionPackager.load_manifest(package_dir)
        mission_path = package_dir / manifest.mission_file
        mission = load_mission_spec(str(mission_path))
        return mission, manifest

    def deploy_package(
        self,
        package_dir: Path | str,
        *,
        environment_override: str | None = None,
        workspace: Path | str | None = None,
        write_report: Path | str | None = None,
    ) -> DeploymentReport:
        """Validate mission package and produce a deployment report."""
        package_dir = Path(package_dir)
        mission, manifest = self.load_package(package_dir)

        environment = environment_override or (manifest.deployment or {}).get('environment')
        analyzer = GraphAnalyzer(mission.graph)
        semantic_issues = analyzer.validate_semantics()

        graph_load_ok = False
        loader_error: str | None = None
        try:
            self.loader.load_graph(mission.graph)
            graph_load_ok = True
        except Exception as exc:  # pragma: no cover - defensive logging
            loader_error = str(exc)

        status = 'ready' if not semantic_issues and graph_load_ok else 'blocked'
        metadata: dict[str, Any] = {
            'mission_id': mission.mission_id,
            'mission_version': mission.version,
            'package_id': manifest.package_id,
            'workspace': str(workspace) if workspace else None,
        }
        report = DeploymentReport(
            environment=environment,
            semantic_issues=semantic_issues,
            graph_load_ok=graph_load_ok,
            loader_error=loader_error,
            status=status,
            metadata=metadata,
        )

        if write_report:
            Path(write_report).write_text(report.model_dump_json(indent=2), encoding='utf-8')
        return report
