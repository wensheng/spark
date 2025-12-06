---
title: Reasoning Strategies Reference
parent: Graph
nav_order: 3
---
# Reasoning Strategies Reference

This reference covers Spark's pluggable reasoning strategies for structuring agent thought processes and decision-making patterns.

## Overview

Reasoning strategies define how agents structure their thinking, plan actions, and approach problem-solving. Spark provides multiple built-in strategies and a framework for creating custom reasoning patterns.

Key capabilities:
- Pluggable strategy pattern
- Built-in reasoning implementations (ReAct, Chain-of-Thought, Plan-and-Solve)
- Custom strategy development
- History tracking and inspection
- Template re-rendering for multi-step reasoning

## Strategy Pattern Overview

### ReasoningStrategy Interface

All strategies implement the `ReasoningStrategy` base class:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class ReasoningStrategy(ABC):
    """Base class for reasoning strategies."""

    @abstractmethod
    async def process_step(
        self,
        parsed_output: Dict[str, Any],
        tool_result_blocks: List[Dict],
        state: Dict[str, Any],
        context: Any = None
    ) -> None:
        """Process a single reasoning step.

        Args:
            parsed_output: Parsed model output
            tool_result_blocks: Tool execution results
            state: Agent state dictionary
            context: Optional context object
        """
        pass

    @abstractmethod
    def should_continue(self, parsed_output: Dict[str, Any]) -> bool:
        """Determine if reasoning should continue.

        Args:
            parsed_output: Parsed model output

        Returns:
            True if agent should continue reasoning
        """
        pass

    @abstractmethod
    def get_history(self, state: Dict[str, Any]) -> List[Dict]:
        """Get reasoning history.

        Args:
            state: Agent state dictionary

        Returns:
            List of reasoning steps
        """
        pass

    def reset(self, state: Dict[str, Any]) -> None:
        """Reset strategy state (optional)."""
        pass
```

### Configuring Strategies

Strategies are configured via `AgentConfig`:

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",  # Required for most strategies
    reasoning_strategy=ReActStrategy(verbose=True)
)

agent = Agent(config=config)
```

## NoOpStrategy

The default strategy with no structured reasoning - direct question-and-answer pattern.

### Use Cases

- Simple question answering
- Single-step tasks
- No reasoning transparency needed
- Minimal token overhead

### Configuration

```python
from spark.agents import Agent, AgentConfig, NoOpStrategy

config = AgentConfig(
    model=model,
    reasoning_strategy=NoOpStrategy()  # Default, can omit
)

agent = Agent(config=config)
```

### Characteristics

- ✅ Simple and fast
- ✅ Lowest token cost
- ✅ Direct responses
- ❌ No reasoning transparency
- ❌ No step tracking
- ❌ Limited for complex tasks

### Example

```python
from spark.agents import Agent
from spark.models.openai import OpenAIModel

# NoOpStrategy is default
model = OpenAIModel(model_id="gpt-4o")
agent = Agent()

# Direct responses
result = await agent.run(user_message="What is the capital of France?")
print(result)  # "The capital of France is Paris."

# No reasoning history
# agent._state.tool_traces will be empty
```

## ReActStrategy

Reasoning + Acting strategy with iterative thought → action → observation cycles.

### Use Cases

- Multi-step problem solving
- Tool-heavy workflows
- Transparent reasoning required
- Complex decision trees
- Research and analysis tasks

### Configuration

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=ReActStrategy(
        verbose=True,  # Log reasoning steps
        max_iterations=None  # Use agent's max_steps
    ),
    tools=[search_tool, calculate_tool]
)

agent = Agent(config=config)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `verbose` | `bool` | `False` | Log reasoning steps to console |
| `max_iterations` | `int` | `None` | Override agent max_steps (None uses agent setting) |

### Characteristics

- ✅ Transparent reasoning
- ✅ Excellent for multi-step tasks
- ✅ Clear thought process
- ✅ Works well with tools
- ❌ Higher token cost
- ❌ More verbose output
- ❌ Requires JSON output mode

### ReAct Cycle

1. **Thought**: Agent reasons about next action
2. **Action**: Agent calls tool or takes action
3. **Observation**: Result of action
4. **Repeat**: Until task complete or max_steps reached

### Example

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.tools.decorator import tool
from spark.models.openai import OpenAIModel

# Define tools
@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

@tool
def calculate(expression: str) -> float:
    """Evaluate mathematical expression."""
    return eval(expression)

# Configure agent with ReAct
model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True),
    tools=[search_web, calculate],
    max_steps=5
)

