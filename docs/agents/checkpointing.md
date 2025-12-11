---
title: Agent Checkpointing
parent: Agent
nav_order: 6
---
# Agent Checkpointing
---

Agent checkpointing enables saving and restoring complete agent state, including configuration, conversation history, tool traces, cost tracking data, and reasoning strategy state. Checkpoints support:

- State persistence across sessions
- Error recovery and fault tolerance
- Debugging and inspection
- Testing with pre-configured states
- Long-running workflows with interruptions
- Cost tracking across sessions

## Agent Checkpoint Structure

### Checkpoint Contents

A checkpoint contains all agent state:

```python
{
    "config": {
        "model": {...},  # Model configuration
        "tools": [...],  # Tool specifications
        "system_prompt": "...",
        "output_mode": "text",
        "max_steps": 10,
        "memory_policy": "full",
        "reasoning_strategy": {...},
        "parallel_tool_execution": false,
        "enable_cost_tracking": true
    },
    "state": {
        "conversation_history": [...],  # All messages
        "tool_traces": [...],  # Tool execution history
        "last_result": "...",
        "last_error": null,
        "last_output": {...}
    },
    "cost_tracking": {
        "calls": [...],  # All API calls
        "total_cost": 0.0,
        "total_tokens": 0
    },
    "strategy_state": {...},  # Strategy-specific state
    "metadata": {
        "checkpoint_version": "1.0",
        "created_at": "2025-12-05T10:30:00Z",
        "spark_version": "2.0.0"
    }
}
```

### What's Saved

| Component | Content | Restored |
|-----------|---------|----------|
| Configuration | Model, tools, prompts, settings | ✅ |
| Conversation History | All user and assistant messages | ✅ |
| Tool Traces | Tool execution records | ✅ |
| Agent State | Last result, error, output | ✅ |
| Cost Tracking | All API calls and costs | ✅ |
| Strategy State | Reasoning history (ReAct, CoT, etc.) | ✅ |
| Metadata | Timestamp, versions | ✅ |

### What's Not Saved

- Tool implementations (only specifications)
- Model API credentials (security)
- Active connections or streams
- Temporary caches
- Runtime-only objects

## Creating Checkpoints

### In-Memory Checkpoints

Create checkpoints in memory without file I/O:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Create and use agent
model = OpenAIModel(model_id="gpt-4o")
agent = Agent()

await agent.run(user_message="My name is Alice.")
await agent.run(user_message="I like Python programming.")

# Create in-memory checkpoint
checkpoint = agent.checkpoint()

# checkpoint is a dictionary
print(f"Checkpoint keys: {checkpoint.keys()}")
print(f"History messages: {len(checkpoint['state']['conversation_history'])}")
```

### Use Cases for In-Memory Checkpoints

- Temporary state snapshots
- Testing and debugging
- State validation
- Passing state between systems
- Rollback points

### Checkpoint as Dictionary

```python
agent = Agent()
await agent.run(user_message="Hello")

# Get checkpoint dict
checkpoint = agent.checkpoint()

# Inspect checkpoint
print(f"System prompt: {checkpoint['config']['system_prompt']}")
print(f"Messages: {len(checkpoint['state']['conversation_history'])}")
print(f"Total cost: ${checkpoint['cost_tracking']['total_cost']:.4f}")

# Modify if needed
checkpoint['config']['max_steps'] = 5

# Restore modified checkpoint
restored = Agent.restore(checkpoint, config=None)  # Uses checkpoint config
```

## Saving to File

### Basic File Save

Save checkpoint to JSON file:

```python
from spark.agents import Agent

agent = Agent()

# Use agent
await agent.run(user_message="Hello")
await agent.run(user_message="How are you?")

# Save checkpoint to file
agent.save_checkpoint("agent_state.json")

# File created with complete state
```

### Custom File Path

```python
import os
from datetime import datetime

agent = Agent()
await agent.run(user_message="Hello")

# Create timestamped checkpoint
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
checkpoint_dir = "checkpoints"
os.makedirs(checkpoint_dir, exist_ok=True)

checkpoint_path = f"{checkpoint_dir}/agent_{timestamp}.json"
agent.save_checkpoint(checkpoint_path)

print(f"Checkpoint saved: {checkpoint_path}")
```

### Formatted Output

Control JSON formatting:

```python
import json

