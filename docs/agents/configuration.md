---
title: Agent Configuration
parent: Agent
nav_order: 1
---
# Agent Configuration
---

`AgentConfig` is the primary configuration object for agents, providing validation and type safety for all agent settings. Configuration includes:

- Model selection and parameters
- Tool registration
- Prompt templates (system and user prompts)
- Output modes (text vs. structured JSON)
- Memory policies and settings
- Reasoning strategy selection
- Execution settings (step limits, parallel execution)
- Cost tracking options

## AgentConfig Class

### Complete Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | `Model` | Required | LLM model instance (OpenAI, Bedrock, Gemini) |
| `tools` | `List[BaseTool]` | `[]` | List of tools available to the agent |
| `system_prompt` | `str` | `None` | System prompt template (supports Jinja2) |
| `user_prompt_template` | `str` | `None` | User message template (supports Jinja2) |
| `output_mode` | `str` | `"text"` | Output format: "text" or "json" |
| `max_steps` | `int` | `10` | Maximum reasoning/tool calling steps |
| `memory_policy` | `MemoryPolicy` | `FULL` | Memory management strategy |
| `memory_config` | `dict` | `{}` | Policy-specific memory configuration |
| `reasoning_strategy` | `ReasoningStrategy` | `NoOpStrategy()` | Reasoning pattern implementation |
| `parallel_tool_execution` | `bool` | `False` | Enable concurrent tool execution |
| `enable_cost_tracking` | `bool` | `True` | Track token usage and API costs |
| `cost_tracker_config` | `dict` | `{}` | Cost tracker configuration |
| `validation_rules` | `dict` | `{}` | Custom validation rules |

### Basic Configuration

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Minimal configuration
model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(model=model)
agent = Agent(config=config)

# Full configuration
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant.",
    max_steps=5,
    output_mode="text",
    memory_policy=MemoryPolicy.FULL,
    parallel_tool_execution=True,
    enable_cost_tracking=True
)
agent = Agent(config=config)
```

## Model Configuration

### OpenAI Models

Configure OpenAI and OpenAI-compatible providers:

```python
from spark.models.openai import OpenAIModel

# Basic OpenAI configuration
model = OpenAIModel(
    model_id="gpt-5-mini",
    temperature=0.7,
    max_tokens=2000,
    api_key="your-api-key"  # Or set OPENAI_API_KEY env var
)

# With response caching
model = OpenAIModel(
    model_id="gpt-5-mini",
    temperature=0.7,
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour cache
)

# OpenAI-compatible provider (e.g., Azure, custom endpoint)
model = OpenAIModel(
    model_id="gpt-4",
    api_base="https://custom-endpoint.com/v1",
    api_key="your-key"
)

config = AgentConfig(model=model)
```

### AWS Bedrock Models

Configure AWS Bedrock models (Claude, Titan, etc.):

```python
from spark.models.bedrock import BedrockModel

# Basic Bedrock configuration
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-east-1",
    temperature=0.7,
    max_tokens=4096
)

# With AWS credentials
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-west-2",
    aws_access_key_id="your-key-id",
    aws_secret_access_key="your-secret-key",
    aws_session_token="your-session-token"  # Optional
)

# With guardrails
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    guardrail_config={
        "guardrailIdentifier": "guardrail-id",
        "guardrailVersion": "1"
    }
)

config = AgentConfig(model=model)
```

### Google Gemini Models

Configure Google Gemini models:

```python
from spark.models.gemini import GeminiModel

# Basic Gemini configuration
model = GeminiModel(
    model_id="gemini-1.5-pro",
    temperature=0.9,
    max_tokens=2048,
    api_key="your-google-api-key"
)

config = AgentConfig(model=model)
```

### Model Selection Guidelines

| Use Case | Recommended Model | Reasoning |
|----------|------------------|-----------|
| General purpose | `gpt-5.2` | Balanced performance and cost |
| Low latency | `gpt-5-mini` | Fast, cost-effective |
| Complex reasoning | `claude-sonnet-4-5` | Superior reasoning capabilities |
| Long context | `gemini-3-pro` | 1 million token context window |
| Cost-sensitive | `gpt-5-nano` | Lowest cost per token |
| Production (AWS) | Bedrock models | Better rate limits, SLAs |

## Tool Registration

### Registering Tools

Tools are registered via the `tools` parameter:

```python
from spark.agents import AgentConfig
from spark.tools.decorator import tool