agent = Agent(config=config)

# Run with complex query
result = await agent.run(
    user_message="What is the population of Paris multiplied by 2?"
)

# Output includes reasoning:
# Thought: I need to find the population of Paris first
# Action: search_web(query="Paris population")
# Observation: Paris has approximately 2.2 million residents
# Thought: Now I'll multiply by 2
# Action: calculate(expression="2200000 * 2")
# Observation: 4400000
# Answer: The population of Paris multiplied by 2 is 4,400,000

print(result)
```

### Accessing ReAct History

```python
# Get reasoning history
history = agent._state.tool_traces
for step in history:
    print(f"Thought: {step.get('thought')}")
    print(f"Action: {step.get('action')}")
    print(f"Observation: {step.get('observation')}")
    print()
```

### ReAct Output Format

Expected JSON structure from model:

```json
{
  "thought": "I need to search for information about...",
  "action": "search_web",
  "action_input": {"query": "Paris population"},
  "done": false
}

// Final step
{
  "thought": "I have all the information needed",
  "answer": "The population of Paris multiplied by 2 is 4,400,000",
  "done": true
}
```

## ChainOfThoughtStrategy

Step-by-step reasoning strategy for mathematical and logical problems.

### Use Cases

- Mathematical problem solving
- Logical reasoning tasks
- Multi-step calculations
- Proof-based reasoning
- Analysis requiring explicit steps

### Configuration

```python
from spark.agents import Agent, AgentConfig, ChainOfThoughtStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=ChainOfThoughtStrategy(verbose=True)
)

agent = Agent(config=config)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `verbose` | `bool` | `False` | Log reasoning steps to console |

### Characteristics

- ✅ Clear step-by-step reasoning
- ✅ Excellent for math/logic
- ✅ Transparent process
- ✅ Better accuracy on complex problems
- ❌ Higher token cost
- ❌ Slower than direct responses
- ❌ Requires JSON output mode

### Example

```python
from spark.agents import Agent, AgentConfig, ChainOfThoughtStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ChainOfThoughtStrategy(verbose=True),
    system_prompt="Solve problems step-by-step, showing your reasoning."
)

agent = Agent(config=config)

# Complex math problem
result = await agent.run(
    user_message="If a train travels 60 mph for 2.5 hours, then 80 mph for 1.5 hours, what is the total distance?"
)

# Output includes steps:
# Step 1: Calculate distance for first segment: 60 mph × 2.5 hours = 150 miles
# Step 2: Calculate distance for second segment: 80 mph × 1.5 hours = 120 miles
# Step 3: Add distances: 150 + 120 = 270 miles
# Answer: 270 miles

print(result)
```

### Chain-of-Thought Output Format

Expected JSON structure:

```json
{
  "steps": [
    "Calculate distance for first segment: 60 mph × 2.5 hours = 150 miles",
    "Calculate distance for second segment: 80 mph × 1.5 hours = 120 miles",
    "Add distances: 150 + 120 = 270 miles"
  ],
  "answer": "270 miles",
  "done": true
}
```

### Accessing CoT History

```python
# Get reasoning steps
history = agent._state.tool_traces
for i, step in enumerate(history):
    print(f"Step {i+1}: {step.get('step')}")

print(f"\nFinal Answer: {agent._state.last_result}")
```

## PlanAndSolveStrategy

Plan-first execution strategy with explicit planning phase and step tracking.

### Use Cases

- Complex multi-step workflows
- Project planning tasks
- Recipes and instructions
- Procedural problem solving
- Tasks requiring structured approach

### Configuration

```python
from spark.agents import Agent, AgentConfig, PlanAndSolveStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=PlanAndSolveStrategy(
        max_plan_steps=10,
        allow_replanning=True,
        verbose=True
    )
)

agent = Agent(config=config)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_plan_steps` | `int` | `10` | Maximum steps in plan |
| `allow_replanning` | `bool` | `True` | Allow plan modification during execution |
| `verbose` | `bool` | `False` | Log planning and execution steps |

### Characteristics

- ✅ Structured approach
- ✅ Clear plan before execution
- ✅ Progress tracking
- ✅ Can replan if needed
- ✅ Good for complex workflows
- ❌ Higher token cost (planning + execution)
- ❌ May over-plan for simple tasks
- ❌ Requires JSON output mode

### Plan-and-Solve Phases

1. **Planning Phase**: Create step-by-step plan
2. **Execution Phase**: Execute steps in order
3. **Replanning** (optional): Adjust plan if needed
4. **Completion**: Verify all steps completed

