"""
Tests for CLI enhancements (Phase 5).

Tests the new CLI commands:
- analyze: Graph analysis
- diff: Spec comparison
- optimize: Optimization suggestions
- test: Validation and round-trip testing
- introspect: Python graph inspection
- merge: Spec merging
- extract: Subgraph extraction
"""

import pytest
import json
import tempfile
import os
from pathlib import Path

from spark.kit.spec_cli import main
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec
from spark.graphs.graph import Graph
from spark.nodes.nodes import Node


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def simple_spec_file(tmp_path):
    """Create a simple spec file."""
    spec = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node', description='Node A'),
            NodeSpec(id='b', type='Node', description='Node B'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    spec_file = tmp_path / 'test.json'
    with open(spec_file, 'w') as f:
        json.dump(spec.model_dump(), f, indent=2)

    return str(spec_file)


@pytest.fixture
def complex_spec_file(tmp_path):
    """Create a complex spec file with issues."""
    spec = GraphSpec(
        id='complex',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
            NodeSpec(id='unreachable', type='Node'),  # Unreachable
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='b', to_node='c'),
            EdgeSpec(id='e3', from_node='c', to_node='a'),  # Creates cycle
        ]
    )

    spec_file = tmp_path / 'complex.json'
    with open(spec_file, 'w') as f:
        json.dump(spec.model_dump(), f, indent=2)

    return str(spec_file)


@pytest.fixture
def two_spec_files(tmp_path):
    """Create two spec files for diffing."""
    spec1 = GraphSpec(
        id='v1',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    spec2 = GraphSpec(
        id='v2',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),  # Added
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='b', to_node='c'),  # Added
        ]
    )

    spec1_file = tmp_path / 'v1.json'
    spec2_file = tmp_path / 'v2.json'

    with open(spec1_file, 'w') as f:
        json.dump(spec1.model_dump(), f, indent=2)
    with open(spec2_file, 'w') as f:
        json.dump(spec2.model_dump(), f, indent=2)

    return str(spec1_file), str(spec2_file)


# ==============================================================================
# Analyze Command Tests
# ==============================================================================

