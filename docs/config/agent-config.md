---
title: AgentConfig
parent: Config
nav_order: 3
---
# AgentConfig
---

`AgentConfig` is a Pydantic model that extends `NodeConfig` and provides agent-specific configuration including model settings, tools, memory management, reasoning strategies, output modes, and validation rules.

**Import**:
```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
```

**Basic Usage**:
```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")

config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant.",
    max_steps=100,
    tools=[search_tool, calculator_tool]
)

agent = Agent(config=config)
response = await agent.run("What is the weather today?")
```

## Complete Field Reference

### Model Configuration

#### `model`

**Type**: `Model` (required)
**Default**: None (must be provided)
**Description**: LLM model instance for agent execution.

**Usage**:
```python
from spark.models.openai import OpenAIModel
from spark.models.bedrock import BedrockModel

# OpenAI model
config = AgentConfig(model=OpenAIModel(model_id="gpt-4o"))

# Bedrock model
config = AgentConfig(model=BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0"
))

# With caching enabled
config = AgentConfig(model=OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600
))
```

**Notes**:
- Required field; agent cannot function without a model
- Model must be an instance, not a class
- See [Models Guide](../models/models.md) for supported providers

### Identity and Description

#### `name`

**Type**: `str | None`
**Default**: `None`
**Description**: Human-readable name for the agent.

**Usage**:
```python
config = AgentConfig(
    model=model,
    name="ResearchAssistant"
)
```

**Notes**:
- Used for logging, telemetry, and debugging
- Helpful when multiple agents collaborate
- Included in graph specifications

#### `description`

**Type**: `str | None`
**Default**: `None`
**Description**: Detailed description of the agent's purpose and capabilities.

**Usage**:
```python
config = AgentConfig(
    model=model,
    name="DataAnalyst",
    description="Analyzes datasets and generates insights using SQL and visualization tools"
)
```

### Prompting Configuration

#### `system_prompt`

**Type**: `str | None`
**Default**: `None`
**Description**: System prompt to guide model behavior and persona.

**Usage**:
```python
config = AgentConfig(
    model=model,
    system_prompt="""You are a helpful coding assistant.

Guidelines:
- Write clean, well-documented code
- Explain your reasoning
- Follow best practices
- Ask clarifying questions when needed"""
)
```

**Notes**:
- Sets the agent's role and behavior
- Persists across all interactions
- Can be overridden per-run via agent methods
- Use for persona, constraints, and guidelines

**Example - Common Patterns**:
```python
# Concise assistant
system_prompt = "You are a helpful assistant. Be concise and accurate."

# Domain expert
system_prompt = """You are a Python expert specializing in data science.
Provide complete, working examples with explanations."""

# Tool-focused agent
system_prompt = """You are an API integration specialist.
Use the provided tools to fetch and process data.
Always validate API responses before returning results."""

# Structured output agent
system_prompt = """You are a data extraction agent.
Extract information from text and return it in the specified JSON format.
Be thorough and precise."""
```

#### `prompt_template`

**Type**: `str | None`
**Default**: `None`
**Description**: Jinja2 template for formatting user prompts with variables.

**Usage**:
{% raw %}
```python
config = AgentConfig(
    model=model,
    prompt_template="""
Task: {{ task }}
Context: {{ context }}
User Query: {{ query }}

Provide a {{ response_format }} response.
"""
)
```
{% endraw %}

# Use with variables
response = await agent.run(
    prompt_variables={
        'task': 'data analysis',
        'context': 'Q1 sales data',
        'query': 'What are the trends?',
        'response_format': 'detailed'
    }
)
```

**Notes**:
- Uses Jinja2 syntax for templating
- Supports conditionals, loops, filters
- Variables passed via `prompt_variables` parameter
- Re-rendered on each step for multi-step reasoning

**Example - Advanced Templates**:
{% raw %}
```python
# Conditional template
prompt_template = """
{% if use_tools %}
You have access to: {{ tools | join(', ') }}
{% endif %}

Task: {{ task }}

{% if examples %}
Examples:
{% for example in examples %}
- {{ example }}
{% endfor %}
{% endif %}
"""

