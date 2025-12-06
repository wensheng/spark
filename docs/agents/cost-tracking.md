---
title: Cost Tracking Reference
parent: Agent
nav_order: 5
---
# Cost Tracking Reference

This reference covers Spark's built-in cost tracking system for monitoring token usage and API costs in agent operations.

## Overview

Every Spark agent includes automatic cost tracking for LLM API calls. The cost tracking system monitors:

- Input tokens per call
- Output tokens per call
- Total tokens across all calls
- Estimated API costs based on model pricing
- Call counts and breakdowns by model
- Aggregated statistics

Cost tracking is enabled by default and requires no additional configuration.

## CostTracker Overview

The `CostTracker` class manages cost tracking for agents:

```python
from spark.agents.cost_tracker import CostTracker

# Create tracker (usually automatic)
tracker = CostTracker()

# Record API call
tracker.record_call(
    model_id="gpt-4o",
    input_tokens=1500,
    output_tokens=800
)

# Get statistics
stats = tracker.get_stats()
print(f"Total cost: ${stats.total_cost:.4f}")
print(f"Total tokens: {stats.total_tokens:,}")
```

### CostTracker Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `record_call(model_id, input_tokens, output_tokens)` | Record API call | `None` |
| `get_stats(model_filter=None)` | Get cost statistics | `CostStats` |
| `get_calls(model_filter=None)` | Get all recorded calls | `List[CallRecord]` |
| `get_summary(model_filter=None)` | Get formatted summary | `str` |
| `reset()` | Clear all records | `None` |
| `reload_pricing(config_path)` | Reload pricing config | `None` |

## Recording API Calls

### Automatic Recording

Agents automatically record all API calls:

```python
from spark.agents import Agent
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
agent = Agent()

# API calls automatically recorded
result = await agent.run(user_message="Hello, how are you?")

# Get cost stats
stats = agent.get_cost_stats()
print(f"Tokens used: {stats.total_tokens:,}")
print(f"Cost: ${stats.total_cost:.4f}")
```

### Manual Recording

Record calls manually if needed:

```python
from spark.agents import Agent

agent = Agent()

# Manually record call
agent.cost_tracker.record_call(
    model_id="gpt-4o",
    input_tokens=1000,
    output_tokens=500
)

# Get updated stats
stats = agent.get_cost_stats()
```

### Recording Custom Models

Record calls for custom or non-standard models:

```python
agent.cost_tracker.record_call(
    model_id="custom-model-v1",
    input_tokens=2000,
    output_tokens=1000
)

# Uses default pricing if model not in config
stats = agent.get_cost_stats()
```

## Pricing Configuration

### Default Pricing

CostTracker includes default pricing for common models:

```python
# Default prices (per 1M tokens in USD)
DEFAULT_PRICING = {
    "openai": {
        "gpt-4o": {"input": 5.00, "output": 15.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    },
    "anthropic": {
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
    },
    "default": {"input": 5.00, "output": 15.00}
}
```

### Custom Pricing Configuration

Create custom pricing configuration file:

**model_pricing.json**:
```json
{
  "openai": {
    "gpt-4o": {
      "input": 5.00,
      "output": 15.00
    },
    "gpt-4o-mini": {
      "input": 0.15,
      "output": 0.60
    }
  },
  "anthropic": {
    "claude-sonnet-4-5": {
      "input": 3.00,
      "output": 15.00
    }
  },
  "aws": {
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {
      "input": 3.00,
      "output": 15.00
    }
  },
  "custom": {
    "my-model-v1": {
      "input": 2.50,
      "output": 10.00
    }
  },
  "default": {
    "input": 5.00,
    "output": 15.00
  }
}
```

**Note**: All prices are per 1 million tokens in USD.

### Loading Custom Pricing

CostTracker searches for pricing config in this order:

1. `SPARK_PRICING_CONFIG` environment variable path
2. `./model_pricing.json` (current directory)
3. `~/.spark/model_pricing.json` (user home directory)
4. `spark/agents/model_pricing.json` (package default)
5. Hardcoded fallback values