### Example

```python
from spark.agents import Agent, AgentConfig, PlanAndSolveStrategy
from spark.tools.decorator import tool
from spark.models.openai import OpenAIModel

# Define tools
@tool
def check_inventory(item: str) -> dict:
    """Check item availability in inventory."""
    return {"item": item, "quantity": 50, "available": True}

@tool
def calculate_cost(quantity: int, unit_price: float) -> float:
    """Calculate total cost."""
    return quantity * unit_price

@tool
def process_order(item: str, quantity: int) -> dict:
    """Process order for item."""
    return {"order_id": "ORD-123", "status": "confirmed"}

# Configure agent
model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=PlanAndSolveStrategy(
        max_plan_steps=5,
        allow_replanning=True,
        verbose=True
    ),
    tools=[check_inventory, calculate_cost, process_order]
)

agent = Agent(config=config)

# Complex task
result = await agent.run(
    user_message="Order 30 units of Product A at $25 each"
)

# Output shows plan:
# Plan:
#   Step 1: Check inventory for Product A
#   Step 2: Calculate total cost (30 × $25)
#   Step 3: Process order if inventory sufficient
#   Step 4: Return confirmation
#
# Execution:
#   Step 1: ✓ Inventory check complete - 50 units available
#   Step 2: ✓ Cost calculated - $750
#   Step 3: ✓ Order processed - ORD-123
#   Step 4: ✓ Confirmation sent
#
# Result: Order confirmed for 30 units of Product A, total cost $750

print(result)
```

### Plan-and-Solve Output Format

Expected JSON structure:

```json
// Planning phase
{
  "phase": "planning",
  "plan": [
    "Check inventory for Product A",
    "Calculate total cost",
    "Process order",
    "Return confirmation"
  ],
  "done": false
}

// Execution phase
{
  "phase": "executing",
  "current_step": 1,
  "action": "check_inventory",
  "action_input": {"item": "Product A"},
  "done": false
}

// Replanning (if needed)
{
  "phase": "replanning",
  "reason": "Inventory insufficient",
  "updated_plan": [...],
  "done": false
}

// Completion
{
  "phase": "complete",
  "answer": "Order confirmed...",
  "steps_completed": 4,
  "done": true
}
```

### Accessing Plan History

```python
# Get plan and execution history
history = agent._state.tool_traces

# Extract plan
plan = history[0].get('plan', [])
print("Plan:")
for i, step in enumerate(plan, 1):
    print(f"  {i}. {step}")

# Extract execution
print("\nExecution:")
for trace in history[1:]:
    step = trace.get('current_step')
    status = trace.get('status', 'complete')
    print(f"  Step {step}: {status}")
```

## Strategy Configuration and Parameters

### Selecting Strategy

Choose strategy based on task characteristics:

| Task Type | Recommended Strategy | Reason |
|-----------|---------------------|--------|
| Simple Q&A | NoOpStrategy | Direct, fast, low cost |
| Web research | ReActStrategy | Multiple tool calls, reasoning needed |
| Math problems | ChainOfThoughtStrategy | Step-by-step clarity |
| Complex workflows | PlanAndSolveStrategy | Structured approach |
| API integration | ReActStrategy | Tool orchestration |
| Data analysis | ChainOfThoughtStrategy | Logical steps |

### Combining with Tools

Different strategies work differently with tools:

```python
from spark.agents import AgentConfig, ReActStrategy
from spark.tools.decorator import tool

# ReAct - excellent with tools
@tool
def search(query: str) -> str:
    """Search for information."""
    return "..."

config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(),
    tools=[search]  # Tools integrated into reasoning loop
)

# ChainOfThought - tools less emphasized
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ChainOfThoughtStrategy(),
    tools=[search]  # Tools available but not primary focus
)

# NoOp - tools called but no reasoning
config = AgentConfig(
    model=model,
    reasoning_strategy=NoOpStrategy(),
    tools=[search]  # Direct tool calls
)
```

### Strategy Parameters Summary

| Strategy | Required output_mode | Key Parameters | Typical Use |
|----------|---------------------|----------------|-------------|
| NoOpStrategy | text or json | None | Simple tasks |
| ReActStrategy | json | verbose, max_iterations | Tool-heavy tasks |
| ChainOfThoughtStrategy | json | verbose | Math/logic |
| PlanAndSolveStrategy | json | max_plan_steps, allow_replanning | Complex workflows |

## Custom Strategy Development

### Implementing Custom Strategy

Create custom strategies by extending `ReasoningStrategy`:

```python
from spark.agents.strategies import ReasoningStrategy
from typing import Any, Dict, List

class DebugStrategy(ReasoningStrategy):
    """Custom strategy that logs detailed debug information."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    async def process_step(
        self,
        parsed_output: Dict[str, Any],
        tool_result_blocks: List[Dict],
        state: Dict[str, Any],
        context: Any = None
    ) -> None:
        """Process and log each step."""
        # Store step in history
        if 'debug_history' not in state:
            state['debug_history'] = []

        step_info = {
            'step_number': len(state['debug_history']) + 1,
            'output': parsed_output,
            'tool_results': tool_result_blocks,
            'timestamp': time.time()
        }

        state['debug_history'].append(step_info)

        if self.verbose:
            print(f"\n=== Step {step_info['step_number']} ===")
            print(f"Output: {parsed_output}")
            print(f"Tools called: {len(tool_result_blocks)}")

    def should_continue(self, parsed_output: Dict[str, Any]) -> bool:
        """Continue until 'done' flag set."""
        return not parsed_output.get('done', False)

    def get_history(self, state: Dict[str, Any]) -> List[Dict]:
        """Return debug history."""
        return state.get('debug_history', [])

    def reset(self, state: Dict[str, Any]) -> None:
        """Clear debug history."""
        state['debug_history'] = []
```

### Using Custom Strategy

```python
from spark.agents import Agent, AgentConfig

# Use custom strategy
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=DebugStrategy(verbose=True)
)

agent = Agent(config=config)
result = await agent.run(user_message="Test query")

# Access custom history
debug_history = agent._state.get('debug_history', [])
for step in debug_history:
    print(f"Step {step['step_number']}: {step['timestamp']}")
```

### Advanced Custom Strategy: Iterative Refinement

```python
from spark.agents.strategies import ReasoningStrategy
from typing import Any, Dict, List

class IterativeRefinementStrategy(ReasoningStrategy):
    """Strategy that iteratively refines answers."""

    def __init__(self, max_refinements: int = 3, confidence_threshold: float = 0.9):
        self.max_refinements = max_refinements
        self.confidence_threshold = confidence_threshold

    async def process_step(
        self,
        parsed_output: Dict[str, Any],
        tool_result_blocks: List[Dict],
        state: Dict[str, Any],
        context: Any = None
    ) -> None:
        """Track refinement iterations."""
        if 'refinements' not in state:
            state['refinements'] = []

        refinement = {
            'iteration': len(state['refinements']) + 1,
            'answer': parsed_output.get('answer'),
            'confidence': parsed_output.get('confidence', 0.0),
            'reasoning': parsed_output.get('reasoning')
        }

        state['refinements'].append(refinement)

        # Update best answer if confidence improved
        if 'best_answer' not in state or refinement['confidence'] > state['best_confidence']:
            state['best_answer'] = refinement['answer']
            state['best_confidence'] = refinement['confidence']

    def should_continue(self, parsed_output: Dict[str, Any]) -> bool:
        """Continue if below threshold and under max refinements."""
        confidence = parsed_output.get('confidence', 0.0)
        iteration = parsed_output.get('iteration', 1)

        return (
            confidence < self.confidence_threshold
            and iteration < self.max_refinements
            and not parsed_output.get('done', False)
        )

    def get_history(self, state: Dict[str, Any]) -> List[Dict]:
        """Return refinement history."""
        return state.get('refinements', [])

    def reset(self, state: Dict[str, Any]) -> None:
        """Clear refinement state."""
        state.pop('refinements', None)
        state.pop('best_answer', None)
        state.pop('best_confidence', None)
```

## Strategy Selection Guidelines

### Decision Tree

```
Is the task simple and direct?
├─ Yes → NoOpStrategy
└─ No → Does it require tools?
          ├─ Yes → ReActStrategy
          └─ No → Is it mathematical/logical?
                  ├─ Yes → ChainOfThoughtStrategy
                  └─ No → Is it a complex workflow?
                          ├─ Yes → PlanAndSolveStrategy
                          └─ No → ReActStrategy (default for complex)
```

### Performance Comparison

| Strategy | Avg Tokens | Accuracy | Speed | Transparency |
|----------|-----------|----------|-------|--------------|
| NoOpStrategy | 1x | Good | Fast | Low |
| ReActStrategy | 2-3x | Very Good | Medium | High |
| ChainOfThoughtStrategy | 2x | Excellent | Medium | High |
| PlanAndSolveStrategy | 3-4x | Very Good | Slow | Very High |

### Cost Considerations

