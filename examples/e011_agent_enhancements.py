"""
Example 10: Agent Enhancements (Phase 4)

This example demonstrates the Phase 4 enhancements to the agent system:
1. Parallel tool execution
2. Cost tracking
3. Agent checkpointing (save/restore state)

These features improve performance, observability, and resilience for production agents.
"""

import asyncio
import tempfile
import os
from spark.agents import (
    Agent,
    AgentConfig,
    PlanAndSolveStrategy,
    AgentBudgetConfig,
    HumanInteractionPolicy,
    AgentBudgetExceededError,
    HumanApprovalRequired,
    AgentStoppedError,
)
from spark.models.echo import EchoModel
from spark.tools.decorator import tool
from spark.nodes.types import ExecutionContext, NodeMessage


# Define some example tools
@tool
def search_database(query: str) -> str:
    """Search the database for information.

    Args:
        query: The search query
    """
    # Simulate database search
    return f"Database results for '{query}': Found 10 matching records"


@tool
def fetch_user_data(user_id: str) -> dict:
    """Fetch user data from the user service.

    Args:
        user_id: The user identifier
    """
    # Simulate user service call
    return {
        'user_id': user_id,
        'name': 'John Doe',
        'email': 'john@example.com',
        'status': 'active'
    }


@tool
def calculate_metrics(data: str) -> dict:
    """Calculate metrics from data.

    Args:
        data: The data to analyze
    """
    # Simulate metric calculation
    return {
        'total_records': 100,
        'average_score': 85.5,
        'max_value': 100,
        'min_value': 50
    }


# ============================================================================
# Example 1: Sequential Tool Execution (Default)
# ============================================================================

async def example_1_sequential():
    """Example 1: Default sequential tool execution."""
    print("\n" + "="*70)
    print("Example 1: Sequential Tool Execution (Default)")
    print("="*70)

    config = AgentConfig(
        model=EchoModel(),
        tools=[search_database, fetch_user_data, calculate_metrics],
        parallel_tool_execution=False  # Default: sequential
    )

    agent = Agent(config=config)

    print(f"Parallel execution enabled: {agent.config.parallel_tool_execution}")
    print("Tools execute one after another (sequential)\n")


# ============================================================================
# Example 2: Parallel Tool Execution
# ============================================================================

async def example_2_parallel():
    """Example 2: Enable parallel tool execution for better performance."""
    print("\n" + "="*70)
    print("Example 2: Parallel Tool Execution")
    print("="*70)

    config = AgentConfig(
        model=EchoModel(),
        tools=[search_database, fetch_user_data, calculate_metrics],
        parallel_tool_execution=True  # Enable parallel execution
    )

    agent = Agent(config=config)

    print(f"Parallel execution enabled: {agent.config.parallel_tool_execution}")
    print("When multiple tools are called, they execute concurrently!")
    print("This improves performance for independent tool operations.\n")


# ============================================================================
# Example 3: Cost Tracking
# ============================================================================

async def example_3_cost_tracking():
    """Example 3: Track token usage and API costs."""
    print("\n" + "="*70)
    print("Example 3: Cost Tracking")
    print("="*70)

    agent = Agent()  # All agents have cost tracking built-in

    # Simulate recording some API calls
    print("Recording API calls...")
    agent.cost_tracker.record_call('gpt-4o', input_tokens=1500, output_tokens=800)
    agent.cost_tracker.record_call('gpt-4o', input_tokens=2000, output_tokens=1200)
    agent.cost_tracker.record_call('gpt-3.5-turbo', input_tokens=3000, output_tokens=1500)

    # Get cost statistics
    stats = agent.get_cost_stats()

    print(f"\nCost Statistics:")
    print(f"  Total calls: {stats.total_calls}")
    print(f"  Total tokens: {stats.total_tokens:,}")
    print(f"    - Input: {stats.total_input_tokens:,}")
    print(f"    - Output: {stats.total_output_tokens:,}")
    print(f"  Total cost: ${stats.total_cost:.6f}")

    print(f"\nCost by model:")
    for model, cost in stats.cost_by_model.items():
        print(f"    - {model}: ${cost:.6f}")

    # Get formatted summary
    print("\n" + agent.get_cost_summary())

    # Get call history
    gpt4_calls = agent.cost_tracker.get_calls('gpt-4o')
    print(f"\nGPT-4o calls: {len(gpt4_calls)}")

    # Reset tracking
    agent.reset_cost_tracking()
    stats = agent.get_cost_stats()
    print(f"\nAfter reset - Total calls: {stats.total_calls}")


