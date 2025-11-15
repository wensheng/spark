"""
Unit tests for enhanced specification models in spark/nodes/spec.py.

Tests all Phase 1 spec models including:
- Agent specifications (ReasoningStrategySpec, MemoryConfigSpec, etc.)
- Tool system specifications (ToolParameterSpec, ToolDefinitionSpec, etc.)
- Advanced node type specifications (BatchProcessingSpec, JoinNodeSpec, etc.)
- Graph feature specifications (GraphStateSpec, GraphEventBusSpec, etc.)
- Enhanced edge and condition specifications
"""

import pytest
from pydantic import ValidationError

from spark.nodes.spec import (
    # Agent Configuration Specs
    ReasoningStrategySpec,
    MemoryConfigSpec,
    ToolConfigSpec,
    StructuredOutputSpec,
    CostTrackingSpec,
    AgentHooksSpec,
    EnhancedAgentConfigSpec,
    # Tool System Specs
    ToolParameterSpec,
    ToolDefinitionSpec,
    ToolDepotSpec,
    # Advanced Node Type Specs
    BatchProcessingSpec,
    JoinNodeSpec,
    RpcNodeSpec,
    SubgraphNodeSpec,
    # Graph Feature Specs
    ModelSpec,
    GraphStateSpec,
    GraphEventBusSpec,
    BudgetSpec,
    TaskSpec,
    # Edge and Condition Specs
    ConditionSpec,
    EdgeSpec,
    # Core Specs
    GraphSpec,
    NodeSpec,
)


# ==============================================================================
# Agent Configuration Specification Tests
# ==============================================================================


def test_reasoning_strategy_spec_react():
    """Test ReasoningStrategySpec with react type."""
    spec = ReasoningStrategySpec(type='react', config={'verbose': True})
    assert spec.type == 'react'
    assert spec.config == {'verbose': True}
    assert spec.custom_class is None


def test_reasoning_strategy_spec_plan_and_solve():
    """Test ReasoningStrategySpec with plan_and_solve type."""
    spec = ReasoningStrategySpec(type='plan_and_solve')
    assert spec.type == 'plan_and_solve'
    assert spec.custom_class is None


def test_reasoning_strategy_spec_custom_requires_class():
    """Test that custom strategy requires custom_class."""
    with pytest.raises(ValidationError) as exc_info:
        ReasoningStrategySpec(type='custom')
    assert 'custom_class is required' in str(exc_info.value)


def test_reasoning_strategy_spec_custom_with_class():
    """Test custom strategy with custom_class."""
    spec = ReasoningStrategySpec(
        type='custom',
        custom_class='myapp.strategies:MyStrategy',
        config={'param': 'value'}
    )
    assert spec.type == 'custom'
    assert spec.custom_class == 'myapp.strategies:MyStrategy'


def test_memory_config_spec():
    """Test MemoryConfigSpec."""
    spec = MemoryConfigSpec(
        policy='rolling_window',
        window=10,
        summary_max_chars=1000
    )
    assert spec.policy == 'rolling_window'
    assert spec.window == 10
    assert spec.summary_max_chars == 1000


def test_tool_config_spec():
    """Test ToolConfigSpec."""
    spec = ToolConfigSpec(
        name='search_web',
        source='tools:search_web',
        enabled=True,
        config={'max_results': 5}
    )
    assert spec.name == 'search_web'
    assert spec.source == 'tools:search_web'
    assert spec.enabled is True
    assert spec.config == {'max_results': 5}


def test_structured_output_spec():
    """Test StructuredOutputSpec."""
    spec = StructuredOutputSpec(
        mode='json',
        output_schema={'type': 'object', 'properties': {}},
        schema_class='myapp.models:Response'
    )
    assert spec.mode == 'json'
    assert spec.output_schema is not None
    assert spec.schema_class == 'myapp.models:Response'


def test_cost_tracking_spec():
    """Test CostTrackingSpec."""
    spec = CostTrackingSpec(
        enabled=True,
        track_tokens=True,
        track_cost=True,
        cost_limits={'max_cost': 1.0}
    )
    assert spec.enabled is True
    assert spec.track_tokens is True
    assert spec.cost_limits == {'max_cost': 1.0}


def test_agent_hooks_spec():
    """Test AgentHooksSpec."""
    spec = AgentHooksSpec(
        before_llm_hooks=['myapp.hooks:before'],
        after_llm_hooks=['myapp.hooks:after'],
        on_error='myapp.hooks:error'
    )
    assert len(spec.before_llm_hooks) == 1
    assert len(spec.after_llm_hooks) == 1
    assert spec.on_error == 'myapp.hooks:error'


