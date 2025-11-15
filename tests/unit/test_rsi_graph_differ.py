"""Tests for RSI GraphDiffer."""

import pytest
import json
from spark.rsi.graph_differ import GraphDiffer
from spark.rsi.types import StructuralDiff, NodeModification, EdgeModification
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def simple_graph_spec():
    """Create a simple graph spec for testing."""
    return GraphSpec(
        id="test_graph",
        version="1.0",
        start="node_a",
        nodes=[
            NodeSpec(id="node_a", type="InputNode", config={'param': 'value1'}),
            NodeSpec(id="node_b", type="ProcessNode", config={}),
            NodeSpec(id="node_c", type="OutputNode", config={}),
        ],
        edges=[
            EdgeSpec(id="edge_ab", from_node="node_a", to_node="node_b"),
            EdgeSpec(id="edge_bc", from_node="node_b", to_node="node_c"),
        ]
    )


@pytest.fixture
def modified_graph_spec():
    """Create a modified graph spec for testing."""
    return GraphSpec(
        id="test_graph",
        version="1.1",
        start="node_a",
        nodes=[
            NodeSpec(id="node_a", type="InputNode", config={'param': 'value2'}),  # Modified config
            NodeSpec(id="node_b", type="ProcessNode", config={}),
            NodeSpec(id="node_d", type="NewNode", config={}),  # Added node (replaced node_c)
        ],
        edges=[
            EdgeSpec(id="edge_ab", from_node="node_a", to_node="node_b"),
            EdgeSpec(id="edge_bd", from_node="node_b", to_node="node_d"),  # Added edge
            # edge_bc removed
        ]
    )


@pytest.fixture
def sample_diff():
    """Create a sample diff for testing formatters."""
    return StructuralDiff(
        nodes_added=['node_d'],
        nodes_removed=['node_c'],
        nodes_modified=[
            NodeModification(
                node_id='node_a',
                field='config',
                old_value={'param': 'value1'},
                new_value={'param': 'value2'}
            )
        ],
        edges_added=['edge_bd'],
        edges_removed=['edge_bc'],
        edges_modified=[],
        complexity_delta=0,
        summary="1 node(s) added, 1 node(s) removed, 1 node(s) modified, 1 edge(s) added, 1 edge(s) removed"
    )


@pytest.fixture
def empty_diff():
    """Create an empty diff for testing."""
    return StructuralDiff(
        nodes_added=[],
        nodes_removed=[],
        nodes_modified=[],
        edges_added=[],
        edges_removed=[],
        edges_modified=[],
        complexity_delta=0,
        summary="No changes"
    )


@pytest.fixture
def differ():
    """Create a GraphDiffer instance."""
    return GraphDiffer()


# ============================================================================
# Test compute_diff
# ============================================================================

def test_compute_diff_simple(differ, simple_graph_spec, modified_graph_spec):
    """Test computing diff between two graph specs."""
    diff = differ.compute_diff(simple_graph_spec, modified_graph_spec)

    assert len(diff.nodes_added) == 1
    assert 'node_d' in diff.nodes_added

    assert len(diff.nodes_removed) == 1
    assert 'node_c' in diff.nodes_removed

    assert len(diff.nodes_modified) > 0

    assert len(diff.edges_added) == 1
    assert 'edge_bd' in diff.edges_added

    assert len(diff.edges_removed) == 1
    assert 'edge_bc' in diff.edges_removed


def test_compute_diff_no_changes(differ, simple_graph_spec):
    """Test computing diff when there are no changes."""
    import copy
    spec_copy = copy.deepcopy(simple_graph_spec)

    diff = differ.compute_diff(simple_graph_spec, spec_copy)

    assert len(diff.nodes_added) == 0
    assert len(diff.nodes_removed) == 0
    assert len(diff.nodes_modified) == 0
    assert len(diff.edges_added) == 0
    assert len(diff.edges_removed) == 0
    assert diff.complexity_delta == 0
    assert diff.summary == "No changes"


# ============================================================================
# Test format_diff_text
# ============================================================================

def test_format_diff_text_simple(differ, sample_diff):
    """Test text formatting of diff."""
    text = differ.format_diff_text(sample_diff)

    assert "GRAPH DIFF" in text
    assert "Summary:" in text
    assert "NODES ADDED" in text
    assert "+ node_d" in text
    assert "NODES REMOVED" in text
    assert "- node_c" in text
    assert "NODES MODIFIED" in text
    assert "node_a" in text
    assert "EDGES ADDED" in text
    assert "+ edge_bd" in text
    assert "EDGES REMOVED" in text
    assert "- edge_bc" in text


