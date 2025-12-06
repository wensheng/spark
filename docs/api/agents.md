---
title: Agent Classes API Reference
parent: API
nav_order: 2
---
# Agent Classes API Reference

This document provides the complete API reference for Spark's agent system, including the main Agent class, configuration, memory management, reasoning strategies, and cost tracking.

## Table of Contents

- [Agent](#agent)
- [AgentConfig](#agentconfig)
- [MemoryManager](#memorymanager)
- [MemoryConfig](#memoryconfig)
- [ReasoningStrategy](#reasoningstrategy)
  - [NoOpStrategy](#noopstrategy)
  - [ReActStrategy](#reactstrategy)
  - [ChainOfThoughtStrategy](#chainofthoughtstrategy)
  - [PlanAndSolveStrategy](#planandsolvestrategy)
- [CostTracker](#costtracker)

---

## Agent

**Module**: `spark.agents.agent`

The main agent class that orchestrates LLM calls, tool execution, and conversation management. Agents are intelligent nodes that can use tools, maintain conversation history, and apply reasoning strategies.

### Constructor

```python
def __init__(
    self,
    config: Optional[AgentConfig] = None,
    **kwargs
) -> None
```

**Parameters:**
- `config` (AgentConfig, optional): Agent configuration. If None, creates default config with EchoModel.
- `**kwargs`: Additional parameters passed to Node constructor and config if no config provided.

**Example:**
```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o-mini"),
    system_prompt="You are a helpful assistant.",
    tools=[search_tool, calculator_tool]
)
agent = Agent(config=config)
```

### Properties

#### state

```python
@property
def state(self) -> AgentState
```

Get the current state of the agent. The state includes conversation messages, tool traces, last result/error, and strategy-specific data.

**Returns:** AgentState dictionary with keys:
- `messages`: Conversation history (synchronized from memory_manager)
- `tool_traces`: List of tool execution traces
- `last_result`: Last agent result
- `last_error`: Last error message
- `last_output`: Last structured output (for JSON mode)
- `history`: Strategy-specific history

#### messages

```python
@property
def messages(self) -> list[dict[str, Any]]
```

Get conversation messages from memory manager. This is the preferred way to access conversation history.

**Returns:** List of message dictionaries with `role` and `content` keys.

#### result

```python
@property
def result(self) -> Optional[dict[str, Any]]
```

Get the last agent result.

**Returns:** Last result dictionary or None.

### Main Methods

#### process

```python
async def process(
    self,
    context: ExecutionContext[AgentState] | None = None
) -> NodeMessage
```

Process the execution context and return an agent result. This is the main method called by `do()` or `go()`.

**Parameters:**
- `context` (ExecutionContext, optional): Execution context with inputs, state, and metadata.

**Returns:** NodeMessage containing the agent's response.

**Raises:**
- `AgentError`: Base exception for agent-related errors
- `ToolExecutionError`: Tool execution failed
- `ModelError`: LLM model call failed
- `ConfigurationError`: Invalid configuration

**Example:**
```python
context = ExecutionContext(inputs=NodeMessage(content="What is 2+2?"))
result = await agent.process(context)
print(result.content)
```

#### build_prompt

```python
def build_prompt(self, context: ExecutionContext) -> Messages
```

Build the prompt payload for LLM call from the execution context. Handles both message-based inputs and template-based inputs.

**Parameters:**
- `context` (ExecutionContext): Execution context with inputs.

**Returns:** Messages list in LLM format.

### Memory Management

#### add_message_to_history

```python
def add_message_to_history(self, message: dict[str, Any] | str) -> None
```

Add a message to the agent's conversation history. Messages are stored in memory_manager with policy enforcement.

**Parameters:**
- `message`: Message dictionary with `role` and `content`, or string (treated as user message).

**Example:**
```python
agent.add_message_to_history({"role": "user", "content": "Hello"})
agent.add_message_to_history("Hello")  # Equivalent
```

#### get_history

```python
def get_history(self) -> list[dict[str, Any]]
```

Get the conversation history.

**Returns:** List of message dictionaries.

#### clear_history

```python
def clear_history(self) -> None
```

Clear the conversation history.

#### set_memory_policy

```python
def set_memory_policy(
    self,
    policy: MemoryPolicyType | Callable,
    memory_window: int | None = None
) -> None
```

Set the memory policy for the agent.

**Parameters:**
- `policy`: Memory policy type or custom callable
- `memory_window`: Optional window size for rolling window policy

**Example:**
```python
from spark.agents.memory import MemoryPolicyType

agent.set_memory_policy(MemoryPolicyType.ROLLING_WINDOW, memory_window=20)
```

### Tool Traces

#### get_tool_traces

```python
def get_tool_traces(self) -> list[ToolTrace]
```

Get the history of all tool executions.

**Returns:** List of ToolTrace records containing timing, inputs, outputs, and errors.

#### get_last_tool_trace

```python
def get_last_tool_trace(self) -> Optional[ToolTrace]
```

Get the most recent tool execution trace.

**Returns:** Last ToolTrace record or None.

#### get_tool_traces_by_name

```python
def get_tool_traces_by_name(self, tool_name: str) -> list[ToolTrace]
```

Get all traces for a specific tool.

**Parameters:**
- `tool_name`: Name of the tool to filter by

**Returns:** List of ToolTrace records for the specified tool.

#### get_failed_tool_traces

```python
def get_failed_tool_traces(self) -> list[ToolTrace]
```

Get all tool traces that resulted in errors.

**Returns:** List of ToolTrace records where execution failed.

#### clear_tool_traces

```python
def clear_tool_traces(self) -> None
```

Clear all tool execution traces.

### Cost Tracking

#### get_cost_stats

```python
def get_cost_stats(self, namespace: str | None = None) -> CostStats
```

Get cost tracking statistics for this agent.

**Parameters:**
- `namespace`: Optional namespace to filter by

**Returns:** CostStats object with totals and breakdowns.

#### get_cost_summary

```python
def get_cost_summary(self, namespace: str | None = None) -> str
```

Get formatted cost summary.

**Parameters:**
- `namespace`: Optional namespace to filter by

**Returns:** Formatted string with cost breakdown.

#### reset_cost_tracking

```python
def reset_cost_tracking(self) -> None
```

Reset cost tracking data.

### Checkpointing

#### checkpoint

```python
def checkpoint(self) -> dict[str, Any]
```

Create a checkpoint of the agent's current state. Saves all stateful information needed to restore the agent later.

**Returns:** Dictionary containing checkpoint data including:
- Configuration (prompts, settings, max_steps, parallel_tool_execution)
- Memory (messages, policy, window)
- State (tool_traces, last_result, last_error, history)
- Cost tracking (stats and call history)

**Example:**
```python
checkpoint = agent.checkpoint()
# Save to file
agent.save_checkpoint('agent_state.json')
```

#### restore (classmethod)

```python
@classmethod
def restore(
    cls,
    checkpoint: dict[str, Any],
    config: Optional[AgentConfig] = None
) -> Agent
```

Restore an agent from a checkpoint.

**Parameters:**
- `checkpoint`: Checkpoint data from `agent.checkpoint()`
- `config`: Optional AgentConfig. If None, creates config from checkpoint (model/tools must be provided separately).

**Returns:** Restored Agent instance.

**Example:**
```python
# Restore with original config
restored_agent = Agent.restore(checkpoint, config)

# Load from file
agent = Agent.load_checkpoint('agent_state.json', config)
```

#### save_checkpoint

```python
def save_checkpoint(self, filepath: str) -> None
```

Save checkpoint to a JSON file.

**Parameters:**
- `filepath`: Path to save the checkpoint file

#### load_checkpoint (classmethod)

```python
@classmethod
def load_checkpoint(
    cls,
    filepath: str,
    config: Optional[AgentConfig] = None
) -> Agent
```

Load agent from a checkpoint file.

**Parameters:**
- `filepath`: Path to the checkpoint file
- `config`: Optional AgentConfig (required for model, tools, hooks)

**Returns:** Restored Agent instance.

### Human-in-the-Loop

#### pause

```python
def pause(self, reason: str | None = None) -> None
```

Trigger the configured stop token so operators can resume later.

**Parameters:**
- `reason`: Optional reason for pausing

**Raises:**
- `ConfigurationError`: If no stop_token is configured

#### resume

```python
def resume(self) -> None
```

Clear the stop token to resume execution.

### Error Handling

#### handle_model_error

```python
def handle_model_error(self, exc: Exception) -> NodeMessage
```

Handle model errors and return an error result with detailed information.

**Parameters:**
- `exc`: The exception that was raised

**Returns:** NodeMessage containing error details with category and timestamp.

---

## AgentConfig

**Module**: `spark.agents.config`

Configuration class for Agent with validation and defaults.

### Constructor

```python
class AgentConfig(NodeConfig):
    model: Model
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: str | None = None
    prompt_template: str | None = None
    preload_messages: Messages = Field(default_factory=list)
    memory_config: MemoryConfig = Field(default_factory=MemoryConfig)
    output_mode: Literal['json', 'text'] = 'text'
    output_schema: type[BaseModel] = DefaultOutputSchema
    record_direct_tool_call: bool = True
    hooks: Optional[list[Any]] = None
    before_llm_hooks: list[HookRef] = Field(default_factory=list)
    after_llm_hooks: list[HookRef] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)
    tool_choice: Literal['auto', 'any', 'none'] | str = 'auto'
    max_steps: int = 100
    parallel_tool_execution: bool = False
    reasoning_strategy: Optional[Any] = None
    budget: AgentBudgetConfig | None = None
    human_policy: HumanInteractionPolicy | None = None
    policy_set: PolicySet | None = None
```

**Key Fields:**

- **model** (Model, required): LLM model instance (OpenAIModel, BedrockModel, etc.)
- **system_prompt** (str, optional): System prompt to guide model behavior
- **prompt_template** (str, optional): Jinja2 template for prompts
- **preload_messages** (Messages): Initial messages to pre-load into conversation
- **memory_config** (MemoryConfig): Memory management configuration
- **output_mode** ('json' | 'text'): Output format from model
- **output_schema** (BaseModel): Pydantic model for structured output (JSON mode only)
- **tools** (list): List of tools available to the agent
- **tool_choice** ('auto' | 'any' | 'none' | str): Tool selection strategy
  - `'auto'`: LLM decides whether to use tools
  - `'any'`: LLM must use at least one tool
  - `'none'`: Disable tools
  - `'<tool_name>'`: Force specific tool
- **max_steps** (int): Maximum tool execution steps (0 = unlimited)
- **parallel_tool_execution** (bool): Enable concurrent tool execution
- **reasoning_strategy** (ReasoningStrategy, optional): Strategy for structured thinking
- **before_llm_hooks** (list[HookRef]): Hooks to run before LLM calls
- **after_llm_hooks** (list[HookRef]): Hooks to run after LLM calls

**Example:**
```python
from spark.agents import AgentConfig
from spark.agents.strategies import ReActStrategy
from spark.models.openai import OpenAIModel

config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    system_prompt="You are a research assistant.",
    tools=[search_tool, calculator_tool],
    tool_choice='auto',
    max_steps=20,
    parallel_tool_execution=True,
    reasoning_strategy=ReActStrategy(verbose=True),
    output_mode='json'
)
```

### Methods

#### validate_config

```python
@model_validator(mode='after')
def validate_config(self) -> AgentConfig
```

Validate agent configuration for consistency. Automatically called after initialization.

**Raises:**
- `ValueError`: If configuration is invalid (e.g., tool_choice='any' without tools)

#### resolve_hook

```python
def resolve_hook(self, hook: HookRef) -> HookFn
```

Resolve a hook reference to a callable.

**Parameters:**
- `hook`: Callable or module:function string reference

**Returns:** Resolved callable hook function

#### resolve_strategy

```python
def resolve_strategy(self, strategy: Optional[Any] = None) -> Optional[ReasoningStrategy]
```

Resolve a strategy reference to an instance.

**Parameters:**
- `strategy`: Strategy name (string), instance, or None

**Returns:** Strategy instance or None

**Example:**
```python
# Resolve string name
strategy = config.resolve_strategy("react")

# Pass through instance
strategy = config.resolve_strategy(ReActStrategy())
```

---

## MemoryManager

**Module**: `spark.agents.memory`

Manages conversation history with configurable memory policies.

### Constructor

```python
def __init__(
    self,
    config: MemoryConfig | None = None,
    **kwargs
) -> None
```

**Parameters:**
- `config`: Memory configuration
- `**kwargs`: Configuration options if config is None

### Attributes

- **memory** (list[dict[str, Any]]): List of message dictionaries

### Methods

#### add_message

```python
def add_message(self, message: dict[str, Any]) -> None
```

Add a message to memory with policy enforcement.

**Parameters:**
- `message`: Message dictionary with `role` and `content`

#### export_to_dict

```python
def export_to_dict(self) -> dict[str, Any]
```

Export memory state and configuration to a serializable dict.

**Returns:** Dictionary with policy, window, summary_max_chars, and memory.

#### save

```python
def save(self, file_path: str | Path) -> None
```

Save memory state to a JSON file.

**Parameters:**
- `file_path`: Path to save memory

#### load

```python
def load(self, file_path: str | Path) -> None
```

Load memory state from a JSON file.

**Parameters:**
- `file_path`: Path to load from

**Example:**
```python
from spark.agents.memory import MemoryManager, MemoryConfig

manager = MemoryManager(MemoryConfig(policy="rolling_window", window=10))
manager.add_message({"role": "user", "content": "Hello"})
manager.save("memory.json")
```

---

## MemoryConfig

**Module**: `spark.agents.memory`

Configuration for memory management policies.

```python
class MemoryConfig(BaseModel):
    policy: MemoryPolicyType = MemoryPolicyType.ROLLING_WINDOW
    window: int = 10
    summary_max_chars: int = 1000
    callable: Optional[Callable] = None
```

**Fields:**
- **policy** (MemoryPolicyType): Memory policy
  - `NULL`: No memory retention
  - `ROLLING_WINDOW`: Keep last N messages
  - `SUMMARIZE`: Compress older messages, keep recent ones
  - `CUSTOM`: Use custom callable
- **window** (int): Number of messages to keep (for rolling window)
- **summary_max_chars** (int): Max characters for summaries
- **callable** (Callable, optional): Custom memory management function

---

## ReasoningStrategy

**Module**: `spark.agents.strategies`

Abstract base class for reasoning strategies. Strategies define how agents structure their thinking process during multi-step reasoning.

### Methods

#### process_step (abstract)

```python
async def process_step(
    self,
    parsed_output: Any,
    tool_result_blocks: list[dict[str, Any]],
    state: dict[str, Any],
    context: Optional[Any] = None
) -> None
```

Process a reasoning step and update state.

**Parameters:**
- `parsed_output`: Structured output from the model
- `tool_result_blocks`: List of tool result ContentBlocks
- `state`: Agent state dictionary to update
- `context`: Optional execution context

#### should_continue (abstract)

```python
def should_continue(self, parsed_output: Any) -> bool
```

Determine if reasoning should continue based on the output.

**Parameters:**
- `parsed_output`: Structured output from the model

**Returns:** True if reasoning should continue, False if complete.

#### get_history (abstract)

```python
def get_history(self, state: dict[str, Any]) -> list[dict[str, Any]]
```

Get the reasoning history from state.

**Parameters:**
- `state`: Agent state dictionary

**Returns:** List of reasoning steps/history.

#### initialize_state

```python
def initialize_state(self, state: dict[str, Any]) -> None
```

Initialize strategy-specific state fields.

**Parameters:**
- `state`: Agent state dictionary to initialize

---

## NoOpStrategy

**Module**: `spark.agents.strategies`

No-operation strategy that performs no special reasoning structure. This is the default strategy for simple agents.

### Example

```python
from spark.agents.strategies import NoOpStrategy

strategy = NoOpStrategy()
# Used automatically when no reasoning_strategy is specified
```

---

## ReActStrategy

**Module**: `spark.agents.strategies`

ReAct (Reasoning + Acting) strategy where the agent alternates between thought, action, and observation.

### Constructor

```python
def __init__(self, verbose: bool = True) -> None
```

**Parameters:**
- `verbose`: Whether to print reasoning steps

### Expected Output Structure

When using ReActStrategy with JSON output mode, the structured output should have:
- **thought** (str): The agent's reasoning
- **action** (str): Tool name to call (or null for final answer)
- **action_input** (str | dict): Input for the tool
- **final_answer** (str, optional): The final answer when action is null

### Example

```python
from spark.agents import Agent, AgentConfig
from spark.agents.strategies import ReActStrategy
from pydantic import BaseModel

class ReActOutput(BaseModel):
    thought: str
    action: str | None
    action_input: str | dict | None
    final_answer: str | None = None

config = AgentConfig(
    model=model,
    tools=[search_tool],
    output_mode='json',
    output_schema=ReActOutput,
    reasoning_strategy=ReActStrategy(verbose=True)
)

agent = Agent(config=config)
result = await agent.process(context)
```

---

## ChainOfThoughtStrategy

**Module**: `spark.agents.strategies`

Chain-of-Thought (CoT) strategy that encourages step-by-step reasoning without necessarily calling tools.

### Expected Output Structure

- **steps** (list): List of reasoning steps
- **answer** (str): Final answer

### Example

```python
from spark.agents.strategies import ChainOfThoughtStrategy
from pydantic import BaseModel

class CoTOutput(BaseModel):
    steps: list[str]
    answer: str

config = AgentConfig(
    model=model,
    output_mode='json',
    output_schema=CoTOutput,
    reasoning_strategy=ChainOfThoughtStrategy()
)
```

---

## PlanAndSolveStrategy

**Module**: `spark.agents.strategies`

Strategy that creates and tracks a structured plan before execution.

### Constructor

```python
def __init__(
    self,
    plan_steps: Optional[list[str]] = None,
    name: str = "plan-and-solve",
    auto_start: bool = True
) -> None
```

**Parameters:**
- `plan_steps`: List of step descriptions for the plan
- `name`: Name of the plan
- `auto_start`: Whether to auto-start the first step

### Methods

#### generate_plan

```python
async def generate_plan(self, context: Any | None = None) -> StrategyPlan
```

Generate a plan for the current mission.

**Parameters:**
- `context`: Optional execution context

**Returns:** StrategyPlan with steps.

### Example

```python
from spark.agents.strategies import PlanAndSolveStrategy

strategy = PlanAndSolveStrategy(
    plan_steps=[
        "Analyze the user request",
        "Gather necessary information",
        "Formulate a response",
        "Verify the answer"
    ],
    auto_start=True
)

config = AgentConfig(
    model=model,
    reasoning_strategy=strategy
)
```

---

## CostTracker

**Module**: `spark.agents.cost_tracker`

Track costs for LLM API calls with configurable pricing.

### Constructor

```python
def __init__(self, pricing_config_path: Optional[str] = None) -> None
```

**Parameters:**
- `pricing_config_path`: Optional path to custom pricing config file

### Methods

#### record_call

```python
def record_call(
    self,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    timestamp: Optional[float] = None,
    *,
    namespace: str | None = None
) -> CallCost
```

Record an LLM API call and calculate cost.

**Parameters:**
- `model_id`: Model identifier
- `input_tokens`: Number of input tokens
- `output_tokens`: Number of output tokens
- `timestamp`: When the call was made (defaults to current time)
- `namespace`: Optional namespace for tracking

**Returns:** CallCost object with cost breakdown.

**Example:**
```python
from spark.agents.cost_tracker import CostTracker

tracker = CostTracker()
call_cost = tracker.record_call('gpt-4o', input_tokens=1500, output_tokens=800)
print(f"Cost: ${call_cost.total_cost:.6f}")
```

#### get_stats

```python
def get_stats(self, namespace: str | None = None) -> CostStats
```

Get aggregated cost statistics.

**Parameters:**
- `namespace`: Optional namespace to filter by

**Returns:** CostStats object with totals and breakdowns.

#### get_calls

```python
def get_calls(
    self,
    model_id: Optional[str] = None,
    namespace: str | None = None
) -> list[CallCost]
```

Get call history, optionally filtered by model or namespace.

**Parameters:**
- `model_id`: Optional model ID to filter by
- `namespace`: Optional namespace to filter by

**Returns:** List of CallCost objects.

#### reset

```python
def reset(self) -> None
```

Reset all tracking data.

#### format_summary

```python
def format_summary(self, namespace: str | None = None) -> str
```

Format a human-readable cost summary.

**Parameters:**
- `namespace`: Optional namespace to filter by

**Returns:** Formatted string with cost breakdown.

#### reload_pricing

```python
def reload_pricing(self, config_path: Optional[str] = None) -> None
```

Reload pricing configuration from file.

**Parameters:**
- `config_path`: Optional path to pricing config file

### Data Classes

#### CallCost

```python
@dataclass
class CallCost:
    model_id: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    timestamp: float
    namespace: str = "default"
```

Cost information for a single LLM call.

#### CostStats

```python
@dataclass
class CostStats:
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    cost_by_model: dict[str, float] = field(default_factory=dict)
```

Aggregated cost statistics.

### Pricing Configuration

The CostTracker loads model pricing from a JSON configuration file. It searches for config files in this order:

1. `SPARK_PRICING_CONFIG` environment variable
2. `./model_pricing.json` (current directory)
3. `~/.spark/model_pricing.json` (user home directory)
4. `spark/agents/model_pricing.json` (package default)
5. Hardcoded fallback values

**Config File Format** (`model_pricing.json`):
```json
{
  "openai": {
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60}
  },
  "anthropic": {
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00}
  },
  "default": {"input": 5.00, "output": 15.00}
}
```

Prices are per 1M tokens in USD.

**Example:**
```python
from spark.agents.cost_tracker import CostTracker

# Use custom pricing
tracker = CostTracker(pricing_config_path='my_pricing.json')

# Or reload at runtime
tracker.reload_pricing('updated_pricing.json')

# Get statistics
stats = tracker.get_stats()
print(f"Total cost: ${stats.total_cost:.4f}")
print(f"Total tokens: {stats.total_tokens:,}")
print(tracker.format_summary())
```

---

## See Also

- [Node Classes](nodes.md) - Base Node class and execution context
- [Tool Classes](tools.md) - Tool decorator and registry
- [Model Classes](models.md) - LLM model providers
- [Examples](/examples/) - Complete agent examples
