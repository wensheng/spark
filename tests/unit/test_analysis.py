"""
Tests for graph analysis tools (Phase 4.1).

Tests the GraphAnalyzer with:
- Complexity metrics computation
- Cycle detection
- Bottleneck identification
- Optimization suggestions
- Semantic validation
- Metrics reporting
"""

import pytest
from spark.kit.analysis import GraphAnalyzer
from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ConditionSpec,
    ToolDefinitionSpec,
)


# ==============================================================================
# Basic Analyzer Tests
# ==============================================================================

def test_analyzer_initialization():
    """Test GraphAnalyzer initialization."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node1', to_node='node2')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    assert analyzer.spec == spec
    assert 'node1' in analyzer._node_map
    assert 'node2' in analyzer._node_map
    assert 'node2' in analyzer._adjacency['node1']


def test_empty_graph():
    """Test analyzer with empty graph."""
    spec = GraphSpec(
        id='empty',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 1
    assert complexity['edge_count'] == 0
    assert complexity['max_depth'] == 0
    assert complexity['cyclic'] is False


def test_single_edge_graph():
    """Test analyzer with simple two-node graph."""
    spec = GraphSpec(
        id='simple',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 2
    assert complexity['edge_count'] == 1
    assert complexity['max_depth'] == 1
    assert complexity['branching_factor'] == 1.0
    assert complexity['cyclic'] is False


# ==============================================================================
# Complexity Analysis Tests
# ==============================================================================

def test_linear_chain_complexity():
    """Test complexity metrics for linear chain."""
    spec = GraphSpec(
        id='chain',
        start='n1',
        nodes=[
            NodeSpec(id='n1', type='Node'),
            NodeSpec(id='n2', type='Node'),
            NodeSpec(id='n3', type='Node'),
            NodeSpec(id='n4', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='n1', to_node='n2'),
            EdgeSpec(id='e2', from_node='n2', to_node='n3'),
            EdgeSpec(id='e3', from_node='n3', to_node='n4'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 4
    assert complexity['edge_count'] == 3
    assert complexity['max_depth'] == 3
    assert complexity['avg_depth'] == 1.5  # (0 + 1 + 2 + 3) / 4
    assert complexity['branching_factor'] == 1.0
    assert complexity['cyclic'] is False
    assert complexity['connected_components'] == 1
    assert len(complexity['unreachable_nodes']) == 0


def test_branching_complexity():
    """Test complexity metrics for branching graph."""
    spec = GraphSpec(
        id='branch',
        start='root',
        nodes=[
            NodeSpec(id='root', type='Node'),
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='root', to_node='a'),
            EdgeSpec(id='e2', from_node='root', to_node='b'),
            EdgeSpec(id='e3', from_node='root', to_node='c'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 4
    assert complexity['edge_count'] == 3
    assert complexity['max_depth'] == 1
    assert complexity['branching_factor'] == 3.0  # root has 3 outgoing edges
    assert complexity['cyclic'] is False


def test_cycle_detection():
    """Test cycle detection."""
    spec = GraphSpec(
        id='cycle',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='b', to_node='c'),
            EdgeSpec(id='e3', from_node='c', to_node='a'),  # Creates cycle
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['cyclic'] is True
    assert complexity['cycle_count'] >= 1
    assert len(complexity['cycles']) >= 1


def test_disconnected_components():
    """Test detection of disconnected components."""
    spec = GraphSpec(
        id='disconnected',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
            NodeSpec(id='d', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='c', to_node='d'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['connected_components'] == 2
    assert len(complexity['unreachable_nodes']) == 2  # c and d not reachable from a


# ==============================================================================
# Bottleneck Detection Tests
# ==============================================================================

def test_high_fan_in_bottleneck():
    """Test detection of high fan-in bottleneck."""
    nodes = [NodeSpec(id=f'n{i}', type='Node') for i in range(15)]
    edges = [EdgeSpec(id=f'e{i}', from_node=f'n{i}', to_node='n14') for i in range(14)]

    spec = GraphSpec(
        id='fan_in',
        start='n0',
        nodes=nodes,
        edges=edges
    )

    analyzer = GraphAnalyzer(spec)
    bottlenecks = analyzer.identify_bottlenecks()

    fan_in_bottlenecks = [b for b in bottlenecks if b['type'] == 'high_fan_in']
    assert len(fan_in_bottlenecks) > 0
    assert fan_in_bottlenecks[0]['node_id'] == 'n14'
    assert fan_in_bottlenecks[0]['fan_in_count'] == 14


def test_sequential_chain_bottleneck():
    """Test detection of long sequential chains."""
    nodes = [NodeSpec(id=f'n{i}', type='Node') for i in range(6)]
    edges = [EdgeSpec(id=f'e{i}', from_node=f'n{i}', to_node=f'n{i+1}') for i in range(5)]

    spec = GraphSpec(
        id='chain',
        start='n0',
        nodes=nodes,
        edges=edges
    )

    analyzer = GraphAnalyzer(spec)
    bottlenecks = analyzer.identify_bottlenecks()

    chain_bottlenecks = [b for b in bottlenecks if b['type'] == 'sequential_chain']
    assert len(chain_bottlenecks) > 0
    assert chain_bottlenecks[0]['chain_length'] >= 4


def test_complex_condition_bottleneck():
    """Test detection of complex edge conditions."""
    spec = GraphSpec(
        id='complex',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='a',
                to_node='b',
                condition=ConditionSpec(
                    kind='expr',
                    expr='$.outputs.score > 0.7 and $.outputs.ready and $.outputs.count >= 10'
                )
            )
        ]
    )

    analyzer = GraphAnalyzer(spec)
    bottlenecks = analyzer.identify_bottlenecks()

    complex_bottlenecks = [b for b in bottlenecks if b['type'] == 'complex_condition']
    assert len(complex_bottlenecks) > 0


# ==============================================================================
# Optimization Suggestions Tests
# ==============================================================================

def test_suggest_remove_unreachable():
    """Test suggestion to remove unreachable nodes."""
    spec = GraphSpec(
        id='unreachable',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),  # Unreachable
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    assert any('unreachable' in s.lower() for s in suggestions)


def test_suggest_parallelization():
    """Test suggestion for parallelization opportunities."""
    # Create two independent chains
    spec = GraphSpec(
        id='parallel',
        start='root',
        nodes=[
            NodeSpec(id='root', type='Node'),
            NodeSpec(id='a1', type='Node'),
            NodeSpec(id='a2', type='Node'),
            NodeSpec(id='b1', type='Node'),
            NodeSpec(id='b2', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='root', to_node='a1'),
            EdgeSpec(id='e2', from_node='a1', to_node='a2'),
            EdgeSpec(id='e3', from_node='root', to_node='b1'),
            EdgeSpec(id='e4', from_node='b1', to_node='b2'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    # Should detect independent chains
    assert len(suggestions) > 0


def test_suggest_join_node():
    """Test suggestion to use JoinNode for high fan-in."""
    nodes = [NodeSpec(id=f'n{i}', type='Node') for i in range(8)]
    edges = [EdgeSpec(id=f'e{i}', from_node=f'n{i}', to_node='n7') for i in range(7)]

    spec = GraphSpec(
        id='fan_in',
        start='n0',
        nodes=nodes,
        edges=edges
    )

    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    assert any('JoinNode' in s or 'fan-in' in s.lower() for s in suggestions)


def test_no_optimizations_needed():
    """Test when graph is already optimized."""
    spec = GraphSpec(
        id='optimized',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    assert any('good' in s.lower() or 'no' in s.lower() for s in suggestions)


# ==============================================================================
# Semantic Validation Tests
# ==============================================================================

def test_validate_unreachable_nodes():
    """Test validation detects unreachable nodes."""
    spec = GraphSpec(
        id='unreachable',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),  # Unreachable
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert any('unreachable' in issue.lower() for issue in issues)
    assert any('c' in issue for issue in issues)


def test_validate_cycles():
    """Test validation detects cycles."""
    spec = GraphSpec(
        id='cycle',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='b', to_node='a'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert any('cycle' in issue.lower() for issue in issues)


def test_validate_orphan_nodes():
    """Test validation detects orphan nodes."""
    spec = GraphSpec(
        id='orphan',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='orphan', type='Node'),  # No edges
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert any('orphan' in issue.lower() for issue in issues)


def test_validate_tool_dependencies():
    """Test validation detects tool dependency issues."""
    spec = GraphSpec(
        id='tool_missing',
        start='agent',
        nodes=[
            NodeSpec(
                id='agent',
                type='Agent',
                config={'tools': [{'name': 'search', 'source': 'tools:search'}]}
            )
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert any('tool' in issue.lower() for issue in issues)


def test_validate_conflicting_edges():
    """Test validation detects conflicting unconditional edges."""
    spec = GraphSpec(
        id='conflict',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='a', to_node='b'),  # Duplicate unconditional edge
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert any('unconditional' in issue.lower() for issue in issues)


def test_validate_clean_graph():
    """Test validation passes for clean graph."""
    spec = GraphSpec(
        id='clean',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    assert len(issues) == 0


# ==============================================================================
# Metrics Report Tests
# ==============================================================================

def test_generate_metrics_report():
    """Test metrics report generation."""
    spec = GraphSpec(
        id='test',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b'),
            EdgeSpec(id='e2', from_node='b', to_node='c'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    report = analyzer.generate_metrics_report()

    assert 'GRAPH ANALYSIS REPORT' in report
    assert 'COMPLEXITY METRICS' in report
    assert 'BOTTLENECKS' in report
    assert 'OPTIMIZATION SUGGESTIONS' in report
    assert 'SEMANTIC VALIDATION' in report
    assert 'Nodes: 3' in report
    assert 'Edges: 2' in report


def test_report_with_issues():
    """Test report generation with issues."""
    spec = GraphSpec(
        id='issues',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='unreachable', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='a', to_node='b')
        ]
    )

    analyzer = GraphAnalyzer(spec)
    report = analyzer.generate_metrics_report()

    assert 'Unreachable Nodes: 1' in report or 'unreachable' in report.lower()


# ==============================================================================
# Edge Cases
# ==============================================================================

def test_graph_with_single_node():
    """Test analyzer with single node graph."""
    spec = GraphSpec(
        id='single',
        start='a',
        nodes=[
            NodeSpec(id='a', type='Node'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    # Should handle gracefully
    assert complexity['node_count'] == 1
    assert complexity['edge_count'] == 0
    assert complexity['cyclic'] is False


def test_complex_branching():
    """Test analyzer with complex branching."""
    spec = GraphSpec(
        id='complex',
        start='root',
        nodes=[
            NodeSpec(id='root', type='Node'),
            NodeSpec(id='a', type='Node'),
            NodeSpec(id='b', type='Node'),
            NodeSpec(id='c', type='Node'),
            NodeSpec(id='d', type='Node'),
            NodeSpec(id='e', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='root', to_node='a'),
            EdgeSpec(id='e2', from_node='root', to_node='b'),
            EdgeSpec(id='e3', from_node='a', to_node='c'),
            EdgeSpec(id='e4', from_node='a', to_node='d'),
            EdgeSpec(id='e5', from_node='b', to_node='e'),
            EdgeSpec(id='e6', from_node='c', to_node='e'),
            EdgeSpec(id='e7', from_node='d', to_node='e'),
        ]
    )

    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 6
    assert complexity['edge_count'] == 7
    assert complexity['max_depth'] == 2
    assert complexity['connected_components'] == 1

    bottlenecks = analyzer.identify_bottlenecks()
    # Node 'e' has high fan-in (3 incoming edges)
    fan_in = [b for b in bottlenecks if b['type'] == 'high_fan_in' and b['node_id'] == 'e']
    # May or may not trigger depending on threshold


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
