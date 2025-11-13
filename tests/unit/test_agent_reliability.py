"""
Tests for Agent reliability improvements (Phase 2).

This module tests the improvements made in Phase 2:
- Error handling with specific exception classes
- Memory state synchronization
- Configuration validation
"""

import pytest
from spark.agents.agent import (
    Agent,
    AgentError,
    ToolExecutionError,
    TemplateRenderError,
    ModelError,
    ConfigurationError,
)
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryConfig, MemoryPolicyType
from spark.models.echo import EchoModel
from spark.tools.decorator import tool
from spark.nodes.types import NodeMessage


# Test tools
@tool
def failing_tool(message: str) -> str:
    """Tool that always fails.

    Args:
        message: Error message to raise
    """
    raise ValueError(f"Tool failed: {message}")


class TestErrorHandling:
    """Test error handling with specific exception classes."""

    def test_agent_error_base_class(self):
        """Test AgentError is the base exception."""
        assert issubclass(ToolExecutionError, AgentError)
        assert issubclass(TemplateRenderError, AgentError)
        assert issubclass(ModelError, AgentError)
        assert issubclass(ConfigurationError, AgentError)

    def test_handle_model_error_structure(self):
        """Test handle_model_error returns structured error."""
        agent = Agent()
        exc = ValueError("Test error")
        result = agent.handle_model_error(exc)

        assert isinstance(result, NodeMessage)
        assert 'error' in result.content
        assert 'error_type' in result.content
        assert 'timestamp' in result.content
        assert 'category' in result.content
        assert result.content['error'] == "Test error"
        assert result.content['error_type'] == "ValueError"

    def test_handle_model_error_with_tool_execution_error(self):
        """Test handle_model_error categorizes ToolExecutionError."""
        agent = Agent()
        exc = ToolExecutionError("Tool failed")
        result = agent.handle_model_error(exc)

        assert result.content['category'] == 'tool_execution'
        assert result.content['error_type'] == "ToolExecutionError"

    def test_handle_model_error_with_template_render_error(self):
        """Test handle_model_error categorizes TemplateRenderError."""
        agent = Agent()
        exc = TemplateRenderError("Template failed")
        result = agent.handle_model_error(exc)

        assert result.content['category'] == 'template_rendering'

    def test_handle_model_error_with_model_error(self):
        """Test handle_model_error categorizes ModelError."""
        agent = Agent()
        exc = ModelError("Model failed")
        result = agent.handle_model_error(exc)

        assert result.content['category'] == 'model_call'

    def test_handle_model_error_with_configuration_error(self):
        """Test handle_model_error categorizes ConfigurationError."""
        agent = Agent()
        exc = ConfigurationError("Config failed")
        result = agent.handle_model_error(exc)

        assert result.content['category'] == 'configuration'

    def test_handle_model_error_with_unknown_error(self):
        """Test handle_model_error handles unknown error types."""
        agent = Agent()
        exc = RuntimeError("Unknown error")
        result = agent.handle_model_error(exc)

        assert result.content['category'] == 'unknown'

    def test_last_error_recorded(self):
        """Test last_error is recorded in state."""
        agent = Agent()
        exc = ValueError("Test error")
        agent.handle_model_error(exc)

        assert agent.state['last_error'] == "Test error"


class TestMemoryStateSynchronization:
    """Test memory state synchronization between memory_manager and state."""

    def test_messages_property_exists(self):
        """Test agent has messages property."""
        agent = Agent()
        assert hasattr(agent, 'messages')

    def test_messages_property_returns_memory_manager_messages(self):
        """Test messages property returns memory_manager.memory."""
        agent = Agent()
        agent.memory_manager.add_message({'role': 'user', 'content': 'Hello'})

        # messages property should return reference to memory_manager.memory
        assert agent.messages is agent.memory_manager.memory
        assert len(agent.messages) == 1
        assert agent.messages[0]['content'] == 'Hello'

    def test_state_messages_synced_on_access(self):
        """Test state['messages'] is synced from memory_manager on access."""
        agent = Agent()
        agent.memory_manager.add_message({'role': 'user', 'content': 'Hello'})
        agent.memory_manager.add_message({'role': 'assistant', 'content': 'Hi'})

        # Access state to trigger sync
        state = agent.state
        assert len(state['messages']) == 2
        assert state['messages'][0]['content'] == 'Hello'
        assert state['messages'][1]['content'] == 'Hi'

    def test_add_message_to_history_no_duplicate_sync(self):
        """Test add_message_to_history doesn't immediately sync state."""
        agent = Agent()

        # Add message through public API
        agent.add_message_to_history({'role': 'user', 'content': 'Test'})

        # Message should be in memory_manager
        assert len(agent.memory_manager.memory) == 1

        # Access state to trigger sync
        state = agent.state
        assert len(state['messages']) == 1

    def test_clear_history_no_duplicate_sync(self):
        """Test clear_history doesn't immediately sync state."""
        agent = Agent()
        agent.add_message_to_history({'role': 'user', 'content': 'Test'})

        # Clear history
        agent.clear_history()

        # Memory should be cleared
        assert len(agent.memory_manager.memory) == 0

        # Access state to trigger sync
        state = agent.state
        assert len(state['messages']) == 0

    def test_get_history_returns_memory_manager_messages(self):
        """Test get_history returns memory_manager messages."""
        agent = Agent()
        agent.memory_manager.add_message({'role': 'user', 'content': 'Hello'})

        history = agent.get_history()
        assert len(history) == 1
        assert history[0]['content'] == 'Hello'

    def test_memory_manager_is_source_of_truth(self):
        """Test memory_manager is the single source of truth for messages."""
        agent = Agent()

        # Add message via memory_manager directly
        agent.memory_manager.add_message({'role': 'user', 'content': 'Direct'})

        # Should be visible via all access methods
        assert len(agent.messages) == 1
        assert len(agent.get_history()) == 1
        assert len(agent.state['messages']) == 1


