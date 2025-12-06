---
title: Models
nav_order: 8
---
# Model Abstraction

The Spark Models System provides a unified abstraction layer for working with Large Language Models (LLMs) from different providers. This abstraction enables you to write code once and seamlessly switch between providers without changing your application logic.

## Why Model Abstraction Matters

### Provider Independence

Spark agents are **model-agnostic** by design. The abstraction layer means:

- Write agent logic once, swap models without code changes
- Switch providers based on cost, performance, or availability
- Test with cheap models, deploy with powerful models
- Compare providers easily for your specific use case
- Avoid vendor lock-in

### Unified Interface

All model providers implement the same core interface:

```python
from spark.models.openai import OpenAIModel

# Works the same way regardless of provider
model = OpenAIModel(model_id="gpt-4o")

messages = [
    {"role": "user", "content": [{"text": "What is the capital of France?"}]}
]

# Standard method across all providers
response = await model.get_text(messages=messages)
print(response.content)  # "The capital of France is Paris."
```

### Integration with Agents

The abstraction layer is what makes Spark agents portable:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Create agent with OpenAI
model = OpenAIModel(model_id="gpt-4o")
config = AgentConfig(model=model)
agent = Agent(config=config)

# Later: Switch to different provider by changing one line
# from spark.models.bedrock import BedrockModel
# model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5")
# config = AgentConfig(model=model)  # Agent code unchanged!
```

## The Model Interface

All model providers in Spark inherit from the abstract `Model` base class and implement these core methods:

### Core Methods

#### `get_text()`

Get a text completion from the model.

```python
async def get_text(
    self,
    messages: Messages,
    system_prompt: str | None = None,
    tool_specs: list[dict] | None = None,
    tool_choice: dict | None = None,
    **kwargs
) -> ModelResponse:
    """Get text completion from the model."""
```

**Parameters**:
- `messages`: List of conversation messages in unified format
- `system_prompt`: Optional system prompt to set model behavior
- `tool_specs`: Optional list of tool specifications for tool calling
- `tool_choice`: Optional tool choice configuration
- `**kwargs`: Provider-specific parameters (temperature, max_tokens, etc.)

**Returns**: `ModelResponse` object with:
- `content`: String response text
- `stop_reason`: Why the model stopped (end_turn, tool_use, max_tokens, etc.)
- `usage`: Token usage statistics
- `raw_response`: Provider-specific response object

#### `get_json()`

Get structured JSON output from the model.

```python
async def get_json(
    self,
    messages: Messages,
    system_prompt: str | None = None,
    json_schema: dict | None = None,
    **kwargs
) -> ModelResponse:
    """Get structured JSON output from the model."""
```

**Parameters**:
- `messages`: List of conversation messages
- `system_prompt`: Optional system prompt
- `json_schema`: Optional JSON schema for structured output validation
- `**kwargs`: Provider-specific parameters

**Returns**: `ModelResponse` with `content` containing valid JSON string

#### Configuration Methods

```python
def update_config(self, **kwargs) -> None:
    """Update model configuration."""

def get_config(self) -> dict:
    """Get current model configuration."""
```

## Unified Message Format

Spark uses a consistent message format across all providers:

```python
from spark.models.types import Messages

messages: Messages = [
    {
        "role": "user",
        "content": [{"text": "What's the weather?"}]
    },
    {
        "role": "assistant",
        "content": [{"text": "I'll check the weather for you."}]
    }
]
```

### Message Structure

Each message is a dictionary with:

- **`role`**: String - `"user"`, `"assistant"`, or `"system"`
- **`content`**: List of content blocks

### Content Blocks

Content blocks can be:

**Text block**:
```python
{"text": "Hello, how are you?"}
```

**Image block** (if supported by provider):
```python
{
    "image": {
        "format": "png",  # or "jpeg", "gif", "webp"
        "source": {
            "bytes": base64_encoded_bytes  # or "url": "https://..."
        }
    }
}
```

**Tool use block** (for tool calling):
```python
{
    "toolUse": {
        "toolUseId": "unique_id",
        "name": "web_search",
        "input": {"query": "weather"}
    }
}
```

**Tool result block** (for tool responses):
```python
{
    "toolResult": {
        "toolUseId": "unique_id",
        "content": [{"text": "Weather is sunny, 72°F"}],
        "status": "success"  # or "error"
    }
}
```

### Why Unified Format?

The unified format provides:

1. **Consistency**: Same structure regardless of provider
2. **Portability**: Move conversations between providers
3. **Simplicity**: One format to learn and use
4. **Tool Support**: Standardized tool calling across providers

Internally, each provider adapter converts this format to and from the provider's native format.

## Tool Calling Support

All models support tool calling through a unified interface:

```python
from spark.tools.decorator import tool