def test_enhanced_agent_config_spec():
    """Test EnhancedAgentConfigSpec."""
    spec = EnhancedAgentConfigSpec(
        model='gpt-4o',
        system_prompt='You are a helpful assistant',
        tools=[ToolConfigSpec(name='search', source='tools:search')],
        tool_choice='auto',
        max_steps=5
    )
    assert spec.model == 'gpt-4o'
    assert spec.system_prompt == 'You are a helpful assistant'
    assert len(spec.tools) == 1
    assert spec.max_steps == 5


def test_enhanced_agent_config_spec_tool_choice_validation():
    """Test that tool_choice='any' requires tools."""
    with pytest.raises(ValidationError) as exc_info:
        EnhancedAgentConfigSpec(
            model='gpt-4o',
            tool_choice='any',
            tools=[]
        )
    assert 'requires at least one tool' in str(exc_info.value)


def test_enhanced_agent_config_spec_negative_max_steps():
    """Test that max_steps must be non-negative."""
    with pytest.raises(ValidationError) as exc_info:
        EnhancedAgentConfigSpec(
            model='gpt-4o',
            max_steps=-1
        )
    assert 'must be non-negative' in str(exc_info.value)


# ==============================================================================
# Tool System Specification Tests
# ==============================================================================


def test_tool_parameter_spec():
    """Test ToolParameterSpec."""
    spec = ToolParameterSpec(
        name='query',
        type='str',
        description='Search query',
        required=True
    )
    assert spec.name == 'query'
    assert spec.type == 'str'
    assert spec.required is True


def test_tool_definition_spec():
    """Test ToolDefinitionSpec."""
    spec = ToolDefinitionSpec(
        name='search_web',
        function='tools:search_web',
        description='Search the web',
        parameters=[
            ToolParameterSpec(name='query', type='str', required=True)
        ],
        return_type='str',
        is_async=False
    )
    assert spec.name == 'search_web'
    assert spec.function == 'tools:search_web'
    assert len(spec.parameters) == 1


def test_tool_depot_spec():
    """Test ToolDepotSpec."""
    spec = ToolDepotSpec(
        depot_id='git_tools',
        tools=[
            ToolDefinitionSpec(
                name='git_status',
                function='depot.git:status',
                description='Get git status'
            )
        ],
        version='1.0'
    )
    assert spec.depot_id == 'git_tools'
    assert len(spec.tools) == 1
    assert spec.version == '1.0'


# ==============================================================================
# Advanced Node Type Specification Tests
# ==============================================================================


def test_batch_processing_spec():
    """Test BatchProcessingSpec."""
    spec = BatchProcessingSpec(
        mode='parallel',
        failure_strategy='skip_failed',
        max_workers=4,
        timeout_per_item=30.0
    )
    assert spec.mode == 'parallel'
    assert spec.failure_strategy == 'skip_failed'
    assert spec.max_workers == 4


def test_join_node_spec():
    """Test JoinNodeSpec."""
    spec = JoinNodeSpec(
        keys=['branch1', 'branch2'],
        mode='all',
        timeout=30.0,
        reducer='myapp.reducers:merge'
    )
    assert spec.keys == ['branch1', 'branch2']
    assert spec.mode == 'all'
    assert spec.timeout == 30.0


def test_rpc_node_spec():
    """Test RpcNodeSpec."""
    spec = RpcNodeSpec(
        host='0.0.0.0',
        port=8000,
        protocol='http',
        methods=['rpc_process', 'rpc_status']
    )
    assert spec.host == '0.0.0.0'
    assert spec.port == 8000
    assert spec.protocol == 'http'
    assert len(spec.methods) == 2


def test_subgraph_node_spec_with_source():
    """Test SubgraphNodeSpec with graph_source."""
    spec = SubgraphNodeSpec(
        graph_source='myapp.graphs:my_graph',
        input_mapping={'query': 'user_query'}
    )
    assert spec.graph_source == 'myapp.graphs:my_graph'
    assert spec.graph_spec is None


def test_subgraph_node_spec_share_flags():
    """Test SubgraphNodeSpec share_state/share_event_bus toggles."""
    spec = SubgraphNodeSpec(
        graph_source='myapp.graphs:my_graph',
        share_state=False,
        share_event_bus=True,
    )
    assert spec.share_state is False
    assert spec.share_event_bus is True


