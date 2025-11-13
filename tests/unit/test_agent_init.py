"""
Tests for Agent initialization and configuration.
"""

import pytest
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryConfig, MemoryPolicyType
from spark.models.echo import EchoModel
from spark.models.openai import OpenAIModel
from spark.nodes.types import NodeMessage


class TestAgentInitialization:
    """Test agent initialization."""

    def test_agent_init_with_default_config(self):
        """Test agent initializes with default config."""
        agent = Agent()

        assert agent.config is not None
        assert isinstance(agent.config.model, EchoModel)
        assert agent.config.output_mode == 'text'
        assert agent.config.max_steps == 100

    def test_agent_init_with_custom_config(self):
        """Test agent initializes with custom config."""
        config = AgentConfig(
            model=EchoModel(),
            name="TestAgent",
            description="Test agent description",
            system_prompt="You are a test agent",
            max_steps=10
        )
        agent = Agent(config=config)

        assert agent.config.name == "TestAgent"
        assert agent.config.description == "Test agent description"
        assert agent.config.system_prompt == "You are a test agent"
        assert agent.config.max_steps == 10

    def test_agent_init_with_model_id_kwargs(self):
        """Test agent initializes with model_id in kwargs."""
        # This should create a model from the model_id
        # Note: model_id must have a provider prefix
        agent = Agent(model_id='openai/gpt-4')

        assert agent.config.model is not None
        assert isinstance(agent.config.model, OpenAIModel)

    def test_agent_state_initialized(self):
        """Test agent state is properly initialized."""
        agent = Agent()

        assert agent.state is not None
        assert 'messages' in agent.state
        assert 'tool_traces' in agent.state
        assert 'last_result' in agent.state
        assert agent.state['messages'] == []
        assert agent.state['tool_traces'] == []

    def test_agent_memory_manager_initialized(self):
        """Test memory manager is initialized."""
        agent = Agent()

        assert agent.memory_manager is not None
        assert agent.memory_manager.policy == MemoryPolicyType.ROLLING_WINDOW
        assert agent.memory_manager.window == 10

    def test_agent_with_custom_memory_config(self):
        """Test agent with custom memory configuration."""
        memory_config = MemoryConfig(
            policy=MemoryPolicyType.NULL,
            window=5
        )
        config = AgentConfig(
            model=EchoModel(),
            memory_config=memory_config
        )
        agent = Agent(config=config)

        assert agent.memory_manager.policy == MemoryPolicyType.NULL
        assert agent.memory_manager.window == 5

    def test_agent_state_can_be_updated(self):
        """Test agent state can be updated after initialization."""
        agent = Agent()

        # Can add custom fields to state after init
        agent._state['custom_field'] = 'custom_value'
        assert agent.state.get('custom_field') == 'custom_value'

    def test_agent_with_preload_messages(self):
        """Test agent with preloaded messages."""
        messages = [
            {'role': 'user', 'content': [{'text': 'Hello'}]},
            {'role': 'assistant', 'content': [{'text': 'Hi there!'}]}
        ]
        config = AgentConfig(
            model=EchoModel(),
            preload_messages=messages
        )
        agent = Agent(config=config)

        assert len(agent.memory_manager.memory) == 2
        assert agent.memory_manager.memory[0]['role'] == 'user'

    def test_agent_tool_registry_initialized(self):
        """Test tool registry is initialized."""
        agent = Agent()

        assert agent.tool_registry is not None
        assert agent.tool_specs == []

    def test_agent_with_jinja2_template(self):
        """Test agent with Jinja2 template."""
        config = AgentConfig(
            model=EchoModel(),
            prompt_template="Hello {{ name }}!"
        )
        agent = Agent(config=config)

        assert agent.jinja2_template is not None

    def test_agent_without_template(self):
        """Test agent without template."""
        agent = Agent()

        assert agent.jinja2_template is None


class TestAgentConfig:
    """Test agent configuration."""

    def test_agent_config_defaults(self):
        """Test default configuration values."""
        config = AgentConfig(model=EchoModel())

        assert config.output_mode == 'text'
        assert config.max_steps == 100
        assert config.tool_choice == 'auto'
        assert config.system_prompt is None
        assert config.prompt_template is None
        assert config.tools == []
        assert config.before_llm_hooks == []
        assert config.after_llm_hooks == []

    def test_agent_config_custom_values(self):
        """Test custom configuration values."""
        config = AgentConfig(
            model=EchoModel(),
            name="CustomAgent",
            system_prompt="Custom prompt",
            output_mode='json',
            max_steps=50,
            tool_choice='auto'
        )

        assert config.name == "CustomAgent"
        assert config.system_prompt == "Custom prompt"
        assert config.output_mode == 'json'
        assert config.max_steps == 50
        assert config.tool_choice == 'auto'

    def test_agent_config_with_hooks(self):
        """Test configuration with hooks."""
        def before_hook(msgs, context):
            pass

        def after_hook(result, context):
            pass

        config = AgentConfig(
            model=EchoModel(),
            before_llm_hooks=[before_hook],
            after_llm_hooks=[after_hook]
        )

        assert len(config.before_llm_hooks) == 1
        assert len(config.after_llm_hooks) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