# Define tools
@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: Search query string
    """
    # Implementation
    return search_results

@tool
def calculate(expression: str) -> float:
    """Evaluate a mathematical expression.

    Args:
        expression: Math expression to evaluate
    """
    return eval(expression)

# Register tools with agent
config = AgentConfig(
    model=model,
    tools=[search_web, calculate]
)

agent = Agent(config=config)
```

### Tool Validation

Tools are validated at configuration time:

```python
# Invalid tool raises error at config creation
@tool
def invalid_tool():
    """Missing type hints and return type."""
    pass

config = AgentConfig(
    model=model,
    tools=[invalid_tool]  # Raises ValidationError
)
```

### Tool Context Injection

Tools can receive execution context:

```python
from spark.tools.decorator import tool
from spark.tools.types import ToolContext

@tool
def get_user_data(user_id: str, context: ToolContext = None) -> dict:
    """Get user data with context awareness.

    Args:
        user_id: User identifier
        context: Tool execution context (injected)
    """
    # Access context metadata
    if context:
        agent_id = context.metadata.get("agent_id")
        print(f"Called by agent: {agent_id}")

    return {"user_id": user_id, "name": "Alice"}

config = AgentConfig(
    model=model,
    tools=[get_user_data]
)
```

See [Tools Reference](tools.md) for complete tool documentation.

## Prompt Templates and System Prompts

### System Prompts

System prompts define agent behavior and persona:

```python
# Basic system prompt
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant specializing in Python programming."
)

# Detailed system prompt
system_prompt = """You are an expert data analyst assistant.

Your responsibilities:
- Analyze datasets and provide insights
- Create visualizations when helpful
- Explain statistical concepts clearly
- Recommend appropriate analysis techniques

Guidelines:
- Always verify data quality first
- Explain your reasoning step-by-step
- Ask clarifying questions when needed
- Provide actionable recommendations
"""

config = AgentConfig(
    model=model,
    system_prompt=system_prompt
)
```

### Jinja2 Templating

Templates support Jinja2 syntax for dynamic prompts:

{% raw %}
```python
from spark.agents import AgentConfig

# Template with variables
system_template = """You are {{ role }}.

Your expertise: {{ expertise }}
Your tone: {{ tone }}

Available tools: {{ tools|length }}
"""

config = AgentConfig(
    model=model,
    system_prompt=system_template
)

# Render with context
agent = Agent(config=config)
result = await agent.run(
    user_message="Help me",
    context={
        "role": "senior developer",
        "expertise": "Python and ML",
        "tone": "friendly and professional"
    }
)
```
{% endraw %}

### User Prompt Templates

Customize user message formatting:

{% raw %}
```python
# Template for user messages
user_template = """User Query: {{ query }}

Context:
{% if context %}
{{ context }}
{% endif %}

Please respond with:
1. Analysis
2. Recommendations
3. Next steps
"""

config = AgentConfig(
    model=model,
    user_prompt_template=user_template
)

agent = Agent(config=config)
result = await agent.run(
    user_message="Analyze this data",
    context={"data": "..."}
)
```
{% endraw %}

### Template Variables

Available variables in templates:

| Variable | Description | Example |
|----------|-------------|---------|
| `query` | User message | `{% raw %}{{ query }}{% endraw %}` |
| `context` | Additional context dict | `{% raw %}{{ context.key }}{% endraw %}` |
| `tools` | Available tools list | `{% raw %}{{ tools|length }}{% endraw %}` |
| `history_length` | Conversation history size | `{% raw %}{{ history_length }}{% endraw %}` |
| Custom variables | From context dict | `{% raw %}{{ context.custom_var }}{% endraw %}` |

### Template Filters

Jinja2 filters for formatting:

{% raw %}
```python
system_prompt = """Tools available: {{ tools|map(attribute='tool_name')|join(', ') }}

Context summary: {{ context.text|truncate(100) }}