def test_analyze_command_basic(simple_spec_file, capsys):
    """Test basic analyze command."""
    exit_code = main(['analyze', simple_spec_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'GRAPH ANALYSIS REPORT' in captured.out
    assert 'COMPLEXITY METRICS' in captured.out
    assert 'Nodes: 2' in captured.out


def test_analyze_command_with_report(simple_spec_file, tmp_path):
    """Test analyze command with report output."""
    report_file = tmp_path / 'report.txt'
    exit_code = main(['analyze', simple_spec_file, '--report', str(report_file)])
    assert exit_code == 0
    assert report_file.exists()

    content = report_file.read_text()
    assert 'GRAPH ANALYSIS REPORT' in content


def test_analyze_command_html_report(simple_spec_file, tmp_path):
    """Test analyze command with HTML report."""
    report_file = tmp_path / 'report.html'
    exit_code = main(['analyze', simple_spec_file, '--report', str(report_file)])
    assert exit_code == 0
    assert report_file.exists()

    content = report_file.read_text()
    assert '<!DOCTYPE html>' in content
    assert 'Graph Analysis Report' in content


def test_analyze_command_complex_graph(complex_spec_file, capsys):
    """Test analyze command with complex graph."""
    exit_code = main(['analyze', complex_spec_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Unreachable Nodes: 1' in captured.out or 'unreachable' in captured.out.lower()


def test_analyze_command_invalid_file(tmp_path, capsys):
    """Test analyze command with invalid file."""
    invalid_file = tmp_path / 'invalid.json'
    invalid_file.write_text('invalid json')

    exit_code = main(['analyze', str(invalid_file)])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Error loading spec' in captured.err


# ==============================================================================
# Diff Command Tests
# ==============================================================================

def test_diff_command_basic(two_spec_files, capsys):
    """Test basic diff command."""
    old_file, new_file = two_spec_files
    exit_code = main(['diff', old_file, new_file])
    assert exit_code == 1  # Has changes

    captured = capsys.readouterr()
    assert 'v1' in captured.out
    assert 'v2' in captured.out
    assert 'added' in captured.out.lower()


def test_diff_command_json_format(two_spec_files, capsys):
    """Test diff command with JSON format."""
    old_file, new_file = two_spec_files
    exit_code = main(['diff', old_file, new_file, '--format', 'json'])
    assert exit_code == 1

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert 'nodes_added' in result
    assert result['nodes_added'] == 1


def test_diff_command_summary_format(two_spec_files, capsys):
    """Test diff command with summary format."""
    old_file, new_file = two_spec_files
    exit_code = main(['diff', old_file, new_file, '--format', 'summary'])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert 'Changes detected' in captured.out


def test_diff_command_identical_specs(simple_spec_file, capsys):
    """Test diff command with identical specs."""
    exit_code = main(['diff', simple_spec_file, simple_spec_file])
    assert exit_code == 0  # No changes

    captured = capsys.readouterr()
    assert 'No changes' in captured.out


# ==============================================================================
# Optimize Command Tests
# ==============================================================================

def test_optimize_command_basic(simple_spec_file, capsys):
    """Test basic optimize command."""
    exit_code = main(['optimize', simple_spec_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Optimization suggestions' in captured.out


def test_optimize_command_with_issues(complex_spec_file, capsys):
    """Test optimize command with complex graph."""
    exit_code = main(['optimize', complex_spec_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'unreachable' in captured.out.lower() or 'Remove' in captured.out


def test_optimize_command_auto_fix(complex_spec_file, tmp_path):
    """Test optimize command with auto-fix."""
    output_file = tmp_path / 'optimized.json'
    exit_code = main(['optimize', complex_spec_file, '--auto-fix', '-o', str(output_file)])
    assert exit_code == 0
    assert output_file.exists()

    # Load and verify optimized spec
    with open(output_file) as f:
        spec_dict = json.load(f)

    spec = GraphSpec.model_validate(spec_dict)
    # Should have removed unreachable node
    assert len(spec.nodes) < 4


# ==============================================================================
# Test Command Tests
# ==============================================================================

def test_test_command_basic(simple_spec_file, capsys):
    """Test basic test command."""
    exit_code = main(['test', simple_spec_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Spec is valid' in captured.out


def test_test_command_with_validation(simple_spec_file, capsys):
    """Test test command with semantic validation."""
    exit_code = main(['test', simple_spec_file, '--validate'])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Semantic validation passed' in captured.out


def test_test_command_with_round_trip(simple_spec_file, capsys):
    """Test test command with round-trip testing."""
    exit_code = main(['test', simple_spec_file, '--round-trip'])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Code generation succeeded' in captured.out
    assert 'Round-trip serialization succeeded' in captured.out
    assert 'All tests passed' in captured.out


def test_test_command_invalid_spec(tmp_path, capsys):
    """Test test command with invalid spec."""
    invalid_file = tmp_path / 'invalid.json'
    invalid_file.write_text('invalid json')

    exit_code = main(['test', str(invalid_file)])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Validation failed' in captured.err


# ==============================================================================
# Merge Command Tests
# ==============================================================================

def test_merge_command_basic(two_spec_files, tmp_path, capsys):
    """Test basic merge command."""
    old_file, new_file = two_spec_files
    output_file = tmp_path / 'merged.json'

    exit_code = main(['merge', old_file, new_file, '-o', str(output_file)])
    assert exit_code == 0
    assert output_file.exists()

    # Load and verify merged spec
    with open(output_file) as f:
        spec_dict = json.load(f)

    spec = GraphSpec.model_validate(spec_dict)
    # Should have all unique nodes from both specs
    assert len(spec.nodes) >= 2


def test_merge_command_stdout(two_spec_files, capsys):
    """Test merge command with stdout output."""
    old_file, new_file = two_spec_files
    exit_code = main(['merge', old_file, new_file])
    assert exit_code == 0

    captured = capsys.readouterr()
    spec_dict = json.loads(captured.out)
    spec = GraphSpec.model_validate(spec_dict)
    assert len(spec.nodes) >= 2


def test_merge_command_single_file(simple_spec_file, capsys):
    """Test merge command with single file (should fail)."""
    exit_code = main(['merge', simple_spec_file])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'need at least 2 specs' in captured.err


# ==============================================================================
# Extract Command Tests
# ==============================================================================

def test_extract_command_basic(simple_spec_file, tmp_path):
    """Test basic extract command."""
    output_file = tmp_path / 'subgraph.json'
    exit_code = main(['extract', simple_spec_file, '--node', 'a', '-o', str(output_file)])
    assert exit_code == 0
    assert output_file.exists()

    # Load and verify subgraph
    with open(output_file) as f:
        spec_dict = json.load(f)

    spec = GraphSpec.model_validate(spec_dict)
    assert spec.start == 'a'
    assert any(n.id == 'a' for n in spec.nodes)


def test_extract_command_with_edges(simple_spec_file, capsys):
    """Test extract command includes reachable nodes and edges."""
    exit_code = main(['extract', simple_spec_file, '--node', 'a'])
    assert exit_code == 0

    captured = capsys.readouterr()
    spec_dict = json.loads(captured.out)
    spec = GraphSpec.model_validate(spec_dict)

    # Should include both nodes since b is reachable from a
    assert len(spec.nodes) == 2
    assert len(spec.edges) == 1


def test_extract_command_nonexistent_node(simple_spec_file, capsys):
    """Test extract command with nonexistent node."""
    exit_code = main(['extract', simple_spec_file, '--node', 'nonexistent'])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'not found' in captured.err


# ==============================================================================
# Enhanced Existing Commands Tests
# ==============================================================================

def test_validate_command_with_semantic(simple_spec_file, capsys):
    """Test enhanced validate command with semantic validation."""
    exit_code = main(['validate', simple_spec_file, '--semantic'])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert 'Valid spec' in captured.out
    assert 'No semantic issues' in captured.out


def test_validate_command_strict_mode(complex_spec_file, capsys):
    """Test validate command with strict mode."""
    exit_code = main(['validate', complex_spec_file, '--semantic', '--strict'])
    # Should fail due to semantic issues
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Semantic issues' in captured.out


def test_compile_command_with_style(simple_spec_file, tmp_path):
    """Test enhanced compile command with style parameter."""
    exit_code = main(['compile', simple_spec_file, '-o', str(tmp_path), '--style', 'production'])
    assert exit_code == 0

    # Check generated file exists
    generated_files = list(tmp_path.glob('*.py'))
    assert len(generated_files) > 0


def test_compile_command_with_tests(simple_spec_file, tmp_path):
    """Test compile command with test generation."""
    exit_code = main(['compile', simple_spec_file, '-o', str(tmp_path), '--tests'])
    assert exit_code == 0

    # Check test file was generated
    test_files = list(tmp_path.glob('*_test.py'))
    assert len(test_files) > 0


# ==============================================================================
# Error Handling Tests
# ==============================================================================

def test_analyze_nonexistent_file(capsys):
    """Test analyze command with nonexistent file."""
    exit_code = main(['analyze', 'nonexistent.json'])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Error loading spec' in captured.err


def test_diff_nonexistent_files(capsys):
    """Test diff command with nonexistent files."""
    exit_code = main(['diff', 'old.json', 'new.json'])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Error loading specs' in captured.err


def test_optimize_nonexistent_file(capsys):
    """Test optimize command with nonexistent file."""
    exit_code = main(['optimize', 'nonexistent.json'])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert 'Error loading spec' in captured.err


# ==============================================================================
# Integration Tests
# ==============================================================================

def test_cli_workflow_analyze_and_optimize(simple_spec_file, tmp_path, capsys):
    """Test workflow: analyze then optimize."""
    # First analyze
    exit_code = main(['analyze', simple_spec_file])
    assert exit_code == 0

    # Then optimize
    output_file = tmp_path / 'optimized.json'
    exit_code = main(['optimize', simple_spec_file, '-o', str(output_file)])
    assert exit_code == 0


def test_cli_workflow_diff_and_merge(two_spec_files, tmp_path):
    """Test workflow: diff then merge."""
    old_file, new_file = two_spec_files

    # First diff
    exit_code = main(['diff', old_file, new_file])
    assert exit_code == 1  # Has changes

    # Then merge
    merged_file = tmp_path / 'merged.json'
    exit_code = main(['merge', old_file, new_file, '-o', str(merged_file)])
    assert exit_code == 0
    assert merged_file.exists()


def test_cli_workflow_extract_and_test(simple_spec_file, tmp_path):
    """Test workflow: extract subgraph then test it."""
    # Extract subgraph
    subgraph_file = tmp_path / 'subgraph.json'
    exit_code = main(['extract', simple_spec_file, '--node', 'a', '-o', str(subgraph_file)])
    assert exit_code == 0

    # Test the subgraph
    exit_code = main(['test', str(subgraph_file), '--validate'])
    assert exit_code == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