agent = Agent()
await agent.run(user_message="Hello")

# Get checkpoint
checkpoint = agent.checkpoint()

# Save with custom formatting
with open("agent_state.json", "w") as f:
    json.dump(checkpoint, f, indent=2, sort_keys=True)

# Or compact format
with open("agent_state_compact.json", "w") as f:
    json.dump(checkpoint, f, separators=(',', ':'))
```

## Loading from File

### Basic File Load

Load agent from checkpoint file:

```python
from spark.agents import Agent

# Load checkpoint and restore agent
agent = Agent.load_checkpoint("agent_state.json", config=None)

# Agent fully restored with conversation history
result = await agent.run(user_message="What did I ask before?")
# Agent remembers previous conversation
```

### Load with Custom Config

Override config when loading:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Create new config
new_model = OpenAIModel(model_id="gpt-4o-mini")  # Different model
new_config = AgentConfig(
    model=new_model,
    max_steps=20  # Different settings
)

# Load checkpoint but use new config
agent = Agent.load_checkpoint(
    "agent_state.json",
    config=new_config  # Override checkpoint config
)

# Agent has checkpoint state but new config
```

### Error Handling

Handle checkpoint loading errors:

```python
from spark.agents import Agent
import json

try:
    agent = Agent.load_checkpoint("agent_state.json")
except FileNotFoundError:
    print("Checkpoint file not found")
    agent = Agent()  # Create new agent
except json.JSONDecodeError:
    print("Invalid checkpoint format")
    agent = Agent()
except Exception as e:
    print(f"Error loading checkpoint: {e}")
    agent = Agent()
```

## Restoring Agents from Checkpoints

### Basic Restore

Restore from in-memory checkpoint:

```python
from spark.agents import Agent

# Original agent
agent1 = Agent()
await agent1.run(user_message="My name is Bob.")

# Create checkpoint
checkpoint = agent1.checkpoint()

# Restore to new agent
agent2 = Agent.restore(checkpoint, config=None)

# agent2 has same state as agent1
result = await agent2.run(user_message="What's my name?")
print(result)  # "Your name is Bob."
```

### Restore with Config

Provide config when restoring:

```python
from spark.agents import Agent, AgentConfig

# Get checkpoint
checkpoint = agent1.checkpoint()

# Create config for restored agent
config = AgentConfig(
    model=model,
    max_steps=15,
    # ... other settings
)

# Restore with config
agent2 = Agent.restore(checkpoint, config=config)
```

### Restore vs Load

**restore()**: From in-memory checkpoint dictionary
**load_checkpoint()**: From file path

```python
# From memory
checkpoint_dict = agent.checkpoint()
restored = Agent.restore(checkpoint_dict, config=None)

# From file
loaded = Agent.load_checkpoint("agent_state.json", config=None)

# Both equivalent if checkpoint came from file
```

## Conversation History Persistence

### Complete History Preserved

All conversation messages are saved:

```python
from spark.agents import Agent

agent = Agent()

# Multiple exchanges
await agent.run(user_message="My favorite color is blue.")
await agent.run(user_message="I work in AI research.")
await agent.run(user_message="I like hiking.")

# Save checkpoint
agent.save_checkpoint("session.json")

# Later: restore
agent2 = Agent.load_checkpoint("session.json")

# All context preserved
result = await agent2.run(user_message="What's my favorite color and hobby?")
print(result)  # "Your favorite color is blue and you like hiking."
```

### Message Format Preserved

Complete message structure saved:

```python
# Original agent with tool calls
agent1 = Agent(config=AgentConfig(
    model=model,
    tools=[search_tool]
))

await agent1.run(user_message="Search for Python tutorials")

# Checkpoint includes tool call messages
checkpoint = agent1.checkpoint()
history = checkpoint['state']['conversation_history']

for msg in history:
    print(f"Role: {msg['role']}")
    for item in msg['content']:
        if 'text' in item:
            print(f"  Text: {item['text'][:50]}")
        elif 'toolUse' in item:
            print(f"  Tool: {item['toolUse']['name']}")
        elif 'toolResult' in item:
            print(f"  Result: {item['toolResult']['toolUseId']}")
```

## Cost Tracking Persistence

### Complete Cost Data Saved

All cost tracking information persists:

```python
from spark.agents import Agent

agent = Agent()

# Use agent
for i in range(10):
    await agent.run(user_message=f"Question {i}")

# Check cost
stats1 = agent.get_cost_stats()
print(f"Session cost: ${stats1.total_cost:.4f}")

# Save checkpoint
agent.save_checkpoint("agent_with_costs.json")

# Later: restore
agent2 = Agent.load_checkpoint("agent_with_costs.json")

# Cost data preserved
stats2 = agent2.get_cost_stats()
print(f"Restored cost: ${stats2.total_cost:.4f}")
assert stats1.total_cost == stats2.total_cost
```

### Aggregating Costs Across Checkpoints

```python
import json
from spark.agents import Agent

# Multiple checkpoint files
checkpoint_files = [
    "session1.json",
    "session2.json",
    "session3.json"
]

total_cost = 0.0
total_tokens = 0

for checkpoint_file in checkpoint_files:
    # Load checkpoint
    with open(checkpoint_file) as f:
        checkpoint = json.load(f)

    # Extract cost data
    cost_data = checkpoint['cost_tracking']
    total_cost += cost_data['total_cost']
    total_tokens += cost_data['total_tokens']

print(f"Total across sessions: ${total_cost:.4f}")
print(f"Total tokens: {total_tokens:,}")
```

## Strategy State Persistence

### ReAct Strategy State

ReAct reasoning history preserved:

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True),
    tools=[search_tool]
)

agent = Agent(config=config)

# Use ReAct strategy
await agent.run(user_message="Search for Python and analyze results")

# ReAct history stored in tool_traces
traces = agent._state.tool_traces
print(f"Reasoning steps: {len(traces)}")

# Save checkpoint
agent.save_checkpoint("react_agent.json")

# Restore
agent2 = Agent.load_checkpoint("react_agent.json", config=config)

# Reasoning history preserved
restored_traces = agent2._state.tool_traces
print(f"Restored steps: {len(restored_traces)}")
```

### Plan-and-Solve Strategy State

Plan execution state preserved:

```python
from spark.agents import Agent, AgentConfig, PlanAndSolveStrategy

config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=PlanAndSolveStrategy(
        max_plan_steps=10,
        allow_replanning=True
    ),
    tools=[...]
)

agent = Agent(config=config)

# Create and partially execute plan
await agent.run(user_message="Order 30 units of Product A")

# Save during execution
agent.save_checkpoint("plan_in_progress.json")

# Later: restore and continue
agent2 = Agent.load_checkpoint("plan_in_progress.json", config=config)

# Can continue from where it left off
```

## Use Cases and Patterns

### Long-Running Workflows

Checkpoint periodically for fault tolerance:

```python
from spark.agents import Agent
import asyncio

agent = Agent()

async def long_running_workflow():
    """Long workflow with checkpointing."""
    tasks = ["task1", "task2", "task3", "task4", "task5"]

    for i, task in enumerate(tasks):
        # Execute task
        result = await agent.run(user_message=f"Execute {task}")

        # Checkpoint after each task
        agent.save_checkpoint(f"checkpoint_step_{i}.json")
        print(f"Checkpoint saved after {task}")

        # Simulate delay
        await asyncio.sleep(1)

    return "Workflow complete"

# Run workflow
result = await long_running_workflow()

# If interrupted, resume from last checkpoint
# agent = Agent.load_checkpoint("checkpoint_step_2.json")
```

### Error Recovery

Recover from errors using checkpoints:

```python
from spark.agents import Agent, AgentError

agent = Agent()

try:
    # Checkpoint before risky operation
    checkpoint = agent.checkpoint()

    # Risky operation
    result = await agent.run(user_message="Complex operation that might fail")

except AgentError as e:
    print(f"Error occurred: {e}")

    # Restore from checkpoint
    agent = Agent.restore(checkpoint, config=agent.config)
    print("Agent state restored")

    # Retry or alternative approach
    result = await agent.run(user_message="Simpler alternative operation")
```

### Debugging and Inspection

Use checkpoints for debugging:

```python
from spark.agents import Agent
import json

agent = Agent()

# Execute and capture state
await agent.run(user_message="Complex query")

# Save checkpoint for debugging
agent.save_checkpoint("debug_checkpoint.json")