# ============================================================================
# Example 4: Agent Checkpointing
# ============================================================================

async def example_4_checkpointing():
    """Example 4: Save and restore agent state."""
    print("\n" + "="*70)
    print("Example 4: Agent Checkpointing")
    print("="*70)

    # Create an agent and add some state
    config = AgentConfig(
        model=EchoModel(),
        name="ProductionAgent",
        system_prompt="You are a helpful assistant."
    )

    agent1 = Agent(config=config)
    agent1.add_message_to_history({'role': 'user', 'content': 'Hello'})
    agent1.add_message_to_history({'role': 'assistant', 'content': 'Hi there!'})
    agent1.cost_tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)

    print(f"Agent 1 - Messages: {len(agent1.messages)}")
    print(f"Agent 1 - Cost calls: {agent1.cost_tracker.get_stats().total_calls}")

    # Create checkpoint (in-memory)
    checkpoint = agent1.checkpoint()
    print(f"\nCreated checkpoint at timestamp: {checkpoint['timestamp']}")
    print(f"Checkpoint contains:")
    print(f"  - {len(checkpoint['memory']['messages'])} messages")
    print(f"  - {len(checkpoint['cost_tracking']['calls'])} cost records")
    print(f"  - Config: {checkpoint['config']['name']}")

    # Restore to a new agent
    agent2 = Agent.restore(checkpoint, config)

    print(f"\nAgent 2 (restored) - Messages: {len(agent2.messages)}")
    print(f"Agent 2 (restored) - Cost calls: {agent2.cost_tracker.get_stats().total_calls}")
    print("✓ State successfully restored!")


# ============================================================================
# Example 5: Save/Load Checkpoint from File
# ============================================================================

async def example_5_checkpoint_file():
    """Example 5: Save and load checkpoint from file."""
    print("\n" + "="*70)
    print("Example 5: Save/Load Checkpoint from File")
    print("="*70)

    # Create an agent with state
    config = AgentConfig(
        model=EchoModel(),
        name="FileCheckpointAgent",
        max_steps=50
    )

    agent1 = Agent(config=config)
    agent1.add_message_to_history({'role': 'user', 'content': 'What is AI?'})
    agent1.add_message_to_history({'role': 'assistant', 'content': 'AI stands for...'})
    agent1.cost_tracker.record_call('gpt-4o', input_tokens=500, output_tokens=300)

    # Save to temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        filepath = f.name

    try:
        agent1.save_checkpoint(filepath)
        print(f"✓ Saved checkpoint to: {filepath}")

        # Check file size
        file_size = os.path.getsize(filepath)
        print(f"  File size: {file_size} bytes")

        # Load from file
        agent2 = Agent.load_checkpoint(filepath, config)

        print(f"\n✓ Loaded checkpoint from file")
        print(f"  Messages: {len(agent2.messages)}")
        print(f"  Cost calls: {agent2.cost_tracker.get_stats().total_calls}")
        print(f"  Config name: {agent2.config.name}")

    finally:
        # Cleanup
        if os.path.exists(filepath):
            os.unlink(filepath)
            print(f"\n✓ Cleaned up temporary file")


# ============================================================================
# Example 6: Combined Features - Parallel + Cost + Checkpoint
# ============================================================================

