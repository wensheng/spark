---
title: Custom Model Providers
parent: Models
nav_order: 4
---
# Custom Model Providers

Spark's model abstraction layer makes it straightforward to integrate custom LLM providers or self-hosted models. This guide shows you how to implement the `Model` interface to add support for new providers.

## Overview

Creating a custom model provider involves:

1. Implementing the `Model` base class
2. Converting between unified and provider-specific message formats
3. Handling tool calling (optional but recommended)
4. Implementing error handling
5. Testing your provider
6. Registering and using with agents

## Quick Start

Here's a minimal custom model provider:

```python
from spark.models.base import Model, ModelResponse
from spark.models.types import Messages

class MyCustomModel(Model):
    """Custom model provider."""

    def __init__(self, model_id: str, api_key: str, **kwargs):
        super().__init__(model_id=model_id)
        self.api_key = api_key
        self.config = kwargs

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        tool_specs: list[dict] | None = None,
        tool_choice: dict | None = None,
        **kwargs
    ) -> ModelResponse:
        """Get text completion from custom provider."""
        # 1. Convert messages to provider format
        provider_messages = self._convert_messages(messages, system_prompt)

        # 2. Call provider API
        response = await self._call_api(provider_messages, **kwargs)

        # 3. Convert response to ModelResponse
        return ModelResponse(
            content=response["text"],
            stop_reason=response["stop_reason"],
            usage=response["usage"],
            raw_response=response
        )

    async def get_json(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        json_schema: dict | None = None,
        **kwargs
    ) -> ModelResponse:
        """Get JSON output from custom provider."""
        # Similar to get_text but request JSON format
        pass

    def _convert_messages(self, messages: Messages, system_prompt: str | None):
        """Convert unified format to provider format."""
        # Implementation specific to provider
        pass

    async def _call_api(self, messages, **kwargs):
        """Call provider API."""
        # Implementation specific to provider
        pass
```

## Implementing the Model Interface

### Required Methods

Every custom model must implement:

#### 1. `get_text()`

```python
async def get_text(
    self,
    messages: Messages,
    system_prompt: str | None = None,
    tool_specs: list[dict] | None = None,
    tool_choice: dict | None = None,
    **kwargs
) -> ModelResponse:
    """Get text completion.

    Args:
        messages: Conversation history in unified format
        system_prompt: Optional system prompt
        tool_specs: Optional tool specifications
        tool_choice: Optional tool choice configuration
        **kwargs: Provider-specific parameters

    Returns:
        ModelResponse with content, stop_reason, usage
    """
```

#### 2. `get_json()`

```python
async def get_json(
    self,
        messages: Messages,
    system_prompt: str | None = None,
    json_schema: dict | None = None,
    **kwargs
) -> ModelResponse:
    """Get structured JSON output.

    Args:
        messages: Conversation history
        system_prompt: Optional system prompt
        json_schema: Optional JSON schema for validation
        **kwargs: Provider-specific parameters

    Returns:
        ModelResponse with JSON string content
    """
```

### Optional Methods

You can also override:

```python
def update_config(self, **kwargs) -> None:
    """Update model configuration."""
    self.config.update(kwargs)

def get_config(self) -> dict:
    """Get current configuration."""
    return self.config.copy()
```

## Message Format Conversion

The most important part of a custom provider is converting between Spark's unified message format and the provider's native format.

### Understanding Unified Format

Spark uses this format:

```python
messages = [
    {
        "role": "user",  # or "assistant", "system"
        "content": [
            {"text": "Message text"},
            # Optionally: images, tool calls, tool results
        ]
    }
]
```

### Conversion Example: Simple Provider

```python
def _convert_messages(self, messages: Messages, system_prompt: str | None):
    """Convert to provider format."""
    provider_messages = []

    # Add system prompt if provided
    if system_prompt:
        provider_messages.append({
            "role": "system",
            "content": system_prompt
        })

    # Convert each message
    for msg in messages:
        role = msg["role"]
        content_blocks = msg["content"]

        # Extract text from content blocks
        text_parts = []
        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])

        # Create provider message
        provider_messages.append({
            "role": role,
            "content": " ".join(text_parts)
        })

    return provider_messages
```

### Conversion Example: Provider with Images

```python
def _convert_messages(self, messages: Messages, system_prompt: str | None):
    """Convert with image support."""
    provider_messages = []

    if system_prompt:
        provider_messages.append({
            "role": "system",
            "content": system_prompt
        })

    for msg in messages:
        role = msg["role"]
        content_blocks = msg["content"]

        provider_content = []

        for block in content_blocks:
            if "text" in block:
                # Text content
                provider_content.append({
                    "type": "text",
                    "text": block["text"]
                })
            elif "image" in block:
                # Image content
                image = block["image"]
                provider_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": image["source"].get("url") or
                               f"data:image/{image['format']};base64,{image['source']['bytes']}"
                    }
                })

        provider_messages.append({
            "role": role,
            "content": provider_content
        })

    return provider_messages
```

