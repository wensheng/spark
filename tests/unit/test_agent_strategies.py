"""
Tests for Agent reasoning strategies (Phase 3).

This module tests the strategy pattern implementation for pluggable
reasoning patterns like ReAct, Chain-of-Thought, and custom strategies.
"""

import pytest
import pytest_asyncio
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.agents.strategies import (
    ReasoningStrategy,
    NoOpStrategy,
    ReActStrategy,
    ChainOfThoughtStrategy
)
from spark.models.echo import EchoModel


class TestReasoningStrategyInterface:
    """Test the ReasoningStrategy base class interface."""

    def test_reasoning_strategy_is_abstract(self):
        """Test ReasoningStrategy cannot be instantiated."""
        with pytest.raises(TypeError):
            ReasoningStrategy()  # type: ignore

    def test_reasoning_strategy_requires_process_step(self):
        """Test subclasses must implement process_step."""
        class IncompleteStrategy(ReasoningStrategy):
            def should_continue(self, parsed_output):
                return False

            def get_history(self, state):
                return []

        with pytest.raises(TypeError):
            IncompleteStrategy()  # type: ignore

    def test_reasoning_strategy_requires_should_continue(self):
        """Test subclasses must implement should_continue."""
        class IncompleteStrategy(ReasoningStrategy):
            async def process_step(self, parsed_output, tool_result_blocks, state, context=None):
                pass

            def get_history(self, state):
                return []

        with pytest.raises(TypeError):
            IncompleteStrategy()  # type: ignore

    def test_reasoning_strategy_requires_get_history(self):
        """Test subclasses must implement get_history."""
        class IncompleteStrategy(ReasoningStrategy):
            async def process_step(self, parsed_output, tool_result_blocks, state, context=None):
                pass

            def should_continue(self, parsed_output):
                return False

        with pytest.raises(TypeError):
            IncompleteStrategy()  # type: ignore


class TestNoOpStrategy:
    """Test the NoOpStrategy implementation."""

    def test_noop_strategy_instantiation(self):
        """Test NoOpStrategy can be instantiated."""
        strategy = NoOpStrategy()
        assert isinstance(strategy, ReasoningStrategy)

    @pytest.mark.asyncio
    async def test_noop_process_step_does_nothing(self):
        """Test NoOpStrategy.process_step does nothing."""
        strategy = NoOpStrategy()
        state = {'history': []}

        await strategy.process_step(
            parsed_output={'action': 'test'},
            tool_result_blocks=[],
            state=state
        )

        # State should be unchanged
        assert state == {'history': []}

    def test_noop_should_continue_returns_false(self):
        """Test NoOpStrategy.should_continue always returns False."""
        strategy = NoOpStrategy()

        assert strategy.should_continue({'action': 'test'}) is False
        assert strategy.should_continue({'final_answer': 'done'}) is False
        assert strategy.should_continue(None) is False

    def test_noop_get_history_returns_empty(self):
        """Test NoOpStrategy.get_history returns empty list."""
        strategy = NoOpStrategy()
        state = {'history': [1, 2, 3]}

        assert strategy.get_history(state) == []

    def test_noop_initialize_state_does_nothing(self):
        """Test NoOpStrategy.initialize_state does nothing."""
        strategy = NoOpStrategy()
        state = {}

        strategy.initialize_state(state)

        # State should remain empty
        assert state == {}