async def example_6_combined():
    """Example 6: Use all Phase 4 features together."""
    print("\n" + "="*70)
    print("Example 6: All Features Combined")
    print("="*70)

    # Create agent with all features
    config = AgentConfig(
        model=EchoModel(),
        tools=[search_database, fetch_user_data, calculate_metrics],
        parallel_tool_execution=True,  # Enable parallel execution
        name="ProductionAgent",
        max_steps=20
    )

    agent = Agent(config=config)

    print("Agent configuration:")
    print(f"  - Parallel execution: {agent.config.parallel_tool_execution}")
    print(f"  - Cost tracking: Enabled (built-in)")
    print(f"  - Checkpointing: Available")

    # Simulate some work
    agent.add_message_to_history({'role': 'user', 'content': 'Process this data'})
    agent.cost_tracker.record_call('gpt-4o', input_tokens=2000, output_tokens=1000)
    agent.cost_tracker.record_call('gpt-4o', input_tokens=1500, output_tokens=800)

    print(f"\nAgent state:")
    print(f"  - Messages: {len(agent.messages)}")
    print(f"  - API calls: {agent.cost_tracker.get_stats().total_calls}")
    print(f"  - Total cost: ${agent.cost_tracker.get_stats().total_cost:.6f}")

    # Create checkpoint
    checkpoint = agent.checkpoint()
    print(f"\n✓ Created checkpoint with {len(checkpoint['memory']['messages'])} messages")

    # Simulate agent restart
    agent2 = Agent.restore(checkpoint, config)

    print(f"\n✓ Agent restored:")
    print(f"  - Messages preserved: {len(agent2.messages)}")
    print(f"  - Cost data preserved: {agent2.cost_tracker.get_stats().total_calls} calls")
    print(f"  - Config preserved: {agent2.config.parallel_tool_execution=}")

    # Continue from where we left off
    agent2.add_message_to_history({'role': 'assistant', 'content': 'Processed successfully'})
    agent2.cost_tracker.record_call('gpt-4o', input_tokens=500, output_tokens=300)

    print(f"\n✓ Continued execution:")
    print(f"  - Total messages: {len(agent2.messages)}")
    print(f"  - Total API calls: {agent2.cost_tracker.get_stats().total_calls}")
    print(f"  - Total cost: ${agent2.cost_tracker.get_stats().total_cost:.6f}")


# ============================================================================
# Example 7: Cost Tracking for Production Budget Management
# ============================================================================

async def example_7_budget_management():
    """Example 7: Use cost tracking for budget management."""
    print("\n" + "="*70)
    print("Example 7: Budget Management with Cost Tracking")
    print("="*70)

    agent = Agent()

    # Set a budget
    BUDGET_LIMIT = 0.10  # $0.10

    print(f"Budget limit: ${BUDGET_LIMIT:.4f}")

    # Simulate conversation with budget tracking
    conversation_turns = [
        ('gpt-4o', 1000, 500),   # Turn 1
        ('gpt-4o', 1500, 800),   # Turn 2
        ('gpt-4o', 2000, 1000),  # Turn 3
        ('gpt-4o', 1200, 600),   # Turn 4
    ]

    for i, (model, input_tokens, output_tokens) in enumerate(conversation_turns, 1):
        agent.cost_tracker.record_call(model, input_tokens, output_tokens)
        stats = agent.get_cost_stats()

        print(f"\nTurn {i}:")
        print(f"  Tokens: {input_tokens + output_tokens:,}")
        print(f"  Cost this turn: ${stats.cost_by_model[model] / i:.6f}")
        print(f"  Total cost so far: ${stats.total_cost:.6f}")

        # Check budget
        if stats.total_cost > BUDGET_LIMIT:
            print(f"  ⚠️  BUDGET EXCEEDED! Stopping conversation.")
            break
        else:
            remaining = BUDGET_LIMIT - stats.total_cost
            print(f"  ✓ Remaining budget: ${remaining:.6f}")

    # Final summary
    print("\n" + agent.get_cost_summary())


# ============================================================================
# Example 8: Plan-First Strategy & Budgets
# ============================================================================