```bash
# Set custom pricing config location
export SPARK_PRICING_CONFIG=/path/to/my_pricing.json

# Run application
python my_app.py
```

### Reloading Pricing at Runtime

```python
from spark.agents.cost_tracker import CostTracker

tracker = CostTracker()

# Load custom pricing
tracker.reload_pricing("/path/to/updated_pricing.json")

# Future calls use new pricing
tracker.record_call("gpt-4o", 1000, 500)
```

### Creating Pricing Config Programmatically

```python
import json

pricing_config = {
    "openai": {
        "gpt-4o": {"input": 5.00, "output": 15.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60}
    },
    "default": {"input": 5.00, "output": 15.00}
}

# Save to file
with open("my_pricing.json", "w") as f:
    json.dump(pricing_config, f, indent=2)

# Use with tracker
tracker = CostTracker(pricing_config_path="my_pricing.json")
```

## Getting Cost Statistics

### CostStats Object

Cost statistics are returned as `CostStats` dataclass:

```python
from dataclasses import dataclass

@dataclass
class CostStats:
    """Cost tracking statistics."""
    total_calls: int  # Total API calls
    total_input_tokens: int  # Total input tokens
    total_output_tokens: int  # Total output tokens
    total_tokens: int  # Total tokens (input + output)
    total_cost: float  # Total cost in USD
    model_breakdown: Dict[str, Dict[str, any]]  # Per-model breakdown
```

### Basic Statistics

```python
from spark.agents import Agent

agent = Agent()

# Use agent
await agent.run(user_message="Hello")
await agent.run(user_message="Tell me about Python")

# Get statistics
stats = agent.get_cost_stats()

print(f"Total calls: {stats.total_calls}")
print(f"Total tokens: {stats.total_tokens:,}")
print(f"Input tokens: {stats.total_input_tokens:,}")
print(f"Output tokens: {stats.total_output_tokens:,}")
print(f"Total cost: ${stats.total_cost:.4f}")
```

### Model Breakdown

Get per-model statistics:

```python
stats = agent.get_cost_stats()

# Iterate model breakdown
for model_id, model_stats in stats.model_breakdown.items():
    print(f"\nModel: {model_id}")
    print(f"  Calls: {model_stats['calls']}")
    print(f"  Tokens: {model_stats['total_tokens']:,}")
    print(f"  Cost: ${model_stats['cost']:.4f}")
```

### Filtering by Model

Get statistics for specific model:

```python
from spark.agents import Agent

agent = Agent()

# Use agent...

# Filter by model
gpt4_stats = agent.get_cost_stats(model_filter="gpt-4o")
print(f"GPT-4o cost: ${gpt4_stats.total_cost:.4f}")

mini_stats = agent.get_cost_stats(model_filter="gpt-4o-mini")
print(f"GPT-4o-mini cost: ${mini_stats.total_cost:.4f}")
```

## Cost Summaries and Reports

### Formatted Summary

Get human-readable summary:

```python
from spark.agents import Agent

agent = Agent()

# Use agent
for i in range(10):
    await agent.run(user_message=f"Question {i}")

# Get formatted summary
summary = agent.get_cost_summary()
print(summary)

# Output:
# Cost Tracking Summary
# ====================
# Total Calls: 10
# Total Tokens: 15,234 (Input: 8,123, Output: 7,111)
# Total Cost: $0.1823
#
# Model Breakdown:
# - gpt-4o: 10 calls, 15,234 tokens, $0.1823
```

### Custom Reporting

Create custom reports from call records:

```python
from spark.agents import Agent

agent = Agent()

# Use agent...

# Get all call records
calls = agent.cost_tracker.get_calls()

# Custom analysis
total_calls = len(calls)
avg_input = sum(c.input_tokens for c in calls) / total_calls
avg_output = sum(c.output_tokens for c in calls) / total_calls

print(f"Average input tokens: {avg_input:.1f}")
print(f"Average output tokens: {avg_output:.1f}")

# Find most expensive call
most_expensive = max(calls, key=lambda c: c.cost)
print(f"Most expensive call: ${most_expensive.cost:.4f}")
```

