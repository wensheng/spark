"""
CLI for Spark spec operations.

Commands:
 - export: Serialize a Python Graph to JSON spec
 - validate: Validate a JSON spec against the schema
 - compile: Reverse-compile JSON spec to Python code
 - generate: Create a JSON spec from a description
 - analyze: Analyze graph structure and complexity
 - diff: Compare two specs and show differences
 - optimize: Suggest and apply optimizations
 - test: Test spec validity and round-trip conversion
 - introspect: Inspect Python graph and show detailed info
 - merge: Merge multiple specs into one
 - extract: Extract subgraph from a spec
 - approval-list: List governance approvals stored in GraphState
 - approval-resolve: Approve or reject a pending approval request
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Type

from spark.governance.approval import ApprovalGateManager, ApprovalStatus
from spark.governance.policy import PolicyEffect, PolicyRule, PolicySet
from spark.graphs.artifacts import ArtifactPolicy
from spark.graphs.base import BaseGraph
from spark.graphs.graph_state import GraphState
from spark.graphs.mission_control import MissionPlan
from spark.graphs.state_backend import JSONFileStateBackend, SQLiteStateBackend
from spark.graphs.state_schema import MissionStateModel
from spark.kit.analysis import GraphAnalyzer
from spark.kit.codegen import CodeGenerator, generate
from spark.kit.deployment import MissionDeployer, MissionPackager
from spark.kit.diff import SpecDiffer, diff_mission_specs
from spark.kit.simulation import SimulationRunner, SimulationRunResult
from spark.nodes.serde import (
    graph_to_spec,
    load_graph_spec,
    load_mission_spec,
    save_graph_json,
    save_mission_spec,
)
from spark.nodes.spec import (
    EdgeSpec,
    GraphSpec,
    MissionDeploymentSpec,
    MissionPlanSpec,
    MissionPlanStepSpec,
    MissionSimulationSpec,
    MissionSpec,
    MissionStateSchemaSpec,
    MissionStrategyBindingSpec,
    NodeSpec,
    ReasoningStrategySpec,
)


def _import_attr(target: str) -> Any:
    if ':' not in target:
        raise ValueError("target must be in form 'module:attr'")
    mod_name, attr_name = target.split(':', 1)
    module = importlib.import_module(mod_name)
    return getattr(module, attr_name)


def _resolve_target(target: str) -> Any:
    """Import module:attr and return attribute value or callable result."""
    obj = _import_attr(target)
    if callable(obj):
        result = obj()
    else:
        result = obj
    return result


def _resolve_schema(target: str) -> Type[MissionStateModel]:
    """Load a MissionStateModel class from module:attr reference."""

    obj = _import_attr(target)
    if isinstance(obj, type) and issubclass(obj, MissionStateModel):
        return obj
    if isinstance(obj, MissionStateModel):
        return obj.__class__
    raise TypeError(f"Target '{target}' is not a MissionStateModel subclass")


def _extract_schema_fields(schema_cls: Type[MissionStateModel]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for name, fld in schema_cls.model_fields.items():
        annotation = fld.annotation
        type_name = getattr(annotation, '__name__', str(annotation))
        fields[name] = {
            'type': type_name,
            'required': fld.is_required(),
            'default': None if fld.is_required() else fld.default,
        }
    return fields


def _resolve_artifact_policy(value: str | None) -> dict[str, Any] | None:
    """Resolve artifact policy metadata from JSON file, inline JSON, or module reference."""
    if not value:
        return None
    path = Path(value)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        target = _import_attr(value)
        if callable(target):
            target = target()
        if isinstance(target, ArtifactPolicy):
            return asdict(target)
        if isinstance(target, dict):
            return target
        raise TypeError(f"Artifact policy target '{value}' must return dict or ArtifactPolicy")


# =============================================================================
# Governance helpers
# =============================================================================


def _build_state_backend(path: str, backend: str, table: str | None = None):
    """Instantiate a GraphState backend from CLI options."""

    if backend == 'file':
        return JSONFileStateBackend(path)
    if backend == 'sqlite':
        return SQLiteStateBackend(path, table_name=table or 'graph_state')
    raise ValueError(f"Unsupported backend '{backend}'. Use 'file' or 'sqlite'.")


async def _load_graph_state_for_cli(args: argparse.Namespace) -> GraphState:
    """Initialize GraphState against a persisted backend for CLI ops."""

    backend = _build_state_backend(args.state, getattr(args, 'backend', 'file'), getattr(args, 'table', None))
    graph_state = GraphState(backend=backend)
    await graph_state.initialize()
    return graph_state


async def _load_approval_manager(args: argparse.Namespace) -> ApprovalGateManager:
    """Return an ApprovalGateManager bound to CLI-provided state."""

    state = await _load_graph_state_for_cli(args)
    storage_key = getattr(args, 'storage_key', 'approval_requests')
    return ApprovalGateManager(state, storage_key=storage_key)


def _load_policy_set(path: str) -> PolicySet:
    with open(path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    return PolicySet.model_validate(payload)


# ==============================================================================
# Existing Commands
# ==============================================================================

def cmd_export(args: argparse.Namespace) -> int:
    """Export a Python `BaseGraph` target to JSON spec, optionally to a file."""
    obj = _resolve_target(args.target)
    if not isinstance(obj, BaseGraph):
        # Accept a factory returning BaseGraph when awaited or called
        if callable(obj):
            obj = obj()
        if not isinstance(obj, BaseGraph):
            print('Error: target is not a BaseGraph instance', file=sys.stderr)
            return 2

    # Support full-fidelity export
    full_fidelity = getattr(args, 'full_fidelity', False)

    if args.output:
        save_graph_json(args.output, obj, spark_version=args.version, indent=2)
        print(f'Wrote spec to {args.output}')
        return 0
    spec = graph_to_spec(obj, spark_version=args.version)
    print(json.dumps(spec.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a JSON spec file and print a brief summary or error."""
    try:
        spec = load_graph_spec(args.file)
    except Exception as exc:
        print(f'Invalid: {exc}', file=sys.stderr)
        return 2

    print(f'Valid spec: id={spec.id}, nodes={len(spec.nodes)}, edges={len(spec.edges)}')

    # Semantic validation if requested
    if getattr(args, 'semantic', False):
        analyzer = GraphAnalyzer(spec)
        issues = analyzer.validate_semantics()
        if issues:
            print('\nSemantic issues found:')
            for issue in issues:
                print(f'  ⚠ {issue}')
            if getattr(args, 'strict', False):
                return 2
        else:
            print('✓ No semantic issues detected')

    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Compile a JSON spec into Python code using the codegen tool."""
    spec = load_graph_spec(args.file)
    out_dir = args.output or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)

    # Support style parameter
    style = getattr(args, 'style', 'simple')

    try:
        out_path = generate(spec, out_dir, style=style)
    except NotImplementedError:
        # Skeleton fallback: write a placeholder
        fname = os.path.join(out_dir, f"graph_{spec.id.replace('.', '_')}.py")
        with open(fname, 'w', encoding='utf-8') as f:
            f.write('# TODO: implement reverse compiler\n')
            f.write(f'# Graph id: {spec.id}\n')
        print(f'Wrote skeleton to {fname}')
        return 0

    print(f'Generated code: {out_path}')

    # Generate tests if requested
    if getattr(args, 'tests', False):
        test_path = out_path.replace('.py', '_test.py')
        with open(test_path, 'w') as f:
            f.write(f'"""Tests for generated graph {spec.id}"""\n')
            f.write('import pytest\n\n')
            f.write('def test_graph_construction():\n')
            f.write('    """Test graph can be constructed."""\n')
            f.write('    from ')
            f.write(os.path.basename(out_path).replace('.py', ''))
            f.write(' import build_graph\n')
            f.write('    graph = build_graph()\n')
            f.write('    assert graph is not None\n')
        print(f'Generated tests: {test_path}')

    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a minimal graph JSON spec from a description or file path."""
    desc = args.desc
    if os.path.isfile(desc):
        with open(desc, 'r', encoding='utf-8') as f:
            desc = f.read().strip()

    # Offline minimal template: single node echo flow
    node_id = 'entry'
    node = NodeSpec(id=node_id, type='Node', description=desc or 'generated', config={})
    graph = GraphSpec(id='generated.graph', description=desc or None, start=node_id, nodes=[node], edges=[])

    payload = graph.model_dump()
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f'Wrote spec to {args.output}')
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_mission_generate(args: argparse.Namespace) -> int:
    """Generate a mission spec (graph + plan + strategies) from a description."""
    desc = args.desc
    if os.path.isfile(desc):
        with open(desc, 'r', encoding='utf-8') as f:
            desc = f.read().strip()

    node_id = 'entry'
    node = NodeSpec(id=node_id, type='Node', description=desc or 'entry node', config={})
    graph = GraphSpec(
        id=f'{args.mission_id}.graph',
        description=desc or None,
        start=node_id,
        nodes=[node],
        edges=[],
    )

    plan = None
    if not args.no_plan:
        plan = MissionPlanSpec(
            name='spae_plan',
            description='Sense → Plan → Act → Evaluate scaffold',
            steps=[
                MissionPlanStepSpec(id='sense', description='Collect mission context'),
                MissionPlanStepSpec(id='plan', description='Draft mission plan', depends_on=['sense']),
                MissionPlanStepSpec(id='act', description='Execute nodes/tools', depends_on=['plan']),
                MissionPlanStepSpec(id='evaluate', description='Review outcomes', depends_on=['act']),
            ],
        )

    strategies: list[MissionStrategyBindingSpec] = []
    if not args.no_strategy:
        strategy_cfg = {'type': args.strategy}
        if args.strategy == 'custom':
            if not args.strategy_class:
                print('custom strategy requires --strategy-class', file=sys.stderr)
                return 2
            strategy_cfg['custom_class'] = args.strategy_class
        strategies.append(
            MissionStrategyBindingSpec(
                target='graph',
                reference='graph',
                strategy=ReasoningStrategySpec.model_validate(strategy_cfg),
            )
        )

    state_schema = None
    if not args.no_schema:
        state_schema = MissionStateSchemaSpec(name=args.schema_name, version=args.schema_version)

    deployment = None
    if not args.no_deployment:
        deployment = MissionDeploymentSpec(
            environment=args.deploy_environment,
            runtime=args.deploy_runtime,
            entrypoint=args.deploy_entrypoint,
            health_check=args.deploy_health_check,
        )

    mission = MissionSpec(
        mission_id=args.mission_id,
        version=args.version,
        description=desc or None,
        graph=graph,
        plan=plan,
        strategies=strategies,
        state_schema=state_schema,
        deployment=deployment,
    )

    if args.output:
        save_mission_spec(args.output, mission, indent=2)
        print(f'Wrote mission spec to {args.output}')
    else:
        print(json.dumps(mission.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_mission_validate(args: argparse.Namespace) -> int:
    """Validate a mission spec JSON file."""
    try:
        mission = load_mission_spec(args.file)
    except Exception as exc:
        print(f'Invalid mission spec: {exc}', file=sys.stderr)
        return 2

    print(f'Valid mission spec: {mission.mission_id} v{mission.version}')
    print(f'  Graph nodes={len(mission.graph.nodes)}, edges={len(mission.graph.edges)}')
    if mission.plan:
        print(f'  Plan steps={len(mission.plan.steps)}')
    if mission.strategies:
        print(f'  Strategy bindings={len(mission.strategies)}')

    if getattr(args, 'semantic', False):
        analyzer = GraphAnalyzer(mission.graph)
        issues = analyzer.validate_semantics()
        if issues:
            print('\nSemantic issues:')
            for issue in issues:
                print(f'  ⚠ {issue}')
            if getattr(args, 'strict', False):
                return 2
        else:
            print('✓ No semantic issues detected')

    return 0


def cmd_mission_diff(args: argparse.Namespace) -> int:
    """Diff two mission specs (graph + metadata)."""
    try:
        mission_old = load_mission_spec(args.old)
        mission_new = load_mission_spec(args.new)
    except Exception as exc:
        print(f'Error loading mission specs: {exc}', file=sys.stderr)
        return 2

    diff_result = diff_mission_specs(mission_old, mission_new)
    if args.format == 'json':
        print(json.dumps(diff_result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(diff_result)

    return 1 if diff_result.has_changes else 0


def cmd_mission_package(args: argparse.Namespace) -> int:
    """Bundle mission spec + schema/artifact metadata into a package directory."""
    try:
        mission = load_mission_spec(args.file)
    except Exception as exc:
        print(f'Invalid mission spec: {exc}', file=sys.stderr)
        return 2

    schema_cls: Type[MissionStateModel] | None = None
    if args.schema:
        try:
            schema_cls = _resolve_schema(args.schema)
        except Exception as exc:  # pragma: no cover - defensive
            print(f'Failed to resolve schema {args.schema}: {exc}', file=sys.stderr)
            return 2

    artifact_policy = _resolve_artifact_policy(getattr(args, 'artifact_policy', None))

    output_dir = args.output_dir or os.getcwd()
    packager = MissionPackager(output_dir)
    package = packager.build_package(
        mission,
        package_id=args.package_id,
        schema_cls=schema_cls,
        artifact_policy=artifact_policy,
        notes=args.notes,
    )
    print(f"Packaged mission to {package.path}")
    print(f"Manifest: {package.path / 'manifest.json'}")
    return 0


def cmd_mission_deploy(args: argparse.Namespace) -> int:
    """Run deployment readiness checks on a mission package."""
    package_path = args.package
    workspace = args.workspace
    if workspace:
        Path(workspace).mkdir(parents=True, exist_ok=True)
    deployer = MissionDeployer(import_policy=getattr(args, 'import_policy', 'allow_all'))
    report = deployer.deploy_package(
        package_path,
        environment_override=args.environment,
        workspace=workspace,
        write_report=args.report,
    )
    print(f"Deployment status: {report.status}")
    if report.environment:
        print(f"Environment: {report.environment}")
    if report.semantic_issues:
        print("Semantic issues:")
        for issue in report.semantic_issues:
            print(f"  ⚠ {issue}")
    if not report.graph_load_ok and report.loader_error:
        print(f"Graph load error: {report.loader_error}", file=sys.stderr)
    if args.report:
        print(f"Wrote deployment report to {args.report}")
    return 0 if report.status == 'ready' else 1


# ==============================================================================
# New Commands (Phase 5)
# ==============================================================================

def cmd_analyze(args: argparse.Namespace) -> int:
    """Analyze graph structure and complexity."""
    try:
        spec = load_graph_spec(args.file)
    except Exception as exc:
        print(f'Error loading spec: {exc}', file=sys.stderr)
        return 2

    analyzer = GraphAnalyzer(spec)

    # Generate report
    if getattr(args, 'report', None):
        report = analyzer.generate_metrics_report()
        if args.report.endswith('.html'):
            # Generate HTML report
            html_report = f"""<!DOCTYPE html>
<html>
<head>
    <title>Graph Analysis Report - {spec.id}</title>
    <style>
        body {{ font-family: monospace; padding: 20px; background: #f5f5f5; }}
        pre {{ background: white; padding: 20px; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>Graph Analysis Report</h1>
    <pre>{report}</pre>
</body>
</html>"""
            with open(args.report, 'w') as f:
                f.write(html_report)
            print(f'Wrote HTML report to {args.report}')
        else:
            with open(args.report, 'w') as f:
                f.write(report)
            print(f'Wrote report to {args.report}')
    else:
        # Print to stdout
        print(analyzer.generate_metrics_report())

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare two specs and show differences."""
    try:
        spec1 = load_graph_spec(args.old)
        spec2 = load_graph_spec(args.new)
    except Exception as exc:
        print(f'Error loading specs: {exc}', file=sys.stderr)
        return 2

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    # Output format
    output_format = getattr(args, 'format', 'unified')

    if output_format == 'unified':
        print(str(result))
    elif output_format == 'json':
        summary = result.summary
        summary['has_changes'] = result.has_changes
        print(json.dumps(summary, indent=2))
    elif output_format == 'summary':
        if result.has_changes:
            summary = result.summary
            print('Changes detected:')
            for key, value in summary.items():
                if value > 0:
                    print(f'  {key}: {value}')
        else:
            print('No changes detected')

    return 0 if not result.has_changes else 1


def cmd_optimize(args: argparse.Namespace) -> int:
    """Suggest and apply optimizations."""
    try:
        spec = load_graph_spec(args.file)
    except Exception as exc:
        print(f'Error loading spec: {exc}', file=sys.stderr)
        return 2

    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    print('Optimization suggestions:')
    for suggestion in suggestions:
        print(f'  • {suggestion}')

    # Auto-fix if requested
    if getattr(args, 'auto_fix', False):
        # Remove unreachable nodes
        complexity = analyzer.analyze_complexity()
        if complexity['unreachable_nodes']:
            reachable = [n for n in spec.nodes if n.id not in complexity['unreachable_nodes']]
            spec.nodes = reachable
            print(f"\nRemoved {len(complexity['unreachable_nodes'])} unreachable nodes")

        # Save optimized spec
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(spec.model_dump(), f, indent=2)
            print(f'Wrote optimized spec to {args.output}')

    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Test spec validity and round-trip conversion."""
    try:
        spec = load_graph_spec(args.file)
    except Exception as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 2

    print(f'✓ Spec is valid: {spec.id}')

    # Semantic validation
    if getattr(args, 'validate', False):
        analyzer = GraphAnalyzer(spec)
        issues = analyzer.validate_semantics()
        if issues:
            print('\nSemantic issues:')
            for issue in issues:
                print(f'  ⚠ {issue}')
            return 2
        else:
            print('✓ Semantic validation passed')

    # Round-trip test
    if getattr(args, 'round_trip', False):
        print('\nTesting round-trip conversion...')

        # Convert to code
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                generate(spec, tmpdir, style='production')
                print('✓ Code generation succeeded')
            except Exception as exc:
                print(f'✗ Code generation failed: {exc}', file=sys.stderr)
                return 2

        # Re-serialize spec
        try:
            spec_dict = spec.model_dump()
            spec2 = GraphSpec.model_validate(spec_dict)
            print('✓ Round-trip serialization succeeded')
        except Exception as exc:
            print(f'✗ Round-trip serialization failed: {exc}', file=sys.stderr)
            return 2

    print('\n✓ All tests passed')
    return 0


def cmd_introspect(args: argparse.Namespace) -> int:
    """Inspect Python graph and show detailed info."""
    try:
        obj = _resolve_target(args.target)
    except Exception as exc:
        print(f'Error loading target: {exc}', file=sys.stderr)
        return 2

    if not isinstance(obj, BaseGraph):
        if callable(obj):
            obj = obj()
        if not isinstance(obj, BaseGraph):
            print('Error: target is not a BaseGraph instance', file=sys.stderr)
            return 2

    # Convert to spec for analysis
    spec = graph_to_spec(obj)
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    output_format = getattr(args, 'format', 'text')

    if output_format == 'json':
        info = {
            'id': spec.id,
            'description': spec.description,
            'start': spec.start,
            'nodes': [{'id': n.id, 'type': n.type, 'description': n.description} for n in spec.nodes],
            'edges': [{'id': e.id, 'from': e.from_node, 'to': e.to_node} for e in spec.edges],
            'complexity': complexity
        }
        print(json.dumps(info, indent=2))
    else:
        print(f'Graph: {spec.id}')
        if spec.description:
            print(f'Description: {spec.description}')
        print(f'Start: {spec.start}')
        print(f'\nNodes ({len(spec.nodes)}):')
        for node in spec.nodes:
            print(f'  - {node.id} ({node.type}): {node.description or ""}')
        print(f'\nEdges ({len(spec.edges)}):')
        for edge in spec.edges:
            print(f'  - {edge.from_node} → {edge.to_node}')
        print(f'\nComplexity:')
        print(f'  Max depth: {complexity["max_depth"]}')
        print(f'  Branching factor: {complexity["branching_factor"]:.2f}')
        print(f'  Cyclic: {complexity["cyclic"]}')

    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    """Merge multiple specs into one."""
    try:
        specs = [load_graph_spec(f) for f in args.files]
    except Exception as exc:
        print(f'Error loading specs: {exc}', file=sys.stderr)
        return 2

    if len(specs) < 2:
        print('Error: need at least 2 specs to merge', file=sys.stderr)
        return 2

    # Track node IDs to avoid duplicates
    node_ids = set()
    edge_ids = set()
    all_nodes = []
    all_edges = []

    for spec in specs:
        for node in spec.nodes:
            if node.id not in node_ids:
                all_nodes.append(node)
                node_ids.add(node.id)
            else:
                print(f'Warning: Duplicate node ID {node.id}, skipping', file=sys.stderr)

        for edge in spec.edges:
            if edge.id not in edge_ids:
                all_edges.append(edge)
                edge_ids.add(edge.id)
            else:
                print(f'Warning: Duplicate edge ID {edge.id}, skipping', file=sys.stderr)

    # Create merged spec with all nodes
    merged = GraphSpec(
        id=f'merged.{specs[0].id}',
        description=f'Merged graph from {len(specs)} specs',
        start=specs[0].start,
        nodes=all_nodes,
        edges=all_edges
    )

    # Save merged spec
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(merged.model_dump(), f, indent=2)
        print(f'Wrote merged spec to {args.output}')
    else:
        print(json.dumps(merged.model_dump(), indent=2))

    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract subgraph from a spec."""
    try:
        spec = load_graph_spec(args.file)
    except Exception as exc:
        print(f'Error loading spec: {exc}', file=sys.stderr)
        return 2

    node_id = args.node

    # Check if node exists
    node = next((n for n in spec.nodes if n.id == node_id), None)
    if not node:
        print(f'Error: node {node_id} not found', file=sys.stderr)
        return 2

    # Find all reachable nodes from this node using BFS
    from collections import deque

    # Build adjacency map
    adjacency = {n.id: [] for n in spec.nodes}
    for edge in spec.edges:
        adjacency[edge.from_node].append(edge.to_node)

    # BFS to find reachable nodes
    visited = set()
    queue = deque([node_id])
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for successor in adjacency.get(current, []):
            if successor not in visited:
                queue.append(successor)

    # Extract subgraph
    subgraph = GraphSpec(
        id=f'{spec.id}.subgraph.{node_id}',
        description=f'Subgraph starting from {node_id}',
        start=node_id,
        nodes=[n for n in spec.nodes if n.id in visited],
        edges=[e for e in spec.edges if e.from_node in visited and e.to_node in visited]
    )

    # Save subgraph
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(subgraph.model_dump(), f, indent=2)
        print(f'Wrote subgraph to {args.output}')
        print(f'Extracted {len(subgraph.nodes)} nodes and {len(subgraph.edges)} edges')
    else:
        print(json.dumps(subgraph.model_dump(), indent=2))

    return 0


def cmd_schema_render(args: argparse.Namespace) -> int:
    """Render MissionStateModel metadata + JSON schema."""

    schema_cls = _resolve_schema(args.target)
    payload = {
        'metadata': schema_cls.schema_metadata(),
        'json_schema': schema_cls.model_json_schema(),
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Wrote schema to {args.output}")
        return 0
    print(output)
    return 0


def cmd_schema_validate(args: argparse.Namespace) -> int:
    """Validate a fixture against a MissionStateModel."""

    schema_cls = _resolve_schema(args.schema)
    try:
        with open(args.fixture, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Failed to load fixture {args.fixture}: {exc}", file=sys.stderr)
        return 2

    try:
        schema_cls.model_validate(data)
    except Exception as exc:  # ValidationError or others
        print(f"Invalid fixture for {schema_cls.schema_metadata()['name']}: {exc}", file=sys.stderr)
        return 2

    print(f"Fixture {args.fixture} is valid for {schema_cls.schema_metadata()['name']}")
    return 0


def cmd_schema_migrate(args: argparse.Namespace) -> int:
    """Apply registered migrations to a state snapshot."""

    schema_cls = _resolve_schema(args.schema)
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Failed to load input state {args.input}: {exc}", file=sys.stderr)
        return 2

    current_version = data.pop('__schema_version__', None)
    try:
        migrated, version = schema_cls.migrate_state(data, current_version=current_version)
    except Exception as exc:
        print(f"Failed to migrate state: {exc}", file=sys.stderr)
        return 2

    migrated['__schema_version__'] = version
    output = json.dumps(migrated, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Wrote migrated state to {args.output}")
    else:
        print(output)
    return 0


def cmd_plan_render(args: argparse.Namespace) -> int:
    """Render a plan snapshot JSON file."""

    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Failed to load plan file {args.file}: {exc}", file=sys.stderr)
        return 2

    snapshot = data
    if isinstance(data, dict):
        snapshot = data.get('mission_plan') or data.get('plan') or data.get('steps')
    if not isinstance(snapshot, list):
        print('Plan JSON must be a list of steps or contain mission_plan field', file=sys.stderr)
        return 2

    plan = MissionPlan.from_snapshot(snapshot)
    print(plan.render_text())
    return 0


def _format_timestamp(epoch: float | None) -> str:
    if not epoch:
        return '—'
    return datetime.fromtimestamp(epoch).isoformat(timespec='seconds')


def cmd_approval_list(args: argparse.Namespace) -> int:
    """List approval requests stored in a GraphState backend."""

    async def _run() -> int:
        manager = await _load_approval_manager(args)
        status_filter = getattr(args, 'status', 'pending')
        if status_filter == 'pending':
            approvals = await manager.pending_requests()
        else:
            approvals = await manager.list_requests()
            if status_filter != 'all':
                status_enum = ApprovalStatus(status_filter)
                approvals = [req for req in approvals if req.status == status_enum]
        approvals.sort(key=lambda req: req.created_at, reverse=True)
        limit = getattr(args, 'limit', None)
        if limit:
            approvals = approvals[:limit]
        output_format = getattr(args, 'format', 'table')
        if output_format == 'json':
            payload = [req.model_dump() for req in approvals]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if not approvals:
            print('No approval requests found.')
            return 0
        for req in approvals:
            created = _format_timestamp(req.created_at)
            decided = _format_timestamp(req.decided_at)
            print(f"[{req.status.value:^8}] {req.approval_id}  {req.action} -> {req.resource}")
            print(f"  created: {created}  decided: {decided}")
            if req.reason:
                print(f"  reason: {req.reason}")
            if req.decided_by:
                print(f"  reviewer: {req.decided_by}")
            if req.notes:
                print(f"  notes: {req.notes}")
            if req.metadata:
                metadata = json.dumps(req.metadata, ensure_ascii=False)
                print(f"  metadata: {metadata}")
            print()
        return 0

    try:
        return asyncio.run(_run())
    except Exception as exc:
        print(f"Error listing approvals: {exc}", file=sys.stderr)
        return 2


def cmd_approval_resolve(args: argparse.Namespace) -> int:
    """Mark an approval request as approved or rejected."""

    async def _run() -> int:
        manager = await _load_approval_manager(args)
        status = ApprovalStatus(args.status)
        resolved = await manager.resolve_request(
            args.approval_id,
            status=status,
            reviewer=getattr(args, 'reviewer', None),
            notes=getattr(args, 'notes', None),
        )
        output_format = getattr(args, 'format', 'text')
        if output_format == 'json':
            print(json.dumps(resolved.model_dump(), ensure_ascii=False, indent=2))
            return 0
        decided = _format_timestamp(resolved.decided_at)
        print(f"Approval {resolved.approval_id} marked as {resolved.status.value} at {decided}")
        if resolved.decided_by:
            print(f"Reviewer: {resolved.decided_by}")
        if resolved.notes:
            print(f"Notes: {resolved.notes}")
        return 0

    try:
        return asyncio.run(_run())
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error resolving approval: {exc}", file=sys.stderr)
        return 2


def cmd_policy_generate(args: argparse.Namespace) -> int:
    """Generate a policy set skeleton."""

    default_effect = PolicyEffect(args.default_effect)
    policy = PolicySet(
        name=args.name,
        description=args.description or f"Policy set for {args.name}",
        default_effect=default_effect,
    )
    if not args.empty:
        example_rule = PolicyRule(
            name=args.rule_name,
            description=args.rule_description,
            effect=PolicyEffect(args.rule_effect),
            actions=[args.rule_action],
            resources=[args.rule_resource],
            constraints=[],
        )
        policy.rules.append(example_rule)
    payload = json.dumps(policy.model_dump(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding='utf-8')
        print(f"Wrote policy set to {args.output}")
    else:
        print(payload)
    return 0


def cmd_policy_validate(args: argparse.Namespace) -> int:
    """Validate a policy JSON file."""

    try:
        policy = _load_policy_set(args.file)
    except Exception as exc:
        print(f"Invalid policy file: {exc}", file=sys.stderr)
        return 2
    print(f"Valid policy set '{policy.name}' with {len(policy.rules)} rule(s).")
    return 0


def cmd_policy_diff(args: argparse.Namespace) -> int:
    """Diff two policy sets."""

    try:
        old_policy = _load_policy_set(args.old)
        new_policy = _load_policy_set(args.new)
    except Exception as exc:
        print(f"Failed to load policy files: {exc}", file=sys.stderr)
        return 2

    summary = _diff_policy_sets(old_policy, new_policy)
    if args.format == 'json':
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    lines: list[str] = []
    if summary['default_effect_changed']:
        lines.append(
            f"- Default effect changed: {summary['default_effect_changed']['old']} -> {summary['default_effect_changed']['new']}"
        )
    if summary['added_rules']:
        lines.append(f"- Added rules: {', '.join(sorted(summary['added_rules']))}")
    if summary['removed_rules']:
        lines.append(f"- Removed rules: {', '.join(sorted(summary['removed_rules']))}")
    if summary['updated_rules']:
        lines.append("- Updated rules:")
        for name, diff in summary['updated_rules'].items():
            lines.append(f"  * {name}")
            for field, change in diff.items():
                lines.append(f"    - {field}: {change['old']} -> {change['new']}")
    if not lines:
        lines.append("Policies are identical.")
    print('\n'.join(lines))
    return 0


def _diff_policy_sets(old: PolicySet, new: PolicySet) -> dict[str, Any]:
    old_rules = {rule.name: rule for rule in old.rules}
    new_rules = {rule.name: rule for rule in new.rules}
    added = sorted(set(new_rules) - set(old_rules))
    removed = sorted(set(old_rules) - set(new_rules))
    updated: dict[str, dict[str, dict[str, Any]]] = {}
    common = set(old_rules) & set(new_rules)
    for name in common:
        old_dump = old_rules[name].model_dump(mode='json')
        new_dump = new_rules[name].model_dump(mode='json')
        diff: dict[str, dict[str, Any]] = {}
        for key in sorted(set(old_dump) | set(new_dump)):
            if old_dump.get(key) != new_dump.get(key):
                diff[key] = {'old': old_dump.get(key), 'new': new_dump.get(key)}
        if diff:
            updated[name] = diff
    default_diff = None
    if old.default_effect != new.default_effect:
        default_diff = {'old': old.default_effect.value, 'new': new.default_effect.value}
    return {
        'default_effect_changed': default_diff,
        'added_rules': added,
        'removed_rules': removed,
        'updated_rules': updated,
    }


def cmd_simulation_run(args: argparse.Namespace) -> int:
    """Run a mission spec using simulation tool overrides."""

    mission = load_mission_spec(args.mission)
    sim_override = None
    if args.simulation_config:
        try:
            with open(args.simulation_config, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            sim_override = MissionSimulationSpec.model_validate(payload)
        except Exception as exc:
            print(f"Failed to load simulation config: {exc}", file=sys.stderr)
            return 2

    try:
        inputs: dict[str, Any] = {}
        if args.inputs:
            with open(args.inputs, 'r', encoding='utf-8') as f:
                inputs = json.load(f)
    except Exception as exc:
        print(f"Failed to load inputs: {exc}", file=sys.stderr)
        return 2

    runner = SimulationRunner(mission, import_policy=args.import_policy)

    async def _run() -> SimulationRunResult:
        return await runner.run(inputs=inputs, simulation_override=sim_override)

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        print(f"Simulation run failed: {exc}", file=sys.stderr)
        return 2

    if args.format == 'json':
        payload = {
            'outputs': result.outputs,
            'policy_events': result.policy_events,
            'tool_records': {
                name: [
                    {
                        'tool_use_id': record.tool_use_id,
                        'inputs': record.inputs,
                        'outputs': record.outputs,
                        'status': record.status,
                        'started_at': record.started_at,
                        'completed_at': record.completed_at,
                        'metadata': record.metadata,
                    }
                    for record in records
                ]
                for name, records in result.tool_records.items()
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Simulation completed.")
    print(f"  Outputs: {result.outputs}")
    print(f"  Policy events: {len(result.policy_events)}")
    if result.tool_records:
        print("  Tool calls:")
        for name, records in result.tool_records.items():
            print(f"    - {name}: {len(records)} invocation(s)")
    else:
        print("  Tool calls: none")
    return 0


def cmd_simulation_diff(args: argparse.Namespace) -> int:
    """Diff two simulation run artifacts."""

    try:
        with open(args.baseline, 'r', encoding='utf-8') as f:
            baseline = json.load(f)
        with open(args.candidate, 'r', encoding='utf-8') as f:
            candidate = json.load(f)
    except Exception as exc:
        print(f"Failed to load simulation outputs: {exc}", file=sys.stderr)
        return 2

    summary = _diff_simulation_payloads(baseline, candidate)
    if args.format == 'json':
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    lines: list[str] = []
    lines.append("Outputs match." if summary['outputs_equal'] else "Outputs differ.")
    lines.append(
        f"Policy events: baseline={summary['policy_events']['baseline']} "
        f"candidate={summary['policy_events']['candidate']} delta={summary['policy_events']['delta']}"
    )
    if summary['tool_invocations']['counts']:
        lines.append("Tool invocation deltas:")
        for name, counts in summary['tool_invocations']['counts'].items():
            lines.append(
                f"  - {name}: baseline={counts['baseline']} "
                f"candidate={counts['candidate']} delta={counts['delta']}"
            )
    else:
        lines.append("Tool invocation deltas: none")
    if summary['tool_invocations']['added']:
        lines.append(f"Added tools: {', '.join(summary['tool_invocations']['added'])}")
    if summary['tool_invocations']['removed']:
        lines.append(f"Removed tools: {', '.join(summary['tool_invocations']['removed'])}")
    print('\n'.join(lines))
    return 0


def _diff_simulation_payloads(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    outputs_equal = baseline.get('outputs') == candidate.get('outputs')
    baseline_policy = baseline.get('policy_events') or []
    candidate_policy = candidate.get('policy_events') or []
    policy_summary = {
        'baseline': len(baseline_policy),
        'candidate': len(candidate_policy),
        'delta': len(candidate_policy) - len(baseline_policy),
    }

    baseline_tools = baseline.get('tool_records') or {}
    candidate_tools = candidate.get('tool_records') or {}
    tool_counts: dict[str, dict[str, int]] = {}
    all_tools = set(baseline_tools) | set(candidate_tools)
    for name in sorted(all_tools):
        base_len = len(baseline_tools.get(name, []))
        cand_len = len(candidate_tools.get(name, []))
        if base_len != cand_len:
            tool_counts[name] = {'baseline': base_len, 'candidate': cand_len, 'delta': cand_len - base_len}
    added = sorted(set(candidate_tools) - set(baseline_tools))
    removed = sorted(set(baseline_tools) - set(candidate_tools))

    summary: dict[str, Any] = {
        'outputs_equal': outputs_equal,
        'policy_events': policy_summary,
        'tool_invocations': {
            'counts': tool_counts,
            'added': added,
            'removed': removed,
        },
    }
    if not outputs_equal:
        summary['output_diff'] = {
            'baseline': baseline.get('outputs'),
            'candidate': candidate.get('outputs'),
        }
    return summary


def cmd_schema_diff(args: argparse.Namespace) -> int:
    """Compare two MissionStateModel definitions."""

    base_cls = _resolve_schema(args.old)
    new_cls = _resolve_schema(args.new)

    base_fields = _extract_schema_fields(base_cls)
    new_fields = _extract_schema_fields(new_cls)

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for name, meta in new_fields.items():
        if name not in base_fields:
            added.append({'field': name, **meta})
        else:
            old_meta = base_fields[name]
            if old_meta != meta:
                changed.append({'field': name, 'old': old_meta, 'new': meta})

    for name, meta in base_fields.items():
        if name not in new_fields:
            removed.append({'field': name, **meta})

    report = {
        'old': base_cls.schema_metadata(),
        'new': new_cls.schema_metadata(),
        'added': added,
        'removed': removed,
        'changed': changed,
    }

    if args.format == 'json':
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    def _format_field(entry: dict[str, Any]) -> str:
        return f"{entry['field']} (type={entry['type']}, required={entry['required']}, default={entry['default']})"

    if added:
        print('Added fields:')
        for entry in added:
            print(f"  + {_format_field(entry)}")
    if removed:
        print('Removed fields:')
        for entry in removed:
            print(f"  - {_format_field(entry)}")
    if changed:
        print('Changed fields:')
        for entry in changed:
            old_meta = entry['old']
            new_meta = entry['new']
            print(
                f"  * {entry['field']}: type {old_meta['type']} -> {new_meta['type']}, "
                f"required {old_meta['required']} -> {new_meta['required']}"
            )
    if not any((added, removed, changed)):
        print('No schema differences detected.')
    return 0


# ==============================================================================
# CLI Parser
# ==============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser for spec operations."""
    p = argparse.ArgumentParser(prog='spark-spec', description='Spark spec tooling')
    sub = p.add_subparsers(dest='cmd', required=True)

    # Export command
    pe = sub.add_parser('export', help='Export a Python Graph to JSON spec')
    pe.add_argument('target', help="Target in the form 'module:attr' (attr can be a factory)")
    pe.add_argument('-o', '--output', help='Output file path (stdout if omitted)')
    pe.add_argument('--version', default='1.0', help='spec version (default: 1.0)')
    pe.add_argument('--full-fidelity', action='store_true', help='Enable full-fidelity export')
    pe.set_defaults(func=cmd_export)

    # Validate command
    pv = sub.add_parser('validate', help='Validate a JSON spec file')
    pv.add_argument('file', help='Path to JSON spec file')
    pv.add_argument('--semantic', action='store_true', help='Enable semantic validation')
    pv.add_argument('--strict', action='store_true', help='Fail on semantic issues')
    pv.set_defaults(func=cmd_validate)

    # Compile command
    pc = sub.add_parser('compile', help='Compile JSON spec to Python code')
    pc.add_argument('file', help='Path to JSON spec file')
    pc.add_argument('-o', '--output', help='Output directory (defaults to CWD)')
    pc.add_argument('--style', choices=['simple', 'production', 'documented'], default='simple',
                    help='Code generation style')
    pc.add_argument('--tests', action='store_true', help='Generate test file')
    pc.set_defaults(func=cmd_compile)

    # Generate command
    pg = sub.add_parser('generate', help='Generate JSON spec from description')
    pg.add_argument('desc', help='Description text or path to a file')
    pg.add_argument('-o', '--output', help='Output file path (stdout if omitted)')
    pg.set_defaults(func=cmd_generate)

    # Mission generate command
    pmg = sub.add_parser('mission-generate', help='Generate mission spec from description')
    pmg.add_argument('desc', help='Description text or path to file')
    pmg.add_argument('-o', '--output', help='Output file path (stdout if omitted)')
    pmg.add_argument('--mission-id', default='mission.generated', help='Mission identifier')
    pmg.add_argument('--version', default='1.0', help='Mission version')
    pmg.add_argument(
        '--strategy',
        choices=['noop', 'react', 'chain_of_thought', 'plan_and_solve', 'custom'],
        default='plan_and_solve',
        help='Strategy binding for the generated mission',
    )
    pmg.add_argument('--strategy-class', help='Module:Class for custom strategy bindings')
    pmg.add_argument('--no-plan', action='store_true', help='Skip default mission plan generation')
    pmg.add_argument('--no-strategy', action='store_true', help='Skip default strategy binding')
    pmg.add_argument('--no-schema', action='store_true', help='Skip default state schema metadata')
    pmg.add_argument('--schema-name', default='MissionState', help='Default schema name when included')
    pmg.add_argument('--schema-version', default='1.0', help='Default schema version when included')
    pmg.add_argument('--no-deployment', action='store_true', help='Skip deployment metadata')
    pmg.add_argument('--deploy-environment', default='dev', help='Deployment environment identifier')
    pmg.add_argument('--deploy-runtime', default=None, help='Runtime (service, batch, worker)')
    pmg.add_argument('--deploy-entrypoint', default=None, help='Deployment entrypoint reference')
    pmg.add_argument('--deploy-health-check', default=None, help='Health check command or path')
    pmg.set_defaults(func=cmd_mission_generate)

    # Mission validate command
    pmv = sub.add_parser('mission-validate', help='Validate mission spec JSON file')
    pmv.add_argument('file', help='Mission spec JSON path')
    pmv.add_argument('--semantic', action='store_true', help='Validate underlying graph semantics')
    pmv.add_argument('--strict', action='store_true', help='Fail when semantic issues are present')
    pmv.set_defaults(func=cmd_mission_validate)

    # Mission diff command
    pmd = sub.add_parser('mission-diff', help='Diff two mission specs (graph + metadata)')
    pmd.add_argument('old', help='Baseline mission spec JSON')
    pmd.add_argument('new', help='Updated mission spec JSON')
    pmd.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    pmd.set_defaults(func=cmd_mission_diff)

    # Mission package command
    pmp = sub.add_parser('mission-package', help='Create deployable mission package')
    pmp.add_argument('file', help='Mission spec JSON path')
    pmp.add_argument('--output-dir', help='Package output directory (defaults to CWD)')
    pmp.add_argument('--package-id', help='Override package identifier')
    pmp.add_argument('--schema', help="Optional MissionStateModel reference 'module:Class'")
    pmp.add_argument('--artifact-policy', help='Artifact policy JSON path, inline JSON, or module:attr reference')
    pmp.add_argument('--notes', help='Optional notes stored in manifest')
    pmp.set_defaults(func=cmd_mission_package)

    # Mission deploy command
    pmdp = sub.add_parser('mission-deploy', help='Run deployment readiness checks on a package')
    pmdp.add_argument('package', help='Path to mission package directory')
    pmdp.add_argument('--env', dest='environment', help='Override environment label')
    pmdp.add_argument('--workspace', help='Workspace path to prepare')
    pmdp.add_argument('--report', help='Write deployment report JSON to path')
    pmdp.add_argument('--import-policy', choices=['safe', 'allow_all'], default='allow_all', help='Tool import policy')
    pmdp.set_defaults(func=cmd_mission_deploy)

    # Analyze command
    pa = sub.add_parser('analyze', help='Analyze graph structure and complexity')
    pa.add_argument('file', help='Path to JSON spec file')
    pa.add_argument('--report', help='Output report to file (text or HTML)')
    pa.set_defaults(func=cmd_analyze)

    # Diff command
    pd = sub.add_parser('diff', help='Compare two specs and show differences')
    pd.add_argument('old', help='Path to old JSON spec file')
    pd.add_argument('new', help='Path to new JSON spec file')
    pd.add_argument('--format', choices=['unified', 'json', 'summary'], default='unified',
                    help='Output format')
    pd.set_defaults(func=cmd_diff)

    # Optimize command
    po = sub.add_parser('optimize', help='Suggest and apply optimizations')
    po.add_argument('file', help='Path to JSON spec file')
    po.add_argument('-o', '--output', help='Output optimized spec to file')
    po.add_argument('--auto-fix', action='store_true', help='Automatically apply fixes')
    po.set_defaults(func=cmd_optimize)

    # Test command
    pt = sub.add_parser('test', help='Test spec validity and round-trip conversion')
    pt.add_argument('file', help='Path to JSON spec file')
    pt.add_argument('--validate', action='store_true', help='Run semantic validation')
    pt.add_argument('--round-trip', action='store_true', help='Test round-trip conversion')
    pt.set_defaults(func=cmd_test)

    # Introspect command
    pi = sub.add_parser('introspect', help='Inspect Python graph and show detailed info')
    pi.add_argument('target', help="Target in the form 'module:attr'")
    pi.add_argument('--format', choices=['text', 'json'], default='text',
                    help='Output format')
    pi.set_defaults(func=cmd_introspect)

    # Merge command
    pm = sub.add_parser('merge', help='Merge multiple specs into one')
    pm.add_argument('files', nargs='+', help='Paths to JSON spec files to merge')
    pm.add_argument('-o', '--output', help='Output merged spec to file')
    pm.set_defaults(func=cmd_merge)

    # Extract command
    px = sub.add_parser('extract', help='Extract subgraph from a spec')
    px.add_argument('file', help='Path to JSON spec file')
    px.add_argument('--node', required=True, help='Node ID to start extraction from')
    px.add_argument('-o', '--output', help='Output subgraph to file')
    px.set_defaults(func=cmd_extract)

    # Schema render command
    psr = sub.add_parser('schema-render', help='Render MissionStateModel metadata + JSON schema')
    psr.add_argument('target', help="Schema target in the form 'module:Class'")
    psr.add_argument('-o', '--output', help='Output file (stdout if omitted)')
    psr.set_defaults(func=cmd_schema_render)

    # Schema validate command
    psv = sub.add_parser('schema-validate', help='Validate fixture against MissionStateModel')
    psv.add_argument('schema', help="Schema target in the form 'module:Class'")
    psv.add_argument('fixture', help='JSON file containing state snapshot to validate')
    psv.set_defaults(func=cmd_schema_validate)

    # Schema migrate command
    psm = sub.add_parser('schema-migrate', help='Run schema migrations against a state snapshot')
    psm.add_argument('schema', help="Schema target in the form 'module:Class'")
    psm.add_argument('input', help='Input JSON state file to migrate')
    psm.add_argument('-o', '--output', help='Optional output file (stdout if omitted)')
    psm.set_defaults(func=cmd_schema_migrate)

    # Schema diff command
    psd = sub.add_parser('schema-diff', help='Diff two MissionStateModel definitions')
    psd.add_argument('old', help="Existing schema target 'module:Class'")
    psd.add_argument('new', help="New schema target 'module:Class'")
    psd.add_argument('--format', choices=['text', 'json'], default='text', help='Diff output format')
    psd.set_defaults(func=cmd_schema_diff)

    # Plan render command
    ppr = sub.add_parser('plan-render', help='Render a mission plan snapshot to text')
    ppr.add_argument('file', help='Path to plan snapshot JSON file')
    ppr.set_defaults(func=cmd_plan_render)

    # Approval commands
    pal = sub.add_parser('approval-list', help='List approval requests from stored GraphState')
    pal.add_argument('--state', required=True, help='Path to GraphState backend (JSON file or SQLite DB)')
    pal.add_argument('--backend', choices=['file', 'sqlite'], default='file', help='State backend type')
    pal.add_argument('--table', default='graph_state', help='SQLite table name (when backend=sqlite)')
    pal.add_argument('--storage-key', default='approval_requests', help='State key storing approval entries')
    pal.add_argument('--status', choices=['all', 'pending', 'approved', 'rejected'], default='pending',
                     help='Filter approvals by status')
    pal.add_argument('--limit', type=int, help='Limit the number of approvals displayed')
    pal.add_argument('--format', choices=['table', 'json'], default='table', help='Output format')
    pal.set_defaults(func=cmd_approval_list)

    par = sub.add_parser('approval-resolve', help='Approve or reject a pending approval request')
    par.add_argument('approval_id', help='Approval identifier to update')
    par.add_argument('--state', required=True, help='Path to GraphState backend (JSON file or SQLite DB)')
    par.add_argument('--backend', choices=['file', 'sqlite'], default='file', help='State backend type')
    par.add_argument('--table', default='graph_state', help='SQLite table name (when backend=sqlite)')
    par.add_argument('--storage-key', default='approval_requests', help='State key storing approval entries')
    par.add_argument('--status', choices=['approved', 'rejected'], required=True, help='New approval status')
    par.add_argument('--reviewer', help='Reviewer identifier recorded with the decision')
    par.add_argument('--notes', help='Optional notes recorded with the decision')
    par.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    par.set_defaults(func=cmd_approval_resolve)

    # Policy commands
    ppg = sub.add_parser('policy-generate', help='Generate a policy set scaffold')
    ppg.add_argument('--name', default='mission.policies', help='Policy set name')
    ppg.add_argument('--description', help='Optional description')
    ppg.add_argument('--default-effect', choices=[e.value for e in PolicyEffect], default=PolicyEffect.ALLOW.value)
    ppg.add_argument('--rule-name', default='sample_rule', help='Example rule name')
    ppg.add_argument('--rule-description', default='Edit this rule before use.', help='Example rule description')
    ppg.add_argument('--rule-effect', choices=[e.value for e in PolicyEffect], default=PolicyEffect.DENY.value)
    ppg.add_argument('--rule-action', default='agent:tool_execute', help='Example action glob')
    ppg.add_argument('--rule-resource', default='tool://example', help='Example resource glob')
    ppg.add_argument('--empty', action='store_true', help='Skip adding the sample rule')
    ppg.add_argument('-o', '--output', help='Output file (stdout if omitted)')
    ppg.set_defaults(func=cmd_policy_generate)

    ppv = sub.add_parser('policy-validate', help='Validate a policy JSON file')
    ppv.add_argument('file', help='Policy JSON path')
    ppv.set_defaults(func=cmd_policy_validate)

    ppd = sub.add_parser('policy-diff', help='Diff two policy JSON files')
    ppd.add_argument('old', help='Baseline policy file')
    ppd.add_argument('new', help='Updated policy file')
    ppd.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    ppd.set_defaults(func=cmd_policy_diff)

    psim = sub.add_parser('simulation-run', help='Run a mission spec with simulated tools')
    psim.add_argument('mission', help='Path to mission spec JSON')
    psim.add_argument('--inputs', help='JSON file containing initial graph inputs')
    psim.add_argument('--simulation-config', help='Optional simulation config override JSON')
    psim.add_argument('--import-policy', choices=['safe', 'allow_all'], default='safe', help='Import policy for loader')
    psim.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    psim.set_defaults(func=cmd_simulation_run)

    psd = sub.add_parser('simulation-diff', help='Diff two simulation output JSON artifacts')
    psd.add_argument('baseline', help='Baseline simulation JSON')
    psd.add_argument('candidate', help='Candidate simulation JSON')
    psd.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    psd.set_defaults(func=cmd_simulation_diff)

    return p


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for the spec CLI; dispatch subcommands and return exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
