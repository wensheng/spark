"""
Tests for Agent enhancements (Phase 4).

This module tests the enhancements made in Phase 4:
- Parallel tool execution
- Cost tracking
- Agent checkpointing
"""

import pytest
import tempfile
import os
import time
from spark.agents import (
    Agent,
    AgentConfig,
    CostTracker,
    CallCost,
    CostStats,
    PlanAndSolveStrategy,
    AgentBudgetConfig,
    AgentBudgetManager,
    AgentBudgetExceededError,
    HumanInteractionPolicy,
    HumanPolicyManager,
    HumanApprovalRequired,
    AgentStoppedError,
)
from spark.models.echo import EchoModel
from spark.tools.decorator import tool
from spark.nodes.types import ExecutionContext, NodeMessage


# Test tools
@tool
def tool_a(x: int) -> int:
    """Tool A."""
    return x * 2


@tool
def tool_b(x: int) -> int:
    """Tool B."""
    return x + 10


class TestParallelToolExecution:
    """Test parallel tool execution capability."""

    def test_parallel_execution_config(self):
        """Test parallel_tool_execution config option."""
        config = AgentConfig(
            model=EchoModel(),
            parallel_tool_execution=True
        )
        assert config.parallel_tool_execution is True

    def test_default_is_sequential(self):
        """Test default is sequential execution."""
        config = AgentConfig(model=EchoModel())
        assert config.parallel_tool_execution is False

    def test_agent_has_parallel_config(self):
        """Test agent respects parallel config."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[tool_a, tool_b],
            parallel_tool_execution=True
        )
        agent = Agent(config=config)
        assert agent.config.parallel_tool_execution is True


class TestCostTracker:
    """Test cost tracking functionality."""

    def test_cost_tracker_initialization(self):
        """Test CostTracker can be initialized."""
        tracker = CostTracker()
        assert len(tracker.calls) == 0

    def test_record_call(self):
        """Test recording a single call."""
        tracker = CostTracker()
        call = tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)

        assert isinstance(call, CallCost)
        assert call.model_id == 'gpt-4o'
        assert call.input_tokens == 100
        assert call.output_tokens == 50
        assert call.total_cost > 0

    def test_record_multiple_calls(self):
        """Test recording multiple calls."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        tracker.record_call('gpt-3.5-turbo', input_tokens=200, output_tokens=100)

        assert len(tracker.calls) == 2

    def test_get_stats(self):
        """Test getting aggregated statistics."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        tracker.record_call('gpt-4o', input_tokens=200, output_tokens=100)

        stats = tracker.get_stats()
        assert isinstance(stats, CostStats)
        assert stats.total_calls == 2
        assert stats.total_input_tokens == 300
        assert stats.total_output_tokens == 150
        assert stats.total_tokens == 450
        assert stats.total_cost > 0

    def test_cost_by_model(self):
        """Test cost breakdown by model."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        tracker.record_call('gpt-3.5-turbo', input_tokens=200, output_tokens=100)

        stats = tracker.get_stats()
        assert 'gpt-4o' in stats.cost_by_model
        assert 'gpt-3.5-turbo' in stats.cost_by_model
        assert stats.cost_by_model['gpt-4o'] > 0
        assert stats.cost_by_model['gpt-3.5-turbo'] > 0

    def test_get_calls_all(self):
        """Test getting all calls."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        tracker.record_call('gpt-3.5-turbo', input_tokens=200, output_tokens=100)

        calls = tracker.get_calls()
        assert len(calls) == 2

    def test_get_calls_filtered(self):
        """Test getting calls filtered by model."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
        tracker.record_call('gpt-3.5-turbo', input_tokens=200, output_tokens=100)
        tracker.record_call('gpt-4o', input_tokens=50, output_tokens=25)

        gpt4_calls = tracker.get_calls('gpt-4o')
        assert len(gpt4_calls) == 2
        assert all(c.model_id == 'gpt-4o' for c in gpt4_calls)

    def test_reset(self):
        """Test resetting tracker."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)

        tracker.reset()

        assert len(tracker.calls) == 0
        stats = tracker.get_stats()
        assert stats.total_calls == 0
        assert stats.total_cost == 0.0

    def test_format_summary(self):
        """Test formatting cost summary."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)

        summary = tracker.format_summary()
        assert 'Cost Summary' in summary
        assert 'Total Calls: 1' in summary
        assert 'gpt-4o' in summary

    def test_unknown_model_uses_default_pricing(self):
        """Test unknown models use default pricing."""
        tracker = CostTracker()
        call = tracker.record_call('unknown-model', input_tokens=100, output_tokens=50)

        # Should not raise, should use default pricing
        assert call.total_cost > 0

    def test_namespaced_stats(self):
        """Test stats can be segmented by namespace."""
        tracker = CostTracker()
        tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50, namespace='alpha')
        tracker.record_call('gpt-4o', input_tokens=200, output_tokens=100, namespace='beta')

        all_stats = tracker.get_stats()
        alpha_stats = tracker.get_stats('alpha')
        beta_stats = tracker.get_stats('beta')

        assert all_stats.total_calls == 2
        assert alpha_stats.total_calls == 1
        assert beta_stats.total_calls == 1
        assert tracker.get_calls(namespace='alpha')[0].namespace == 'alpha'