### Call Record Structure

```python
from dataclasses import dataclass

@dataclass
class CallRecord:
    """Record of single API call."""
    model_id: str  # Model identifier
    input_tokens: int  # Input tokens
    output_tokens: int  # Output tokens
    cost: float  # Estimated cost
    timestamp: float  # Unix timestamp
```

### Exporting Call Records

Export call records for analysis:

```python
import json
from datetime import datetime

agent = Agent()

# Use agent...

# Get call records
calls = agent.cost_tracker.get_calls()

# Convert to exportable format
export_data = [
    {
        "model_id": call.model_id,
        "input_tokens": call.input_tokens,
        "output_tokens": call.output_tokens,
        "cost": call.cost,
        "timestamp": datetime.fromtimestamp(call.timestamp).isoformat()
    }
    for call in calls
]

# Save to JSON
with open("cost_report.json", "w") as f:
    json.dump(export_data, f, indent=2)
```

## Resetting Cost Tracking

### Clear All Records

```python
from spark.agents import Agent

agent = Agent()

# Use agent
await agent.run(user_message="Hello")

# Get stats
stats = agent.get_cost_stats()
print(f"Cost: ${stats.total_cost:.4f}")

# Reset tracking
agent.reset_cost_tracking()

# Stats now zero
stats = agent.get_cost_stats()
print(f"Cost after reset: ${stats.total_cost:.4f}")  # $0.0000
```

### Reset Between Sessions

```python
agent = Agent()

# Session 1
for i in range(10):
    await agent.run(user_message=f"Query {i}")

session1_cost = agent.get_cost_stats().total_cost
print(f"Session 1 cost: ${session1_cost:.4f}")

# Reset for session 2
agent.reset_cost_tracking()

# Session 2
for i in range(5):
    await agent.run(user_message=f"Query {i}")

session2_cost = agent.get_cost_stats().total_cost
print(f"Session 2 cost: ${session2_cost:.4f}")
```

## Cost Tracking with Checkpoints

### Saving Cost Data

Cost tracking data is automatically included in checkpoints:

```python
from spark.agents import Agent

agent = Agent()

# Use agent
await agent.run(user_message="Hello")

# Save checkpoint (includes cost data)
agent.save_checkpoint("agent_state.json")

# Restore in new session
restored_agent = Agent.load_checkpoint("agent_state.json", config=agent.config)

# Cost data restored
stats = restored_agent.get_cost_stats()
print(f"Restored cost: ${stats.total_cost:.4f}")
```

### Aggregating Costs Across Sessions

```python
import json

# Load multiple checkpoints and aggregate costs
total_cost = 0.0
total_tokens = 0

checkpoint_files = ["session1.json", "session2.json", "session3.json"]

for checkpoint_file in checkpoint_files:
    agent = Agent.load_checkpoint(checkpoint_file, config=config)
    stats = agent.get_cost_stats()

    total_cost += stats.total_cost
    total_tokens += stats.total_tokens

print(f"Total across all sessions: ${total_cost:.4f}")
print(f"Total tokens: {total_tokens:,}")
```

## Monitoring and Alerts

### Cost Thresholds

Implement cost monitoring and alerts:

```python
from spark.agents import Agent

agent = Agent()
cost_threshold = 1.00  # $1.00 limit

async def run_with_monitoring(message: str):
    """Run agent with cost monitoring."""
    result = await agent.run(user_message=message)

    # Check cost
    stats = agent.get_cost_stats()
    if stats.total_cost > cost_threshold:
        print(f"Warning: Cost threshold exceeded: ${stats.total_cost:.4f}")
        # Take action (alert, stop, etc.)

    return result

# Use monitored execution
result = await run_with_monitoring("Complex query")
```

### Per-Call Cost Tracking

Track cost for individual operations:

```python
from spark.agents import Agent

agent = Agent()

async def track_operation_cost(operation_name: str, message: str):
    """Track cost for specific operation."""
    # Get baseline
    baseline_stats = agent.get_cost_stats()
    baseline_cost = baseline_stats.total_cost

    # Execute operation
    result = await agent.run(user_message=message)

    # Calculate operation cost
    updated_stats = agent.get_cost_stats()
    operation_cost = updated_stats.total_cost - baseline_cost

    print(f"{operation_name} cost: ${operation_cost:.4f}")
    return result

# Track operations
await track_operation_cost("Search", "Search for Python tutorials")
await track_operation_cost("Analyze", "Analyze the results")
```

### Budget Enforcement

Enforce budget limits:

```python
from spark.agents import Agent

class BudgetEnforcedAgent:
    """Agent with budget enforcement."""

    def __init__(self, config, budget: float):
        self.agent = Agent(config=config)
        self.budget = budget

    async def run(self, user_message: str):
        """Run with budget check."""
        # Check budget before execution
        stats = self.agent.get_cost_stats()
        if stats.total_cost >= self.budget:
            raise RuntimeError(f"Budget exceeded: ${stats.total_cost:.4f} >= ${self.budget:.2f}")

        # Execute
        result = await self.agent.run(user_message=user_message)

        # Verify still under budget
        stats = self.agent.get_cost_stats()
        if stats.total_cost > self.budget:
            print(f"Warning: Budget exceeded during execution: ${stats.total_cost:.4f}")

        return result

# Use budget-enforced agent
budget_agent = BudgetEnforcedAgent(config=config, budget=5.00)
result = await budget_agent.run("Query")
```

## Cost Optimization

### Model Selection

Choose cost-effective models:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Cost comparison
models = {
    "premium": OpenAIModel(model_id="gpt-4o"),
    "standard": OpenAIModel(model_id="gpt-4o-mini")
}

results = {}
for name, model in models.items():
    agent = Agent(config=AgentConfig(model=model))
    result = await agent.run(user_message="What is 2+2?")

    stats = agent.get_cost_stats()
    results[name] = {
        "cost": stats.total_cost,
        "tokens": stats.total_tokens,
        "result": result
    }

# Compare
for name, data in results.items():
    print(f"{name}: ${data['cost']:.4f}, {data['tokens']} tokens")

# Output:
# premium: $0.0002, 150 tokens
# standard: $0.0000, 150 tokens (96% cheaper)
```

### Caching for Cost Reduction

Use response caching to reduce API calls:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Enable caching
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

agent = Agent(config=AgentConfig(model=model))

# First call - hits API
result1 = await agent.run(user_message="What is Python?")
stats1 = agent.get_cost_stats()
print(f"First call cost: ${stats1.total_cost:.4f}")

# Reset cost tracking
agent.reset_cost_tracking()

# Second call - cache hit (free!)
result2 = await agent.run(user_message="What is Python?")
stats2 = agent.get_cost_stats()
print(f"Second call cost: ${stats2.total_cost:.4f}")  # $0.0000

# Savings: 100%
```

### Token Optimization

Monitor token usage patterns:

```python
agent = Agent()

# Track token efficiency
async def analyze_token_usage():
    """Analyze token usage patterns."""
    test_queries = [
        "What is Python?",  # Short
        "Explain Python programming in detail.",  # Medium
        "Write a comprehensive guide to Python...",  # Long
    ]

    for query in test_queries:
        agent.reset_cost_tracking()
        result = await agent.run(user_message=query)

        stats = agent.get_cost_stats()
        efficiency = len(result) / stats.total_tokens if stats.total_tokens > 0 else 0

        print(f"\nQuery length: {len(query)}")
        print(f"Tokens used: {stats.total_tokens}")
        print(f"Response length: {len(result)}")
        print(f"Efficiency: {efficiency:.2f} chars/token")

await analyze_token_usage()
```

## Production Best Practices

### 1. Always Enable Cost Tracking