## Tool Calling Integration

Supporting tool calling enables your model to work with Spark agents:

### Tool Spec Conversion

```python
def _convert_tool_specs(self, tool_specs: list[dict] | None) -> list[dict] | None:
    """Convert Spark tool specs to provider format."""
    if not tool_specs:
        return None

    provider_tools = []

    for spec in tool_specs:
        provider_tools.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["inputSchema"]
            }
        })

    return provider_tools
```

### Tool Use Response Handling

```python
async def get_text(
    self,
    messages: Messages,
    system_prompt: str | None = None,
    tool_specs: list[dict] | None = None,
    **kwargs
) -> ModelResponse:
    """Handle tool calling in response."""

    provider_messages = self._convert_messages(messages, system_prompt)
    provider_tools = self._convert_tool_specs(tool_specs)

    response = await self._call_api(
        provider_messages,
        tools=provider_tools,
        **kwargs
    )

    # Check if response contains tool calls
    if response.get("tool_calls"):
        # Convert tool calls to Spark format
        content = []
        for tool_call in response["tool_calls"]:
            content.append({
                "toolUse": {
                    "toolUseId": tool_call["id"],
                    "name": tool_call["function"]["name"],
                    "input": json.loads(tool_call["function"]["arguments"])
                }
            })

        return ModelResponse(
            content=content,
            stop_reason="tool_use",
            usage=response["usage"]
        )
    else:
        # Regular text response
        return ModelResponse(
            content=response["content"],
            stop_reason="end_turn",
            usage=response["usage"]
        )
```

### Tool Result Handling

```python
def _convert_messages(self, messages: Messages, system_prompt: str | None):
    """Convert messages including tool results."""
    provider_messages = []

    if system_prompt:
        provider_messages.append({
            "role": "system",
            "content": system_prompt
        })

    for msg in messages:
        role = msg["role"]
        content_blocks = msg["content"]

        # Check for tool calls
        tool_calls = []
        text_parts = []

        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                tool_calls.append({
                    "id": tool_use["toolUseId"],
                    "type": "function",
                    "function": {
                        "name": tool_use["name"],
                        "arguments": json.dumps(tool_use["input"])
                    }
                })
            elif "toolResult" in block:
                # Tool result in user message
                tool_result = block["toolResult"]
                result_text = tool_result["content"][0]["text"]
                provider_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["toolUseId"],
                    "content": result_text
                })
                continue

        # Create message
        if tool_calls:
            provider_messages.append({
                "role": role,
                "content": " ".join(text_parts) if text_parts else None,
                "tool_calls": tool_calls
            })
        elif text_parts:
            provider_messages.append({
                "role": role,
                "content": " ".join(text_parts)
            })

    return provider_messages
```

## Error Handling

Implement proper error handling to integrate with Spark's error system:

```python
from spark.models.base import (
    ModelError,
    ModelAPIError,
    ModelRateLimitError,
    ModelContextWindowError,
    ModelConfigurationError
)

async def _call_api(self, messages, **kwargs):
    """Call API with error handling."""
    try:
        # Make API call
        response = await self.client.create(
            model=self.model_id,
            messages=messages,
            **kwargs
        )
        return response

    except ProviderRateLimitError as e:
        # Convert provider error to Spark error
        raise ModelRateLimitError(
            f"Rate limit exceeded: {e}"
        ) from e

    except ProviderContextWindowError as e:
        raise ModelContextWindowError(
            f"Context window exceeded: {e}"
        ) from e

    except ProviderAPIError as e:
        raise ModelAPIError(
            f"API error: {e}"
        ) from e

    except Exception as e:
        raise ModelError(
            f"Unexpected error: {e}"
        ) from e
```

## Complete Example: Custom Provider

Here's a complete example implementing a custom provider for a fictional API:

```python
import json
from typing import Any
import httpx
from spark.models.base import Model, ModelResponse, ModelAPIError, ModelRateLimitError
from spark.models.types import Messages

class AcmeModel(Model):
    """Custom provider for Acme AI API."""

    def __init__(
        self,
        model_id: str,
        api_key: str,
        base_url: str = "https://api.acme-ai.com/v1",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ):
        """Initialize Acme model.

        Args:
            model_id: Model identifier (e.g., "acme-large")
            api_key: API key for authentication
            base_url: API endpoint URL
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional configuration
        """
        super().__init__(model_id=model_id)
        self.api_key = api_key
        self.base_url = base_url
        self.config = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        tool_specs: list[dict] | None = None,
        tool_choice: dict | None = None,
        **kwargs
    ) -> ModelResponse:
        """Get text completion from Acme AI."""

        # Convert messages
        acme_messages = self._convert_messages(messages, system_prompt)

        # Convert tools
        acme_tools = self._convert_tool_specs(tool_specs) if tool_specs else None

        # Merge configuration
        params = {**self.config, **kwargs}

        # Call API
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model_id,
                    "messages": acme_messages,
                    "tools": acme_tools,
                    **params
                }
            )
            response.raise_for_status()
            result = response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ModelRateLimitError("Rate limit exceeded") from e
            else:
                raise ModelAPIError(f"API error: {e}") from e

        except Exception as e:
            raise ModelAPIError(f"Request failed: {e}") from e

        # Parse response
        choice = result["choices"][0]
        message = choice["message"]

        # Check for tool calls
        if message.get("tool_calls"):
            content = []
            for tool_call in message["tool_calls"]:
                content.append({
                    "toolUse": {
                        "toolUseId": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "input": json.loads(tool_call["function"]["arguments"])
                    }
                })

            return ModelResponse(
                content=content,
                stop_reason="tool_use",
                usage={
                    "input_tokens": result["usage"]["prompt_tokens"],
                    "output_tokens": result["usage"]["completion_tokens"],
                    "total_tokens": result["usage"]["total_tokens"]
                },
                raw_response=result
            )
        else:
            return ModelResponse(
                content=message["content"],
                stop_reason=choice["finish_reason"],
                usage={
                    "input_tokens": result["usage"]["prompt_tokens"],
                    "output_tokens": result["usage"]["completion_tokens"],
                    "total_tokens": result["usage"]["total_tokens"]
                },
                raw_response=result
            )

    async def get_json(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        json_schema: dict | None = None,
        **kwargs
    ) -> ModelResponse:
        """Get JSON output from Acme AI."""

        # Add JSON instruction to system prompt
        json_instruction = "Respond with valid JSON only."
        if json_schema:
            json_instruction += f"\n\nJSON Schema:\n{json.dumps(json_schema, indent=2)}"

        if system_prompt:
            system_prompt = f"{system_prompt}\n\n{json_instruction}"
        else:
            system_prompt = json_instruction

        # Call get_text with modified prompt
        response = await self.get_text(
            messages=messages,
            system_prompt=system_prompt,
            **kwargs
        )

        return response

    def _convert_messages(self, messages: Messages, system_prompt: str | None):
        """Convert to Acme format."""
        acme_messages = []

        if system_prompt:
            acme_messages.append({
                "role": "system",
                "content": system_prompt
            })

        for msg in messages:
            role = msg["role"]
            content_blocks = msg["content"]

            # Handle different content types
            text_parts = []
            tool_calls = []
            tool_result = None

            for block in content_blocks:
                if "text" in block:
                    text_parts.append(block["text"])
                elif "toolUse" in block:
                    tool_use = block["toolUse"]
                    tool_calls.append({
                        "id": tool_use["toolUseId"],
                        "type": "function",
                        "function": {
                            "name": tool_use["name"],
                            "arguments": json.dumps(tool_use["input"])
                        }
                    })
                elif "toolResult" in block:
                    tool_result = block["toolResult"]

            # Build message
            if tool_result:
                # Tool result message
                acme_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result["toolUseId"],
                    "content": tool_result["content"][0]["text"]
                })
            elif tool_calls:
                # Assistant message with tool calls
                acme_messages.append({
                    "role": role,
                    "content": " ".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls
                })
            elif text_parts:
                # Regular text message
                acme_messages.append({
                    "role": role,
                    "content": " ".join(text_parts)
                })

        return acme_messages

    def _convert_tool_specs(self, tool_specs: list[dict]) -> list[dict]:
        """Convert tool specs to Acme format."""
        acme_tools = []

        for spec in tool_specs:
            acme_tools.append({
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": spec["inputSchema"]
                }
            })

        return acme_tools

    def update_config(self, **kwargs):
        """Update configuration."""
        self.config.update(kwargs)

    def get_config(self) -> dict:
        """Get current configuration."""
        return self.config.copy()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()
```

## Testing Custom Providers

### Unit Tests