async def example_8_strategy_and_budgets():
    """Example 8: Combine plan-first strategies with budget enforcement."""
    print("\n" + "="*70)
    print("Example 8: Plan-First Strategy + Budget Guardrails")
    print("="*70)

    strategy = PlanAndSolveStrategy(
        plan_steps=["Assess the request", "Draft an approach", "Validate & report"],
        name="mission-plan",
    )
    config = AgentConfig(
        model=EchoModel(),
        reasoning_strategy=strategy,
        budget=AgentBudgetConfig(max_total_cost=0.0002, max_llm_calls=1),
    )
    agent = Agent(config=config)

    # Bootstrap the plan (demonstration only; production would use lifecycle hooks)
    context = ExecutionContext(inputs=NodeMessage(content={}, metadata={}), state=agent.state)
    await agent._ensure_strategy_plan(context)  # type: ignore[attr-defined]
    plan_snapshot = agent.state.get('strategy_plan', {})

    print("Generated plan:")
    for step in plan_snapshot.get('steps', []):
        print(f"  - {step['id']}: {step['description']} ({step['status']})")

    print("\nRecording budgeted LLM calls...")
    agent.cost_tracker.record_call('gpt-4o', input_tokens=100, output_tokens=50)
    try:
        agent.cost_tracker.record_call('gpt-4o', input_tokens=800, output_tokens=400)
    except AgentBudgetExceededError as exc:
        print(f"Budget enforcement triggered: {exc}")


# ============================================================================
# Example 9: Human Interaction Policies
# ============================================================================

async def example_9_human_policies():
    """Example 9: Require operator approvals and stop tokens."""
    print("\n" + "="*70)
    print("Example 9: Human Interaction Policies")
    print("="*70)

    policy = HumanInteractionPolicy(
        require_tool_approval=True,
        auto_approved_tools=['search_database'],
        stop_token='maintenance-window',
    )
    config = AgentConfig(
        model=EchoModel(),
        tools=[search_database, fetch_user_data, calculate_metrics],
        human_policy=policy,
    )
    agent = Agent(config=config)

    print("Requesting approval for 'calculate_metrics'...")
    try:
        agent.human_policy_manager.ensure_tool_allowed('calculate_metrics')
    except HumanApprovalRequired as exc:
        print(f"  Approval required: {exc}")

    print("Auto-approved tool access:")
    agent.human_policy_manager.ensure_tool_allowed('search_database')
    print("  ✓ search_database allowed without prompt")

    print("\nIssuing stop signal...")
    agent.pause("Scheduled maintenance")
    try:
        agent.human_policy_manager.ensure_not_stopped()
    except AgentStoppedError as exc:
        print(f"  Agent paused: {exc}")

    print("Clearing stop signal...")
    agent.resume()
    agent.human_policy_manager.ensure_not_stopped()
    print("  ✓ Agent resumed")


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("AGENT ENHANCEMENTS - PHASE 4 EXAMPLES")
    print("="*70)
    print("\nDemonstrating:")
    print("  1. Parallel Tool Execution")
    print("  2. Cost Tracking & Budget Guardrails")
    print("  3. Agent Checkpointing & Human Policies")

    await example_1_sequential()
    await example_2_parallel()
    await example_3_cost_tracking()
    await example_4_checkpointing()
    await example_5_checkpoint_file()
    await example_6_combined()
    await example_7_budget_management()
    await example_8_strategy_and_budgets()
    await example_9_human_policies()

    print("\n" + "="*70)
    print("ALL EXAMPLES COMPLETED SUCCESSFULLY!")
    print("="*70)
    print("\nPhase 4 Features Summary:")
    print("  ✓ Parallel Tool Execution - Improve performance")
    print("  ✓ Cost Tracking & Budgets - Monitor and enforce mission limits")
    print("  ✓ Agent Checkpointing - Save/restore state for resilience")
    print("  ✓ Human Policies - Require approvals and support stop/resume controls")
    print("\nThe agent system is now production-ready! 🚀")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