# Inspect checkpoint
with open("debug_checkpoint.json") as f:
    checkpoint = json.load(f)

# Analyze state
print("=== Debug Analysis ===")
print(f"Messages: {len(checkpoint['state']['conversation_history'])}")
print(f"Tool calls: {len(checkpoint['state']['tool_traces'])}")
print(f"Cost: ${checkpoint['cost_tracking']['total_cost']:.4f}")

# Print last few messages
history = checkpoint['state']['conversation_history']
for msg in history[-3:]:
    print(f"\n{msg['role']}: {msg['content'][0].get('text', 'N/A')[:100]}")
```

### Testing with Pre-configured States

Create test fixtures from checkpoints:

```python
import pytest
from spark.agents import Agent

# Create checkpoint with specific state
def create_test_checkpoint():
    """Create checkpoint for testing."""
    agent = Agent()

    # Set up specific state
    agent.add_message_to_history({
        "role": "user",
        "content": [{"text": "My name is Test User."}]
    })
    agent.add_message_to_history({
        "role": "assistant",
        "content": [{"text": "Hello, Test User!"}]
    })

    # Save test checkpoint
    agent.save_checkpoint("test_fixture.json")

# Use in tests
@pytest.mark.asyncio
async def test_agent_with_context():
    """Test agent with pre-configured context."""
    # Load test fixture
    agent = Agent.load_checkpoint("test_fixture.json")

    # Test with context
    result = await agent.run(user_message="What's my name?")
    assert "Test User" in result
```

### Multi-Session Continuity

Maintain continuity across sessions:

```python
from spark.agents import Agent
import os

SESSION_CHECKPOINT = "current_session.json"

def start_session():
    """Start or resume session."""
    if os.path.exists(SESSION_CHECKPOINT):
        # Resume existing session
        agent = Agent.load_checkpoint(SESSION_CHECKPOINT)
        print("Session resumed")
    else:
        # Start new session
        agent = Agent()
        print("New session started")

    return agent

def end_session(agent):
    """End session and save state."""
    agent.save_checkpoint(SESSION_CHECKPOINT)
    print("Session saved")

# Usage
agent = start_session()

# Use agent
await agent.run(user_message="Hello")
await agent.run(user_message="Tell me about Python")

# End session
end_session(agent)

# Later: resume
agent = start_session()
result = await agent.run(user_message="What did we discuss?")
# Agent remembers previous session
```

### Checkpoint Versioning

Implement checkpoint versioning:

```python
from spark.agents import Agent
from datetime import datetime
import os

class VersionedCheckpointManager:
    """Manage versioned checkpoints."""

    def __init__(self, agent_id: str, checkpoint_dir: str = "checkpoints"):
        self.agent_id = agent_id
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

    def save(self, agent: Agent, version: str = None):
        """Save versioned checkpoint."""
        if version is None:
            version = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{self.agent_id}_{version}.json"
        filepath = os.path.join(self.checkpoint_dir, filename)

        agent.save_checkpoint(filepath)
        print(f"Saved checkpoint: {filename}")

        return filepath

    def load_latest(self) -> Agent:
        """Load most recent checkpoint."""
        files = [f for f in os.listdir(self.checkpoint_dir)
                if f.startswith(self.agent_id)]

        if not files:
            raise FileNotFoundError("No checkpoints found")

        # Sort by timestamp (in filename)
        latest = sorted(files)[-1]
        filepath = os.path.join(self.checkpoint_dir, latest)

        print(f"Loading checkpoint: {latest}")
        return Agent.load_checkpoint(filepath)

    def load_version(self, version: str) -> Agent:
        """Load specific version."""
        filename = f"{self.agent_id}_{version}.json"
        filepath = os.path.join(self.checkpoint_dir, filename)

        return Agent.load_checkpoint(filepath)

# Usage
manager = VersionedCheckpointManager(agent_id="my_agent")

agent = Agent()
await agent.run(user_message="Hello")

# Save v1
manager.save(agent, version="v1")

await agent.run(user_message="More conversation")

# Save v2
manager.save(agent, version="v2")

# Load latest
agent_latest = manager.load_latest()

# Load specific version
agent_v1 = manager.load_version("v1")
```

## Best Practices

### 1. Regular Checkpointing

Checkpoint at logical points:

```python
agent = Agent()

