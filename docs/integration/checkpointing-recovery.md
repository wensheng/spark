---
title: Checkpointing and Recovery
parent: Integration
nav_order: 6
---
# Checkpointing and Recovery

This guide covers checkpointing and recovery strategies for building resilient long-running workflows and agents that can recover from failures and interruptions.

## Table of Contents

- [Overview](#overview)
- [Graph Checkpointing](#graph-checkpointing)
- [Agent Checkpointing](#agent-checkpointing)
- [State Backend Selection](#state-backend-selection)
- [Recovery Strategies](#recovery-strategies)
- [Checkpoint Frequency Tuning](#checkpoint-frequency-tuning)
- [Testing Recovery](#testing-recovery)

## Overview

Checkpointing enables workflows and agents to save their state and resume from the last checkpoint after failures, restarts, or interruptions. This is essential for long-running processes and production resilience.

**Key Concepts**:
- **Graph Checkpoints**: Save complete graph execution state
- **Agent Checkpoints**: Save agent conversation and internal state
- **State Backends**: Persistent storage for checkpoints (memory, file, database)
- **Recovery**: Restore from checkpoints and continue execution

## Graph Checkpointing

Save and restore complete graph execution state:

### Basic Graph Checkpointing

```python
from spark.graphs import Graph, GraphCheckpoint
from spark.nodes import Node

class StatefulProcessingNode(Node):
    """Node that maintains processing state."""

    async def process(self, context):
        # Read from graph state
        processed_count = await context.graph_state.get('processed_count', 0)

        # Do work
        data = context.inputs.content.get('data')
        result = self.process_data(data)

        # Update state
        await context.graph_state.set('processed_count', processed_count + 1)

        return {'result': result}

# Create graph with checkpointing
graph = Graph(
    start=processing_node,
    enable_graph_state=True,
    initial_state={'processed_count': 0}
)

# Run with periodic checkpointing
for i in range(100):
    result = await graph.run({'data': f'item_{i}'})

    # Create checkpoint every 10 iterations
    if i % 10 == 0:
        checkpoint = graph.create_checkpoint()
        graph.save_checkpoint(f'checkpoint_{i}.json')
        print(f"Saved checkpoint at iteration {i}")

# Later: restore from checkpoint
graph = Graph.load_from_checkpoint('checkpoint_50.json')
# Continue from where we left off
```

### Auto-Checkpointing Configuration

Configure automatic checkpointing:

```python
from spark.graphs import Graph, CheckpointConfig

checkpoint_config = CheckpointConfig(
    enabled=True,
    strategy='iteration',  # or 'time', 'event'
    interval=10,           # Every 10 iterations
    backend='file',        # 'memory', 'file', 'database'
    path='./checkpoints',
    retention_count=5      # Keep last 5 checkpoints
)

graph = Graph(
    start=start_node,
    enable_graph_state=True,
    checkpoint_config=checkpoint_config
)

# Checkpoints created automatically during execution
result = await graph.run()

# Recovery is automatic on failure
try:
    result = await graph.run()
except Exception as e:
    print(f"Failure detected: {e}")
    # Graph automatically recovers from last checkpoint
    result = await graph.recover_and_continue()
```

### Manual Checkpoint Control

Fine-grained control over checkpointing:

```python
class CheckpointControlNode(Node):
    """Node that controls when checkpoints are created."""

    async def process(self, context):
        result = self.do_expensive_work(context.inputs.content)

        # Create checkpoint after expensive work
        if self.should_checkpoint(result):
            checkpoint_id = await context.create_checkpoint()
            print(f"Created checkpoint: {checkpoint_id}")

        return {'result': result}

    def should_checkpoint(self, result):
        """Decide if we should checkpoint."""
        # Checkpoint on significant milestones
        return result.get('milestone_reached', False)
```

### Checkpoint Contents

What gets saved in a graph checkpoint:

```python
checkpoint = {
    'version': '1.0',
    'timestamp': '2024-12-05T10:30:00Z',
    'graph_metadata': {
        'graph_id': 'production_workflow',
        'graph_version': '2.1.0',
        'execution_id': 'exec_123'
    },
    'graph_state': {
        # All GraphState contents
        'processed_count': 50,
        'accumulated_results': [...],
        'current_phase': 'processing'
    },
    'node_states': {
        'node1': {
            'context_snapshot': {...},
            'processing': False,
            'process_count': 50
        },
        'node2': {...}
    },
    'current_node': 'node2',  # Next node to execute
    'execution_history': [...]  # Execution trace
}
```

## Agent Checkpointing

Save and restore agent state for resilience:

### Basic Agent Checkpointing

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Create agent
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    name="ProductionAgent",
    system_prompt="You are a helpful assistant."
)

agent = Agent(config=config)

# Have conversation
agent.add_message_to_history({'role': 'user', 'content': 'Hello'})
result = await agent.run("Tell me about AI")
agent.add_message_to_history({'role': 'user', 'content': 'Tell me more'})
result = await agent.run("Explain in detail")

# Create checkpoint (in-memory)
checkpoint = agent.checkpoint()

# Save to file
agent.save_checkpoint('agent_state.json')

# Later: restore from file
agent2 = Agent.load_checkpoint('agent_state.json', config)

# Agent2 has complete conversation history
# and can continue seamlessly
result = await agent2.run("What were we discussing?")
# Agent remembers the full conversation about AI
```

### Agent Checkpoint Contents

```python
agent_checkpoint = {
    'version': '1.0',
    'timestamp': '2024-12-05T10:30:00Z',
    'config': {
        'name': 'ProductionAgent',
        'system_prompt': '...',
        'max_steps': 10,
        'parallel_tool_execution': True,
        # All agent configuration
    },
    'memory': {
        'messages': [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there!'},
            # Full conversation history
        ],
        'memory_policy': 'full'
    },
    'state': {
        'tool_traces': [...],
        'last_result': {...},
        'step_count': 5
    },
    'cost_tracking': {
        'calls': [
            {'model': 'gpt-4o', 'input_tokens': 100, 'output_tokens': 50},
            # All cost records
        ]
    },
    'strategy_state': {
        # Reasoning strategy state if applicable
        'react_history': [...]
    }
}
```

### Periodic Agent Checkpointing

Checkpoint agents during long-running operations:

```python
class CheckpointingAgentNode(Node):
    """Agent node with periodic checkpointing."""

    def __init__(
        self,
        agent: Agent,
        checkpoint_interval: int = 10,
        checkpoint_path: str = './agent_checkpoints',
        **kwargs
    ):
        super().__init__(**kwargs)
        self.agent = agent
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_path = checkpoint_path
        self.call_count = 0

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Run agent
        result = await self.agent.run(query)

        # Increment counter
        self.call_count += 1

        # Periodic checkpoint
        if self.call_count % self.checkpoint_interval == 0:
            checkpoint_file = f"{self.checkpoint_path}/agent_{self.call_count}.json"
            self.agent.save_checkpoint(checkpoint_file)
            print(f"Saved agent checkpoint: {checkpoint_file}")

        return {'response': result.output, 'call_count': self.call_count}

# Recovery
class RecoverableAgentNode(Node):
    """Agent that can recover from last checkpoint."""

    def __init__(self, agent_config, checkpoint_path, **kwargs):
        super().__init__(**kwargs)
        self.agent_config = agent_config
        self.checkpoint_path = checkpoint_path

        # Try to restore from latest checkpoint
        latest_checkpoint = self.find_latest_checkpoint()
        if latest_checkpoint:
            self.agent = Agent.load_checkpoint(latest_checkpoint, agent_config)
            print(f"Restored from checkpoint: {latest_checkpoint}")
        else:
            self.agent = Agent(config=agent_config)
            print("Starting fresh (no checkpoint found)")

    def find_latest_checkpoint(self):
        """Find most recent checkpoint file."""
        import glob
        checkpoints = glob.glob(f"{self.checkpoint_path}/agent_*.json")
        if checkpoints:
            return max(checkpoints, key=os.path.getmtime)
        return None
```

## State Backend Selection

Choose appropriate storage backend for checkpoints:

### Memory Backend (Development)

```python
# In-memory checkpoints (fast, but lost on restart)
checkpoint = graph.create_checkpoint()

# Pros: Very fast, no I/O
# Cons: Lost on process restart, high memory usage for large states
# Use for: Development, testing, short-lived processes
```

### File Backend (Single Instance)

```python
from spark.graphs.backends import FileBackend

# File-based checkpoints
backend = FileBackend(
    path='./checkpoints',
    format='json',  # or 'pickle'
    compression=True  # Compress checkpoints
)

graph = Graph(
    start=start_node,
    enable_graph_state=True,
    state_backend=backend
)

# Checkpoints persisted to disk
checkpoint_id = graph.create_checkpoint()
# Saved to: ./checkpoints/checkpoint_{id}.json.gz

# Pros: Persistent, simple, no external dependencies
# Cons: Not suitable for distributed systems, slower than memory
# Use for: Single-server deployments, long-running workflows
```

### Database Backend (Production)

```python
from spark.graphs.backends import SQLiteBackend, PostgreSQLBackend

# SQLite for single instance
sqlite_backend = SQLiteBackend(
    db_path='./checkpoints.db',
    table_name='graph_checkpoints'
)

# PostgreSQL for distributed systems
postgres_backend = PostgreSQLBackend(
    connection_string='postgresql://user:pass@host:5432/checkpoints',
    table_name='graph_checkpoints'
)

graph = Graph(
    start=start_node,
    enable_graph_state=True,
    state_backend=postgres_backend
)

# Checkpoints stored in database
checkpoint_id = graph.create_checkpoint()

# Query checkpoints
recent_checkpoints = await postgres_backend.list_checkpoints(
    graph_id='production_workflow',
    limit=10
)

# Pros: ACID guarantees, distributed access, queryable, scalable
# Cons: Requires database, network overhead
# Use for: Production, distributed systems, mission-critical workflows
```

### S3 Backend (Cloud)

```python
from spark.graphs.backends import S3Backend

# S3 for cloud deployments
s3_backend = S3Backend(
    bucket='my-checkpoints',
    prefix='workflows/',
    region='us-east-1'
)

graph = Graph(
    start=start_node,
    enable_graph_state=True,
    state_backend=s3_backend
)

# Checkpoints stored in S3
# s3://my-checkpoints/workflows/checkpoint_{id}.json

# Pros: Durable, scalable, serverless, cross-region
# Cons: Network latency, eventual consistency, costs
# Use for: Cloud deployments, serverless, cross-region recovery
```

## Recovery Strategies

Different strategies for recovering from failures:

### Automatic Recovery

```python
class AutoRecoveringGraph:
    """Graph that automatically recovers from failures."""

    def __init__(self, graph, max_retries=3):
        self.graph = graph
        self.max_retries = max_retries

    async def run_with_recovery(self, inputs):
        """Run with automatic recovery on failure."""
        for attempt in range(self.max_retries):
            try:
                # Try to run
                result = await self.graph.run(inputs)
                return result

            except Exception as e:
                print(f"Failure on attempt {attempt + 1}: {e}")

                if attempt < self.max_retries - 1:
                    # Recover from last checkpoint
                    last_checkpoint = self.graph.get_last_checkpoint()
                    if last_checkpoint:
                        print(f"Recovering from checkpoint: {last_checkpoint.id}")
                        self.graph.restore_from_checkpoint(last_checkpoint)
                    else:
                        print("No checkpoint available, restarting from beginning")
                else:
                    # Max retries exceeded
                    raise

# Usage
auto_graph = AutoRecoveringGraph(graph)
result = await auto_graph.run_with_recovery(inputs)
```

### Manual Recovery

```python
# Save checkpoint before risky operation
checkpoint_id = graph.create_checkpoint()

try:
    # Risky operation
    result = await graph.run_complex_workflow()

except Exception as e:
    print(f"Workflow failed: {e}")

    # Manually restore from checkpoint
    graph.restore_from_checkpoint(checkpoint_id)

    # Analyze failure
    failure_node = graph.get_current_node()
    print(f"Failed at node: {failure_node}")

    # Fix issue and retry
    graph.skip_node(failure_node)  # Skip problematic node
    result = await graph.continue_from_checkpoint()
```

### Progressive Recovery

```python
class ProgressiveRecoveryGraph:
    """Graph with progressive recovery strategy."""

    async def run_with_progressive_recovery(self, inputs):
        """Try multiple recovery strategies."""

        # Strategy 1: Try from last checkpoint
        try:
            last_checkpoint = self.graph.get_last_checkpoint()
            if last_checkpoint:
                self.graph.restore_from_checkpoint(last_checkpoint)
                return await self.graph.continue_from_checkpoint()
        except Exception as e:
            print(f"Recovery from last checkpoint failed: {e}")

        # Strategy 2: Try from earlier checkpoint
        try:
            earlier_checkpoint = self.graph.get_checkpoint(offset=2)
            if earlier_checkpoint:
                self.graph.restore_from_checkpoint(earlier_checkpoint)
                return await self.graph.continue_from_checkpoint()
        except Exception as e:
            print(f"Recovery from earlier checkpoint failed: {e}")

        # Strategy 3: Restart from beginning
        print("All recovery attempts failed, starting fresh")
        return await self.graph.run(inputs)
```

## Checkpoint Frequency Tuning

Balance checkpoint overhead with recovery granularity:

### Adaptive Checkpointing

```python
class AdaptiveCheckpointNode(Node):
    """Node with adaptive checkpointing frequency."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_checkpoint_time = time.time()
        self.operations_since_checkpoint = 0
        self.base_interval = 10

    async def process(self, context):
        result = self.do_work(context.inputs.content)

        self.operations_since_checkpoint += 1
        time_since_checkpoint = time.time() - self.last_checkpoint_time

        # Adaptive logic
        should_checkpoint = (
            # Time-based: every 60 seconds
            time_since_checkpoint > 60 or
            # Operation-based: every N operations (adaptive)
            self.operations_since_checkpoint >= self.get_checkpoint_interval(result) or
            # Event-based: on significant events
            result.get('significant_milestone', False)
        )

        if should_checkpoint:
            await context.create_checkpoint()
            self.last_checkpoint_time = time.time()
            self.operations_since_checkpoint = 0

        return result

    def get_checkpoint_interval(self, result):
        """Adapt interval based on operation characteristics."""
        # More frequent checkpoints for expensive operations
        if result.get('expensive', False):
            return self.base_interval // 2

        # Less frequent for cheap operations
        if result.get('cheap', False):
            return self.base_interval * 2

        return self.base_interval
```

### Cost-Benefit Analysis

```python
class CostAwareCheckpointing:
    """Checkpoint based on cost-benefit analysis."""

    def should_checkpoint(self, work_done, checkpoint_cost):
        """Decide if checkpointing is worth it."""

        # Estimate cost of redoing work if failure occurs
        redo_cost = work_done * self.failure_probability

        # Checkpoint if expected savings exceed checkpoint cost
        return redo_cost > checkpoint_cost

# Example usage
class SmartCheckpointNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.work_done_since_checkpoint = 0
        self.cost_analyzer = CostAwareCheckpointing()

    async def process(self, context):
        result = await self.expensive_operation()

        # Track work done
        self.work_done_since_checkpoint += result['cost']

        # Decide if we should checkpoint
        checkpoint_cost = 0.1  # Cost of creating checkpoint
        if self.cost_analyzer.should_checkpoint(
            self.work_done_since_checkpoint,
            checkpoint_cost
        ):
            await context.create_checkpoint()
            self.work_done_since_checkpoint = 0

        return result
```

## Testing Recovery

Comprehensive testing strategies for checkpointing:

### Unit Testing Checkpoints

```python
import pytest

@pytest.mark.asyncio
async def test_graph_checkpoint_restore():
    """Test graph checkpoint and restore."""

    # Create graph with state
    graph = Graph(
        start=stateful_node,
        enable_graph_state=True,
        initial_state={'counter': 0}
    )

    # Run a few iterations
    for i in range(5):
        await graph.run({'data': i})

    # Get state
    counter = graph.get_state_snapshot()['counter']
    assert counter == 5

    # Create checkpoint
    checkpoint = graph.create_checkpoint()

    # Continue execution
    for i in range(5, 10):
        await graph.run({'data': i})

    assert graph.get_state_snapshot()['counter'] == 10

    # Restore from checkpoint
    graph.restore_from_checkpoint(checkpoint)

    # State should be back to checkpoint
    assert graph.get_state_snapshot()['counter'] == 5

@pytest.mark.asyncio
async def test_agent_checkpoint_restore():
    """Test agent checkpoint and restore."""

    agent = Agent(config=config)

    # Have conversation
    agent.add_message_to_history({'role': 'user', 'content': 'Test'})
    assert len(agent.messages) == 1

    # Checkpoint
    checkpoint = agent.checkpoint()

    # Continue conversation
    agent.add_message_to_history({'role': 'assistant', 'content': 'Response'})
    assert len(agent.messages) == 2

    # Restore
    agent2 = Agent.restore(checkpoint, config)

    # Should have state from checkpoint
    assert len(agent2.messages) == 1
```

### Chaos Testing

```python
class ChaosTestingGraph:
    """Graph that randomly fails to test recovery."""

    def __init__(self, graph, failure_rate=0.1):
        self.graph = graph
        self.failure_rate = failure_rate

    async def run_with_chaos(self, inputs):
        """Run with random failures."""

        # Create checkpoint before starting
        checkpoint = self.graph.create_checkpoint()

        for attempt in range(10):
            try:
                # Inject random failures
                if random.random() < self.failure_rate:
                    raise Exception("Chaos monkey failure!")

                result = await self.graph.run(inputs)
                return result

            except Exception as e:
                print(f"Failure injected, recovering: {e}")
                # Recover from checkpoint
                self.graph.restore_from_checkpoint(checkpoint)

# Test recovery under chaos
chaos_graph = ChaosTestingGraph(graph, failure_rate=0.3)
result = await chaos_graph.run_with_chaos(inputs)
```

## Best Practices

1. **Checkpoint Early, Checkpoint Often**: For long-running workflows, checkpoint frequently
2. **Test Recovery**: Regularly test checkpoint/restore functionality
3. **Monitor Overhead**: Track checkpointing performance impact
4. **Version Checkpoints**: Include version info for compatibility
5. **Cleanup Old Checkpoints**: Implement retention policies
6. **Secure Checkpoints**: Encrypt checkpoints if they contain sensitive data
7. **Validate After Restore**: Verify state integrity after restore
8. **Idempotent Operations**: Design operations to be safely re-executed

## Related Documentation

- [Graph State](/docs/graphs/graph-state.md) - State management
- [Agent Checkpointing](/docs/agents/checkpointing.md) - Agent checkpoint reference
- [Production Deployment](/docs/best-practices/production.md) - Production patterns
- [Testing Strategies](/docs/best-practices/testing.md) - Testing approaches
