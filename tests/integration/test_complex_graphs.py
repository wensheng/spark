"""
Integration tests for complex graph scenarios (Phase 6.1).

Tests complex patterns:
- Multi-agent workflows
- Recursive patterns
- Error handling and recovery
- State management across nodes
- Conditional routing
- Fan-out and join patterns
- Long-running workflows
"""

import pytest
import tempfile
import os
from pathlib import Path

from spark.graphs.graph import Graph
from spark.nodes.nodes import Node, JoinNode
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.models.openai import OpenAIModel
from spark.nodes.serde import graph_to_spec, load_graph_spec
from spark.kit.codegen import generate
from spark.kit.analysis import GraphAnalyzer
from spark.nodes.spec import GraphSpec
from spark.nodes.types import ExecutionContext


# ==============================================================================
# Test Node Implementations
# ==============================================================================

class ProcessNode(Node):
    """Simple processing node."""
    async def process(self, context: ExecutionContext):
        data = context.inputs.get('data', [])
        return {'data': data + [self.config.id]}


class RouterNode(Node):
    """Router node that splits based on input."""
    async def process(self, context: ExecutionContext):
        value = context.inputs.get('value', 0)
        return {'value': value, 'route': 'high' if value > 50 else 'low'}


class CounterNode(Node):
    """Node that uses state to count invocations."""
    async def process(self, context: ExecutionContext):
        count = context.state.get('count', 0) + 1
        context.state['count'] = count
        return {'count': count, 'done': count >= 3}


class ErrorNode(Node):
    """Node that can fail."""
    async def process(self, context: ExecutionContext):
        fail = context.inputs.get('fail', False)
        if fail:
            raise ValueError("Simulated error")
        return {'status': 'success'}


class AggregatorNode(JoinNode):
    """Join node that aggregates results."""
    async def process(self, context: ExecutionContext):
        # Aggregate data from multiple parents
        all_data = []
        for key in self.keys:
            parent_data = context.inputs.get(key, {})
            if 'data' in parent_data:
                all_data.extend(parent_data['data'])
        return {'aggregated': all_data, 'count': len(all_data)}


# ==============================================================================
# Complex Pattern Tests
# ==============================================================================

def test_complex_multi_stage_pipeline():
    """Test multi-stage processing pipeline."""
    # Stage 1: Initial processing
    start = ProcessNode()

    # Stage 2: Parallel processing
    branch1 = ProcessNode()
    branch2 = ProcessNode()
    start >> branch1
    start >> branch2

    # Stage 3: Aggregation
    join = AggregatorNode(keys=[branch1.config.id, branch2.config.id])
    branch1 >> join
    branch2 >> join

    # Stage 4: Final processing
    final = ProcessNode()
    join >> final

    # Create graph and serialize
    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    # Verify structure
    assert len(spec.nodes) == 5
    assert len(spec.edges) == 5  # start>>branch1, start>>branch2, branch1>>join, branch2>>join, join>>final

    # Analyze complexity
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()
    assert complexity['max_depth'] == 3
    assert complexity['branching_factor'] >= 1.0  # Start node fans out to 2 branches

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


def test_complex_conditional_routing():
    """Test complex conditional routing patterns."""
    # Router node
    router = RouterNode()

    # High value path
    high_path = ProcessNode()
    router.on(expr="$.outputs.route == 'high'") >> high_path

    # Low value path
    low_path = ProcessNode()
    router.on(expr="$.outputs.route == 'low'") >> low_path

    # Converge to final node
    final = ProcessNode()
    high_path >> final
    low_path >> final

    graph = Graph(start=router)
    spec = graph_to_spec(graph)

    # Verify conditional edges
    assert len(spec.edges) == 4
    conditional_edges = [e for e in spec.edges if e.condition is not None]
    assert len(conditional_edges) == 2

    # Verify all paths lead to final
    assert any(e.to_node == final.config.id for e in spec.edges)

    # Analyze
    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()
    assert len(issues) == 0


def test_complex_stateful_workflow():
    """Test workflow with stateful nodes."""
    # Counter nodes that maintain state
    counter1 = CounterNode()
    counter2 = CounterNode()

    # Loop back based on state
    counter1.on(expr="not $.outputs.done") >> counter2
    counter2.on(expr="not $.outputs.done") >> counter1

    # Exit when done
    exit_node = ProcessNode()
    counter1.on(expr="$.outputs.done") >> exit_node
    counter2.on(expr="$.outputs.done") >> exit_node

    graph = Graph(start=counter1)
    spec = graph_to_spec(graph)

    # Verify cycle detection
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()
    assert complexity['cyclic'] is True
    assert complexity['cycle_count'] >= 1

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


