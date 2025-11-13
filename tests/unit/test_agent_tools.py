"""
Tests for Agent tool execution and tracing.
"""

import pytest
import pytest_asyncio

from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.agents.memory import MemoryPolicyType
from spark.models.echo import EchoModel
from spark.tools.decorator import tool
from spark.nodes.types import NodeMessage


# Define test tools
@tool
def calculator_add(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number
        b: Second number
    """
    return a + b


@tool
def string_reverse(text: str) -> str:
    """Reverse a string.

    Args:
        text: Text to reverse
    """
    return text[::-1]


@tool
def error_tool(message: str) -> str:
    """Tool that raises an error.

    Args:
        message: Error message
    """
    raise ValueError(f"Tool error: {message}")


class TestAgentTools:
    """Test agent tool functionality."""

    def test_agent_with_tools(self):
        """Test agent initializes with tools."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add, string_reverse]
        )
        agent = Agent(config=config)

        assert len(agent.tool_registry.registry) == 2
        assert 'calculator_add' in agent.tool_registry.registry
        assert 'string_reverse' in agent.tool_registry.registry

    def test_agent_tool_specs(self):
        """Test agent generates tool specs."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add]
        )
        agent = Agent(config=config)

        assert len(agent.tool_specs) == 1
        spec = agent.tool_specs[0]
        assert spec['name'] == 'calculator_add'
        assert 'description' in spec
        assert 'parameters' in spec

    def test_get_tool_choice_auto(self):
        """Test tool choice 'auto' returns correct format."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add],
            tool_choice='auto'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'auto': {}}

    def test_get_tool_choice_any(self):
        """Test tool choice 'any' returns correct format."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add],
            tool_choice='any'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'any': {}}

    def test_get_tool_choice_none(self):
        """Test tool choice 'none' disables tools."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add],
            tool_choice='none'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        assert tool_choice is None

    def test_get_tool_choice_specific_tool(self):
        """Test tool choice with specific tool name."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add, string_reverse],
            tool_choice='calculator_add'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'tool': {'name': 'calculator_add'}}

    def test_get_tool_choice_invalid_tool_name(self):
        """Test tool choice with invalid tool name falls back to auto."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[calculator_add],
            tool_choice='nonexistent_tool'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        # Should fallback to auto
        assert tool_choice == {'auto': {}}

    def test_get_tool_choice_no_tools(self):
        """Test tool choice returns None when no tools available."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[],
            tool_choice='auto'
        )
        agent = Agent(config=config)

        tool_choice = agent._get_tool_choice()
        assert tool_choice is None


class TestAgentToolTracing:
    """Test agent tool execution tracing."""

    def test_tool_traces_initialized_empty(self):
        """Test tool traces start empty."""
        agent = Agent()

        traces = agent.get_tool_traces()
        assert traces == []

    def test_record_tool_trace(self):
        """Test recording a tool trace."""
        agent = Agent()

        agent._record_tool_trace(
            tool_name='test_tool',
            tool_use_id='call_123',
            input_params={'x': 1},
            output='result',
            start_time=1000.0,
            end_time=1000.5,
            error=None
        )

        traces = agent.get_tool_traces()
        assert len(traces) == 1

        trace = traces[0]
        assert trace['tool_name'] == 'test_tool'
        assert trace['tool_use_id'] == 'call_123'
        assert trace['input_params'] == {'x': 1}
        assert trace['output'] == 'result'
        assert trace['duration_ms'] == 500.0
        assert trace['error'] is None

    def test_record_tool_trace_with_error(self):
        """Test recording a tool trace with error."""
        agent = Agent()

        agent._record_tool_trace(
            tool_name='test_tool',
            tool_use_id='call_123',
            input_params={'x': 1},
            output=None,
            start_time=1000.0,
            end_time=1000.5,
            error='Test error'
        )

        traces = agent.get_tool_traces()
        assert len(traces) == 1
        assert traces[0]['error'] == 'Test error'

    def test_get_last_tool_trace(self):
        """Test getting last tool trace."""
        agent = Agent()

        # Add multiple traces
        agent._record_tool_trace(
            tool_name='tool1',
            tool_use_id='call_1',
            input_params={},
            output='result1',
            start_time=1000.0,
            end_time=1000.1
        )
        agent._record_tool_trace(
            tool_name='tool2',
            tool_use_id='call_2',
            input_params={},
            output='result2',
            start_time=1000.2,
            end_time=1000.3
        )

        last_trace = agent.get_last_tool_trace()
        assert last_trace is not None
        assert last_trace['tool_name'] == 'tool2'

    def test_get_last_tool_trace_empty(self):
        """Test getting last tool trace when empty."""
        agent = Agent()

        last_trace = agent.get_last_tool_trace()
        assert last_trace is None

    def test_get_tool_traces_by_name(self):
        """Test filtering traces by tool name."""
        agent = Agent()

        # Add traces for different tools
        agent._record_tool_trace(
            tool_name='tool1',
            tool_use_id='call_1',
            input_params={},
            output='result1',
            start_time=1000.0,
            end_time=1000.1
        )
        agent._record_tool_trace(
            tool_name='tool2',
            tool_use_id='call_2',
            input_params={},
            output='result2',
            start_time=1000.2,
            end_time=1000.3
        )
        agent._record_tool_trace(
            tool_name='tool1',
            tool_use_id='call_3',
            input_params={},
            output='result3',
            start_time=1000.4,
            end_time=1000.5
        )

        tool1_traces = agent.get_tool_traces_by_name('tool1')
        assert len(tool1_traces) == 2
        assert all(t['tool_name'] == 'tool1' for t in tool1_traces)

    def test_get_failed_tool_traces(self):
        """Test getting only failed tool traces."""
        agent = Agent()

        # Add successful and failed traces
        agent._record_tool_trace(
            tool_name='tool1',
            tool_use_id='call_1',
            input_params={},
            output='result1',
            start_time=1000.0,
            end_time=1000.1,
            error=None
        )
        agent._record_tool_trace(
            tool_name='tool2',
            tool_use_id='call_2',
            input_params={},
            output=None,
            start_time=1000.2,
            end_time=1000.3,
            error='Failed'
        )
        agent._record_tool_trace(
            tool_name='tool3',
            tool_use_id='call_3',
            input_params={},
            output=None,
            start_time=1000.4,
            end_time=1000.5,
            error='Also failed'
        )

        failed_traces = agent.get_failed_tool_traces()
        assert len(failed_traces) == 2
        assert all(t['error'] is not None for t in failed_traces)

    def test_clear_tool_traces(self):
        """Test clearing tool traces."""
        agent = Agent()

        # Add some traces
        agent._record_tool_trace(
            tool_name='tool1',
            tool_use_id='call_1',
            input_params={},
            output='result',
            start_time=1000.0,
            end_time=1000.1
        )

        assert len(agent.get_tool_traces()) == 1

        agent.clear_tool_traces()
        assert len(agent.get_tool_traces()) == 0


class TestAgentHistoryManagement:
    """Test agent conversation history management."""

    def test_add_message_to_history(self):
        """Test adding message to history."""
        agent = Agent()

        agent.add_message_to_history({'role': 'user', 'content': 'Hello'})

        history = agent.get_history()
        assert len(history) == 1
        assert history[0]['role'] == 'user'

    def test_add_string_message(self):
        """Test adding string message (converted to user message)."""
        agent = Agent()

        agent.add_message_to_history('Hello')

        history = agent.get_history()
        assert len(history) == 1
        assert history[0]['role'] == 'user'
        assert history[0]['content'] == 'Hello'

    def test_get_history(self):
        """Test getting conversation history."""
        agent = Agent()

        agent.add_message_to_history({'role': 'user', 'content': 'Hello'})
        agent.add_message_to_history({'role': 'assistant', 'content': 'Hi'})

        history = agent.get_history()
        assert len(history) == 2
        assert history[0]['role'] == 'user'
        assert history[1]['role'] == 'assistant'

    def test_clear_history(self):
        """Test clearing conversation history."""
        agent = Agent()

        agent.add_message_to_history({'role': 'user', 'content': 'Hello'})
        agent.add_message_to_history({'role': 'assistant', 'content': 'Hi'})

        assert len(agent.get_history()) == 2

        agent.clear_history()
        assert len(agent.get_history()) == 0

    def test_history_respects_memory_policy(self):
        """Test history respects memory policy."""
        config = AgentConfig(
            model=EchoModel(),
            memory_config={'policy': MemoryPolicyType.ROLLING_WINDOW, 'window': 2}
        )
        agent = Agent(config=config)

        agent.add_message_to_history({'role': 'user', 'content': 'Msg 1'})
        agent.add_message_to_history({'role': 'assistant', 'content': 'Reply 1'})
        agent.add_message_to_history({'role': 'user', 'content': 'Msg 2'})

        # Should only keep last 2 messages
        history = agent.get_history()
        assert len(history) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
