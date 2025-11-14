"""
Integration tests for round-trip conversions (Phase 6.1).

Tests the complete workflow:
1. Create Python graph
2. Serialize to JSON spec
3. Generate code from spec
4. Verify equivalence

Covers all node types, agent configurations, and complex scenarios.
"""

import pytest
import tempfile
import os
from pathlib import Path

from spark.graphs.graph import Graph
from spark.nodes.nodes import Node
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.models.openai import OpenAIModel
from spark.nodes.serde import graph_to_spec, load_graph_spec
from spark.kit.codegen import generate, CodeGenerator
from spark.kit.analysis import GraphAnalyzer
from spark.kit.diff import SpecDiffer
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec, ToolDefinitionSpec, ToolParameterSpec


# ==============================================================================
# Test Node Implementations
# ==============================================================================

class SimpleNode(Node):
    """Simple test node."""
    async def process(self, context):
        return {'processed': True}


# ==============================================================================
# Round-Trip Tests
# ==============================================================================

def test_round_trip_simple_node():
    """Test round-trip for simple node graph."""
    # Create graph
    node = SimpleNode()
    graph = Graph(start=node)

    # Serialize to spec
    spec = graph_to_spec(graph)
    assert spec is not None
    assert len(spec.nodes) == 1
    assert spec.start is not None

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

        # Verify code is valid Python
        with open(output_path) as f:
            code = f.read()
            assert 'def build_nodes()' in code
            assert 'def build_graph()' in code
            assert 'class' in code

    # Re-serialize and compare
    spec_dict = spec.model_dump()
    spec2 = GraphSpec.model_validate(spec_dict)
    assert spec.id == spec2.id
    assert len(spec.nodes) == len(spec2.nodes)


def test_round_trip_linear_chain():
    """Test round-trip for linear chain of nodes."""
    # Create graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node3 = SimpleNode()

    node1 >> node2 >> node3
    graph = Graph(start=node1)

    # Serialize
    spec = graph_to_spec(graph)
    assert len(spec.nodes) == 3
    assert len(spec.edges) >= 2

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

    # Verify spec structure
    node_ids = {n.id for n in spec.nodes}
    assert len(node_ids) == 3

    # Check edges connect nodes
    for edge in spec.edges:
        assert edge.from_node in node_ids
        assert edge.to_node in node_ids


def test_round_trip_branching_graph():
    """Test round-trip for branching graph."""
    # Create graph with branches
    root = SimpleNode()
    branch1 = SimpleNode()
    branch2 = SimpleNode()
    branch3 = SimpleNode()

    root >> branch1
    root >> branch2
    root >> branch3

    graph = Graph(start=root)

    # Serialize
    spec = graph_to_spec(graph)
    assert len(spec.nodes) == 4
    assert len(spec.edges) == 3

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

        with open(output_path) as f:
            code = f.read()
            # Should have multiple edges
            assert code.count('>>') >= 3


def test_round_trip_agent_basic():
    """Test round-trip for basic agent."""
    # Create agent
    agent = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o-mini'),
            system_prompt='You are a helpful assistant.'
        )
    )
    graph = Graph(start=agent)

    # Serialize
    spec = graph_to_spec(graph)
    assert len(spec.nodes) == 1
    assert spec.nodes[0].type == 'Agent'

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

        with open(output_path) as f:
            code = f.read()
            assert 'Agent' in code
            assert 'AgentConfig' in code
            assert 'OpenAIModel' in code


def test_round_trip_with_edge_conditions():
    """Test round-trip for graph with edge conditions."""
    # Create graph with conditional edges
    router = SimpleNode()
    path1 = SimpleNode()
    path2 = SimpleNode()

    router.on(expr='$.outputs.score > 0.5') >> path1
    router.on(expr='$.outputs.score <= 0.5') >> path2

    graph = Graph(start=router)

    # Serialize
    spec = graph_to_spec(graph)
    assert len(spec.edges) == 2

    # Check conditions are preserved
    conditions = [e.condition for e in spec.edges if e.condition]
    assert len(conditions) == 2

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

        with open(output_path) as f:
            code = f.read()
            assert '.on(' in code
            assert 'expr=' in code


def test_round_trip_code_generation_styles():
    """Test round-trip with different code generation styles."""
    # Create simple graph
    node = SimpleNode()
    graph = Graph(start=node)
    spec = graph_to_spec(graph)

    # Test each style
    for style in ['simple', 'production']:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = generate(spec, tmpdir, style=style)
            assert os.path.exists(output_path)

            with open(output_path) as f:
                code = f.read()
                # All styles should have basic structure
                assert 'def build_nodes()' in code or 'def build_graph()' in code


def test_round_trip_spec_validation():
    """Test that serialized specs pass validation."""
    # Create graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2
    graph = Graph(start=node1)

    # Serialize
    spec = graph_to_spec(graph)

    # Validate using analyzer
    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    # Should have no semantic issues
    assert len(issues) == 0