class TestReActStrategy:
    """Test the ReActStrategy implementation."""

    def test_react_strategy_instantiation(self):
        """Test ReActStrategy can be instantiated."""
        strategy = ReActStrategy()
        assert isinstance(strategy, ReasoningStrategy)
        assert strategy.verbose is True

    def test_react_strategy_with_verbose_false(self):
        """Test ReActStrategy with verbose=False."""
        strategy = ReActStrategy(verbose=False)
        assert strategy.verbose is False

    def test_react_initialize_state(self):
        """Test ReActStrategy initializes history in state."""
        strategy = ReActStrategy()
        state = {}

        strategy.initialize_state(state)

        assert 'history' in state
        assert state['history'] == []

    def test_react_initialize_state_preserves_existing_history(self):
        """Test ReActStrategy doesn't overwrite existing history."""
        strategy = ReActStrategy()
        existing_history = [{'step': 1}]
        state = {'history': existing_history}

        strategy.initialize_state(state)

        assert state['history'] is existing_history

    @pytest.mark.asyncio
    async def test_react_process_step_with_valid_output(self):
        """Test ReActStrategy.process_step with valid ReAct output."""
        strategy = ReActStrategy(verbose=False)
        state = {'history': []}

        parsed_output = {
            'thought': 'I need to search for information',
            'action': 'search',
            'action_input': 'test query'
        }

        tool_result_blocks = [{
            'toolResult': {
                'toolUseId': 'call_1',
                'content': [{'text': 'Search result'}],
                'status': 'success'
            }
        }]

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=tool_result_blocks,
            state=state
        )

        assert len(state['history']) == 1
        step = state['history'][0]
        assert step['thought'] == 'I need to search for information'
        assert step['action'] == 'search'
        assert step['action_input'] == 'test query'
        assert step['observation'] == 'Search result'

    @pytest.mark.asyncio
    async def test_react_process_step_with_no_action(self):
        """Test ReActStrategy.process_step skips when no action."""
        strategy = ReActStrategy(verbose=False)
        state = {'history': []}

        parsed_output = {
            'thought': 'I have the answer',
            'final_answer': 'The answer is 42'
        }

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=[],
            state=state
        )

        # Should not add to history
        assert len(state['history']) == 0

    @pytest.mark.asyncio
    async def test_react_process_step_with_null_action(self):
        """Test ReActStrategy.process_step skips when action is 'null'."""
        strategy = ReActStrategy(verbose=False)
        state = {'history': []}

        parsed_output = {
            'thought': 'Done',
            'action': 'null',
            'action_input': ''
        }

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=[],
            state=state
        )

        # Should not add to history
        assert len(state['history']) == 0

    @pytest.mark.asyncio
    async def test_react_process_step_with_no_tool_results(self):
        """Test ReActStrategy.process_step with empty tool results."""
        strategy = ReActStrategy(verbose=False)
        state = {'history': []}

        parsed_output = {
            'thought': 'Testing',
            'action': 'test_action',
            'action_input': 'test'
        }

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=[],
            state=state
        )

        assert len(state['history']) == 1
        assert state['history'][0]['observation'] == 'No observation recorded'

    @pytest.mark.asyncio
    async def test_react_process_step_with_non_dict_output(self):
        """Test ReActStrategy.process_step skips non-dict output."""
        strategy = ReActStrategy(verbose=False)
        state = {'history': []}

        await strategy.process_step(
            parsed_output="not a dict",
            tool_result_blocks=[],
            state=state
        )

        # Should not add to history
        assert len(state['history']) == 0

    def test_react_should_continue_with_action(self):
        """Test ReActStrategy.should_continue returns True with action."""
        strategy = ReActStrategy()

        parsed_output = {
            'thought': 'Next step',
            'action': 'search',
            'action_input': 'query'
        }

        assert strategy.should_continue(parsed_output) is True

    def test_react_should_continue_with_final_answer(self):
        """Test ReActStrategy.should_continue returns False with final_answer."""
        strategy = ReActStrategy()

        parsed_output = {
            'thought': 'Done',
            'action': 'finish',
            'final_answer': '42'
        }

        assert strategy.should_continue(parsed_output) is False

    def test_react_should_continue_with_null_action(self):
        """Test ReActStrategy.should_continue returns False with null action."""
        strategy = ReActStrategy()

        parsed_output = {
            'thought': 'Done',
            'action': 'null',
            'action_input': ''
        }

        assert strategy.should_continue(parsed_output) is False

    def test_react_should_continue_with_no_action(self):
        """Test ReActStrategy.should_continue returns False with no action."""
        strategy = ReActStrategy()

        parsed_output = {
            'thought': 'Done',
            'final_answer': '42'
        }

        assert strategy.should_continue(parsed_output) is False

    def test_react_should_continue_with_non_dict(self):
        """Test ReActStrategy.should_continue returns False with non-dict."""
        strategy = ReActStrategy()

        assert strategy.should_continue("not a dict") is False
        assert strategy.should_continue(None) is False

    def test_react_get_history(self):
        """Test ReActStrategy.get_history returns history from state."""
        strategy = ReActStrategy()
        history = [
            {'thought': 'step1', 'action': 'search', 'action_input': 'q1', 'observation': 'r1'},
            {'thought': 'step2', 'action': 'search', 'action_input': 'q2', 'observation': 'r2'}
        ]
        state = {'history': history}

        assert strategy.get_history(state) == history

    def test_react_get_history_empty(self):
        """Test ReActStrategy.get_history returns empty when no history."""
        strategy = ReActStrategy()
        state = {}

        assert strategy.get_history(state) == []


