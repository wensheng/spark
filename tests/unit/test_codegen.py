"""
Tests for enhanced code generation (Phase 3).

Tests the production-ready code generator with support for:
- Import optimization
- Full agent configuration with tools, memory, reasoning strategies
- All node types (Agent, RpcNode, JoinNode, batch nodes)
- GraphState and EventBus
- Tool generation
- Complete project structure
"""

import os
import tempfile
import pytest
from pathlib import Path

from spark.kit.codegen import (
    CodeGenerator,
    ImportOptimizer,
    generate,
    _safe_module_id,
    _safe_ident,
    _class_name,
)
from spark.nodes.spec import (
    GraphSpec,
    NodeSpec,
    EdgeSpec,
    ConditionSpec,
    ToolDefinitionSpec,
    ToolParameterSpec,
    GraphStateSpec,
    ModelSpec,
)


# ==============================================================================
# Utility Function Tests
# ==============================================================================

def test_safe_module_id():
    """Test module ID generation."""
    assert _safe_module_id("my-graph") == "my_graph"
    assert _safe_module_id("Graph 123") == "graph_123"
    assert _safe_module_id("test.graph") == "test_graph"
    assert _safe_module_id("") == "graph"


def test_safe_ident():
    """Test Python identifier generation."""
    assert _safe_ident("my-node") == "my_node"
    assert _safe_ident("node 123") == "node_123"
    assert _safe_ident("123node") == "_123node"
    assert _safe_ident("") == "_"


def test_class_name():
    """Test class name generation."""
    assert _class_name("my-node", "Node") == "MyNode"  # Already ends with Node
    assert _class_name("search-agent", "Agent") == "SearchAgent"  # Already ends with Agent
    assert _class_name("node", "Agent") == "NodeAgent"  # Add Agent suffix
    assert _class_name("processor", "Node") == "ProcessorNode"  # Add Node suffix
    assert _class_name("analyzer", "Agent") == "AnalyzerAgent"  # Add Agent suffix


# ==============================================================================
# ImportOptimizer Tests
# ==============================================================================

def test_import_optimizer_basic():
    """Test basic import optimization."""
    optimizer = ImportOptimizer()
    optimizer.add_import('typing', ['Any', 'Dict'])
    optimizer.add_import('spark.nodes.nodes', ['Node'])
    optimizer.add_import('spark.agents.agent', ['Agent'])

    imports = optimizer.generate_imports()

    assert 'import typing' in imports or 'from typing import Any, Dict' in imports
    assert 'from spark.agents.agent import Agent' in imports
    assert 'from spark.nodes.nodes import Node' in imports


def test_import_optimizer_analyze_spec():
    """Test import analysis from spec."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Agent', config={'model': 'gpt-4o-mini'}),
            NodeSpec(id='node2', type='Node', description='Basic node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node1', to_node='node2')
        ]
    )

    optimizer = ImportOptimizer()
    optimizer.analyze_spec(spec)
    imports = optimizer.generate_imports()

    # Should have agent imports
    assert 'Agent' in imports
    assert 'AgentConfig' in imports
    # Should have basic node imports
    assert 'Node' in imports
    # Should have model imports
    assert 'OpenAIModel' in imports
    # Should have graph imports
    assert 'Graph' in imports


def test_import_optimizer_with_graph_state():
    """Test import analysis with GraphState."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')],
        graph_state=GraphStateSpec(initial_state={'counter': 0})
    )

    optimizer = ImportOptimizer()
    optimizer.analyze_spec(spec)
    imports = optimizer.generate_imports()

    assert 'GraphState' in imports


def test_import_optimizer_with_tools():
    """Test import analysis with tools."""
    tool = ToolDefinitionSpec(
        name='test_tool',
        function='module:func',
        description='Test',
        parameters=[]
    )

    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Agent')],
        tools=[tool]
    )

    optimizer = ImportOptimizer()
    optimizer.analyze_spec(spec)
    imports = optimizer.generate_imports()

    assert 'tool' in imports


