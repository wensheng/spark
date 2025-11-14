"""
Tests for graph spec diffing tools (Phase 4.3).

Tests the SpecDiffer with:
- Diff generation for nodes, edges, tools
- Change detection (added, removed, modified)
- Patch application
- Migration script generation
"""

import pytest
from spark.kit.diff import (
    SpecDiffer,
    DiffResult,
    NodeDiff,
    EdgeDiff,
    ToolDiff,
    ChangeType,
)
from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ConditionSpec,
    ToolDefinitionSpec,
    ToolParameterSpec,
    GraphStateSpec,
)


# ==============================================================================
# Basic Differ Tests
# ==============================================================================

def test_differ_initialization():
    """Test SpecDiffer initialization."""
    differ = SpecDiffer()
    assert differ is not None


def test_diff_identical_specs():
    """Test diffing two identical specs."""
    spec = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
    )

    differ = SpecDiffer()
    result = differ.diff(spec, spec)

    assert not result.has_changes
    assert len(result.node_diffs) == 1
    assert result.node_diffs[0].change_type == ChangeType.UNCHANGED


def test_diff_result_string():
    """Test DiffResult string representation."""
    spec1 = GraphSpec(
        id='spec1',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='spec2',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    diff_str = str(result)
    assert 'spec1' in diff_str
    assert 'spec2' in diff_str
    assert 'added' in diff_str.lower()


# ==============================================================================
# Node Diff Tests
# ==============================================================================

def test_diff_node_added():
    """Test detection of added node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    added = [d for d in result.node_diffs if d.change_type == ChangeType.ADDED]
    assert len(added) == 1
    assert added[0].node_id == 'b'
    assert result.summary['nodes_added'] == 1


def test_diff_node_removed():
    """Test detection of removed node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    removed = [d for d in result.node_diffs if d.change_type == ChangeType.REMOVED]
    assert len(removed) == 1
    assert removed[0].node_id == 'b'
    assert result.summary['nodes_removed'] == 1


def test_diff_node_modified():
    """Test detection of modified node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', description='Old description')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', description='New description')]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.node_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert modified[0].node_id == 'a'
    assert 'description' in modified[0].field_changes
    assert modified[0].field_changes['description'] == ('Old description', 'New description')
    assert result.summary['nodes_modified'] == 1


def test_diff_node_type_changed():
    """Test detection of node type change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Agent')]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.node_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert 'type' in modified[0].field_changes
    assert modified[0].field_changes['type'] == ('Node', 'Agent')


def test_diff_node_config_changed():
    """Test detection of node config change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', config={'timeout': 30})]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', config={'timeout': 60})]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.node_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert 'config' in modified[0].field_changes


# ==============================================================================
# Edge Diff Tests
# ==============================================================================

def test_diff_edge_added():
    """Test detection of added edge."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    added = [d for d in result.edge_diffs if d.change_type == ChangeType.ADDED]
    assert len(added) == 1
    assert added[0].edge_id == 'e1'
    assert result.summary['edges_added'] == 1


def test_diff_edge_removed():
    """Test detection of removed edge."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    removed = [d for d in result.edge_diffs if d.change_type == ChangeType.REMOVED]
    assert len(removed) == 1
    assert removed[0].edge_id == 'e1'
    assert result.summary['edges_removed'] == 1


def test_diff_edge_condition_modified():
    """Test detection of edge condition change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='a',
                to_node='b',
                condition=ConditionSpec(kind='expr', expr='$.outputs.score > 0.5')
            )
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='a',
                to_node='b',
                condition=ConditionSpec(kind='expr', expr='$.outputs.score > 0.7')
            )
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.edge_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert 'condition' in modified[0].field_changes


def test_diff_edge_priority_changed():
    """Test detection of edge priority change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b', priority=0)
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b', priority=10)
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.edge_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert 'priority' in modified[0].field_changes
    assert modified[0].field_changes['priority'] == (0, 10)


# ==============================================================================
# Tool Diff Tests
# ==============================================================================

def test_diff_tool_added():
    """Test detection of added tool."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        tools=[
            ToolDefinitionSpec(
                name='search',
                function='tools:search',
                description='Search tool',
                parameters=[]
            )
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    added = [d for d in result.tool_diffs if d.change_type == ChangeType.ADDED]
    assert len(added) == 1
    assert added[0].tool_name == 'search'
    assert result.summary['tools_added'] == 1


def test_diff_tool_removed():
    """Test detection of removed tool."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        tools=[
            ToolDefinitionSpec(
                name='search',
                function='tools:search',
                description='Search tool',
                parameters=[]
            )
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    removed = [d for d in result.tool_diffs if d.change_type == ChangeType.REMOVED]
    assert len(removed) == 1
    assert removed[0].tool_name == 'search'
    assert result.summary['tools_removed'] == 1


def test_diff_tool_modified():
    """Test detection of modified tool."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        tools=[
            ToolDefinitionSpec(
                name='search',
                function='tools:search',
                description='Old description',
                parameters=[]
            )
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        tools=[
            ToolDefinitionSpec(
                name='search',
                function='tools:search',
                description='New description',
                parameters=[]
            )
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    modified = [d for d in result.tool_diffs if d.change_type == ChangeType.MODIFIED]
    assert len(modified) == 1
    assert 'description' in modified[0].field_changes
    assert result.summary['tools_modified'] == 1


# ==============================================================================
# Start Node and GraphState Tests
# ==============================================================================

def test_diff_start_node_changed():
    """Test detection of start node change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='b',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    assert result.start_changed
    assert result.old_start == 'a'
    assert result.new_start == 'b'


def test_diff_graph_state_changed():
    """Test detection of graph state change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        graph_state=GraphStateSpec(initial_state={'counter': 0})
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        graph_state=GraphStateSpec(initial_state={'counter': 10})
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    assert result.graph_state_changed


def test_diff_description_changed():
    """Test detection of description change."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        description='Old description'
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')],
        description='New description'
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    assert 'description' in result.metadata_changes
    assert result.metadata_changes['description'] == ('Old description', 'New description')


# ==============================================================================
# Apply Diff Tests
# ==============================================================================

def test_apply_diff_add_node():
    """Test applying diff that adds a node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    assert len(result_spec.nodes) == 2
    assert any(n.id == 'b' for n in result_spec.nodes)


def test_apply_diff_remove_node():
    """Test applying diff that removes a node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    assert len(result_spec.nodes) == 1
    assert not any(n.id == 'b' for n in result_spec.nodes)


def test_apply_diff_modify_node():
    """Test applying diff that modifies a node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', description='Old')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node', description='New')]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    assert result_spec.nodes[0].description == 'New'