class TestAgentCostTracking:
    """Test cost tracking integration with Agent."""

    def test_agent_has_cost_tracker(self):
        """Test agent has cost_tracker attribute."""
        agent = Agent()
        assert hasattr(agent, 'cost_tracker')
        assert isinstance(agent.cost_tracker, CostTracker)

    def test_get_cost_stats(self):
        """Test agent.get_cost_stats() method."""
        agent = Agent()
        stats = agent.get_cost_stats()
        assert isinstance(stats, CostStats)

    def test_reset_cost_tracking(self):
        """Test agent.reset_cost_tracking() method."""
        agent = Agent()
        agent.cost_tracker.record_call('gpt-4o', 100, 50)

        agent.reset_cost_tracking()

        stats = agent.get_cost_stats()
        assert stats.total_calls == 0

    def test_get_cost_summary(self):
        """Test agent.get_cost_summary() method."""
        agent = Agent()
        agent.cost_tracker.record_call('gpt-4o', 100, 50)

        summary = agent.get_cost_summary()
        assert isinstance(summary, str)
        assert 'Cost Summary' in summary


class TestAgentCheckpointing:
    """Test agent checkpointing functionality."""

    def test_checkpoint_creation(self):
        """Test creating a checkpoint."""
        agent = Agent()
        agent.add_message_to_history({'role': 'user', 'content': 'Hello'})

        checkpoint = agent.checkpoint()

        assert 'version' in checkpoint
        assert 'timestamp' in checkpoint
        assert 'config' in checkpoint
        assert 'memory' in checkpoint
        assert 'state' in checkpoint
        assert 'cost_tracking' in checkpoint

    def test_checkpoint_includes_messages(self):
        """Test checkpoint includes conversation history."""
        agent = Agent()
        agent.add_message_to_history({'role': 'user', 'content': 'Hello'})
        agent.add_message_to_history({'role': 'assistant', 'content': 'Hi'})

        checkpoint = agent.checkpoint()

        assert len(checkpoint['memory']['messages']) == 2

    def test_checkpoint_includes_state(self):
        """Test checkpoint includes agent state."""
        agent = Agent()
        agent._state['last_error'] = 'test error'

        checkpoint = agent.checkpoint()

        assert checkpoint['state']['last_error'] == 'test error'

    def test_checkpoint_includes_cost_data(self):
        """Test checkpoint includes cost tracking data."""
        agent = Agent()
        agent.cost_tracker.record_call('gpt-4o', 100, 50)

        checkpoint = agent.checkpoint()

        assert 'cost_tracking' in checkpoint
        assert len(checkpoint['cost_tracking']['calls']) == 1

    def test_restore_from_checkpoint(self):
        """Test restoring agent from checkpoint."""
        # Create agent and add some state
        agent1 = Agent()
        agent1.add_message_to_history({'role': 'user', 'content': 'Hello'})
        agent1.cost_tracker.record_call('gpt-4o', 100, 50)

        # Create checkpoint
        checkpoint = agent1.checkpoint()

        # Restore to new agent
        agent2 = Agent.restore(checkpoint)

        # Verify restoration
        assert len(agent2.messages) == 1
        assert agent2.messages[0]['content'] == 'Hello'
        assert agent2.cost_tracker.get_stats().total_calls == 1

    def test_restore_with_config(self):
        """Test restoring with provided config."""
        config = AgentConfig(
            model=EchoModel(),
            name="TestAgent",
            system_prompt="Test prompt"
        )

        agent1 = Agent(config=config)
        agent1.add_message_to_history({'role': 'user', 'content': 'Test'})

        checkpoint = agent1.checkpoint()

        # Restore with same config
        agent2 = Agent.restore(checkpoint, config)

        assert agent2.config.name == "TestAgent"
        assert agent2.config.system_prompt == "Test prompt"
        assert len(agent2.messages) == 1

    def test_save_and_load_checkpoint(self):
        """Test saving and loading checkpoint from file."""
        agent1 = Agent()
        agent1.add_message_to_history({'role': 'user', 'content': 'Hello'})

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            filepath = f.name

        try:
            agent1.save_checkpoint(filepath)

            # Load from file
            agent2 = Agent.load_checkpoint(filepath)

            # Verify
            assert len(agent2.messages) == 1
            assert agent2.messages[0]['content'] == 'Hello'
        finally:
            if os.path.exists(filepath):
                os.unlink(filepath)

    def test_checkpoint_preserves_tool_traces(self):
        """Test checkpoint preserves tool execution traces."""
        agent = Agent()
        agent._state['tool_traces'].append({
            'tool_name': 'test_tool',
            'tool_use_id': 'id1',
            'input_params': {'x': 1},
            'output': 2,
            'start_time': 1000.0,
            'end_time': 1001.0,
            'duration_ms': 1000.0,
            'error': None
        })

        checkpoint = agent.checkpoint()
        agent2 = Agent.restore(checkpoint)

        assert len(agent2._state['tool_traces']) == 1
        assert agent2._state['tool_traces'][0]['tool_name'] == 'test_tool'


