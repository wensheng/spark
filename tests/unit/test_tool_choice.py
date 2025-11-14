"""Unit tests for tool_choice configuration."""
import pytest
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.models.echo import EchoModel
from spark.tools.decorator import tool


@tool
def sample_tool_a(param: str) -> str:
    """Sample tool A."""
    return f"A: {param}"


@tool
def sample_tool_b(param: str) -> str:
    """Sample tool B."""
    return f"B: {param}"


class TestToolChoice:
    """Test suite for tool_choice configuration."""

    def test_tool_choice_auto(self):
        """Test tool_choice='auto' - model decides."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='auto'
        ))

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'auto': {}}

    def test_tool_choice_any(self):
        """Test tool_choice='any' - must use a tool."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='any'
        ))

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'any': {}}

    def test_tool_choice_none(self):
        """Test tool_choice='none' - disable tools."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='none'
        ))

        tool_choice = agent._get_tool_choice()
        assert tool_choice is None

    def test_tool_choice_specific_valid(self):
        """Test tool_choice with valid tool name."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='sample_tool_a'
        ))

        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'tool': {'name': 'sample_tool_a'}}

    def test_tool_choice_specific_invalid(self):
        """Test tool_choice with invalid tool name falls back to auto."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='nonexistent_tool'
        ))

        tool_choice = agent._get_tool_choice()
        # Should fallback to auto
        assert tool_choice == {'auto': {}}

    def test_tool_choice_default(self):
        """Test default tool_choice is 'auto'."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b]
            # tool_choice not specified
        ))

        # Default should be 'auto'
        assert agent.config.tool_choice == 'auto'
        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'auto': {}}

    def test_tool_choice_none_config(self):
        """Test tool_choice=None config value."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
        ))

        tool_choice = agent._get_tool_choice()
        # None should be treated as 'auto' when tools available
        assert tool_choice == {'auto': {}}

    def test_tool_choice_no_tools(self):
        """Test tool_choice when no tools are available."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[],
            tool_choice='auto'
        ))

        tool_choice = agent._get_tool_choice()
        # Should return None when no tools
        assert tool_choice is None

    @pytest.mark.parametrize("choice,expected", [
        ('auto', {'auto': {}}),
        ('any', {'any': {}}),
        ('none', None),
        ('sample_tool_a', {'tool': {'name': 'sample_tool_a'}}),
    ])
    def test_tool_choice_parametrized(self, choice, expected):
        """Parametrized test for various tool_choice values."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice=choice
        ))

        tool_choice = agent._get_tool_choice()
        assert tool_choice == expected


class TestToolChoiceValidation:
    """Test tool name validation in tool_choice."""

    def test_available_tools_list(self):
        """Test that available tools are correctly identified."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b]
        ))

        tool_names = {spec['name'] for spec in agent.tool_specs}
        assert 'sample_tool_a' in tool_names
        assert 'sample_tool_b' in tool_names
        assert len(tool_names) == 2

    def test_specific_tool_must_exist(self):
        """Test that specifying a non-existent tool logs warning and falls back."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a],
            tool_choice='sample_tool_b'  # Not in tools list
        ))

        # Should fallback to auto
        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'auto': {}}

    def test_case_sensitive_tool_names(self):
        """Test that tool names are case-sensitive."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a],
            tool_choice='Sample_Tool_A'  # Wrong case
        ))

        # Should fallback to auto because case doesn't match
        tool_choice = agent._get_tool_choice()
        assert tool_choice == {'auto': {}}


class TestToolChoiceIntegration:
    """Integration tests for tool_choice in agent execution."""

    @pytest.mark.asyncio
    async def test_agent_with_auto_executes(self):
        """Test that agent executes with tool_choice='auto'."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a],
            tool_choice='auto'
        ))

        result = await agent.do({'messages': [{'role': 'user', 'content': 'test'}]})
        assert result is not None
        assert hasattr(result, 'content')

    @pytest.mark.asyncio
    async def test_agent_with_none_executes(self):
        """Test that agent executes with tool_choice='none'."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a],
            tool_choice='none'
        ))

        result = await agent.do({'messages': [{'role': 'user', 'content': 'test'}]})
        assert result is not None
        # With EchoModel, tools won't actually be called anyway

    @pytest.mark.asyncio
    async def test_agent_with_specific_tool_executes(self):
        """Test that agent executes with specific tool choice."""
        agent = Agent(AgentConfig(
            model=EchoModel(),
            tools=[sample_tool_a, sample_tool_b],
            tool_choice='sample_tool_a'
        ))

        result = await agent.do({'messages': [{'role': 'user', 'content': 'test'}]})
        assert result is not None