# ==============================================================================
# CodeGenerator Basic Tests
# ==============================================================================

def test_code_generator_initialization():
    """Test CodeGenerator initialization."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    generator = CodeGenerator(spec, style='production')
    assert generator.spec == spec
    assert generator.style == 'production'
    assert generator.import_optimizer is not None


def test_generate_basic_node_class():
    """Test generating a basic node class."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node', description='Test node')]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_node_classes()

    assert 'class Node1Node(Node):' in code
    assert 'Test node' in code
    assert 'async def process' in code
    assert 'context: ExecutionContext' in code


def test_generate_agent_class():
    """Test generating an agent class."""
    spec = GraphSpec(
        id='test',
        start='agent1',
        nodes=[
            NodeSpec(
                id='agent1',
                type='Agent',
                description='Test agent',
                config={'model': 'gpt-4o-mini'}
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_node_classes()

    assert 'class Agent1Agent(Agent):' in code
    assert 'Test agent' in code


def test_generate_agent_with_full_config():
    """Test generating agent with full configuration."""
    spec = GraphSpec(
        id='test',
        start='agent1',
        nodes=[
            NodeSpec(
                id='agent1',
                type='Agent',
                config={
                    'model': 'gpt-4o',
                    'system_prompt': 'You are helpful',
                    'max_steps': 5,
                    'tool_choice': 'auto',
                    'output_mode': 'text',
                    'enable_cost_tracking': True,
                }
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_node_instances()

    assert 'OpenAIModel(model_id=\'gpt-4o\')' in code
    assert 'system_prompt=\'You are helpful\'' in code
    assert 'max_steps=5' in code
    assert 'tool_choice=\'auto\'' in code
    assert 'enable_cost_tracking=True' in code


def test_generate_agent_with_tools():
    """Test generating agent with tools."""
    spec = GraphSpec(
        id='test',
        start='agent1',
        nodes=[
            NodeSpec(
                id='agent1',
                type='Agent',
                config={
                    'model': 'gpt-4o-mini',
                    'tools': [
                        {'name': 'search', 'source': 'tools:search'},
                        {'name': 'calculate', 'source': 'tools:calculate'},
                    ]
                }
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_node_instances()

    assert "'search': search" in code
    assert "'calculate': calculate" in code


def test_generate_rpc_node():
    """Test generating RPC node class."""
    spec = GraphSpec(
        id='test',
        start='rpc1',
        nodes=[
            NodeSpec(
                id='rpc1',
                type='RpcNode',
                config={'host': '0.0.0.0', 'port': 8080}
            )
        ]
    )

    generator = CodeGenerator(spec)
    node_classes = generator.generate_node_classes()
    instances = generator.generate_node_instances()

    assert 'class Rpc1Node(RpcNode):' in node_classes
    assert 'async def rpc_example' in node_classes
    assert 'host=\'0.0.0.0\', port=8080' in instances


def test_generate_join_node():
    """Test generating Join node."""
    spec = GraphSpec(
        id='test',
        start='join1',
        nodes=[
            NodeSpec(
                id='join1',
                type='JoinNode',
                config={'keys': ['a', 'b'], 'mode': 'all'}
            )
        ]
    )

    generator = CodeGenerator(spec)
    instances = generator.generate_node_instances()

    assert 'JoinNode' in instances
    assert "keys=['a', 'b']" in instances
    assert "mode='all'" in instances


# ==============================================================================
# Tool Generation Tests
# ==============================================================================

def test_generate_tool_definitions():
    """Test generating tool function definitions."""
    tool = ToolDefinitionSpec(
        name='search_web',
        function='tools:search_web',
        description='Search the web',
        parameters=[
            ToolParameterSpec(
                name='query',
                type='str',
                description='Search query',
                required=True
            )
        ],
        return_type='str',
        return_description='Search results',
        is_async=False
    )

    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')],
        tools=[tool]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_tool_definitions()

    assert '@tool' in code
    assert 'def search_web(query: str) -> str:' in code
    assert 'Search the web' in code
    assert 'query: Search query' in code
    assert 'Search results' in code


def test_generate_async_tool():
    """Test generating async tool."""
    tool = ToolDefinitionSpec(
        name='fetch_data',
        function='tools:fetch_data',
        description='Fetch data',
        parameters=[],
        is_async=True
    )

    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')],
        tools=[tool]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_tool_definitions()

    assert 'async def fetch_data()' in code


# ==============================================================================
# Graph Assembly Tests
# ==============================================================================

def test_generate_graph_assembly_simple():
    """Test generating simple graph assembly."""
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

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert 'def build_graph()' in code
    assert "nodes['node1'] >> nodes['node2']" in code
    assert "Graph(start=nodes['node1'])" in code


def test_generate_graph_with_conditions():
    """Test generating graph with edge conditions."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node'),
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='node1',
                to_node='node2',
                condition=ConditionSpec(kind='expr', expr='$.outputs.score > 0.5')
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert ".on(expr='$.outputs.score > 0.5')" in code


def test_generate_graph_with_equals_condition():
    """Test generating graph with equals condition."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node'),
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='node1',
                to_node='node2',
                condition=ConditionSpec(kind='equals', equals={'action': 'search'})
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert ".on(action='search')" in code


def test_generate_graph_with_priority():
    """Test generating graph with edge priority."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node'),
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='node1',
                to_node='node2',
                condition=ConditionSpec(kind='expr', expr='$.outputs.ready'),
                priority=10
            )
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert 'priority=10' in code


def test_generate_graph_with_state():
    """Test generating graph with GraphState."""
    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')],
        graph_state=GraphStateSpec(
            initial_state={'counter': 0, 'max': 10},
            concurrent_mode=True
        )
    )

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert "await graph.state.set('counter', 0)" in code
    assert "await graph.state.set('max', 10)" in code
    assert 'enable_concurrent_mode()' in code


# ==============================================================================
# Complete File Generation Tests
# ==============================================================================

def test_generate_complete_file():
    """Test generating complete Python file."""
    spec = GraphSpec(
        id='test-graph',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Agent', config={'model': 'gpt-4o-mini'}),
            NodeSpec(id='node2', type='Node', description='Process data'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node1', to_node='node2')
        ]
    )

    generator = CodeGenerator(spec, style='production')
    code = generator.generate_complete_file()

    # Check header
    assert 'Generated from GraphSpec: test-graph' in code

    # Check imports
    assert 'from spark.agents.agent import Agent' in code
    assert 'from spark.nodes.nodes import Node' in code
    assert 'from spark.graphs.graph import Graph' in code

    # Check node classes
    assert 'class Node1Agent(Agent):' in code
    assert 'class Node2Node(Node):' in code

    # Check functions
    assert 'def build_nodes()' in code
    assert 'def build_graph()' in code
    assert 'async def main():' in code


def test_generate_with_all_features():
    """Test generating code with all features."""
    tool = ToolDefinitionSpec(
        name='calculate',
        function='tools:calculate',
        description='Calculate result',
        parameters=[
            ToolParameterSpec(name='expr', type='str', required=True)
        ]
    )

    spec = GraphSpec(
        id='comprehensive',
        start='agent1',
        nodes=[
            NodeSpec(
                id='agent1',
                type='Agent',
                description='Main agent',
                config={
                    'model': 'gpt-4o',
                    'system_prompt': 'You are helpful',
                    'tools': [{'name': 'calculate', 'source': 'tools:calculate'}],
                    'max_steps': 5,
                }
            ),
            NodeSpec(id='processor', type='Node', description='Process results'),
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='agent1',
                to_node='processor',
                condition=ConditionSpec(kind='expr', expr='$.outputs.ready')
            )
        ],
        tools=[tool],
        graph_state=GraphStateSpec(initial_state={'step': 0})
    )

    generator = CodeGenerator(spec, style='production')
    code = generator.generate_complete_file()

    # Should have all components
    assert '@tool' in code
    assert 'def calculate' in code
    assert 'class Agent1Agent(Agent):' in code
    assert 'class ProcessorNode(Node):' in code
    assert "await graph.state.set('step', 0)" in code
    assert 'async def main():' in code


# ==============================================================================
# Integration Tests
# ==============================================================================

def test_generate_function_simple_style():
    """Test generate() function with simple style."""
    spec = GraphSpec(
        id='simple-test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node1', to_node='node2')
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='simple')

        assert os.path.exists(output_path)
        assert 'spark_simple_test.py' in output_path

        # Read and verify content
        with open(output_path, 'r') as f:
            content = f.read()
            assert 'class Node1Node(Node):' in content
            assert 'class Node2Node(Node):' in content
            assert 'def build_nodes()' in content
            assert 'def build_graph()' in content


def test_generate_function_production_style():
    """Test generate() function with production style."""
    spec = GraphSpec(
        id='production-test',
        start='agent1',
        nodes=[
            NodeSpec(
                id='agent1',
                type='Agent',
                config={
                    'model': 'gpt-4o-mini',
                    'system_prompt': 'Test',
                }
            ),
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = generate(spec, tmpdir, style='production')

        assert os.path.exists(output_path)

        with open(output_path, 'r') as f:
            content = f.read()
            # Production style should have better formatting
            assert 'AgentConfig(' in content
            assert 'OpenAIModel' in content
            assert 'async def main():' in content


def test_backward_compatibility():
    """Test that simple style maintains backward compatibility."""
    spec = GraphSpec(
        id='compat-test',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Agent', config={'model': 'gpt-4o-mini'}),
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Old style (default was simple)
        output_path = generate(spec, tmpdir, style='simple')

        with open(output_path, 'r') as f:
            content = f.read()

            # Should have backward compatible structure
            assert 'class Node1Agent(Agent):' in content
            assert 'pass' in content
            assert 'from spark.utils import arun' in content


# ==============================================================================
# Model Generation Tests
# ==============================================================================

def test_generate_model_instances():
    """Test generating different model types."""
    spec = GraphSpec(
        id='test',
        start='n',
        nodes=[NodeSpec(id='n', type='Node')]
    )
    generator = CodeGenerator(spec)

    # OpenAI
    assert 'OpenAIModel(model_id=\'gpt-4o\')' == generator._generate_model_instance('gpt-4o')

    # Echo
    echo_config = {'provider': 'echo', 'streaming': True}
    assert 'EchoModel(streaming=True)' == generator._generate_model_instance(echo_config)

    # Bedrock
    bedrock_config = {'provider': 'bedrock', 'model_id': 'claude-3'}
    assert 'BedrockModel(model_id=\'claude-3\')' == generator._generate_model_instance(bedrock_config)


# ==============================================================================
# Edge Case Tests
# ==============================================================================

def test_generate_with_no_edges():
    """Test generating graph with no edges."""
    spec = GraphSpec(
        id='no-edges',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_graph_assembly()

    assert 'def build_graph()' in code
    assert "Graph(start=nodes['node1'])" in code


def test_generate_with_special_characters_in_ids():
    """Test handling special characters in node IDs."""
    spec = GraphSpec(
        id='special-chars',
        start='node-1',
        nodes=[
            NodeSpec(id='node-1', type='Node'),
            NodeSpec(id='node.2', type='Node'),
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node-1', to_node='node.2')
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_complete_file()

    # Should handle special characters
    assert 'class Node1Node(Node):' in code
    assert 'class Node2Node(Node):' in code
    assert 'node_1 =' in code
    assert 'node_2 =' in code


def test_generate_with_empty_config():
    """Test generating nodes with empty config."""
    spec = GraphSpec(
        id='empty-config',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node', config={}),
        ]
    )

    generator = CodeGenerator(spec)
    code = generator.generate_node_instances()

    assert 'node1 = Node1Node()' in code


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
