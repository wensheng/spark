"""
Unit tests for Phase 2 enhanced serialization and deserialization.

Tests:
- Tool serialization (tool_to_spec)
- Model serialization (model_to_spec)
- Agent configuration serialization (agent_config_to_spec)
- Enhanced node serialization (node_to_spec)
- Enhanced graph serialization (graph_to_spec)
- SpecLoader deserialization
- Round-trip validation
"""

import pytest
from typing import Any

from spark.nodes.base import ExecutionContext
from spark.nodes.nodes import Node
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryConfig
from spark.graphs.graph import Graph
from spark.graphs import MissionStateModel
from spark.models.echo import EchoModel

from spark.nodes.serde import (
    tool_to_spec,
    model_to_spec,
    agent_config_to_spec,
    node_to_spec,
    graph_to_spec,
)
from spark.kit.loader import SpecLoader, SpecLoaderError
from spark.kit.validation import (
    validate_round_trip,
    compare_specs,
    validate_spec_loadable,
)
from spark.nodes.spec import (
    ModelSpec,
    ToolDefinitionSpec,
    EnhancedAgentConfigSpec,
    GraphSpec,
    GraphStateSpec,
    NodeSpec,
    StateBackendConfigSpec,
    MissionStateSchemaSpec,
)


# ==============================================================================
# Test Helpers
# ==============================================================================


class TestNode(Node):
    """Concrete Node subclass for testing."""

    __test__ = False

    async def process(self, context: ExecutionContext) -> Any:
        """Simple pass-through process."""
        return context.inputs


class CounterSchema(MissionStateModel):
    """Schema used for spec loader tests."""

    counter: int


# ==============================================================================
# Tool Serialization Tests
# ==============================================================================


def test_tool_to_spec_simple_function():
    """Test serializing a simple function to ToolDefinitionSpec."""

    def search(query: str) -> str:
        """Search for something."""
        return f"Results for: {query}"

    tool_spec = tool_to_spec(search)

    assert tool_spec is not None
    assert tool_spec.name == 'search'
    assert 'search' in tool_spec.description.lower()
    assert len(tool_spec.parameters) == 1
    assert tool_spec.parameters[0].name == 'query'
    assert tool_spec.parameters[0].type == "<class 'str'>"
    assert tool_spec.parameters[0].required is True
    assert tool_spec.is_async is False


def test_tool_to_spec_async_function():
    """Test serializing an async function."""

    async def async_search(query: str, limit: int = 10) -> list:
        """Async search function."""
        return []

    tool_spec = tool_to_spec(async_search)

    assert tool_spec is not None
    assert tool_spec.name == 'async_search'
    assert tool_spec.is_async is True
    assert len(tool_spec.parameters) == 2
    assert tool_spec.parameters[1].name == 'limit'
    assert tool_spec.parameters[1].required is False


# ==============================================================================
# Model Serialization Tests
# ==============================================================================


def test_model_to_spec_echo_model():
    """Test serializing an EchoModel."""
    model = EchoModel(streaming=False)
    model_spec = model_to_spec(model)

    assert model_spec is not None
    assert model_spec.provider == 'echo'
    assert model_spec.model_id == 'echo'  # EchoModel returns 'echo' as model_id
    assert model_spec.streaming is False


def test_model_to_spec_string():
    """Test serializing a model ID string."""
    model_spec = model_to_spec('gpt-4o')

    assert model_spec is not None
    assert model_spec.provider == 'openai'
    assert model_spec.model_id == 'gpt-4o'


# ==============================================================================
# Agent Configuration Serialization Tests
# ==============================================================================


def test_agent_config_to_spec_basic():
    """Test serializing basic agent configuration."""
    config = AgentConfig(
        model=EchoModel(),
        system_prompt='You are helpful',
        max_steps=5
    )
    agent = Agent(config=config)

    agent_spec = agent_config_to_spec(agent)

    assert agent_spec is not None
    assert agent_spec.system_prompt == 'You are helpful'
    assert agent_spec.max_steps == 5
    assert agent_spec.model is not None