def test_format_diff_text_empty(differ, empty_diff):
    """Test text formatting of empty diff."""
    text = differ.format_diff_text(empty_diff)

    assert "GRAPH DIFF" in text
    assert "No changes" in text
    # Should not have sections for empty changes
    assert "NODES ADDED" not in text
    assert "NODES REMOVED" not in text


def test_format_diff_text_long_values(differ):
    """Test text formatting truncates long values."""
    long_value = "x" * 200
    diff = StructuralDiff(
        nodes_added=[],
        nodes_removed=[],
        nodes_modified=[
            NodeModification(
                node_id='node_a',
                field='config',
                old_value=long_value,
                new_value=long_value + "y"
            )
        ],
        edges_added=[],
        edges_removed=[],
        edges_modified=[],
        complexity_delta=0,
        summary="1 node(s) modified"
    )

    text = differ.format_diff_text(diff)

    # Should be truncated
    assert "..." in text
    assert len(text) < len(long_value) * 2 + 500  # Not too long


# ============================================================================
# Test format_diff_markdown
# ============================================================================

def test_format_diff_markdown_simple(differ, sample_diff):
    """Test Markdown formatting of diff."""
    markdown = differ.format_diff_markdown(sample_diff)

    assert "# Graph Diff" in markdown
    assert "## Nodes Added" in markdown
    assert "✅ `node_d`" in markdown
    assert "## Nodes Removed" in markdown
    assert "❌ `node_c`" in markdown
    assert "## Nodes Modified" in markdown
    assert "`node_a`" in markdown
    assert "```diff" in markdown
    assert "## Edges Added" in markdown
    assert "✅ `edge_bd`" in markdown
    assert "## Edges Removed" in markdown
    assert "❌ `edge_bc`" in markdown


def test_format_diff_markdown_empty(differ, empty_diff):
    """Test Markdown formatting of empty diff."""
    markdown = differ.format_diff_markdown(empty_diff)

    assert "# Graph Diff" in markdown
    assert "No changes" in markdown
    # Should not have sections for empty changes
    assert "## Nodes Added" not in markdown


# ============================================================================
# Test format_diff_html
# ============================================================================

def test_format_diff_html_simple(differ, sample_diff):
    """Test HTML formatting of diff."""
    html = differ.format_diff_html(sample_diff)

    assert "<div class='graph-diff'>" in html
    assert "<h1>Graph Diff</h1>" in html
    assert "<h2>Nodes Added" in html
    assert "node_d" in html
    assert "<h2>Nodes Removed" in html
    assert "node_c" in html
    assert "<h2>Nodes Modified" in html
    assert "node_a" in html
    assert "<h2>Edges Added" in html
    assert "edge_bd" in html
    assert "<h2>Edges Removed" in html
    assert "edge_bc" in html
    assert "<pre class='diff'>" in html


def test_format_diff_html_escaping(differ):
    """Test HTML escaping in diff."""
    diff = StructuralDiff(
        nodes_added=[],
        nodes_removed=[],
        nodes_modified=[
            NodeModification(
                node_id='node_a',
                field='config',
                old_value='<script>alert("xss")</script>',
                new_value='<div>safe</div>'
            )
        ],
        edges_added=[],
        edges_removed=[],
        edges_modified=[],
        complexity_delta=0,
        summary="1 node(s) modified"
    )

    html = differ.format_diff_html(diff)

    # Should be escaped
    assert "&lt;script&gt;" in html
    assert "<script>" not in html or "<script>" not in html.replace("&lt;script&gt;", "")


def test_format_diff_html_empty(differ, empty_diff):
    """Test HTML formatting of empty diff."""
    html = differ.format_diff_html(empty_diff)

    assert "<div class='graph-diff'>" in html
    assert "No changes" in html


# ============================================================================
# Test format_diff_json
# ============================================================================

def test_format_diff_json_simple(differ, sample_diff):
    """Test JSON formatting of diff."""
    json_str = differ.format_diff_json(sample_diff)

    # Parse JSON
    data = json.loads(json_str)

    assert data['summary'] == sample_diff.summary
    assert data['complexity_delta'] == 0
    assert 'node_d' in data['nodes_added']
    assert 'node_c' in data['nodes_removed']
    assert len(data['nodes_modified']) == 1
    assert data['nodes_modified'][0]['node_id'] == 'node_a'
    assert 'edge_bd' in data['edges_added']
    assert 'edge_bc' in data['edges_removed']