# Multi-step template
prompt_template = """
Step {{ step_number }} of {{ total_steps }}

Previous results:
{% for result in previous_results %}
{{ loop.index }}. {{ result }}
{% endfor %}

Next task: {{ current_task }}
```
{% endraw %}
```

#### `preload_messages`

**Type**: `Messages` (list of message dicts)
**Default**: `[]` (empty list)
**Description**: Initial messages to pre-load into conversation history.

**Usage**:
```python
config = AgentConfig(
    model=model,
    preload_messages=[
        {
            "role": "user",
            "content": [{"text": "Hello, I need help with data analysis."}]
        },
        {
            "role": "assistant",
            "content": [{"text": "I'd be happy to help with data analysis. What dataset are you working with?"}]
        }
    ]
)
```

**Message Format**:
```python
{
    "role": "user" | "assistant" | "system",
    "content": [
        {"text": "message text"},
        {"image": {...}},  # Image content
        {"toolUse": {...}},  # Tool call
        {"toolResult": {...}}  # Tool result
    ]
}
```

**Example - Common Patterns**:
```python
# Few-shot examples
preload_messages = [
    {"role": "user", "content": [{"text": "Analyze: [1, 2, 3, 4, 5]"}]},
    {"role": "assistant", "content": [{"text": "Mean: 3.0, Median: 3, Std Dev: 1.41"}]},
    {"role": "user", "content": [{"text": "Analyze: [10, 20, 30]"}]},
    {"role": "assistant", "content": [{"text": "Mean: 20.0, Median: 20, Std Dev: 8.16"}]}
]

# Context setting
preload_messages = [
    {
        "role": "system",
        "content": [{"text": "User preferences: technical level=expert, format=json"}]
    }
]
```

### Memory Configuration

#### `memory_config`

**Type**: `MemoryConfig`
**Default**: `MemoryConfig()` (rolling window with size 10)
**Description**: Configuration for conversation history management.

**Usage**:
```python
from spark.agents.memory import MemoryConfig, MemoryPolicyType

config = AgentConfig(
    model=model,
    memory_config=MemoryConfig(
        policy=MemoryPolicyType.ROLLING_WINDOW,
        window=20
    )
)
```

**MemoryConfig Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `policy` | MemoryPolicyType | ROLLING_WINDOW | Memory management policy |
| `window` | int | 10 | Number of messages to retain |
| `summary_max_chars` | int | 1000 | Max characters for summaries (SUMMARIZE policy) |
| `callable` | Callable \| None | None | Custom memory management function |

**Memory Policy Types**:

| Policy | Description | Use Case |
|--------|-------------|----------|
| `NULL` | No memory retention | Stateless agents, one-shot queries |
| `ROLLING_WINDOW` | Keep last N messages | Standard conversation agents |
| `SUMMARIZE` | Compress old messages into summary | Long conversations, context preservation |
| `CUSTOM` | User-provided function | Custom memory logic |

**Example - Memory Policies**:
```python
# No memory (stateless)
memory_config = MemoryConfig(policy=MemoryPolicyType.NULL)

# Short rolling window (fast, limited context)
memory_config = MemoryConfig(
    policy=MemoryPolicyType.ROLLING_WINDOW,
    window=5
)

# Long rolling window (more context, more tokens)
memory_config = MemoryConfig(
    policy=MemoryPolicyType.ROLLING_WINDOW,
    window=50
)

# Summarization (context preservation, efficient)
memory_config = MemoryConfig(
    policy=MemoryPolicyType.SUMMARIZE,
    window=10,
    summary_max_chars=500
)

# Custom memory management
def custom_memory_fn(messages):
    # Keep only important messages
    return [m for m in messages if m.get('important', False)]

memory_config = MemoryConfig(
    policy=MemoryPolicyType.CUSTOM,
    callable=custom_memory_fn
)
```

### Output Configuration

#### `output_mode`

**Type**: `Literal['json', 'text']`
**Default**: `'text'`
**Description**: Output format for agent responses.

**Usage**:
```python
# Text mode (default)
config = AgentConfig(model=model, output_mode='text')

# JSON mode (structured output)
config = AgentConfig(model=model, output_mode='json')
```

**Notes**:
- `'text'`: Free-form text responses
- `'json'`: Structured JSON output validated against schema
- JSON mode requires `output_schema` or model's default parsing
- Reasoning strategies like ReAct require JSON mode

**Example**:
```python
# JSON mode with schema
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    key_points: list[str]
    confidence: float

config = AgentConfig(
    model=model,
    output_mode='json',
    output_schema=AnalysisResult
)

response = await agent.run("Analyze this data...")
# response.parsed is an AnalysisResult instance
```

#### `output_schema`

**Type**: `type[BaseModel]`
**Default**: `DefaultOutputSchema` (permissive schema)
**Description**: Pydantic model class defining expected output structure.

**Usage**:
```python
from pydantic import BaseModel, Field

class TaskResult(BaseModel):
    status: str = Field(description="Status: success, failure, or pending")
    result: dict = Field(description="Task results")
    errors: list[str] = Field(default_factory=list)

config = AgentConfig(
    model=model,
    output_mode='json',
    output_schema=TaskResult
)
```

**Notes**:
- Only used when `output_mode='json'`
- Provides type safety and validation
- Model will generate JSON matching the schema
- Use Pydantic's `Field()` for descriptions (helps model)

**Example - Common Schemas**:
```python
# Extraction schema
class EntityExtraction(BaseModel):
    entities: list[dict[str, str]]
    relationships: list[tuple[str, str, str]]
    metadata: dict

# Classification schema
class Classification(BaseModel):
    category: str
    confidence: float
    reasoning: str

# Multi-step reasoning schema
class ReasoningStep(BaseModel):
    thought: str
    action: str | None
    observation: str | None

class ReasoningOutput(BaseModel):
    steps: list[ReasoningStep]
    final_answer: str
```

### Tool Configuration

#### `tools`

**Type**: `list[Any]`
**Default**: `[]` (no tools)
**Description**: List of tools available to the agent.

**Usage**:
```python
from spark.tools.decorator import tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return search(query)

@tool
def calculate(expression: str) -> float:
    """Evaluate a mathematical expression."""
    return eval(expression)

config = AgentConfig(
    model=model,
    tools=[search_web, calculate]
)
```

**Tool Types Supported**:
- Functions decorated with `@tool`
- `Tool` class instances
- Module paths (e.g., `"myapp.tools:search_tool"`)
- Tool names from registry

**Example - Common Patterns**:
```python
# Multiple tools
tools = [search_web, calculate, read_file, write_file]

# Tools from module
tools = ["myapp.tools:search", "myapp.tools:analyze"]

# Mix of types
tools = [
    search_web,  # Function
    "myapp.tools:database",  # Module reference
    custom_tool_instance  # Tool instance
]
```

**Notes**:
- Tools are automatically registered with the agent
- Tool specs are sent to the model for selection
- See [Tools Guide](../tools/tools.md) for details

#### `tool_choice`

**Type**: `Literal['auto', 'any', 'none'] | str`
**Default**: `'auto'`
**Description**: Strategy for tool selection.

**Usage**:
```python
# Let model decide (default)
config = AgentConfig(model=model, tool_choice='auto')

# Force model to use a tool (any tool)
config = AgentConfig(model=model, tool_choice='any')

# Disable tools for this call
config = AgentConfig(model=model, tool_choice='none')

# Force specific tool
config = AgentConfig(model=model, tool_choice='search_web')
```

**Options**:

| Value | Description | Use Case |
|-------|-------------|----------|
| `'auto'` | Model decides whether to use tools | General purpose agents |
| `'any'` | Model must use at least one tool | Tool-dependent workflows |
| `'none'` | Disable all tools | Text-only responses |
| `<tool_name>` | Force specific tool | Constrained tool usage |

**Validation**:
- `'any'` requires at least one tool configured
- Tool name must exist in tool list
- Incompatible with empty tool list

#### `record_direct_tool_call`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to record tool calls in conversation history.

**Usage**:
```python
config = AgentConfig(
    model=model,
    tools=[search_web],
    record_direct_tool_call=True  # Record tool calls in history
)
```

**Notes**:
- When `True`, tool calls appear in conversation history
- When `False`, only tool results are visible
- Affects memory usage and context size

#### `max_steps`

**Type**: `int`
**Default**: `100`
**Description**: Maximum tool execution steps per agent run.

**Usage**:
```python
# Limit to 10 tool calls
config = AgentConfig(model=model, max_steps=10)

# Unlimited tool calls
config = AgentConfig(model=model, max_steps=0)

# Single-shot (no tool iteration)
config = AgentConfig(model=model, max_steps=1)
```

**Notes**:
- Prevents infinite loops in tool-calling agents
- `0` means unlimited (use with caution)
- Counts tool invocation rounds, not individual tool calls
- Raises error when exceeded

#### `parallel_tool_execution`

**Type**: `bool`
**Default**: `False`
**Description**: Execute multiple tool calls concurrently.

**Usage**:
```python
config = AgentConfig(
    model=model,
    tools=[search_web, fetch_data, analyze],
    parallel_tool_execution=True  # Execute tools in parallel
)
```

**Notes**:
- **Performance**: Faster when multiple tools called simultaneously
- **Thread safety**: Only enable if tools are independent and thread-safe
- **Dependencies**: Tools with dependencies must run sequentially
- **Error handling**: Failure in one tool doesn't block others

**Example**:
```python
# Parallel execution for independent tools
config = AgentConfig(
    model=model,
    tools=[search_google, search_wikipedia, fetch_weather],
    parallel_tool_execution=True  # All searches run concurrently
)

# Sequential execution for dependent tools
config = AgentConfig(
    model=model,
    tools=[connect_db, fetch_data, transform_data],
    parallel_tool_execution=False  # Must run in order
)
```

### Reasoning Configuration

#### `reasoning_strategy`

**Type**: `ReasoningStrategy | str | None`
**Default**: `None` (uses NoOpStrategy)
**Description**: Reasoning strategy for structured thinking patterns.

**Usage**:
```python
from spark.agents.strategies import ReActStrategy, ChainOfThoughtStrategy

# ReAct strategy (Reasoning + Acting)
config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy=ReActStrategy(verbose=True)
)

# Chain-of-Thought strategy
config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy=ChainOfThoughtStrategy()
)

# By name (spec-compatible)
config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy="react"
)
```

**Available Strategies**:

| Strategy | Description | Use Case | Requires JSON Mode |
|----------|-------------|----------|-------------------|
| `NoOpStrategy` | No structured reasoning (default) | Simple Q&A, direct responses | No |
| `ReActStrategy` | Iterative reasoning with tool calling | Complex multi-step problems | Yes |
| `ChainOfThoughtStrategy` | Step-by-step reasoning | Math, logic, planning | Yes |
| Custom | User-defined strategy | Domain-specific reasoning | Varies |

**Example - Strategy Configuration**:
```python
# ReAct with configuration
react = ReActStrategy(
    verbose=True,
    max_iterations=10
)

# Chain-of-Thought
cot = ChainOfThoughtStrategy()

# No reasoning (default)
config = AgentConfig(model=model, reasoning_strategy=None)
```

**Notes**:
- Most strategies require `output_mode='json'`
- Strategies can maintain state across steps
- See [Reasoning Strategies](../agents/strategies.md) for details

### Hooks

#### `hooks`

**Type**: `list[Any] | None`
**Default**: `None`
**Description**: Hook providers to add to agent hook registry.

**Usage**:
```python
config = AgentConfig(
    model=model,
    hooks=[LoggingHookProvider(), MetricsHookProvider()]
)
```

**Notes**:
- Hooks provide cross-cutting concerns (logging, metrics, tracing)
- See [Agent Hooks](../agents/hooks.md) for details

#### `before_llm_hooks`

**Type**: `list[HookRef]`
**Default**: `[]` (empty list)
**Description**: Hooks executed before each LLM call.

**Usage**:
```python
def log_request(agent, messages, **kwargs):
    print(f"Calling LLM with {len(messages)} messages")

def add_timestamp(agent, messages, **kwargs):
    kwargs['metadata'] = {'timestamp': time.time()}

config = AgentConfig(
    model=model,
    before_llm_hooks=[log_request, add_timestamp]
)

# Or use string references (spec-compatible)
config = AgentConfig(
    model=model,
    before_llm_hooks=["myapp.hooks:log_request", "myapp.hooks:add_timestamp"]
)
```

**Hook Signature**:
```python
def hook(agent: Agent, messages: Messages, **kwargs) -> None:
    # Can modify messages or kwargs in-place
    pass

async def async_hook(agent: Agent, messages: Messages, **kwargs) -> None:
    # Async hooks also supported
    pass
```

#### `after_llm_hooks`

**Type**: `list[HookRef]`
**Default**: `[]` (empty list)
**Description**: Hooks executed after each LLM call.

**Usage**:
```python
def log_response(agent, response, **kwargs):
    print(f"Received response: {response[:100]}")

def track_cost(agent, response, **kwargs):
    # Track token usage and cost
    pass

config = AgentConfig(
    model=model,
    after_llm_hooks=[log_response, track_cost]
)
```

**Hook Signature**:
```python
def hook(agent: Agent, response: Any, **kwargs) -> None:
    # Access response and metadata
    pass
```

### Budget and Policies

#### `budget`

**Type**: `AgentBudgetConfig | None`
**Default**: `None` (no budget)
**Description**: Runtime budget enforcement for cost and resource control.

**Usage**:
```python
from spark.agents.policies import AgentBudgetConfig

config = AgentConfig(
    model=model,
    budget=AgentBudgetConfig(
        max_total_cost=1.0,  # $1.00 max cost
        max_total_tokens=10000,  # 10k tokens max
        max_llm_calls=50,  # 50 calls max
        max_runtime_seconds=300.0  # 5 minutes max
    )
)
```

**AgentBudgetConfig Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `max_total_cost` | float \| None | Maximum cumulative cost in USD |
| `max_total_tokens` | int \| None | Maximum total tokens (input + output) |
| `max_input_tokens` | int \| None | Maximum input tokens |
| `max_output_tokens` | int \| None | Maximum output tokens |
| `max_llm_calls` | int \| None | Maximum LLM API calls |
| `max_runtime_seconds` | float \| None | Maximum runtime in seconds |

**Example - Budget Patterns**:
```python
# Cost-limited agent
budget = AgentBudgetConfig(max_total_cost=0.50)

# Token-limited agent
budget = AgentBudgetConfig(
    max_input_tokens=5000,
    max_output_tokens=2000
)

# Time-limited agent
budget = AgentBudgetConfig(max_runtime_seconds=60.0)

# Combined limits
budget = AgentBudgetConfig(
    max_total_cost=2.0,
    max_total_tokens=20000,
    max_llm_calls=100,
    max_runtime_seconds=600.0
)
```

**Notes**:
- Raises `AgentBudgetExceededError` when limit exceeded
- Useful for preventing runaway costs
- Enforced during agent execution

#### `human_policy`

**Type**: `HumanInteractionPolicy | None`
**Default**: `None` (no human intervention)
**Description**: Policy for human-in-the-loop controls.

**Usage**:
```python
from spark.agents.policies import HumanInteractionPolicy

config = AgentConfig(
    model=model,
    human_policy=HumanInteractionPolicy(
        require_tool_approval=True,
        auto_approved_tools=['search_web', 'calculate'],
        stop_token='emergency_stop'
    )
)
```

**HumanInteractionPolicy Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `require_tool_approval` | bool | False | Require approval before tool execution |
| `auto_approved_tools` | list[str] | [] | Tools that bypass approval |
| `stop_token` | str \| None | None | Token to pause agent |
| `pause_on_stop_signal` | bool | True | Pause when stop token triggered |
| `metadata` | dict | {} | Arbitrary policy metadata |

**Example**:
```python
# Require approval for all tools
policy = HumanInteractionPolicy(require_tool_approval=True)

# Require approval except for safe tools
policy = HumanInteractionPolicy(
    require_tool_approval=True,
    auto_approved_tools=['search', 'calculate', 'read_file']
)

# Emergency stop capability
policy = HumanInteractionPolicy(
    stop_token='emergency_stop_123',
    pause_on_stop_signal=True
)

# Issue stop signal from another thread
HumanPolicyManager.issue_stop_signal('emergency_stop_123', reason='User intervention')
```

#### `policy_set`

**Type**: `PolicySet | None`
**Default**: `None` (no governance)
**Description**: Governance policies enforced before tool execution.

**Usage**:
```python
from spark.governance import PolicyEngine, PolicyRule, PolicyEffect

engine = PolicyEngine()
engine.add_rule(PolicyRule(
    name="prevent_dangerous_tools",
    effect=PolicyEffect.DENY,
    conditions={"tool_name": {"in": ["shell_exec", "file_delete"]}}
))

config = AgentConfig(
    model=model,
    policy_set=engine.policy_set
)
```

**Notes**:
- Enforces organizational policies
- Can deny, allow, or require approval
- See [Governance Guide](../architecture/governance.md) for details

## Complete Configuration Example

{% raw %}
```python
from spark.agents import Agent, AgentConfig
from spark.agents.memory import MemoryConfig, MemoryPolicyType
from spark.agents.policies import AgentBudgetConfig, HumanInteractionPolicy
from spark.agents.strategies import ReActStrategy
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

# Define tools
@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return search(query)

@tool
def analyze_data(data: dict) -> dict:
    """Analyze data and return insights."""
    return analyze(data)

# Create model with caching
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600
)

# Production agent configuration
config = AgentConfig(
    # Identity
    model=model,
    name="ProductionAgent",
    description="Production-grade agent with full configuration",

    # Prompting
    system_prompt="""You are a data analysis assistant.