def test_subgraph_node_spec_requires_source_or_spec():
    """Test that SubgraphNodeSpec requires either graph_source or graph_spec."""
    with pytest.raises(ValidationError) as exc_info:
        SubgraphNodeSpec()
    assert 'must be provided' in str(exc_info.value)


def test_subgraph_node_spec_not_both():
    """Test that SubgraphNodeSpec doesn't allow both source and spec."""
    with pytest.raises(ValidationError) as exc_info:
        SubgraphNodeSpec(
            graph_source='myapp.graphs:my_graph',
            graph_spec=GraphSpec(
                id='test',
                start='node1',
                nodes=[NodeSpec(id='node1', type='Node')]
            )
        )
    assert 'not both' in str(exc_info.value)


# ==============================================================================
# Graph Feature Specification Tests
# ==============================================================================


def test_model_spec():
    """Test ModelSpec."""
    spec = ModelSpec(
        provider='openai',
        model_id='gpt-4o',
        client_args={'api_key': 'test'},
        streaming=False,
        cache_enabled=False
    )
    assert spec.provider == 'openai'
    assert spec.model_id == 'gpt-4o'
    assert spec.streaming is False


def test_graph_state_spec():
    """Test GraphStateSpec."""
    spec = GraphStateSpec(
        initial_state={'counter': 0, 'status': 'ready'},
        concurrent_mode=False,
        persistence='memory'
    )
    assert spec.initial_state == {'counter': 0, 'status': 'ready'}
    assert spec.concurrent_mode is False


def test_graph_event_bus_spec():
    """Test GraphEventBusSpec."""
    spec = GraphEventBusSpec(
        enabled=True,
        buffer_size=100,
        topics=['sensor.*', 'alerts']
    )
    assert spec.enabled is True
    assert spec.buffer_size == 100
    assert len(spec.topics) == 2


def test_budget_spec():
    """Test BudgetSpec."""
    spec = BudgetSpec(
        max_seconds=300.0,
        max_tokens=10000,
        max_cost=1.0
    )
    assert spec.max_seconds == 300.0
    assert spec.max_tokens == 10000
    assert spec.max_cost == 1.0


def test_task_spec():
    """Test TaskSpec."""
    spec = TaskSpec(
        type='one_off',
        inputs={'query': 'What is AI?'},
        budget=BudgetSpec(max_seconds=60.0)
    )
    assert spec.type == 'one_off'
    assert spec.inputs == {'query': 'What is AI?'}
    assert spec.budget is not None


# ==============================================================================
# Edge and Condition Specification Tests
# ==============================================================================


def test_condition_spec_expr():
    """Test ConditionSpec with expr."""
    spec = ConditionSpec(
        kind='expr',
        expr='$.outputs.score > 0.7',
        description='High quality check'
    )
    assert spec.kind == 'expr'
    assert spec.expr == '$.outputs.score > 0.7'


def test_condition_spec_equals():
    """Test ConditionSpec with equals."""
    spec = ConditionSpec(
        kind='equals',
        equals={'action': 'search'}
    )
    assert spec.kind == 'equals'
    assert spec.equals == {'action': 'search'}


def test_condition_spec_lambda():
    """Test ConditionSpec with lambda."""
    spec = ConditionSpec(
        kind='lambda',
        lambda_source='lambda n: n.outputs.get("ready")'
    )
    assert spec.kind == 'lambda'
    assert 'ready' in spec.lambda_source


def test_condition_spec_always():
    """Test ConditionSpec with always."""
    spec = ConditionSpec(kind='always')
    assert spec.kind == 'always'


def test_edge_spec():
    """Test EdgeSpec."""
    spec = EdgeSpec(
        id='e1',
        from_node='router',
        to_node='processor',
        condition=ConditionSpec(kind='expr', expr='$.outputs.score > 0.7'),
        priority=10,
        description='High quality route',
        metadata={'category': 'quality_check'}
    )
    assert spec.id == 'e1'
    assert spec.from_node == 'router'
    assert spec.to_node == 'processor'
    assert spec.priority == 10
    assert spec.fanout_behavior == 'evaluate_all'


def test_edge_spec_model_dump_standard():
    """Test EdgeSpec.model_dump_standard()."""
    spec = EdgeSpec(
        id='e1',
        from_node='a',
        to_node='b',
        priority=5
    )
    dumped = spec.model_dump_standard()
    assert 'from_node' in dumped
    assert 'to_node' in dumped
    assert dumped['from_node'] == 'a'
    assert dumped['to_node'] == 'b'


