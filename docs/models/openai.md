---
title: OpenAI Models
parent: Models
nav_order: 1
---
# OpenAI Models

The `OpenAIModel` class provides integration with OpenAI's API and OpenAI-compatible providers. This is the primary model implementation in Spark and serves as the reference for how model providers work.

## Overview

OpenAI models offer:

- State-of-the-art language understanding and generation
- Native structured output support (JSON mode)
- Robust function/tool calling
- Wide range of models from fast/cheap to powerful/accurate
- Mature API with extensive documentation

## Quick Start

```python
from spark.models.openai import OpenAIModel

# Create model instance
model = OpenAIModel(
    model_id="gpt-4o",
    api_key="sk-..."  # Or set OPENAI_API_KEY environment variable
)

# Simple text completion
messages = [
    {"role": "user", "content": [{"text": "What is the capital of France?"}]}
]

response = await model.get_text(messages=messages)
print(response.content)  # "The capital of France is Paris."
```

## Installation and Setup

### Install OpenAI Package

```bash
pip install openai
```

### API Key Configuration

Set your OpenAI API key using one of these methods:

**Environment Variable** (recommended):
```bash
export OPENAI_API_KEY="sk-..."
```

**Direct in Code**:
```python
model = OpenAIModel(
    model_id="gpt-4o",
    api_key="sk-..."
)
```

**From File**:
```python
import os
with open("openai_key.txt") as f:
    api_key = f.read().strip()

model = OpenAIModel(model_id="gpt-4o", api_key=api_key)
```

### Get API Key