Use the provided tools to search for information and analyze data.
Be precise and explain your reasoning.""",

    prompt_template="""
Task: {{ task }}
Context: {{ context }}

Provide analysis with tool usage.
""",

    # Memory
    memory_config=MemoryConfig(
        policy=MemoryPolicyType.SUMMARIZE,
        window=20,
        summary_max_chars=1000
    ),

    # Output
    output_mode='json',
    output_schema=AnalysisResult,

    # Tools
    tools=[search_web, analyze_data],
    tool_choice='auto',
    max_steps=50,
    parallel_tool_execution=True,

    # Reasoning
    reasoning_strategy=ReActStrategy(verbose=True),

    # Hooks
    before_llm_hooks=[log_request, validate_input],
    after_llm_hooks=[log_response, track_metrics],

    # Budget
    budget=AgentBudgetConfig(
        max_total_cost=5.0,
        max_total_tokens=50000,
        max_runtime_seconds=600.0
    ),

    # Human-in-the-loop
    human_policy=HumanInteractionPolicy(
        require_tool_approval=True,
        auto_approved_tools=['search_web']
    )
)

# Create and use agent
agent = Agent(config=config)
response = await agent.run("Analyze recent sales trends")
```
{% endraw %}

## Configuration Patterns

### Development Configuration

```python
config = AgentConfig(
    model=model,
    output_mode='text',
    max_steps=10,
    memory_config=MemoryConfig(policy=MemoryPolicyType.NULL),
    before_llm_hooks=[debug_hook]
)
```

### Production Configuration

```python
config = AgentConfig(
    model=model,
    output_mode='json',
    output_schema=ProductionSchema,
    max_steps=100,
    parallel_tool_execution=True,
    memory_config=MemoryConfig(policy=MemoryPolicyType.SUMMARIZE, window=50),
    budget=AgentBudgetConfig(max_total_cost=10.0),
    before_llm_hooks=[metrics_hook, trace_hook],
    after_llm_hooks=[cost_track_hook, alert_hook]
)
```

### Testing Configuration

```python
config = AgentConfig(
    model=mock_model,
    output_mode='json',
    max_steps=5,
    memory_config=MemoryConfig(policy=MemoryPolicyType.NULL),
    budget=AgentBudgetConfig(max_llm_calls=10)
)
```

## Validation

AgentConfig automatically validates configuration for consistency:

**Validation Rules**:
- `tool_choice='any'` requires at least one tool
- `output_schema` only meaningful with `output_mode='json'`
- `max_steps` must be non-negative
- `memory_config.window` must be positive
- `memory_config.policy` must be valid enum value

**Example Validation Errors**:
```python
# Error: tool_choice='any' without tools
config = AgentConfig(model=model, tool_choice='any', tools=[])
# ValueError: tool_choice='any' requires at least one tool

# Warning: output_schema without JSON mode
config = AgentConfig(
    model=model,
    output_mode='text',
    output_schema=MySchema
)
# Warning: output_schema is set but output_mode is 'text'

# Error: invalid max_steps
config = AgentConfig(model=model, max_steps=-1)
# ValueError: max_steps must be non-negative
```

## Serialization

AgentConfig supports serialization to/from dictionaries for specifications:

```python
# Serialize to dict
spec_dict = config.to_spec_dict()

# Deserialize from dict
config = AgentConfig.from_spec_dict(spec_dict, model=model)
```

**Notes**:
- Hooks serialized as string references
- Reasoning strategies serialized by name or reference
- Model must be provided separately (not serialized)
- Tools require separate serialization mechanism

## See Also

- [Agent Guide](../agents/agents.md) - Agent architecture and usage
- [Reasoning Strategies](../agents/strategies.md) - Strategy system
- [Tools Guide](../tools/tools.md) - Tool system
- [NodeConfig Reference](node-config.md) - Base node configuration
- [Memory Management](../agents/memory.md) - Memory policies