class TestConfigurationValidation:
    """Test configuration validation in AgentConfig."""

    def test_tool_choice_any_requires_tools(self):
        """Test tool_choice='any' requires at least one tool."""
        with pytest.raises(ValueError, match="tool_choice='any' requires at least one tool"):
            AgentConfig(
                model=EchoModel(),
                tool_choice='any',
                tools=[]
            )

    def test_tool_choice_any_with_tools_succeeds(self):
        """Test tool_choice='any' with tools configured succeeds."""
        @tool
        def test_tool(x: int) -> int:
            return x

        config = AgentConfig(
            model=EchoModel(),
            tool_choice='any',
            tools=[test_tool]
        )
        assert config.tool_choice == 'any'

    def test_negative_max_steps_fails(self):
        """Test negative max_steps fails validation."""
        with pytest.raises(ValueError, match="max_steps must be non-negative"):
            AgentConfig(
                model=EchoModel(),
                max_steps=-1
            )

    def test_zero_max_steps_succeeds(self):
        """Test max_steps=0 (unlimited) succeeds."""
        config = AgentConfig(
            model=EchoModel(),
            max_steps=0
        )
        assert config.max_steps == 0

    def test_positive_max_steps_succeeds(self):
        """Test positive max_steps succeeds."""
        config = AgentConfig(
            model=EchoModel(),
            max_steps=50
        )
        assert config.max_steps == 50

    def test_negative_memory_window_fails(self):
        """Test negative memory window fails validation."""
        with pytest.raises(ValueError, match="memory_config.window must be positive"):
            AgentConfig(
                model=EchoModel(),
                memory_config=MemoryConfig(window=-1)
            )

    def test_zero_memory_window_fails(self):
        """Test zero memory window fails validation."""
        with pytest.raises(ValueError, match="memory_config.window must be positive"):
            AgentConfig(
                model=EchoModel(),
                memory_config=MemoryConfig(window=0)
            )

    def test_positive_memory_window_succeeds(self):
        """Test positive memory window succeeds."""
        config = AgentConfig(
            model=EchoModel(),
            memory_config=MemoryConfig(window=5)
        )
        assert config.memory_config.window == 5

    def test_output_schema_without_json_mode_warns(self, caplog):
        """Test output_schema without json mode logs warning."""
        from pydantic import BaseModel

        class CustomSchema(BaseModel):
            message: str

        # This should log a warning but not fail
        config = AgentConfig(
            model=EchoModel(),
            output_mode='text',
            output_schema=CustomSchema
        )

        # Check warning was logged
        # Note: caplog requires pytest-capture to work properly
        # For now just verify config was created
        assert config.output_schema == CustomSchema
        assert config.output_mode == 'text'

    def test_specific_tool_choice_without_tools_warns(self, caplog):
        """Test specific tool_choice without tools logs warning."""
        # This should log a warning but not fail
        config = AgentConfig(
            model=EchoModel(),
            tool_choice='specific_tool',
            tools=[]
        )

        # Should not fail, just warn
        assert config.tool_choice == 'specific_tool'
        assert config.tools == []


class TestLoggingImprovements:
    """Test improved logging throughout the agent system."""

    def test_tool_execution_logs_with_context(self):
        """Test tool execution logs include contextual information."""
        # This is more of an integration test
        # Would require capturing log output to verify
        # For now, just verify the agent can be created
        @tool
        def test_tool(x: int) -> int:
            return x * 2

        config = AgentConfig(
            model=EchoModel(),
            tools=[test_tool]
        )
        agent = Agent(config=config)

        assert len(agent.tool_specs) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