1. Visit [platform.openai.com](https://platform.openai.com)
2. Sign up or log in
3. Navigate to API Keys section
4. Create new API key
5. Copy and save securely

## OpenAIModel Class

### Constructor

```python
from spark.models.openai import OpenAIModel

model = OpenAIModel(
    model_id: str,
    api_key: str | None = None,
    base_url: str | None = None,
    organization: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    top_p: float = 1.0,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    stop_sequences: list[str] | None = None,
    enable_cache: bool = False,
    cache_ttl_seconds: int = 86400,
    **kwargs
)
```

### Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `model_id` | str | OpenAI model identifier | Required |
| `api_key` | str \| None | API key (or use OPENAI_API_KEY env) | None |
| `base_url` | str \| None | Custom API endpoint URL | None |
| `organization` | str \| None | OpenAI organization ID | None |
| `temperature` | float | Sampling temperature (0.0-2.0) | 0.7 |
| `max_tokens` | int \| None | Maximum tokens in response | None |
| `top_p` | float | Nucleus sampling (0.0-1.0) | 1.0 |
| `frequency_penalty` | float | Penalize frequent tokens (-2.0 to 2.0) | 0.0 |
| `presence_penalty` | float | Penalize repeated topics (-2.0 to 2.0) | 0.0 |
| `stop_sequences` | list[str] \| None | Stop generation at these strings | None |
| `enable_cache` | bool | Enable response caching | False |
| `cache_ttl_seconds` | int | Cache time-to-live in seconds | 86400 |

### Supported Models

OpenAI offers several model families:

#### GPT-4o (Recommended)

Latest and most capable model family:

```python
# GPT-4o - Best performance
model = OpenAIModel(model_id="gpt-4o")

# GPT-4o Mini - Fast and cost-effective
model = OpenAIModel(model_id="gpt-4o-mini")
```

**Capabilities**:
- 128K context window
- Vision support (images)
- Function calling
- JSON mode
- Strong reasoning

**Use Cases**:
- Production agents
- Complex reasoning tasks
- Multi-modal applications

#### GPT-4 Turbo

Previous generation, still very capable:

```python
model = OpenAIModel(model_id="gpt-4-turbo")
```

**Capabilities**:
- 128K context window
- Vision support
- Function calling
- JSON mode

#### GPT-3.5 Turbo

Fast and economical:

```python
model = OpenAIModel(model_id="gpt-3.5-turbo")
```

**Capabilities**:
- 16K context window
- Function calling
- JSON mode
- Very fast response times

**Use Cases**:
- Development and testing
- Simple tasks
- High-volume, cost-sensitive applications

### Model Selection Guide

| Model | Speed | Cost | Quality | Context | Best For |
|-------|-------|------|---------|---------|----------|
| gpt-4o | Fast | Medium | Excellent | 128K | Production agents |
| gpt-4o-mini | Very Fast | Low | Good | 128K | Development, simple tasks |
| gpt-4-turbo | Medium | High | Excellent | 128K | Complex reasoning |
| gpt-3.5-turbo | Very Fast | Very Low | Good | 16K | High-volume, simple tasks |

## Text Completions

### Basic Usage

```python
messages = [
    {"role": "user", "content": [{"text": "Explain quantum computing in simple terms."}]}
]

response = await model.get_text(messages=messages)
print(response.content)
```

### With System Prompt

```python
response = await model.get_text(
    messages=[
        {"role": "user", "content": [{"text": "What's the weather like?"}]}
    ],
    system_prompt="You are a helpful weather assistant. Always be friendly and concise."
)
```

### Multi-Turn Conversations

```python
messages = [
    {"role": "user", "content": [{"text": "What is Python?"}]},
    {"role": "assistant", "content": [{"text": "Python is a high-level programming language..."}]},
    {"role": "user", "content": [{"text": "What is it used for?"}]}
]

response = await model.get_text(messages=messages)
```

### Controlling Output Length

```python
# Short responses
response = await model.get_text(
    messages=messages,
    max_tokens=50
)

# Longer responses
response = await model.get_text(
    messages=messages,
    max_tokens=1000
)
```

### Controlling Randomness

```python
# Deterministic (always similar output)
response = await model.get_text(
    messages=messages,
    temperature=0.0
)

# Balanced (default)
response = await model.get_text(
    messages=messages,
    temperature=0.7
)

# Creative (more random)
response = await model.get_text(
    messages=messages,
    temperature=1.5
)
```

### Using Stop Sequences

```python
response = await model.get_text(
    messages=[
        {"role": "user", "content": [{"text": "Count from 1 to 10"}]}
    ],
    stop_sequences=["5"]  # Stop when "5" is generated
)
# Output: "1, 2, 3, 4, "
```

## Structured Outputs (JSON Mode)

OpenAI models support native JSON mode for structured outputs:

### Basic JSON Mode

```python
response = await model.get_json(
    messages=[
        {"role": "user", "content": [{"text": "Describe Paris in JSON with fields: name, country, population"}]}
    ]
)

# Response content is valid JSON string
import json
data = json.loads(response.content)
print(data)
# {"name": "Paris", "country": "France", "population": 2161000}
```

### With JSON Schema

```python
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "country": {"type": "string"},
        "population": {"type": "integer"},
        "landmarks": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["name", "country", "population"]
}

response = await model.get_json(
    messages=[
        {"role": "user", "content": [{"text": "Describe Paris"}]}
    ],
    json_schema=schema
)

data = json.loads(response.content)
# Guaranteed to match schema
```

### Complex Structured Output

```python
schema = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "due_date": {"type": "string", "format": "date"},
                    "tags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["title", "priority"]
            }
        }
    }
}

response = await model.get_json(
    messages=[
        {"role": "user", "content": [{"text": "Create a task list for launching a product"}]}
    ],
    system_prompt="You are a project management assistant.",
    json_schema=schema
)

tasks = json.loads(response.content)
for task in tasks["tasks"]:
    print(f"- {task['title']} ({task['priority']})")
```

## Tool Calling (Function Calling)

OpenAI models have robust support for function/tool calling:

### Basic Tool Calling

```python
from spark.tools.decorator import tool

@tool
def get_weather(location: str, unit: str = "fahrenheit") -> str:
    """Get the current weather for a location.

    Args:
        location: City name or zip code
        unit: Temperature unit (fahrenheit or celsius)
    """
    # Implementation
    return f"Weather in {location}: Sunny, 72°F"

# Use tool with model
tool_specs = [get_weather.tool_spec]

response = await model.get_text(
    messages=[
        {"role": "user", "content": [{"text": "What's the weather in San Francisco?"}]}
    ],
    tool_specs=tool_specs
)

# Check if model wants to use tool
if response.stop_reason == "tool_use":
    # Extract tool call from response
    for block in response.content:
        if isinstance(block, dict) and "toolUse" in block:
            tool_use = block["toolUse"]
            print(f"Tool: {tool_use['name']}")
            print(f"Input: {tool_use['input']}")
            # Execute tool and continue conversation...
```

### Multi-Step Tool Calling

```python
@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

@tool
def calculate(expression: str) -> float:
    """Evaluate a mathematical expression."""
    return eval(expression)

tools = [search_web, calculate]
tool_specs = [t.tool_spec for t in tools]

messages = [
    {"role": "user", "content": [{"text": "Search for Python tutorials, then calculate 15 * 8"}]}
]

# First call - model requests tools
response1 = await model.get_text(
    messages=messages,
    tool_specs=tool_specs
)

# Process tool calls and add results to conversation
# (This is automated in Spark agents)
```

### Controlling Tool Choice

```python
# Let model decide whether to use tools
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"auto": {}}  # Default
)

# Require model to use a tool
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"any": {}}  # Must use some tool
)

# Force specific tool
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"tool": {"name": "get_weather"}}
)

# Disable tools
response = await model.get_text(
    messages=messages,
    tool_specs=tool_specs,
    tool_choice={"none": {}}  # Never use tools
)
```

## Context Window Management

OpenAI models have context window limits (e.g., 128K tokens for GPT-4o):

### Handling Context Window Errors

```python
from spark.models.base import ModelContextWindowError

try:
    response = await model.get_text(messages=very_long_messages)
except ModelContextWindowError as e:
    # Truncate conversation to fit
    messages = messages[-20:]  # Keep last 20 messages
    response = await model.get_text(messages=messages)
```

### Estimating Token Count

```python
import tiktoken

def count_tokens(text: str, model_id: str = "gpt-4o") -> int:
    """Estimate token count for text."""
    encoding = tiktoken.encoding_for_model(model_id)
    return len(encoding.encode(text))

# Check before calling API
message_text = "Your prompt here..."
token_count = count_tokens(message_text)

if token_count > 100000:  # Leave room for response
    print("Warning: Prompt may be too long")
```

### Managing Long Conversations

```python
def truncate_conversation(messages: list, max_tokens: int = 100000) -> list:
    """Keep conversation within token limit."""
    total_tokens = 0
    truncated = []

    # Keep messages from most recent backward
    for msg in reversed(messages):
        msg_text = msg["content"][0]["text"]
        msg_tokens = count_tokens(msg_text)

        if total_tokens + msg_tokens > max_tokens:
            break

        truncated.insert(0, msg)
        total_tokens += msg_tokens

    return truncated

# Use before calling model
messages = truncate_conversation(messages, max_tokens=100000)
response = await model.get_text(messages=messages)
```

## Rate Limiting

OpenAI enforces rate limits based on your account tier:

### Handling Rate Limits

```python
from spark.models.base import ModelRateLimitError
import asyncio

async def call_with_retry(model, messages, max_retries=3):
    """Call model with rate limit retry logic."""
    for attempt in range(max_retries):
        try:
            response = await model.get_text(messages=messages)
            return response
        except ModelRateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 10  # Exponential backoff
                print(f"Rate limited. Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise

response = await call_with_retry(model, messages)
```

### Batch Processing with Rate Limits

```python
async def process_batch_with_rate_limit(
    model,
    items: list,
    requests_per_minute: int = 60
):
    """Process items respecting rate limit."""
    delay = 60 / requests_per_minute
    results = []

    for item in items:
        messages = [{"role": "user", "content": [{"text": item}]}]

        try:
            response = await model.get_text(messages=messages)
            results.append(response.content)
        except ModelRateLimitError:
            await asyncio.sleep(delay * 2)  # Wait longer
            response = await model.get_text(messages=messages)
            results.append(response.content)

        await asyncio.sleep(delay)  # Rate limit

    return results
```

## OpenAI-Compatible Providers

The `OpenAIModel` class works with any OpenAI-compatible API by setting a custom base URL:

### Local Models (Ollama)

```python
# Run Ollama locally: ollama run llama2

model = OpenAIModel(
    model_id="llama2",
    base_url="http://localhost:11434/v1",
    api_key="not-needed"  # Ollama doesn't require key
)

response = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "Hello!"}]}]
)
```

### vLLM Server

```python
# Start vLLM: python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-7b-hf

model = OpenAIModel(
    model_id="meta-llama/Llama-2-7b-hf",
    base_url="http://localhost:8000/v1",
    api_key="token-abc"
)

response = await model.get_text(messages=messages)
```

### Together AI

```python
model = OpenAIModel(
    model_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
    base_url="https://api.together.xyz/v1",
    api_key=os.getenv("TOGETHER_API_KEY")
)

response = await model.get_text(messages=messages)
```

### Anyscale Endpoints

```python
model = OpenAIModel(
    model_id="meta-llama/Llama-2-70b-chat-hf",
    base_url="https://api.endpoints.anyscale.com/v1",
    api_key=os.getenv("ANYSCALE_API_KEY")
)

response = await model.get_text(messages=messages)
```

### Using Environment Variables

```bash
# Set custom endpoint via environment
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="not-needed"
```

```python
# Model will use environment variables
model = OpenAIModel(model_id="llama2")
```

## Configuration Management

### Update Configuration Dynamically

```python
model = OpenAIModel(model_id="gpt-4o", temperature=0.7)

# Update configuration
model.update_config(
    temperature=0.9,
    max_tokens=2000,
    top_p=0.95
)

# Get current configuration
config = model.get_config()
print(f"Current temperature: {config['temperature']}")
```

### Configuration Presets

```python
# Development preset: fast and cheap
def create_dev_model():
    return OpenAIModel(
        model_id="gpt-4o-mini",
        temperature=0.7,
        max_tokens=500,
        enable_cache=True
    )

# Production preset: high quality
def create_prod_model():
    return OpenAIModel(
        model_id="gpt-4o",
        temperature=0.3,  # More deterministic
        max_tokens=2000,
        enable_cache=False
    )

# Use based on environment
import os
if os.getenv("ENV") == "production":
    model = create_prod_model()
else:
    model = create_dev_model()
```

## Error Handling

### Complete Error Handling Example

```python
from spark.models.base import (
    ModelError,
    ModelAPIError,
    ModelRateLimitError,
    ModelContextWindowError,
    ModelConfigurationError
)
import asyncio

async def robust_model_call(model, messages, max_retries=3):
    """Call model with comprehensive error handling."""
    for attempt in range(max_retries):
        try:
            response = await model.get_text(messages=messages)
            return response

        except ModelRateLimitError:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 10
                print(f"Rate limited. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise

        except ModelContextWindowError:
            # Truncate and retry
            print("Context too long. Truncating...")
            messages = messages[-10:]  # Keep last 10

        except ModelAPIError as e:
            # API error - might be temporary
            if attempt < max_retries - 1:
                print(f"API error: {e}. Retrying...")
                await asyncio.sleep(5)
            else:
                raise

        except ModelConfigurationError:
            # Configuration error - fix and retry
            print("Configuration error. Using defaults...")
            model.update_config(temperature=0.7, max_tokens=1000)

        except ModelError as e:
            # Other model error - don't retry
            print(f"Model error: {e}")
            raise

    raise ModelError("Max retries exceeded")
```

## Performance Optimization

### Enable Response Caching

For development and testing, enable caching to avoid repeated API calls:

```python
model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

# First call hits API
response1 = await model.get_text(messages=messages)

# Identical call returns cached response (instant!)
response2 = await model.get_text(messages=messages)
```

See [Response Caching](caching.md) for detailed caching documentation.

### Parallel Processing

Process multiple independent requests concurrently:

```python
async def process_parallel(model, prompts: list[str]):
    """Process multiple prompts in parallel."""
    tasks = []

    for prompt in prompts:
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        task = model.get_text(messages=messages)
        tasks.append(task)

    # Run all requests concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle results
    results = []
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            print(f"Request {i} failed: {response}")
            results.append(None)
        else:
            results.append(response.content)

    return results

# Process 10 prompts concurrently
prompts = [f"Summarize topic {i}" for i in range(10)]
results = await process_parallel(model, prompts)
```

### Streaming Responses

For long responses, consider streaming (if supported by your use case):

```python
# Note: Streaming is not directly exposed in current API
# but can be added by extending OpenAIModel
```

## Integration with Agents

OpenAI models work seamlessly with Spark agents:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

# Create tools
@tool
def calculate(expression: str) -> float:
    """Evaluate mathematical expression."""
    return eval(expression)

@tool
def search_web(query: str) -> str:
    """Search the web."""
    from spark.utils.common import search_web
    return search_web(query)

# Create model
model = OpenAIModel(
    model_id="gpt-4o",
    temperature=0.7,
    max_tokens=2000
)

# Create agent with model
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful research assistant.",
    tools=[calculate, search_web],
    max_steps=10,
    parallel_tool_execution=True
)