Date: {{ context.date|default('Unknown') }}
"""
```
{% endraw %}

## Output Modes

### Text Mode (Default)

Text mode returns plain string responses:

```python
config = AgentConfig(
    model=model,
    output_mode="text"
)

agent = Agent(config=config)
result = await agent.run(user_message="Hello")
print(result)  # "Hello! How can I help you today?"
```

### JSON Mode

JSON mode returns structured output:

```python
config = AgentConfig(
    model=model,
    output_mode="json",
    system_prompt="Always respond with JSON containing 'response' and 'confidence' fields."
)

agent = Agent(config=config)
result = await agent.run(user_message="What is 2+2?")
print(result)
# {"response": "4", "confidence": 1.0}
```

### JSON Mode with Reasoning Strategies

JSON mode required for ReAct and Chain-of-Thought strategies:

```python
from spark.agents import ReActStrategy

config = AgentConfig(
    model=model,
    output_mode="json",  # Required for ReAct
    reasoning_strategy=ReActStrategy(verbose=True)
)

agent = Agent(config=config)
result = await agent.run(user_message="Search for Python tutorials")
# Returns structured JSON with thought, action, observation
```

### Output Mode Selection

| Mode | Use Case | Pros | Cons |
|------|----------|------|------|
| `text` | General conversation | Natural, human-readable | Harder to parse programmatically |
| `json` | Programmatic use | Structured, parseable | Requires schema definition |
| `json` + ReAct | Complex reasoning | Transparent reasoning | More verbose, higher token cost |

## Memory Policies

### Memory Policy Types

```python
from spark.agents import MemoryPolicy

# Full memory - keep everything
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL
)

# Rolling window - keep last N tokens
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={"window_size": 4000}
)

# Summarization - auto-summarize old context
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SUMMARIZATION,
    memory_config={
        "max_tokens": 4000,
        "summary_ratio": 0.3
    }
)
```

### Memory Configuration Parameters

#### Full Memory

No configuration needed - keeps complete history.

```python
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL
)
```

#### Sliding Window Memory

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_size` | `int` | `4000` | Maximum tokens to keep in window |

```python
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={
        "window_size": 8000  # Keep last 8K tokens
    }
)
```

#### Summarization Memory

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_tokens` | `int` | `4000` | Threshold for triggering summarization |
| `summary_ratio` | `float` | `0.3` | Target summary length as ratio of original |
| `summary_model` | `Model` | `None` | Optional separate model for summarization |

```python
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SUMMARIZATION,
    memory_config={
        "max_tokens": 6000,
        "summary_ratio": 0.25,  # Compress to 25% of original
        "summary_model": lightweight_model  # Optional
    }
)
```

See [Memory Management Reference](memory.md) for detailed memory documentation.

## Reasoning Strategy Selection

### Available Strategies

```python
from spark.agents import (
    NoOpStrategy,
    ReActStrategy,
    ChainOfThoughtStrategy,
    PlanAndSolveStrategy
)

# No reasoning structure (default)
config = AgentConfig(
    model=model,
    reasoning_strategy=NoOpStrategy()
)

# ReAct: Reasoning + Acting
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=ReActStrategy(verbose=True)
)

# Chain-of-Thought: Step-by-step reasoning
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=ChainOfThoughtStrategy()
)

# Plan-and-Solve: Planning first, then execution
config = AgentConfig(
    model=model,
    output_mode="json",  # Required
    reasoning_strategy=PlanAndSolveStrategy(
        max_plan_steps=5,
        allow_replanning=True
    )
)
```

### Strategy Parameters

#### NoOpStrategy

No parameters - simple direct responses.

#### ReActStrategy

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `verbose` | `bool` | `False` | Log reasoning steps |
| `max_iterations` | `int` | `None` | Override agent max_steps |

#### ChainOfThoughtStrategy

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `verbose` | `bool` | `False` | Log reasoning steps |

#### PlanAndSolveStrategy

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_plan_steps` | `int` | `10` | Maximum steps in plan |
| `allow_replanning` | `bool` | `True` | Allow plan modification |
| `verbose` | `bool` | `False` | Log planning steps |

See [Reasoning Strategies Reference](reasoning-strategies.md) for detailed strategy documentation.

## Execution Settings

### Maximum Steps

Limit reasoning and tool calling iterations:

```python
config = AgentConfig(
    model=model,
    max_steps=5  # Stop after 5 reasoning steps
)
```

Typical values:

| Use Case | Recommended max_steps |
|----------|----------------------|
| Simple Q&A | 1-3 |
| Single tool use | 3-5 |
| Multi-step reasoning | 5-10 |
| Complex workflows | 10-20 |
| Safety limit | 20-30 |

### Parallel Tool Execution

Enable concurrent tool execution for performance:

```python
config = AgentConfig(
    model=model,
    tools=[search_web, get_weather, calculate],
    parallel_tool_execution=True  # Execute independent tools concurrently
)
```

Benefits:
- Faster execution when multiple tools called
- Better resource utilization
- Automatic error handling

Trade-offs:
- Tools must be independent (no shared state)
- Errors in one tool don't block others
- Slightly more complex debugging

See [Tools Reference](tools.md) for parallel execution details.

## Validation Rules

### Custom Validation

Add custom validation rules to configuration:

```python
config = AgentConfig(
    model=model,
    validation_rules={
        "require_tools": True,  # Require at least one tool
        "max_prompt_length": 1000,  # Limit system prompt length
        "allowed_models": ["gpt-5.2", "gpt-5-mini"],  # Whitelist models
    }
)
```

### Built-in Validation

AgentConfig validates:

- Model instance is valid
- Tool specifications are complete
- Memory policy is supported
- Output mode is "text" or "json"
- max_steps is positive
- Templates are valid Jinja2

### Validation Errors

Configuration errors raise `ValueError` with details:

```python
from spark.agents import AgentConfig

try:
    config = AgentConfig(
        model=None,  # Invalid - model required
        max_steps=-1  # Invalid - must be positive
    )
except ValueError as e:
    print(f"Configuration error: {e}")
```

## Configuration Examples

### Minimal Configuration

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(model=model)
agent = Agent(config=config)
```

### Production Configuration

```python
from spark.agents import (
    Agent, AgentConfig, MemoryPolicy, ReActStrategy
)
from spark.models.bedrock import BedrockModel
from spark.tools.decorator import tool

# Define tools
@tool
def search_database(query: str) -> dict:
    """Search internal database."""
    # Implementation
    return {"results": [...]}

# Configure model with caching
model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name="us-east-1",
    temperature=0.7,
    max_tokens=4096
)

# Production configuration
config = AgentConfig(
    model=model,
    tools=[search_database],
    system_prompt="""You are a customer service assistant.