class TestChainOfThoughtStrategy:
    """Test the ChainOfThoughtStrategy implementation."""

    def test_cot_strategy_instantiation(self):
        """Test ChainOfThoughtStrategy can be instantiated."""
        strategy = ChainOfThoughtStrategy()
        assert isinstance(strategy, ReasoningStrategy)

    @pytest.mark.asyncio
    async def test_cot_process_step_with_steps(self):
        """Test ChainOfThoughtStrategy.process_step with reasoning steps."""
        strategy = ChainOfThoughtStrategy()
        state = {'history': []}

        parsed_output = {
            'steps': [
                'First, identify the problem',
                'Second, break it down',
                'Third, solve each part'
            ],
            'answer': 'The solution'
        }

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=[],
            state=state
        )

        assert len(state['history']) == 1
        step = state['history'][0]
        assert len(step['steps']) == 3
        assert step['answer'] == 'The solution'

    @pytest.mark.asyncio
    async def test_cot_process_step_with_no_steps(self):
        """Test ChainOfThoughtStrategy.process_step skips when no steps."""
        strategy = ChainOfThoughtStrategy()
        state = {'history': []}

        parsed_output = {'answer': 'Quick answer'}

        await strategy.process_step(
            parsed_output=parsed_output,
            tool_result_blocks=[],
            state=state
        )

        # Should not add to history
        assert len(state['history']) == 0

    def test_cot_should_continue_with_no_answer(self):
        """Test ChainOfThoughtStrategy.should_continue with no answer."""
        strategy = ChainOfThoughtStrategy()

        parsed_output = {'steps': ['step1', 'step2']}

        assert strategy.should_continue(parsed_output) is True

    def test_cot_should_continue_with_answer(self):
        """Test ChainOfThoughtStrategy.should_continue with answer."""
        strategy = ChainOfThoughtStrategy()

        parsed_output = {
            'steps': ['step1', 'step2'],
            'answer': 'Final answer'
        }

        assert strategy.should_continue(parsed_output) is False

    def test_cot_get_history(self):
        """Test ChainOfThoughtStrategy.get_history."""
        strategy = ChainOfThoughtStrategy()
        history = [{'steps': ['s1', 's2'], 'answer': 'a1'}]
        state = {'history': history}

        assert strategy.get_history(state) == history


class TestAgentWithStrategies:
    """Test Agent integration with different strategies."""

    def test_agent_default_uses_noop_strategy(self):
        """Test Agent uses NoOpStrategy by default."""
        agent = Agent()

        assert isinstance(agent.reasoning_strategy, NoOpStrategy)

    def test_agent_with_react_strategy(self):
        """Test Agent can be configured with ReActStrategy."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=ReActStrategy(verbose=False)
        )
        agent = Agent(config=config)

        assert isinstance(agent.reasoning_strategy, ReActStrategy)
        assert agent.reasoning_strategy.verbose is False

    def test_agent_with_cot_strategy(self):
        """Test Agent can be configured with ChainOfThoughtStrategy."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=ChainOfThoughtStrategy()
        )
        agent = Agent(config=config)

        assert isinstance(agent.reasoning_strategy, ChainOfThoughtStrategy)

    def test_agent_strategy_initializes_state(self):
        """Test Agent's strategy initializes state."""
        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=ReActStrategy()
        )
        agent = Agent(config=config)

        # ReActStrategy should have initialized history
        assert 'history' in agent.state
        assert agent.state['history'] == []

    def test_agent_with_custom_strategy(self):
        """Test Agent can use custom strategy."""
        class CustomStrategy(ReasoningStrategy):
            async def process_step(self, parsed_output, tool_result_blocks, state, context=None):
                state.setdefault('custom', []).append('step')

            def should_continue(self, parsed_output):
                return False

            def get_history(self, state):
                return state.get('custom', [])

        config = AgentConfig(
            model=EchoModel(),
            reasoning_strategy=CustomStrategy()
        )
        agent = Agent(config=config)

        assert isinstance(agent.reasoning_strategy, CustomStrategy)


class TestStrategyExports:
    """Test that strategies are properly exported."""

    def test_strategies_exported_from_agents_module(self):
        """Test strategies can be imported from spark.agents."""
        from spark.agents import (
            ReasoningStrategy,
            NoOpStrategy,
            ReActStrategy,
            ChainOfThoughtStrategy
        )

        assert ReasoningStrategy is not None
        assert NoOpStrategy is not None
        assert ReActStrategy is not None
        assert ChainOfThoughtStrategy is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