agent = Agent(config=config)

# Use agent
response = await agent.process(
    "Search for the population of Tokyo, then calculate what 15% of that would be."
)
print(response)
```

## Complete Example: Advanced Usage

```python
import asyncio
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool
from spark.models.base import ModelRateLimitError, ModelContextWindowError
import json

# Define tools
@tool
def get_user_data(user_id: str) -> dict:
    """Fetch user data from database."""
    return {
        "id": user_id,
        "name": "Alice",
        "preferences": {"theme": "dark", "language": "en"}
    }

@tool
def update_user_preferences(user_id: str, preferences: dict) -> bool:
    """Update user preferences."""
    print(f"Updating preferences for {user_id}: {preferences}")
    return True

# Create model with configuration
model = OpenAIModel(
    model_id="gpt-4o",
    temperature=0.3,  # Deterministic for consistency
    max_tokens=1500,
    enable_cache=True,  # Cache during development
    cache_ttl_seconds=1800  # 30 minutes
)

async def process_user_request(user_id: str, request: str):
    """Process user request with tools."""

    # Prepare tools
    tools = [get_user_data, update_user_preferences]
    tool_specs = [t.tool_spec for t in tools]
    tool_map = {t.tool_name: t for t in tools}

    # Build conversation
    messages = [
        {"role": "user", "content": [{"text": f"User {user_id}: {request}"}]}
    ]

    # Multi-turn conversation with tool calling
    max_turns = 5
    for turn in range(max_turns):
        try:
            # Call model
            response = await model.get_text(
                messages=messages,
                system_prompt="You are a helpful user account assistant. Use tools to fetch and update user data.",
                tool_specs=tool_specs
            )

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Model finished
                return response.content

            elif response.stop_reason == "tool_use":
                # Process tool calls
                tool_results = []

                for block in response.content:
                    if isinstance(block, dict) and "toolUse" in block:
                        tool_use = block["toolUse"]
                        tool_name = tool_use["name"]
                        tool_input = tool_use["input"]
                        tool_use_id = tool_use["toolUseId"]

                        # Execute tool
                        if tool_name in tool_map:
                            try:
                                result = await tool_map[tool_name](**tool_input)
                                tool_results.append({
                                    "toolResult": {
                                        "toolUseId": tool_use_id,
                                        "content": [{"text": json.dumps(result)}],
                                        "status": "success"
                                    }
                                })
                            except Exception as e:
                                tool_results.append({
                                    "toolResult": {
                                        "toolUseId": tool_use_id,
                                        "content": [{"text": f"Error: {str(e)}"}],
                                        "status": "error"
                                    }
                                })

                # Add tool results to conversation
                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

        except ModelRateLimitError:
            print("Rate limited. Waiting...")
            await asyncio.sleep(10)

        except ModelContextWindowError:
            print("Context too long. Truncating...")
            messages = messages[:2] + messages[-3:]  # Keep first and last few

    return "Max turns reached without completion"