Guidelines:
- Be professional and helpful
- Verify customer identity before accessing data
- Escalate complex issues to human agents
- Log all interactions
""",
    output_mode="json",
    max_steps=10,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={"window_size": 8000},
    reasoning_strategy=ReActStrategy(verbose=False),
    parallel_tool_execution=True,
    enable_cost_tracking=True
)

agent = Agent(config=config)
```

### Development Configuration

```python
# Development config with caching and verbose logging
from spark.agents import Agent, AgentConfig, ChainOfThoughtStrategy
from spark.models.openai import OpenAIModel

model = OpenAIModel(
    model_id="gpt-5-mini",  # Cheaper for dev
    enable_cache=True,  # Fast iteration
    cache_ttl_seconds=3600
)

config = AgentConfig(
    model=model,
    system_prompt="You are a test assistant.",
    output_mode="json",
    max_steps=5,
    reasoning_strategy=ChainOfThoughtStrategy(verbose=True),
    enable_cost_tracking=True
)

agent = Agent(config=config)
```

## Configuration Best Practices

### 1. Always Set System Prompts

Define clear agent behavior:

```python
# Good
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant specializing in..."
)

# Avoid - unclear behavior
config = AgentConfig(model=model)
```

### 2. Use Appropriate Memory Policies

Choose based on context length needs:

```python
# Short conversations - full memory
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL
)

# Long conversations - sliding window
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={"window_size": 8000}
)
```

### 3. Enable Caching in Development

Speed up iteration:

```python
model = OpenAIModel(
    model_id="gpt-5-mini",
    enable_cache=True,
    cache_ttl_seconds=3600
)
```

### 4. Set Reasonable max_steps

Prevent runaway costs:

```python
config = AgentConfig(
    model=model,
    max_steps=10,  # Reasonable limit
    tools=[...]
)
```

### 5. Use JSON Mode for Structured Output

Enable programmatic parsing:

```python
config = AgentConfig(
    model=model,
    output_mode="json",
    system_prompt="Respond with JSON containing 'answer' and 'confidence'."
)
```

## Next Steps

- Review [Memory Management](memory.md) for conversation history strategies
- Explore [Reasoning Strategies](reasoning-strategies.md) for advanced reasoning
- See [Tools Reference](tools.md) for tool integration
- Learn about [Cost Tracking](cost-tracking.md) for monitoring expenses