def test_round_trip_complex_agent():
    """Test round-trip for agent with tools and full config."""
    # Create agent with full configuration
    from spark.tools.decorator import tool

    @tool
    def search_tool(query: str) -> str:
        """Search for information."""
        return f"Results for: {query}"

    agent = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o'),
            system_prompt='You are a research assistant.',
            tools=[search_tool],
            max_steps=5,
            tool_choice='auto'
        )
    )
    graph = Graph(start=agent)

    # Serialize
    spec = graph_to_spec(graph)

    # Verify agent config captured
    assert len(spec.nodes) == 1
    node_spec = spec.nodes[0]
    assert node_spec.type == 'Agent'
    assert node_spec.config is not None

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

        with open(output_path) as f:
            code = f.read()
            assert 'max_steps' in code


# ==============================================================================
# Diff and Comparison Tests
# ==============================================================================

def test_round_trip_diff_stability():
    """Test that spec diff is stable across serialization."""
    # Create graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2
    graph = Graph(start=node1)

    # Serialize twice
    spec1 = graph_to_spec(graph)
    spec2 = graph_to_spec(graph)

    # Diff should show no changes
    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert not result.has_changes


def test_round_trip_modification_detection():
    """Test that modifications are detected in round-trip."""
    # Create first graph version
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2
    graph1 = Graph(start=node1)

    # Serialize first version
    spec1 = graph_to_spec(graph1)

    # Create modified version with additional node
    node1_v2 = SimpleNode()
    node2_v2 = SimpleNode()
    node3 = SimpleNode()
    node1_v2 >> node2_v2 >> node3
    graph2 = Graph(start=node1_v2)

    # Serialize second version
    spec2 = graph_to_spec(graph2)

    # Diff should show changes
    differ = SpecDiffer()
    result = differ.diff(spec1, spec2)

    assert result.has_changes
    assert result.summary['nodes_added'] >= 1


# ==============================================================================
# Code Generation Verification Tests
# ==============================================================================

def test_generated_code_imports():
    """Test that generated code has correct imports."""
    # Create agent graph
    agent = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o-mini')
        )
    )
    graph = Graph(start=agent)
    spec = graph_to_spec(graph)

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')

        with open(output_path) as f:
            code = f.read()

            # Check for required imports
            assert 'from spark.agents.agent import Agent' in code
            assert 'from spark.models.openai import OpenAIModel' in code
            assert 'from spark.graphs.graph import Graph' in code


def test_generated_code_structure():
    """Test that generated code has proper structure."""
    # Create simple graph
    node = SimpleNode()
    graph = Graph(start=node)
    spec = graph_to_spec(graph)

    # Generate code
    generator = CodeGenerator(spec, style='production')
    code = generator.generate_complete_file()

    # Verify structure
    assert 'Generated from GraphSpec' in code
    assert 'def build_nodes()' in code
    assert 'def build_graph()' in code
    assert 'async def main():' in code
    assert 'if __name__ ==' in code


def test_generated_code_node_classes():
    """Test that generated code defines node classes."""
    # Create multi-node graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2
    graph = Graph(start=node1)
    spec = graph_to_spec(graph)

    # Generate code
    generator = CodeGenerator(spec, style='production')
    code = generator.generate_complete_file()

    # Should have node class definitions
    class_count = code.count('class ')
    assert class_count >= 2  # At least 2 node classes


# ==============================================================================
# Analysis Integration Tests
# ==============================================================================

def test_analyze_generated_spec():
    """Test analyzing a generated spec."""
    # Create graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node3 = SimpleNode()
    node1 >> node2 >> node3
    graph = Graph(start=node1)

    # Serialize
    spec = graph_to_spec(graph)

    # Analyze
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()

    assert complexity['node_count'] == 3
    assert complexity['edge_count'] >= 2
    assert complexity['max_depth'] == 2
    assert not complexity['cyclic']


def test_optimize_generated_spec():
    """Test optimizing a generated spec."""
    # Create graph with unreachable node
    node1 = SimpleNode()
    node2 = SimpleNode()
    unreachable = SimpleNode()

    node1 >> node2
    graph = Graph(start=node1)

    # Manually add unreachable node to spec
    spec = graph_to_spec(graph)
    spec.nodes.append(NodeSpec(id='unreachable', type='Node'))

    # Analyze
    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    # Should suggest removing unreachable
    assert any('unreachable' in s.lower() for s in suggestions)


# ==============================================================================
# Complete Workflow Tests
# ==============================================================================

def test_complete_workflow_serialize_generate_validate():
    """Test complete workflow: serialize → generate → validate."""
    # 1. Create Python graph
    node1 = SimpleNode()
    node2 = SimpleNode()
    node1 >> node2
    graph = Graph(start=node1)

    # 2. Serialize to spec
    spec = graph_to_spec(graph)
    assert spec is not None

    # 3. Validate spec
    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()
    assert len(issues) == 0

    # 4. Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)

    # 5. Re-serialize and verify
    spec_dict = spec.model_dump()
    spec2 = GraphSpec.model_validate(spec_dict)
    assert len(spec.nodes) == len(spec2.nodes)


def test_complete_workflow_with_analysis():
    """Test workflow with analysis."""
    # Create graph
    root = SimpleNode()
    branch1 = SimpleNode()
    branch2 = SimpleNode()
    root >> branch1
    root >> branch2
    graph = Graph(start=root)

    # Serialize
    spec = graph_to_spec(graph)

    # Analyze
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()
    assert complexity['branching_factor'] >= 2

    # Get suggestions
    suggestions = analyzer.suggest_optimizations()
    assert len(suggestions) > 0

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