# ==============================================================================
# Graph Specification Tests
# ==============================================================================


def test_graph_spec_basic():
    """Test basic GraphSpec."""
    spec = GraphSpec(
        id='test-graph',
        description='Test graph',
        start='node1',
        nodes=[
            NodeSpec(id='node1', type='Node'),
            NodeSpec(id='node2', type='Node')
        ],
        edges=[
            EdgeSpec(id='e1', from_node='node1', to_node='node2')
        ]
    )
    assert spec.id == 'test-graph'
    assert spec.start == 'node1'
    assert len(spec.nodes) == 2
    assert len(spec.edges) == 1


def test_graph_spec_with_features():
    """Test GraphSpec with all features."""
    spec = GraphSpec(
        spark_version='2.0',
        id='test-graph',
        start='node1',
        nodes=[NodeSpec(id='node1', type='Node')],
        graph_state=GraphStateSpec(initial_state={'counter': 0}),
        event_bus=GraphEventBusSpec(enabled=True),
        task=TaskSpec(type='one_off')
    )
    assert spec.spark_version == '2.0'
    assert spec.graph_state is not None
    assert spec.event_bus is not None
    assert spec.task is not None


def test_graph_spec_validates_start_node():
    """Test that GraphSpec validates start node exists."""
    with pytest.raises(ValidationError) as exc_info:
        GraphSpec(
            id='test',
            start='nonexistent',
            nodes=[NodeSpec(id='node1', type='Node')]
        )
    assert 'not found among nodes' in str(exc_info.value)


def test_graph_spec_validates_edge_nodes():
    """Test that GraphSpec validates edge node references."""
    with pytest.raises(ValidationError) as exc_info:
        GraphSpec(
            id='test',
            start='node1',
            nodes=[NodeSpec(id='node1', type='Node')],
            edges=[EdgeSpec(id='e1', from_node='node1', to_node='nonexistent')]
        )
    assert 'missing' in str(exc_info.value)


def test_graph_spec_validates_unique_node_ids():
    """Test that GraphSpec validates unique node IDs."""
    with pytest.raises(ValidationError) as exc_info:
        GraphSpec(
            id='test',
            start='node1',
            nodes=[
                NodeSpec(id='node1', type='Node'),
                NodeSpec(id='node1', type='Node')  # Duplicate
            ]
        )
    assert 'duplicate' in str(exc_info.value)


# ==============================================================================
# Integration Tests
# ==============================================================================


def test_complete_agent_graph_spec():
    """Test complete graph spec with agent configuration."""
    spec = GraphSpec(
        spark_version='2.0',
        id='com.example.agent-graph',
        description='Complete agent graph',
        start='agent',
        nodes=[
            NodeSpec(
                id='agent',
                type='Agent',
                description='Main agent',
                config={
                    'model': {'provider': 'openai', 'model_id': 'gpt-4o'},
                    'system_prompt': 'You are helpful',
                    'tools': [
                        {'name': 'search', 'source': 'tools:search'}
                    ],
                    'tool_choice': 'auto',
                    'max_steps': 5
                }
            )
        ],
        graph_state=GraphStateSpec(initial_state={'queries': 0}),
        event_bus=GraphEventBusSpec(enabled=True),
        tools=[
            ToolDefinitionSpec(
                name='search',
                function='tools:search',
                description='Search tool'
            )
        ]
    )

    assert spec.spark_version == '2.0'
    assert len(spec.nodes) == 1
    assert spec.graph_state is not None
    assert spec.event_bus is not None
    assert len(spec.tools) == 1

    # Test serialization
    dumped = spec.model_dump()
    assert dumped['spark_version'] == '2.0'
    assert dumped['id'] == 'com.example.agent-graph'


def test_spec_json_serialization():
    """Test that all specs can be serialized to JSON."""
    import json

    spec = GraphSpec(
        id='test',
        start='node1',
        nodes=[
            NodeSpec(
                id='node1',
                type='Agent',
                config={
                    'model': 'gpt-4o',
                    'max_steps': 10
                }
            )
        ],
        edges=[],
        graph_state=GraphStateSpec(initial_state={}),
        event_bus=GraphEventBusSpec(enabled=True),
        task=TaskSpec(type='one_off', inputs={})
    )

    # Should be able to serialize to JSON
    json_str = spec.model_dump_json(indent=2)
    assert json_str is not None

    # Should be able to parse back
    parsed = GraphSpec.model_validate_json(json_str)
    assert parsed.id == 'test'
    assert parsed.start == 'node1'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