class TestPhase4Integration:
    """Test Phase 4 features work together."""

    def test_parallel_and_cost_tracking_together(self):
        """Test parallel execution with cost tracking."""
        config = AgentConfig(
            model=EchoModel(),
            tools=[tool_a, tool_b],
            parallel_tool_execution=True
        )
        agent = Agent(config=config)

        # Agent should have both features
        assert agent.config.parallel_tool_execution is True
        assert isinstance(agent.cost_tracker, CostTracker)

    def test_checkpoint_preserves_all_features(self):
        """Test checkpoint preserves parallel config and cost data."""
        config = AgentConfig(
            model=EchoModel(),
            parallel_tool_execution=True
        )
        agent1 = Agent(config=config)
        agent1.cost_tracker.record_call('gpt-4o', 100, 50)

        checkpoint = agent1.checkpoint()

        assert checkpoint['config']['parallel_tool_execution'] is True
        assert len(checkpoint['cost_tracking']['calls']) == 1


class TestStrategyPlanning:
    """Verify plan-first strategy support."""

    @pytest.mark.asyncio
    async def test_plan_strategy_generates_plan(self):
        strategy = PlanAndSolveStrategy(plan_steps=["Assess", "Deliver"])
        config = AgentConfig(model=EchoModel(), reasoning_strategy=strategy)
        agent = Agent(config=config)
        context = ExecutionContext(inputs=NodeMessage(content={}, metadata={}), state=agent.state)
        await agent._ensure_strategy_plan(context)  # type: ignore[attr-defined]
        assert 'strategy_plan' in agent.state
        plan = agent.state['strategy_plan']
        assert len(plan['steps']) == 2


class TestAgentBudgets:
    """Validate agent budget helpers."""

    def test_llm_call_budget(self):
        manager = AgentBudgetManager(AgentBudgetConfig(max_llm_calls=1))
        manager.start_run()
        manager.register_llm_call()
        with pytest.raises(AgentBudgetExceededError):
            manager.register_llm_call()

    def test_runtime_budget(self):
        manager = AgentBudgetManager(AgentBudgetConfig(max_runtime_seconds=0.01))
        manager.start_run()
        time.sleep(0.02)
        with pytest.raises(AgentBudgetExceededError):
            manager.check_runtime()


class TestHumanPolicies:
    """Ensure human policy manager enforces approvals and stops."""

    def test_tool_approval_required(self):
        policy = HumanInteractionPolicy(require_tool_approval=True)
        manager = HumanPolicyManager(policy)
        with pytest.raises(HumanApprovalRequired):
            manager.ensure_tool_allowed('danger')
        policy.auto_approved_tools.append('safe')
        manager.ensure_tool_allowed('safe')

    def test_stop_signal(self):
        policy = HumanInteractionPolicy(stop_token='mission-x')
        manager = HumanPolicyManager(policy)
        HumanPolicyManager.issue_stop_signal('mission-x', reason='pause')
        with pytest.raises(AgentStoppedError):
            manager.ensure_not_stopped()
        HumanPolicyManager.clear_stop_signal('mission-x')
        manager.ensure_not_stopped()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