def test_format_diff_json_empty(differ, empty_diff):
    """Test JSON formatting of empty diff."""
    json_str = differ.format_diff_json(empty_diff)

    data = json.loads(json_str)

    assert data['summary'] == "No changes"
    assert len(data['nodes_added']) == 0
    assert len(data['nodes_removed']) == 0


def test_format_diff_json_complex_values(differ):
    """Test JSON formatting with complex values."""
    diff = StructuralDiff(
        nodes_added=[],
        nodes_removed=[],
        nodes_modified=[
            NodeModification(
                node_id='node_a',
                field='config',
                old_value={'nested': {'key': 'value1'}},
                new_value={'nested': {'key': 'value2'}}
            )
        ],
        edges_added=[],
        edges_removed=[],
        edges_modified=[],
        complexity_delta=0,
        summary="1 node(s) modified"
    )

    json_str = differ.format_diff_json(diff)

    # Should be valid JSON
    data = json.loads(json_str)
    assert 'nodes_modified' in data
    assert len(data['nodes_modified']) == 1


# ============================================================================
# Test generate_visual_diff
# ============================================================================

def test_generate_visual_diff_simple(differ, sample_diff):
    """Test visual diff generation."""
    visual = differ.generate_visual_diff(sample_diff)

    assert 'nodes' in visual
    assert 'edges' in visual
    assert 'summary' in visual
    assert 'complexity_delta' in visual

    # Nodes
    assert len(visual['nodes']['added']) == 1
    assert visual['nodes']['added'][0]['id'] == 'node_d'
    assert visual['nodes']['added'][0]['status'] == 'added'

    assert len(visual['nodes']['removed']) == 1
    assert visual['nodes']['removed'][0]['id'] == 'node_c'
    assert visual['nodes']['removed'][0]['status'] == 'removed'

    assert len(visual['nodes']['modified']) == 1
    assert visual['nodes']['modified'][0]['id'] == 'node_a'
    assert visual['nodes']['modified'][0]['status'] == 'modified'

    # Edges
    assert len(visual['edges']['added']) == 1
    assert visual['edges']['added'][0]['id'] == 'edge_bd'

    assert len(visual['edges']['removed']) == 1
    assert visual['edges']['removed'][0]['id'] == 'edge_bc'


def test_generate_visual_diff_empty(differ, empty_diff):
    """Test visual diff generation for empty diff."""
    visual = differ.generate_visual_diff(empty_diff)

    assert visual['summary'] == "No changes"
    assert len(visual['nodes']['added']) == 0
    assert len(visual['nodes']['removed']) == 0
    assert len(visual['nodes']['modified']) == 0
    assert len(visual['edges']['added']) == 0
    assert len(visual['edges']['removed']) == 0


def test_generate_visual_diff_with_edge_modifications(differ):
    """Test visual diff with edge modifications."""
    diff = StructuralDiff(
        nodes_added=[],
        nodes_removed=[],
        nodes_modified=[],
        edges_added=[],
        edges_removed=[],
        edges_modified=[
            EdgeModification(
                edge_id='edge_ab',
                field='condition',
                old_value='old_condition',
                new_value='new_condition'
            )
        ],
        complexity_delta=0,
        summary="1 edge(s) modified"
    )

    visual = differ.generate_visual_diff(diff)

    assert len(visual['edges']['modified']) == 1
    assert visual['edges']['modified'][0]['id'] == 'edge_ab'
    assert visual['edges']['modified'][0]['status'] == 'modified'
    assert 'changes' in visual['edges']['modified'][0]


# ============================================================================
# Test helper methods
# ============================================================================

def test_truncate_value_short(differ):
    """Test truncate_value with short string."""
    result = differ._truncate_value("short string")
    assert result == "short string"
    assert "..." not in result


def test_truncate_value_long(differ):
    """Test truncate_value with long string."""
    long_string = "x" * 200
    result = differ._truncate_value(long_string, max_length=50)
    assert len(result) <= 53  # 50 + "..."
    assert result.endswith("...")


def test_escape_html(differ):
    """Test HTML escaping."""
    result = differ._escape_html('<script>alert("test")</script>')
    assert "&lt;" in result
    assert "&gt;" in result
    assert "&quot;" in result
    assert "<script>" not in result