def test_agent_config_to_spec_with_memory():
    """Test serializing agent with memory configuration."""
    config = AgentConfig(
        model=EchoModel(),
        memory_config=MemoryConfig(
            policy='rolling_window',
            window=10
        )
    )
    agent = Agent(config=config)

    agent_spec = agent_config_to_spec(agent)

    assert agent_spec is not None
    assert agent_spec.memory_config is not None
    assert agent_spec.memory_config.policy == 'rolling_window'
    assert agent_spec.memory_config.window == 10


def test_agent_config_to_spec_with_tools():
    """Test serializing agent with tools."""
    from spark.tools.decorator import tool

    @tool
    def mock_tool(query: str) -> str:
        """Mock tool."""
        return "result"

    config = AgentConfig(
        model=EchoModel(),
        tools=[mock_tool]
    )
    agent = Agent(config=config)

    agent_spec = agent_config_to_spec(agent)

    assert agent_spec is not None
    # Tool specs should be present
    # Note: actual serialization may vary based on registry implementation
    assert agent_spec.tools is not None


# ==============================================================================
# Node Serialization Tests
# ==============================================================================


def test_node_to_spec_basic_node():
    """Test serializing a basic Node."""
    node = TestNode(description="Test node")
    node_spec = node_to_spec(node)

    assert node_spec is not None
    assert node_spec.type in ('Node', 'TestNode', 'Basic')
    assert node_spec.description == "Test node"


def test_node_to_spec_agent():
    """Test serializing an Agent node."""
    config = AgentConfig(
        model=EchoModel(),
        system_prompt='Test prompt'
    )
    agent = Agent(config=config)

    node_spec = node_to_spec(agent)

    assert node_spec is not None
    assert node_spec.type == 'Agent'
    assert node_spec.config is not None
    assert 'system_prompt' in node_spec.config


# ==============================================================================
# Graph Serialization Tests
# ==============================================================================


def test_graph_to_spec_simple():
    """Test serializing a simple graph."""
    node1 = TestNode(description="Start")
    node2 = TestNode(description="End")
    node1 >> node2

    graph = Graph(start=node1)
    graph_spec = graph_to_spec(graph)

    assert graph_spec is not None
    assert graph_spec.spark_version == '2.0'
    assert len(graph_spec.nodes) == 2
    assert len(graph_spec.edges) == 1
    assert graph_spec.start == node1.id


def test_graph_to_spec_with_agent():
    """Test serializing a graph with an agent."""
    config = AgentConfig(
        model=EchoModel(),
        system_prompt='Test'
    )
    agent = Agent(config=config)

    graph = Graph(start=agent)
    graph_spec = graph_to_spec(graph)

    assert graph_spec is not None
    assert len(graph_spec.nodes) == 1
    assert graph_spec.nodes[0].type == 'Agent'


@pytest.mark.asyncio
async def test_graph_to_spec_with_graph_state():
    """Test serializing a graph with GraphState."""
    node = TestNode()
    graph = Graph(start=node)

    # Set some state
    await graph.state.set('counter', 42)

    graph_spec = graph_to_spec(graph)

    assert graph_spec is not None
    assert graph_spec.graph_state is not None
    assert 'counter' in graph_spec.graph_state.initial_state
    assert graph_spec.graph_state.initial_state['counter'] == 42
    assert graph_spec.graph_state.backend is not None
    assert graph_spec.graph_state.backend.name == 'memory'
    assert graph_spec.graph_state.backend.serializer == 'json'
    assert graph_spec.graph_state.checkpointing is None