@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: Sunny, 72°F"

# Tool specs work the same across providers
tool_specs = [get_weather.tool_spec]

response = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "What's the weather in Paris?"}]}],
    tool_specs=tool_specs
)

# Check if model wants to use a tool
if response.stop_reason == "tool_use":
    # Extract tool calls from response
    for block in response.content:
        if "toolUse" in block:
            tool_name = block["toolUse"]["name"]
            tool_input = block["toolUse"]["input"]
            # Execute tool...
```

### Tool Choice Configuration

Control tool usage behavior:

```python
# Auto: Let model decide
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"auto": {}}
)

# Required: Force model to use a tool
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"any": {}}
)

# Specific tool: Force model to use specific tool
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"tool": {"name": "web_search"}}
)
```

## Configuration Management

Models are configured at initialization and can be updated dynamically:

```python
# Initial configuration
model = OpenAIModel(
    model_id="gpt-4o",
    api_key="sk-...",
    temperature=0.7,
    max_tokens=1000
)

# Update configuration
model.update_config(temperature=0.9, max_tokens=2000)

# Get current configuration
config = model.get_config()
print(f"Temperature: {config['temperature']}")
print(f"Max tokens: {config['max_tokens']}")
```

### Common Configuration Parameters

While providers may support different parameters, these are commonly supported:

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `model_id` | str | Model identifier | Required |
| `temperature` | float | Randomness (0.0-1.0) | 0.7 |
| `max_tokens` | int | Maximum response length | Model-specific |
| `top_p` | float | Nucleus sampling | 1.0 |
| `stop_sequences` | list[str] | Stop generation at sequences | None |
| `enable_cache` | bool | Enable response caching | False |

## Error Handling

The abstraction layer provides consistent error handling:

```python
from spark.models.base import ModelError

try:
    response = await model.get_text(messages=messages)
except ModelError as e:
    print(f"Model error: {e}")
    # Handle error consistently regardless of provider
```

### Exception Hierarchy

```
ModelError (base exception)
├── ModelConfigurationError - Invalid configuration
├── ModelAPIError - API call failed
├── ModelRateLimitError - Rate limit exceeded
├── ModelContextWindowError - Input too long
└── ModelValidationError - Invalid input/output
```

### Provider-Specific Errors

Providers may raise provider-specific exceptions, but they're always wrapped in `ModelError`:

```python
try:
    response = await model.get_text(messages=messages)
except ModelRateLimitError:
    # Wait and retry
    await asyncio.sleep(60)
    response = await model.get_text(messages=messages)
except ModelContextWindowError:
    # Truncate messages
    messages = messages[-10:]  # Keep last 10 messages
    response = await model.get_text(messages=messages)
except ModelError as e:
    # Catch-all for other errors
    print(f"Unexpected model error: {e}")
```

## Provider Selection Guidelines

### By Use Case

**Production Agents**:
- OpenAI GPT-4o: Best general performance, wide tool support
- Anthropic Claude: Strong reasoning, long context windows
- Consider cost, latency, and accuracy trade-offs

**Development/Testing**:
- OpenAI GPT-4o-mini: Fast and cheap
- EchoModel: Free, deterministic testing (see Testing section)

**Enterprise/Compliance**:
- AWS Bedrock: Private deployment, compliance features
- Azure OpenAI: Enterprise SLA, data residency

### By Feature Requirements

**Long Context** (100K+ tokens):
- Anthropic Claude (200K tokens)
- Google Gemini (1M+ tokens)

**Structured Output**:
- OpenAI with `response_format` (native JSON mode)
- Anthropic with tool calling (simulated structured output)

**Function Calling**:
- All providers support tool calling through Spark's unified interface
- OpenAI and Anthropic have the most mature implementations

**Cost Optimization**:
- Use GPT-4o-mini for simple tasks
- Use GPT-4o for complex reasoning
- Enable caching for repeated queries (see Caching section)

### By Deployment Environment

**Cloud**:
- OpenAI API: Fastest to get started
- Provider-specific APIs: Best integration with cloud services

**On-Premises**:
- OpenAI-compatible endpoints (Ollama, vLLM, etc.)
- Self-hosted models via custom providers

## Model Response Object

All models return a `ModelResponse` object:

```python
class ModelResponse:
    content: str  # Response text or JSON
    stop_reason: str  # Why model stopped
    usage: dict  # Token usage statistics
    raw_response: Any  # Provider-specific response