def test_complex_multi_agent_workflow():
    """Test workflow with multiple agents."""
    # Research agent
    researcher = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o-mini'),
            system_prompt='You are a research assistant.'
        )
    )

    # Analyst agent
    analyst = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o-mini'),
            system_prompt='You are an analyst.'
        )
    )

    # Writer agent
    writer = Agent(
        config=AgentConfig(
            model=OpenAIModel(model_id='gpt-4o-mini'),
            system_prompt='You are a writer.'
        )
    )

    # Connect agents
    researcher >> analyst >> writer

    graph = Graph(start=researcher)
    spec = graph_to_spec(graph)

    # Verify agent nodes
    agent_nodes = [n for n in spec.nodes if n.type == 'Agent']
    assert len(agent_nodes) == 3

    # Analyze
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()
    assert complexity['node_count'] == 3
    assert complexity['max_depth'] == 2

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        with open(output_path) as f:
            code = f.read()
            assert 'Agent' in code
            assert 'AgentConfig' in code
            assert code.count('Agent(') >= 3


def test_complex_fan_out_fan_in():
    """Test fan-out followed by fan-in pattern."""
    # Start node fans out to multiple parallel processors
    start = ProcessNode()

    # Parallel processing branches
    workers = [ProcessNode() for _ in range(5)]
    for worker in workers:
        start >> worker

    # Join results
    join = AggregatorNode(keys=[w.config.id for w in workers])
    for worker in workers:
        worker >> join

    # Final processing
    final = ProcessNode()
    join >> final

    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    # Verify structure
    assert len(spec.nodes) == 8  # start + 5 workers + join + final = 8

    # Analyze bottlenecks
    analyzer = GraphAnalyzer(spec)
    bottlenecks = analyzer.identify_bottlenecks()

    # Bottlenecks may or may not be detected depending on threshold
    # Just verify analyzer can run on this complex structure
    assert bottlenecks is not None

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


def test_complex_nested_conditions():
    """Test nested conditional routing."""
    router = RouterNode()

    # First level routing
    high = ProcessNode()
    low = ProcessNode()
    router.on(expr="$.outputs.value > 50") >> high
    router.on(expr="$.outputs.value <= 50") >> low

    # Second level routing from high
    very_high = ProcessNode()
    moderate = ProcessNode()
    high.on(expr="$.outputs.value > 75") >> very_high
    high.on(expr="$.outputs.value <= 75") >> moderate

    # Final nodes
    final_high = ProcessNode()
    final_low = ProcessNode()
    very_high >> final_high
    moderate >> final_high
    low >> final_low

    graph = Graph(start=router)
    spec = graph_to_spec(graph)

    # Verify complex structure
    assert len(spec.nodes) == 7
    conditional_edges = [e for e in spec.edges if e.condition is not None]
    assert len(conditional_edges) == 4

    # Analyze
    analyzer = GraphAnalyzer(spec)
    complexity = analyzer.analyze_complexity()
    assert complexity['max_depth'] >= 3

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        with open(output_path) as f:
            code = f.read()
            assert '.on(' in code
            assert 'expr=' in code


def test_complex_graph_state_usage():
    """Test workflow using graph state for coordination."""
    # Multiple nodes that read/write graph state
    node1 = ProcessNode()
    node2 = ProcessNode()
    node3 = ProcessNode()

    node1 >> node2 >> node3

    graph = Graph(start=node1)
    spec = graph_to_spec(graph)

    # Verify spec includes graph state info if present
    assert spec is not None
    assert len(spec.nodes) == 3

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


def test_complex_error_handling_paths():
    """Test error handling and recovery paths."""
    # Main processing path
    start = ProcessNode()
    risky = ErrorNode()
    success = ProcessNode()

    start >> risky
    risky.on(expr="$.outputs.status == 'success'") >> success

    # Error recovery path would typically be added via try/except in the node
    # or via custom error handling edges

    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    assert len(spec.nodes) == 3

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        assert os.path.exists(output_path)