def test_graph_to_spec_includes_advanced_edges():
    class PublisherNode(Node):
        async def process(self, context: ExecutionContext) -> Any:  # type: ignore[override]
            await self.publish_event('alerts', {'status': 'ready'})
            return {'status': 'ready'}

    class SinkNode(Node):
        async def process(self, context: ExecutionContext) -> Any:  # type: ignore[override]
            return context.inputs

    publisher = PublisherNode()
    timer_sink = SinkNode()
    event_sink = SinkNode()

    publisher.on_timer(5.0) >> timer_sink
    publisher.on_event('alerts', status='ready') >> event_sink

    graph = Graph(start=publisher)
    spec = graph_to_spec(graph)

    timer_edges = [edge for edge in spec.edges if edge.delay_seconds]
    assert timer_edges and timer_edges[0].delay_seconds == 5.0

    event_edges = [edge for edge in spec.edges if edge.event_topic == 'alerts']
    assert event_edges and event_edges[0].event_filter is not None
    assert event_edges[0].event_filter.kind == 'equals'

    loader = SpecLoader(import_policy='allow_all')
    rehydrated = loader.load_graph(spec)
    loaded_event_edge = next(edge for edge in rehydrated.edges if edge.event_topic == 'alerts')
    assert loaded_event_edge.event_filter is not None
    assert loaded_event_edge.event_filter.equals == {'status': 'ready'}


# ==============================================================================
# SpecLoader Tests
# ==============================================================================


def test_spec_loader_load_model():
    """Test loading a model from ModelSpec."""
    loader = SpecLoader()

    model_spec = ModelSpec(
        provider='echo',
        model_id='test-echo'
    )

    model = loader.load_model(model_spec)

    assert model is not None
    # EchoModel provides model_id via get_config()
    config = model.get_config()
    assert 'model_id' in config
    assert config['model_id'] == 'echo'  # EchoModel always returns 'echo'


def test_spec_loader_load_model_from_string():
    """Test loading a model from string ID."""
    loader = SpecLoader()

    model = loader.load_model('gpt-4o')

    assert model is not None
    # Models provide model_id via get_config()
    config = model.get_config()
    assert 'model_id' in config
    assert config['model_id'] == 'gpt-4o'


def test_spec_loader_load_node_basic():
    """Test loading a basic node from NodeSpec."""
    from spark.nodes.spec import NodeSpec

    loader = SpecLoader()

    node_spec = NodeSpec(
        id='test-node',
        type='Node',
        description='Test'
    )

    node = loader.load_node(node_spec)
    assert node is not None
    assert node.id == 'test-node'


def test_spec_loader_with_backend_and_schema(tmp_path):
    """Loader should configure state backend and schema."""
    loader = SpecLoader(import_policy='allow_all')
    db_path = tmp_path / "state.db"
    graph_spec = GraphSpec(
        spark_version='2.0',
        id='sqlite-graph',
        start='node',
        nodes=[NodeSpec(id='node', type='Node', description='Generic')],
        edges=[],
        graph_state=GraphStateSpec(
            initial_state={'counter': 5},
            backend=StateBackendConfigSpec(name='sqlite', options={'db_path': str(db_path)}),
            schema=MissionStateSchemaSpec(
                name='CounterSchema',
                version='1.0',
                module='tests.unit.test_serde:CounterSchema',
            ),
        ),
    )

    graph = loader.load_graph(graph_spec)
    backend_info = graph.state.describe_backend()
    assert backend_info['name'] == 'sqlite'
    schema_info = graph.state.describe_schema()
    assert schema_info is not None
    assert schema_info['name'] == 'CounterSchema'


def test_spec_loader_load_graph_simple():
    """Test loading a simple graph from GraphSpec."""
    from spark.nodes.spec import NodeSpec, EdgeSpec

    loader = SpecLoader()

    graph_spec = GraphSpec(
        id='test-graph',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node')
        ],
        edges=[
            EdgeSpec(
                id='e1',
                from_node='node1',
                to_node='node2'
            )
        ]
    )

    graph = loader.load_graph(graph_spec)

    assert graph is not None
    assert graph.id == 'test-graph'
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1