```

### Stop Reasons

Common stop reasons across providers:

- `"end_turn"`: Model naturally completed response
- `"tool_use"`: Model requested tool call
- `"max_tokens"`: Hit token limit
- `"stop_sequence"`: Hit configured stop sequence
- `"content_filter"`: Response filtered by safety systems

### Usage Statistics

The `usage` dictionary typically contains:

```python
{
    "input_tokens": 150,      # Tokens in prompt
    "output_tokens": 75,      # Tokens in response
    "total_tokens": 225       # Sum of input + output
}
```

Usage information is essential for:
- Cost tracking (see Agent cost tracking)
- Performance monitoring
- Context window management

## Complete Example: Provider-Agnostic Agent

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

# Define tools (work with any provider)
@tool
def calculate(expression: str) -> float:
    """Evaluate a mathematical expression."""
    return eval(expression)

# Create model (swap this line to change provider)
model = OpenAIModel(model_id="gpt-4o")

# Create agent configuration
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful math assistant.",
    tools=[calculate],
    max_steps=10
)

# Create agent
agent = Agent(config=config)

# Use agent (code is provider-agnostic!)
async def solve_problem():
    response = await agent.process(
        "What is 15% of 240 plus 18?"
    )
    print(response)

# To switch providers, only change the model line:
# from spark.models.bedrock import BedrockModel
# model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5")
```

## Best Practices

### 1. Use Type Hints

```python
from spark.models.base import Model
from spark.models.types import Messages

async def process_with_model(model: Model, messages: Messages):
    """Accept any model implementation."""
    response = await model.get_text(messages=messages)
    return response.content
```

### 2. Handle Provider Differences Gracefully

```python
# Some providers may not support all features
try:
    response = await model.get_json(
        messages=messages,
        json_schema=schema
    )
except NotImplementedError:
    # Fallback to get_text with JSON instructions
    response = await model.get_text(
        messages=messages,
        system_prompt="Respond with valid JSON matching this schema: ..."
    )
```

### 3. Configure for Your Use Case

```python
# Development: Fast and cheap
dev_model = OpenAIModel(
    model_id="gpt-4o-mini",
    temperature=0.7,
    enable_cache=True  # Avoid repeated API calls
)

# Production: High quality
prod_model = OpenAIModel(
    model_id="gpt-4o",
    temperature=0.3,  # More deterministic
    max_tokens=2000,
    enable_cache=False  # Fresh responses
)
```

### 4. Monitor Usage and Costs

```python
from spark.agents.cost_tracker import CostTracker

tracker = CostTracker()

response = await model.get_text(messages=messages)

# Track usage
tracker.record_call(
    model_id=model.model_id,
    input_tokens=response.usage["input_tokens"],
    output_tokens=response.usage["output_tokens"]
)

# Monitor costs
stats = tracker.get_stats()
print(f"Total cost: ${stats.total_cost:.4f}")
```

### 5. Test with Multiple Providers

```python
import pytest
from spark.models.openai import OpenAIModel
from spark.models.testing import EchoModel

@pytest.mark.parametrize("model", [
    OpenAIModel(model_id="gpt-4o-mini"),
    EchoModel(),  # Fast, free testing
])
async def test_agent_with_different_models(model):
    agent = Agent(config=AgentConfig(model=model))
    response = await agent.process("Hello")
    assert response is not None
```

## Next Steps

- **[OpenAI Models](openai.md)**: Learn about the primary model implementation
- **[Response Caching](caching.md)**: Speed up development with caching
- **[Testing Models](testing.md)**: Test without API calls using EchoModel
- **[Custom Providers](custom-providers.md)**: Implement your own model provider
- **[Agent System](../agents/README.md)**: Use models with Spark agents