# Use the function
async def main():
    result = await process_user_request(
        user_id="user_123",
        request="Change my theme to light mode and language to Spanish"
    )
    print(result)

asyncio.run(main())
```

## Best Practices

### 1. Use Appropriate Model for Task

```python
# Simple tasks: Use GPT-4o-mini
simple_model = OpenAIModel(model_id="gpt-4o-mini")

# Complex reasoning: Use GPT-4o
complex_model = OpenAIModel(model_id="gpt-4o")
```

### 2. Set Temperature Based on Use Case

```python
# Factual/deterministic: Low temperature
factual_model = OpenAIModel(model_id="gpt-4o", temperature=0.0)

# Creative/diverse: Higher temperature
creative_model = OpenAIModel(model_id="gpt-4o", temperature=1.2)
```

### 3. Always Handle Rate Limits

```python
# Implement retry logic with exponential backoff
# See error handling section
```

### 4. Monitor Token Usage

```python
response = await model.get_text(messages=messages)

# Track usage
input_tokens = response.usage["input_tokens"]
output_tokens = response.usage["output_tokens"]
total_cost = (input_tokens * 0.000005) + (output_tokens * 0.000015)

print(f"Cost: ${total_cost:.6f}")
```

### 5. Use Caching in Development

```python
# Development: Enable caching
dev_model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True
)

