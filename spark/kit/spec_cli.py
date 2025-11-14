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
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from typing import Any

from spark.graphs.base import BaseGraph
from spark.nodes.serde import graph_to_spec, save_graph_json, load_graph_spec
from spark.kit.codegen import generate, CodeGenerator
from spark.kit.analysis import GraphAnalyzer
from spark.kit.diff import SpecDiffer
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec


def _resolve_target(target: str) -> Any:
    """Import module:attr and return attribute value or callable result."""
    if ':' not in target:
        raise ValueError("target must be in form 'module:attr'")
    mod_name, attr_name = target.split(':', 1)
    module = importlib.import_module(mod_name)
    obj = getattr(module, attr_name)
    if callable(obj):
        result = obj()
    else:
        result = obj
    return result


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

    return p


def main(argv: list[str] | None = None) -> int:
    """Entrypoint for the spec CLI; dispatch subcommands and return exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