Cost tracking is enabled by default:

```python
from spark.agents import Agent, AgentConfig

# Cost tracking automatically enabled
config = AgentConfig(
    model=model,
    enable_cost_tracking=True  # Default
)

agent = Agent(config=config)
```

### 2. Monitor Costs in Production

Implement monitoring:

```python
import logging

logger = logging.getLogger(__name__)

async def monitored_agent_call(agent, message):
    """Execute agent call with monitoring."""
    result = await agent.run(user_message=message)

    stats = agent.get_cost_stats()

    # Log costs
    logger.info(
        f"Agent call completed. "
        f"Tokens: {stats.total_tokens:,}, "
        f"Cost: ${stats.total_cost:.4f}"
    )

    # Alert on high cost
    if stats.total_cost > 0.10:
        logger.warning(f"High cost detected: ${stats.total_cost:.4f}")

    return result
```

### 3. Set Budget Limits

Always set budget limits:

```python
DAILY_BUDGET = 100.00  # $100 per day
current_cost = 0.0

async def budget_controlled_execution(agent, message):
    """Execute with budget control."""
    global current_cost

    if current_cost >= DAILY_BUDGET:
        raise RuntimeError("Daily budget exceeded")

    result = await agent.run(user_message=message)

    stats = agent.get_cost_stats()
    current_cost += stats.total_cost

    return result
```

### 4. Use Custom Pricing

Configure accurate pricing:

```bash
# Set pricing config
export SPARK_PRICING_CONFIG=/etc/spark/pricing.json
```

### 5. Regular Reporting

Generate regular cost reports:

```python
from datetime import datetime
import json

def generate_cost_report(agent):
    """Generate cost report."""
    stats = agent.get_cost_stats()

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_calls": stats.total_calls,
        "total_tokens": stats.total_tokens,
        "total_cost": stats.total_cost,
        "model_breakdown": stats.model_breakdown
    }

    # Save report
    filename = f"cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(report, f, indent=2)

    return report

# Generate daily report
report = generate_cost_report(agent)
```

## Testing Cost Tracking

### Unit Testing

```python
import pytest
from spark.agents import Agent
from spark.agents.cost_tracker import CostTracker

def test_cost_tracking():
    """Test basic cost tracking."""
    tracker = CostTracker()

    # Record call
    tracker.record_call("gpt-4o", input_tokens=1000, output_tokens=500)

    # Verify stats
    stats = tracker.get_stats()
    assert stats.total_calls == 1
    assert stats.total_input_tokens == 1000
    assert stats.total_output_tokens == 500
    assert stats.total_tokens == 1500
    assert stats.total_cost > 0

def test_cost_reset():
    """Test cost tracking reset."""
    tracker = CostTracker()

    # Record and verify
    tracker.record_call("gpt-4o", 1000, 500)
    stats1 = tracker.get_stats()
    assert stats1.total_calls == 1

    # Reset and verify
    tracker.reset()
    stats2 = tracker.get_stats()
    assert stats2.total_calls == 0
    assert stats2.total_cost == 0
```

### Integration Testing

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

@pytest.mark.asyncio
async def test_agent_cost_tracking():
    """Test cost tracking in agent."""
    model = OpenAIModel(model_id="gpt-4o", enable_cache=True)
    agent = Agent(config=AgentConfig(model=model))

    # Execute agent
    result = await agent.run(user_message="Hello")

    # Verify cost tracking
    stats = agent.get_cost_stats()
    assert stats.total_calls > 0
    assert stats.total_tokens > 0
    assert stats.total_cost >= 0

    # Verify summary
    summary = agent.get_cost_summary()
    assert "Total Calls" in summary
    assert "Total Cost" in summary
```

## Next Steps

- Review [Agent Configuration](configuration.md) for cost tracking configuration
- See [Checkpointing Reference](checkpointing.md) for cost data persistence
- Learn about [Agent Fundamentals](fundamentals.md) for general usage
- Explore [Error Handling](error-handling.md) for error patterns