# Production: Disable caching
prod_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False
)
```

### 6. Validate JSON Output

```python
response = await model.get_json(messages=messages, json_schema=schema)

# Always parse and validate
try:
    data = json.loads(response.content)
    # Validate against schema if needed
except json.JSONDecodeError:
    print("Invalid JSON response")
```

### 7. Manage Context Windows

```python
# Check conversation length
total_tokens = sum(count_tokens(msg["content"][0]["text"]) for msg in messages)

if total_tokens > 100000:
    messages = truncate_conversation(messages)
```

## Troubleshooting

### Issue: API Key Not Found

```python
# Error: openai.AuthenticationError: No API key provided

# Solution: Set environment variable
import os
os.environ["OPENAI_API_KEY"] = "sk-..."

# Or pass directly
model = OpenAIModel(model_id="gpt-4o", api_key="sk-...")
```

### Issue: Rate Limit Exceeded

```python
# Error: ModelRateLimitError: Rate limit exceeded

# Solution: Implement retry with backoff
async def call_with_retry(model, messages):
    for i in range(3):
        try:
            return await model.get_text(messages=messages)
        except ModelRateLimitError:
            await asyncio.sleep((2 ** i) * 10)
    raise
```

### Issue: Context Window Exceeded

```python
# Error: ModelContextWindowError: Maximum context length exceeded

# Solution: Truncate messages
messages = messages[-20:]  # Keep last 20 messages
response = await model.get_text(messages=messages)
```

### Issue: Invalid JSON Response

```python
# Error: JSONDecodeError when parsing response

# Solution: Use try/except and retry
try:
    data = json.loads(response.content)
except json.JSONDecodeError:
    # Retry or use text mode
    response = await model.get_text(
        messages=messages,
        system_prompt="Respond with valid JSON"
    )
```

## Next Steps

- **[Response Caching](caching.md)**: Speed up development with response caching
- **[Model Abstraction](abstraction.md)**: Understand the model abstraction layer
- **[Testing Models](testing.md)**: Test without API calls
- **[Custom Providers](custom-providers.md)**: Create your own model provider
- **[Agent System](../agents/README.md)**: Use OpenAI models with agents