```python
import pytest
from spark.models.base import ModelResponse

@pytest.mark.asyncio
async def test_acme_model_text():
    """Test basic text completion."""
    model = AcmeModel(
        model_id="acme-large",
        api_key="test-key"
    )

    messages = [
        {"role": "user", "content": [{"text": "Hello"}]}
    ]

    response = await model.get_text(messages=messages)

    assert isinstance(response, ModelResponse)
    assert response.content
    assert response.stop_reason
    assert response.usage

@pytest.mark.asyncio
async def test_acme_model_json():
    """Test JSON output."""
    model = AcmeModel(
        model_id="acme-large",
        api_key="test-key"
    )

    messages = [
        {"role": "user", "content": [{"text": "Get user data"}]}
    ]

    response = await model.get_json(messages=messages)

    # Validate JSON
    import json
    data = json.loads(response.content)
    assert isinstance(data, dict)

@pytest.mark.asyncio
async def test_acme_model_tools():
    """Test tool calling."""
    from spark.tools.decorator import tool

    @tool
    def calculate(expression: str) -> float:
        """Evaluate expression."""
        return eval(expression)

    model = AcmeModel(
        model_id="acme-large",
        api_key="test-key"
    )

    messages = [
        {"role": "user", "content": [{"text": "Calculate 2+2"}]}
    ]

    response = await model.get_text(
        messages=messages,
        tool_specs=[calculate.tool_spec]
    )

    if response.stop_reason == "tool_use":
        # Verify tool call format
        assert isinstance(response.content, list)
        assert "toolUse" in response.content[0]
```

### Integration Tests with Agents

```python
@pytest.mark.asyncio
async def test_acme_with_agent():
    """Test custom provider with agent."""
    from spark.agents import Agent, AgentConfig
    from spark.tools.decorator import tool

    @tool
    def get_weather(location: str) -> str:
        """Get weather."""
        return f"Sunny in {location}"

    model = AcmeModel(
        model_id="acme-large",
        api_key="test-key"
    )

    config = AgentConfig(
        model=model,
        tools=[get_weather],
        max_steps=5
    )

    agent = Agent(config=config)

    response = await agent.process("What's the weather in Paris?")

    assert response
    assert "Paris" in response or "sunny" in response.lower()
```

## Registration and Usage

### Using with Agents

```python
from spark.agents import Agent, AgentConfig
from my_models.acme import AcmeModel

# Create model
model = AcmeModel(
    model_id="acme-large",
    api_key="your-api-key"
)

# Use with agent
config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant.",
    max_steps=10
)

agent = Agent(config=config)

# Use agent
response = await agent.process("Hello!")
```

### Factory Pattern

```python
from typing import Literal
from spark.models.base import Model

def create_model(
    provider: Literal["openai", "acme"],
    model_id: str,
    **kwargs
) -> Model:
    """Factory to create models."""

    if provider == "openai":
        from spark.models.openai import OpenAIModel
        return OpenAIModel(model_id=model_id, **kwargs)

    elif provider == "acme":
        from my_models.acme import AcmeModel
        return AcmeModel(model_id=model_id, **kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}")

# Use factory
model = create_model("acme", "acme-large", api_key="...")
```

## Best Practices

### 1. Follow Spark Conventions

```python
# Use standard parameter names
def __init__(self, model_id: str, temperature: float = 0.7, ...):
    pass

# Return ModelResponse objects
async def get_text(self, ...) -> ModelResponse:
    return ModelResponse(content=..., stop_reason=..., usage=...)
```

### 2. Handle Errors Consistently

```python
from spark.models.base import ModelError, ModelRateLimitError

try:
    response = await self._call_api()
except ProviderError as e:
    raise ModelError(f"Provider error: {e}") from e
```

### 3. Support Tool Calling

```python
# Implement tool spec conversion
def _convert_tool_specs(self, tool_specs):
    ...

# Handle tool use in responses
if "tool_calls" in response:
    return ModelResponse(content=[...], stop_reason="tool_use", ...)
```

### 4. Provide Configuration Management

```python
def update_config(self, **kwargs):
    self.config.update(kwargs)

def get_config(self) -> dict:
    return self.config.copy()
```

### 5. Document Provider-Specific Features

```python
class AcmeModel(Model):
    """Acme AI model provider.

    Supports:
    - Text and JSON completions
    - Tool calling
    - Up to 100K context window
    - Multi-modal inputs (text + images)

    Configuration:
    - temperature: 0.0-2.0 (default: 0.7)
    - max_tokens: Up to 4000 (default: 1000)
    - top_p: 0.0-1.0 (default: 1.0)

    Special features:
    - acme_mode: Enable Acme-specific reasoning mode
    - safety_level: 1-5, controls content filtering
    """
```

### 6. Add Type Hints

```python
from typing import Optional
from spark.models.types import Messages

async def get_text(
    self,
    messages: Messages,
    system_prompt: Optional[str] = None,
    **kwargs
) -> ModelResponse:
    """Get text completion with type hints."""
    pass
```

## Next Steps

- **[Model Abstraction](abstraction.md)**: Understand the model interface
- **[OpenAI Models](openai.md)**: See a complete reference implementation
- **[Testing Models](testing.md)**: Test your custom provider
- **[Agent System](../agents/README.md)**: Use your provider with agents