def test_apply_diff_add_edge():
    """Test applying diff that adds an edge."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    assert len(result_spec.edges) == 1
    assert result_spec.edges[0].id == 'e1'


def test_apply_diff_change_start():
    """Test applying diff that changes start node."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )
    spec2 = GraphSpec(
        id='test',
        start='b',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    assert result_spec.start == 'b'


def test_apply_diff_round_trip():
    """Test that applying diff produces equivalent spec."""
    spec1 = GraphSpec(
        id='test',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    differ = SpecDiffer()
    diff_result = differ.diff(spec1, spec2)

    # Apply diff to spec1
    result_spec = differ.apply_diff(spec1, diff_result)

    # Result should be equivalent to spec2
    assert len(result_spec.nodes) == len(spec2.nodes)
    assert len(result_spec.edges) == len(spec2.edges)

    # Verify no diff between result and spec2
    verify_diff = differ.diff(result_spec, spec2)
    # Should have minimal changes (only UNCHANGED)
    assert all(d.change_type == ChangeType.UNCHANGED for d in verify_diff.node_diffs)
    assert all(d.change_type == ChangeType.UNCHANGED for d in verify_diff.edge_diffs)


# ==============================================================================
# Migration Script Tests
# ==============================================================================

def test_generate_migration_script():
    """Test migration script generation."""
    spec1 = GraphSpec(
        id='old',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='new',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    script = differ.generate_migration(spec1, spec2)

    assert 'def migrate_spec' in script
    assert 'GraphSpec' in script
    assert 'old' in script
    assert 'new' in script


def test_migration_script_with_changes():
    """Test migration script includes all changes."""
    spec1 = GraphSpec(
        id='v1',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='v2',
        start='b',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    differ = SpecDiffer()
    script = differ.generate_migration(spec1, spec2)

    assert 'Apply node changes' in script or 'TODO' in script
    assert 'Apply edge changes' in script or 'TODO' in script
    assert 'Change start' in script or 'start' in script


def test_migration_script_executable():
    """Test that migration script is valid Python."""
    spec1 = GraphSpec(
        id='v1',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='v2',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ]
    )

    differ = SpecDiffer()
    script = differ.generate_migration(spec1, spec2)

    # Should be valid Python (can compile)
    try:
        compile(script, '<string>', 'exec')
    except SyntaxError:
        pytest.fail("Generated migration script has syntax errors")


# ==============================================================================
# Complex Diff Tests
# ==============================================================================

def test_diff_multiple_changes():
    """Test diff with multiple types of changes."""
    spec1 = GraphSpec(
        id='v1',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )
    spec2 = GraphSpec(
        id='v2',
        start='b',
        nodes=[
            NodeSpec(id='b', type='Agent'),  # Modified
            NodeSpec(id='c', type='Node')    # Added
        ],
        edges=[
            EdgeSpec(id='e2', from_node='b', to_node='c')  # Added
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    summary = result.summary
    assert summary['nodes_added'] == 1     # c added
    assert summary['nodes_removed'] == 1   # a removed
    assert summary['nodes_modified'] == 1  # b modified
    assert summary['edges_added'] == 1     # e2 added
    assert summary['edges_removed'] == 1   # e1 removed
    assert result.start_changed


def test_diff_summary():
    """Test diff summary statistics."""
    spec1 = GraphSpec(
        id='v1',
        start='a',
        nodes=[NodeSpec(id='a', type='Node')]
    )
    spec2 = GraphSpec(
        id='v2',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node')
        ]
    )

    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    summary = result.summary
    assert summary['nodes_added'] == 2
    assert summary['nodes_removed'] == 0
    assert summary['nodes_modified'] == 0


# ==============================================================================
# Change Type String Tests
# ==============================================================================

def test_node_diff_string():
    """Test NodeDiff string representation."""
    diff = NodeDiff(
        node_id='test',
        change_type=ChangeType.ADDED,
        new_node=NodeSpec(id='test', type='Node')
    )
    assert 'added' in str(diff).lower()
    assert 'test' in str(diff)


def test_edge_diff_string():
    """Test EdgeDiff string representation."""
    diff = EdgeDiff(
        edge_id='e1',
        change_type=ChangeType.REMOVED,
        old_edge=EdgeSpec(id='e1', from_node='a', to_node='b')
    )
    assert 'removed' in str(diff).lower()
    assert 'e1' in str(diff)


def test_tool_diff_string():
    """Test ToolDiff string representation."""
    diff = ToolDiff(
        tool_name='search',
        change_type=ChangeType.MODIFIED,
        old_tool=ToolDefinitionSpec(name='search', function='old', description='', parameters=[]),
        new_tool=ToolDefinitionSpec(name='search', function='new', description='', parameters=[]),
        field_changes={'function': ('old', 'new')}
    )
    assert 'modified' in str(diff).lower()
    assert 'search' in str(diff)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