```python
# Cost-conscious: NoOpStrategy
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o-mini"),
    reasoning_strategy=NoOpStrategy()
)

# Balanced: ReActStrategy with max_steps limit
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    output_mode="json",
    reasoning_strategy=ReActStrategy(),
    max_steps=5  # Limit iterations
)

# Accuracy-focused: ChainOfThought with premium model
config = AgentConfig(
    model=BedrockModel(model_id="claude-sonnet-4-5"),
    output_mode="json",
    reasoning_strategy=ChainOfThoughtStrategy(verbose=True)
)
```

## Debugging Reasoning

### Enabling Verbose Mode

All strategies support verbose logging:

```python
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True)  # Enable logging
)

agent = Agent(config=config)
result = await agent.run(user_message="Complex query")
# Logs each reasoning step to console
```

### Inspecting Reasoning History

```python
from spark.agents import Agent, ReActStrategy

agent = Agent(config=AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy()
))

result = await agent.run(user_message="Query")

# Get reasoning history
history = agent._state.tool_traces
print(f"Reasoning steps: {len(history)}")

for i, step in enumerate(history, 1):
    print(f"\nStep {i}:")
    print(f"  Thought: {step.get('thought', 'N/A')}")
    print(f"  Action: {step.get('action', 'N/A')}")
    print(f"  Result: {step.get('observation', 'N/A')}")
```

### Testing Strategies

```python
import pytest
from spark.agents import Agent, AgentConfig, ReActStrategy, ChainOfThoughtStrategy

@pytest.mark.asyncio
async def test_react_strategy():
    """Test ReAct strategy produces reasoning history."""
    config = AgentConfig(
        model=model,
        output_mode="json",
        reasoning_strategy=ReActStrategy(),
        tools=[search_tool]
    )

    agent = Agent(config=config)
    result = await agent.run(user_message="Search for Python tutorials")

    # Verify reasoning occurred
    history = agent._state.tool_traces
    assert len(history) > 0
    assert any('thought' in step for step in history)

@pytest.mark.asyncio
async def test_strategy_comparison():
    """Compare strategies on same task."""
    strategies = [
        NoOpStrategy(),
        ChainOfThoughtStrategy()
    ]

    results = {}
    for strategy in strategies:
        agent = Agent(config=AgentConfig(
            model=model,
            output_mode="json" if not isinstance(strategy, NoOpStrategy) else "text",
            reasoning_strategy=strategy
        ))

        result = await agent.run(user_message="What is 25 * 4?")
        stats = agent.get_cost_stats()

        results[strategy.__class__.__name__] = {
            'result': result,
            'tokens': stats.total_tokens,
            'cost': stats.total_cost
        }

    # Compare
    for name, data in results.items():
        print(f"{name}: {data['tokens']} tokens, ${data['cost']:.4f}")
```

## Best Practices

### 1. Match Strategy to Task

```python
# Simple tasks - NoOpStrategy
agent_qa = Agent()  # Default NoOpStrategy

# Tool-heavy - ReActStrategy
agent_tools = Agent(config=AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(),
    tools=[...]
))

# Math/logic - ChainOfThoughtStrategy
agent_math = Agent(config=AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ChainOfThoughtStrategy()
))
```

### 2. Set max_steps Appropriately

```python
# Prevent runaway reasoning
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(),
    max_steps=10  # Reasonable limit
)
```

### 3. Use Verbose Mode in Development

```python
# Development
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=True)  # Debug
)

# Production
config = AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy(verbose=False)  # Quiet
)
```

### 4. Test Strategy Performance

Compare strategies empirically:

```python
strategies_to_test = [
    ReActStrategy(),
    ChainOfThoughtStrategy(),
    PlanAndSolveStrategy()
]

for strategy in strategies_to_test:
    # Test with your specific use case
    # Measure: accuracy, tokens, latency
    pass
```

### 5. Consider Token Costs

```python
# Monitor costs by strategy
agent = Agent(config=AgentConfig(
    model=model,
    output_mode="json",
    reasoning_strategy=ReActStrategy()
))

result = await agent.run(user_message="...")
stats = agent.get_cost_stats()

print(f"Tokens used: {stats.total_tokens:,}")
print(f"Cost: ${stats.total_cost:.4f}")
```

## Next Steps

- Review [Agent Configuration](configuration.md) for strategy configuration
- See [Tools Reference](tools.md) for tool integration with strategies
- Learn about [Cost Tracking](cost-tracking.md) for monitoring strategy costs
- Explore [Agent Fundamentals](fundamentals.md) for general usage