# Checkpoint after important milestones
await agent.run(user_message="Complete step 1")
agent.save_checkpoint("after_step1.json")

await agent.run(user_message="Complete step 2")
agent.save_checkpoint("after_step2.json")
```

### 2. Descriptive Checkpoint Names

Use meaningful names:

```python
# Good
agent.save_checkpoint("customer_session_user123_20251205.json")
agent.save_checkpoint("workflow_completed_v1.json")

# Avoid
agent.save_checkpoint("checkpoint1.json")
agent.save_checkpoint("temp.json")
```

### 3. Checkpoint Cleanup

Remove old checkpoints:

```python
import os
import time

def cleanup_old_checkpoints(directory: str, max_age_days: int = 7):
    """Remove checkpoints older than max_age_days."""
    now = time.time()
    max_age_seconds = max_age_days * 86400

    for filename in os.listdir(directory):
        if not filename.endswith('.json'):
            continue

        filepath = os.path.join(directory, filename)
        age = now - os.path.getmtime(filepath)

        if age > max_age_seconds:
            os.remove(filepath)
            print(f"Removed old checkpoint: {filename}")

# Cleanup weekly
cleanup_old_checkpoints("checkpoints", max_age_days=7)
```

### 4. Validate Checkpoints

Validate before using:

```python
import json

def validate_checkpoint(filepath: str) -> bool:
    """Validate checkpoint file."""
    try:
        with open(filepath) as f:
            checkpoint = json.load(f)

        # Check required keys
        required = ['config', 'state', 'cost_tracking', 'metadata']
        if not all(key in checkpoint for key in required):
            return False

        # Check version
        if 'checkpoint_version' not in checkpoint['metadata']:
            return False

        return True

    except Exception as e:
        print(f"Validation error: {e}")
        return False

# Use validation
if validate_checkpoint("agent_state.json"):
    agent = Agent.load_checkpoint("agent_state.json")
else:
    print("Invalid checkpoint, creating new agent")
    agent = Agent()
```

### 5. Secure Checkpoint Storage

Handle checkpoints securely:

```python
import json
import os
from pathlib import Path

def save_secure_checkpoint(agent: Agent, filepath: str):
    """Save checkpoint with secure permissions."""
    # Get checkpoint
    checkpoint = agent.checkpoint()

    # Remove sensitive data if needed
    if 'api_key' in checkpoint.get('config', {}):
        del checkpoint['config']['api_key']

    # Save with restricted permissions
    with open(filepath, 'w') as f:
        json.dump(checkpoint, f, indent=2)

    # Set secure permissions (Unix)
    os.chmod(filepath, 0o600)  # Only owner can read/write

# Usage
save_secure_checkpoint(agent, "secure_checkpoint.json")
```

## Testing Checkpoints

### Unit Tests

```python
import pytest
from spark.agents import Agent

def test_checkpoint_creation():
    """Test checkpoint creation."""
    agent = Agent()

    # Create checkpoint
    checkpoint = agent.checkpoint()

    # Verify structure
    assert 'config' in checkpoint
    assert 'state' in checkpoint
    assert 'cost_tracking' in checkpoint
    assert 'metadata' in checkpoint

@pytest.mark.asyncio
async def test_checkpoint_restore():
    """Test checkpoint restore."""
    # Original agent
    agent1 = Agent()
    await agent1.run(user_message="Hello")

    # Checkpoint and restore
    checkpoint = agent1.checkpoint()
    agent2 = Agent.restore(checkpoint, config=None)

    # Verify history preserved
    history1 = agent1.get_history()
    history2 = agent2.get_history()
    assert len(history1) == len(history2)

def test_file_checkpoint():
    """Test file save/load."""
    import tempfile
    import os

    agent = Agent()

    # Save to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name

    try:
        agent.save_checkpoint(temp_path)
        assert os.path.exists(temp_path)

        # Load
        agent2 = Agent.load_checkpoint(temp_path)
        assert agent2 is not None

    finally:
        os.remove(temp_path)
```

## Next Steps

- Review [Agent Fundamentals](fundamentals.md) for general agent usage
- See [Cost Tracking Reference](cost-tracking.md) for cost data persistence
- Learn about [Memory Management](memory.md) for conversation history
- Explore [Error Handling](error-handling.md) for error recovery patterns