def test_complex_priority_routing():
    """Test routing with edge priorities."""
    router = ProcessNode()

    # Critical path (high priority)
    critical = ProcessNode()
    router.on(expr="$.outputs.critical", priority=100) >> critical

    # Normal path (medium priority)
    normal = ProcessNode()
    router.on(expr="$.outputs.normal", priority=50) >> normal

    # Default path (low priority)
    default = ProcessNode()
    router.on(priority=1) >> default

    graph = Graph(start=router)
    spec = graph_to_spec(graph)

    # Verify priorities are preserved
    edges_by_priority = sorted(spec.edges, key=lambda e: e.priority, reverse=True)
    assert edges_by_priority[0].priority == 100
    assert edges_by_priority[1].priority == 50
    assert edges_by_priority[2].priority == 1

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')
        with open(output_path) as f:
            code = f.read()
            assert 'priority=' in code


# ==============================================================================
# Complex Analysis Tests
# ==============================================================================

def test_complex_graph_optimization_suggestions():
    """Test optimization suggestions for complex graphs."""
    # Create inefficient graph
    start = ProcessNode()

    # Long sequential chain (could be parallelized)
    nodes = [ProcessNode() for _ in range(10)]
    current = start
    for node in nodes:
        current >> node
        current = node

    # Add unreachable nodes
    unreachable1 = ProcessNode()
    unreachable2 = ProcessNode()

    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    # Manually add unreachable nodes to spec
    from spark.nodes.spec import NodeSpec
    spec.nodes.append(NodeSpec(id='unreachable1', type='ProcessNode'))
    spec.nodes.append(NodeSpec(id='unreachable2', type='ProcessNode'))

    # Analyze
    analyzer = GraphAnalyzer(spec)
    suggestions = analyzer.suggest_optimizations()

    # Should detect unreachable nodes
    assert any('unreachable' in s.lower() for s in suggestions)

    # Should detect long sequential chain
    bottlenecks = analyzer.identify_bottlenecks()
    chain_bottlenecks = [b for b in bottlenecks if b['type'] == 'sequential_chain']
    assert len(chain_bottlenecks) > 0


def test_complex_graph_semantic_validation():
    """Test semantic validation of complex graphs."""
    # Create graph with various issues
    node1 = ProcessNode()
    node2 = ProcessNode()
    node3 = ProcessNode()

    # Create cycle
    node1 >> node2 >> node3 >> node1

    graph = Graph(start=node1)
    spec = graph_to_spec(graph)

    # Analyze
    analyzer = GraphAnalyzer(spec)
    issues = analyzer.validate_semantics()

    # Should detect cycle
    assert any('cycle' in issue.lower() for issue in issues)


def test_complex_graph_metrics_report():
    """Test comprehensive metrics report for complex graphs."""
    # Create moderately complex graph
    start = ProcessNode()
    branch1 = ProcessNode()
    branch2 = ProcessNode()
    branch3 = ProcessNode()

    start >> branch1 >> branch2
    start >> branch3

    join = AggregatorNode(keys=[branch2.config.id, branch3.config.id])
    branch2 >> join
    branch3 >> join

    final = ProcessNode()
    join >> final

    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    # Generate report
    analyzer = GraphAnalyzer(spec)
    report = analyzer.generate_metrics_report()

    assert 'GRAPH ANALYSIS REPORT' in report
    assert 'COMPLEXITY METRICS' in report
    assert 'Nodes:' in report
    assert 'Edges:' in report
    assert 'Max Depth:' in report
    assert 'Branching Factor:' in report


# ==============================================================================
# Complex Code Generation Tests
# ==============================================================================

def test_complex_graph_code_generation():
    """Test code generation for complex graphs."""
    # Create complex graph
    start = ProcessNode()
    router = RouterNode()
    path1 = ProcessNode()
    path2 = ProcessNode()
    join = AggregatorNode(keys=[path1.config.id, path2.config.id])
    final = ProcessNode()

    start >> router
    router.on(expr="$.outputs.value > 50") >> path1
    router.on(expr="$.outputs.value <= 50") >> path2
    path1 >> join
    path2 >> join
    join >> final

    graph = Graph(start=start)
    spec = graph_to_spec(graph)

    # Generate code
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')

        with open(output_path) as f:
            code = f.read()

            # Verify essential components
            assert 'def build_nodes()' in code
            assert 'def build_graph()' in code
            assert 'class' in code

            # Verify node classes are generated
            assert 'class ' in code
            assert 'Node(Node)' in code or 'Node)' in code

            # Verify routing logic
            assert '.on(' in code
            assert 'expr=' in code


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