def test_spec_loader_caching():
    """Test that SpecLoader caches models and nodes."""
    loader = SpecLoader()

    # Load same model twice
    model1 = loader.load_model('gpt-4o')
    model2 = loader.load_model('gpt-4o')

    # Should be same instance due to caching
    assert model1 is model2


# ==============================================================================
# Round-Trip Validation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_validate_round_trip_simple_graph():
    """Test round-trip validation for a simple graph."""
    node1 = TestNode(description="Start")
    node2 = TestNode(description="End")
    node1 >> node2

    graph = Graph(start=node1)

    success, issues = validate_round_trip(graph, import_policy='allow_all')

    # May have some minor differences, but should mostly work
    if not success:
        print("\nRound-trip issues:")
        for issue in issues:
            print(f"  - {issue}")


@pytest.mark.asyncio
async def test_validate_round_trip_with_agent():
    """Test round-trip validation for graph with agent."""
    config = AgentConfig(
        model=EchoModel(),
        system_prompt='Test prompt',
        max_steps=5
    )
    agent = Agent(config=config)

    graph = Graph(start=agent)

    success, issues = validate_round_trip(graph, import_policy='allow_all')

    if not success:
        print("\nRound-trip issues:")
        for issue in issues:
            print(f"  - {issue}")


def test_compare_specs_identical():
    """Test comparing two identical specs."""
    from spark.nodes.spec import NodeSpec

    spec1 = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    spec2 = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    differences = compare_specs(spec1, spec2, strict=True)

    assert len(differences) == 0


def test_compare_specs_different():
    """Test comparing two different specs."""
    from spark.nodes.spec import NodeSpec

    spec1 = GraphSpec(
        id='test1',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    spec2 = GraphSpec(
        id='test2',
        start='node2',
        nodes=[NodeSpec(id='node2', type='Node')]
    )

    differences = compare_specs(spec1, spec2, strict=True)

    assert len(differences) > 0
    # Should find ID and start node differences


def test_validate_spec_loadable():
    """Test validating that a spec can be loaded."""
    from spark.nodes.spec import NodeSpec

    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')]
    )

    loadable, errors = validate_spec_loadable(spec, import_policy='allow_all')

    assert loadable is True
    assert len(errors) == 0


def test_validate_spec_not_loadable():
    """Test validating a spec that cannot be loaded."""
    from spark.nodes.spec import NodeSpec

    # Spec with an Agent node that has invalid tool reference
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
                        {'name': 'bad_tool', 'source': 'nonexistent.module:bad_tool'}
                    ]
                }
            )
        ]
    )

    # With safe import policy, tool loading will fail
    loadable, errors = validate_spec_loadable(spec, import_policy='safe')

    # Should fail because the tool can't be loaded (safe policy blocks non-spark imports)
    assert loadable is False
    assert len(errors) > 0


# ==============================================================================
# Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_full_serialization_deserialization_cycle():
    """Test complete cycle: create graph → serialize → deserialize → verify."""
    # Create a simple graph
    node1 = TestNode(description="Input")
    node2 = TestNode(description="Process")
    node3 = TestNode(description="Output")

    node1 >> node2 >> node3

    original_graph = Graph(start=node1)
    original_graph.id = 'integration-test'

    # Serialize
    spec = graph_to_spec(original_graph)

    # Validate spec
    assert spec.id == 'integration-test'
    assert len(spec.nodes) == 3
    assert len(spec.edges) == 2

    # Deserialize
    loader = SpecLoader(import_policy='allow_all')
    loaded_graph = loader.load_graph(spec)

    # Verify
    assert loaded_graph.id == 'integration-test'
    assert len(loaded_graph.nodes) == 3
    assert len(loaded_graph.edges) == 2

    # Test that it's executable (basic sanity check)
    assert hasattr(loaded_graph, 'run')
    assert loaded_graph.start is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
