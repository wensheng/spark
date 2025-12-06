---
title: Testing Models
parent: Models
nav_order: 3
---
# Testing Models

Spark provides testing utilities that enable development and testing without making expensive LLM API calls. These tools help you iterate quickly, run deterministic tests, and avoid costs during development.

## Overview

Testing models offer:

- **Zero API costs**: No API calls or charges
- **Instant responses**: No network latency
- **Deterministic behavior**: Consistent, predictable outputs
- **Offline development**: Work without internet connection
- **Test isolation**: No external dependencies in tests
- **Debugging support**: Controllable, inspectable behavior

## Quick Start

```python
from spark.models.testing import EchoModel

# Create echo model
model = EchoModel()

# Use like any other model
messages = [
    {"role": "user", "content": [{"text": "Hello, how are you?"}]}
]

response = await model.get_text(messages=messages)
print(response.content)
# Output: "Echo: Hello, how are you?"
```

## EchoModel

The `EchoModel` is a test model that echoes back user messages with predictable behavior.

### Basic Usage

```python
from spark.models.testing import EchoModel

model = EchoModel()

messages = [{"role": "user", "content": [{"text": "Test message"}]}]
response = await model.get_text(messages=messages)

print(response.content)  # "Echo: Test message"
print(response.stop_reason)  # "end_turn"
print(response.usage)  # {"input_tokens": 2, "output_tokens": 4, "total_tokens": 6}
```

### EchoModel Behavior

**Text Responses**:
- Prefixes user message with "Echo: "
- Returns immediately (no network delay)
- Simulates token usage statistics

**JSON Responses**:
```python
messages = [{"role": "user", "content": [{"text": "Get user data"}]}]
response = await model.get_json(messages=messages)

print(response.content)
# '{"echo": "Get user data", "timestamp": 1638360000.123}'
```

**Multi-Turn Conversations**:
```python
messages = [
    {"role": "user", "content": [{"text": "First message"}]},
    {"role": "assistant", "content": [{"text": "Echo: First message"}]},
    {"role": "user", "content": [{"text": "Second message"}]}
]

response = await model.get_text(messages=messages)
print(response.content)  # "Echo: Second message"
```

### Configuration

EchoModel accepts configuration parameters:

```python
model = EchoModel(
    model_id="echo-test",
    delay_seconds=0.1,  # Simulate network delay
    prefix="TEST: "  # Custom prefix
)

messages = [{"role": "user", "content": [{"text": "Hello"}]}]
response = await model.get_text(messages=messages)
print(response.content)  # "TEST: Hello"
```

## Mock Model Patterns

### Custom Mock Models

Create custom mock models for specific test scenarios:

```python
from spark.models.base import Model, ModelResponse
from spark.models.types import Messages

class FixedResponseModel(Model):
    """Model that returns fixed responses."""

    def __init__(self, fixed_response: str):
        super().__init__(model_id="fixed-response")
        self.fixed_response = fixed_response

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs
    ) -> ModelResponse:
        """Return fixed response."""
        return ModelResponse(
            content=self.fixed_response,
            stop_reason="end_turn",
            usage={
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15
            }
        )

    async def get_json(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs
    ) -> ModelResponse:
        """Return fixed JSON response."""
        return ModelResponse(
            content='{"result": "fixed"}',
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        )

# Use in tests
model = FixedResponseModel(fixed_response="Test response")
response = await model.get_text(messages=[])
assert response.content == "Test response"
```

### Sequence Mock Model

Return different responses in sequence:

```python
class SequenceModel(Model):
    """Model that returns responses in sequence."""

    def __init__(self, responses: list[str]):
        super().__init__(model_id="sequence")
        self.responses = responses
        self.call_count = 0

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs
    ) -> ModelResponse:
        """Return next response in sequence."""
        if self.call_count >= len(self.responses):
            response = self.responses[-1]  # Repeat last
        else:
            response = self.responses[self.call_count]

        self.call_count += 1

        return ModelResponse(
            content=response,
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        )

# Use in tests
model = SequenceModel(responses=[
    "First response",
    "Second response",
    "Third response"
])

assert (await model.get_text(messages=[])).content == "First response"
assert (await model.get_text(messages=[])).content == "Second response"
assert (await model.get_text(messages=[])).content == "Third response"
assert (await model.get_text(messages=[])).content == "Third response"  # Repeats
```

### Error Simulation Model

Simulate API errors for testing error handling:

```python
from spark.models.base import ModelError, ModelRateLimitError

class ErrorModel(Model):
    """Model that simulates errors."""

    def __init__(self, error_type: type = ModelError, error_message: str = "Test error"):
        super().__init__(model_id="error")
        self.error_type = error_type
        self.error_message = error_message
        self.call_count = 0
        self.fail_on_call = 1  # Which call to fail on

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs
    ) -> ModelResponse:
        """Raise error on specific call."""
        self.call_count += 1

        if self.call_count == self.fail_on_call:
            raise self.error_type(self.error_message)

        return ModelResponse(
            content="Success after error",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        )

# Test error handling
model = ErrorModel(error_type=ModelRateLimitError, error_message="Rate limited")
model.fail_on_call = 1

try:
    await model.get_text(messages=[])
    assert False, "Should have raised error"
except ModelRateLimitError:
    pass  # Expected

# Second call succeeds
response = await model.get_text(messages=[])
assert response.content == "Success after error"
```

## Testing Without API Calls

### Unit Testing Agents

Test agent logic without real API calls:

```python
import pytest
from spark.agents import Agent, AgentConfig
from spark.models.testing import EchoModel
from spark.tools.decorator import tool

@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@pytest.mark.asyncio
async def test_agent_with_echo_model():
    """Test agent with echo model."""
    model = EchoModel()

    config = AgentConfig(
        model=model,
        system_prompt="You are a math assistant.",
        tools=[add],
        max_steps=3
    )

    agent = Agent(config=config)

    # Test runs instantly without API calls
    response = await agent.process("What is 2 + 2?")

    # Verify agent behavior
    assert response is not None
    assert len(agent.memory.messages) > 0
```

### Integration Testing

Test workflows without API costs:

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.models.testing import EchoModel

class LLMNode(Node):
    """Node that uses LLM."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    async def process(self, context):
        messages = [
            {"role": "user", "content": [{"text": context.inputs.content}]}
        ]
        response = await self.model.get_text(messages=messages)
        return {"result": response.content}

@pytest.mark.asyncio
async def test_llm_workflow():
    """Test workflow with echo model."""
    model = EchoModel()

    node1 = LLMNode(model=model)
    node2 = LLMNode(model=model)

    node1 >> node2

    graph = Graph(start=node1)

    result = await graph.run(inputs={"content": "Test input"})

    # Verify workflow executed
    assert result is not None
    assert "Echo:" in result.content["result"]
```

### Testing Tool Calling

Mock tool calling behavior:

```python
class ToolCallingModel(Model):
    """Model that simulates tool calling."""

    def __init__(self, tool_to_call: str, tool_args: dict):
        super().__init__(model_id="tool-calling")
        self.tool_to_call = tool_to_call
        self.tool_args = tool_args
        self.call_count = 0

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        tool_specs: list[dict] | None = None,
        **kwargs
    ) -> ModelResponse:
        """Simulate tool calling."""
        self.call_count += 1

        if self.call_count == 1 and tool_specs:
            # First call: Request tool use
            return ModelResponse(
                content=[
                    {
                        "toolUse": {
                            "toolUseId": "test_123",
                            "name": self.tool_to_call,
                            "input": self.tool_args
                        }
                    }
                ],
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            )
        else:
            # Subsequent calls: Return final response
            return ModelResponse(
                content="Tool execution complete",
                stop_reason="end_turn",
                usage={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}
            )

# Test tool calling
@tool
def calculate(expression: str) -> float:
    """Evaluate expression."""
    return eval(expression)

model = ToolCallingModel(
    tool_to_call="calculate",
    tool_args={"expression": "2 + 2"}
)

response1 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "Calculate 2+2"}]}],
    tool_specs=[calculate.tool_spec]
)

assert response1.stop_reason == "tool_use"
assert response1.content[0]["toolUse"]["name"] == "calculate"

# Simulate tool result
tool_result = {
    "toolResult": {
        "toolUseId": "test_123",
        "content": [{"text": "4"}],
        "status": "success"
    }
}

messages = [
    {"role": "user", "content": [{"text": "Calculate 2+2"}]},
    {"role": "assistant", "content": response1.content},
    {"role": "user", "content": [tool_result]}
]

response2 = await model.get_text(messages=messages)
assert response2.stop_reason == "end_turn"
```

## Deterministic Testing

### With Response Caching

Use caching for deterministic tests with real models:

```python
from spark.models.openai import OpenAIModel

@pytest.fixture(scope="session")
def cached_model():
    """Model with caching for deterministic tests."""
    return OpenAIModel(
        model_id="gpt-4o-mini",
        enable_cache=True,
        cache_ttl_seconds=86400,  # 24 hours
        temperature=0.0  # Deterministic
    )

@pytest.mark.asyncio
async def test_with_cached_responses(cached_model):
    """Test with cached responses."""
    # First run: Hits API and caches
    # Subsequent runs: Use cached response (deterministic)
    messages = [{"role": "user", "content": [{"text": "What is 2+2?"}]}]

    response = await cached_model.get_text(messages=messages)

    assert "4" in response.content
```

### Fixture-Based Testing

Use fixtures to provide consistent test data:

```python
@pytest.fixture
def fixed_model():
    """Model with fixed responses."""
    return FixedResponseModel(
        fixed_response="The answer is 42."
    )

@pytest.mark.asyncio
async def test_with_fixture(fixed_model):
    """Test with fixed response."""
    response = await fixed_model.get_text(messages=[])
    assert response.content == "The answer is 42."

@pytest.mark.asyncio
async def test_agent_with_fixture(fixed_model):
    """Test agent with fixed response."""
    agent = Agent(config=AgentConfig(model=fixed_model))

    response = await agent.process("Any question")
    assert "42" in response
```

### Snapshot Testing

Compare outputs against saved snapshots:

```python
import json
from pathlib import Path

class SnapshotModel(Model):
    """Model that saves/loads snapshots."""

    def __init__(self, snapshot_file: str, record: bool = False):
        super().__init__(model_id="snapshot")
        self.snapshot_file = Path(snapshot_file)
        self.record = record
        self.snapshots = {}

        if self.snapshot_file.exists():
            with open(self.snapshot_file) as f:
                self.snapshots = json.load(f)

    def _get_key(self, messages: Messages) -> str:
        """Generate key for messages."""
        import hashlib
        content = json.dumps(messages, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    async def get_text(
        self,
        messages: Messages,
        system_prompt: str | None = None,
        **kwargs
    ) -> ModelResponse:
        """Return or record snapshot."""
        key = self._get_key(messages)

        if self.record:
            # Record mode: Call real model and save
            from spark.models.openai import OpenAIModel
            real_model = OpenAIModel(model_id="gpt-4o-mini")
            response = await real_model.get_text(messages=messages)

            self.snapshots[key] = {
                "content": response.content,
                "stop_reason": response.stop_reason,
                "usage": response.usage
            }

            # Save to file
            with open(self.snapshot_file, "w") as f:
                json.dump(self.snapshots, f, indent=2)

            return response

        else:
            # Playback mode: Return saved snapshot
            if key not in self.snapshots:
                raise KeyError(f"No snapshot for key {key}")

            snapshot = self.snapshots[key]
            return ModelResponse(**snapshot)

# Record snapshots (run once)
@pytest.mark.skip("Run manually to record snapshots")
@pytest.mark.asyncio
async def test_record_snapshots():
    """Record snapshots from real model."""
    model = SnapshotModel(
        snapshot_file="tests/snapshots/model_responses.json",
        record=True
    )

    messages = [{"role": "user", "content": [{"text": "What is Python?"}]}]
    await model.get_text(messages=messages)

# Use snapshots in tests (runs always)
@pytest.mark.asyncio
async def test_with_snapshots():
    """Test with recorded snapshots."""
    model = SnapshotModel(
        snapshot_file="tests/snapshots/model_responses.json",
        record=False
    )

    messages = [{"role": "user", "content": [{"text": "What is Python?"}]}]
    response = await model.get_text(messages=messages)

    # Deterministic response from snapshot
    assert "Python" in response.content
```

## Cost-Free Development

### Development Workflow

```python
import os

def create_model_for_env():
    """Create model based on environment."""
    if os.getenv("USE_REAL_MODEL") == "true":
        from spark.models.openai import OpenAIModel
        return OpenAIModel(model_id="gpt-4o-mini")
    else:
        from spark.models.testing import EchoModel
        return EchoModel()

# Use in development
model = create_model_for_env()

# Runs with echo model by default (free)
# Set USE_REAL_MODEL=true to use real model
```

### Hybrid Development

Switch between test and real models:

```python
class HybridModel:
    """Switch between test and real models."""

    def __init__(self, use_real: bool = False):
        if use_real:
            from spark.models.openai import OpenAIModel
            self.model = OpenAIModel(model_id="gpt-4o-mini")
        else:
            from spark.models.testing import EchoModel
            self.model = EchoModel()

    async def get_text(self, messages, **kwargs):
        return await self.model.get_text(messages, **kwargs)

# Develop with test model (free)
model = HybridModel(use_real=False)

# Test with real model occasionally
model = HybridModel(use_real=True)
```

### Progressive Testing

Start with mock, gradually add real models:

```python
@pytest.mark.parametrize("use_real_model", [False, True])
@pytest.mark.asyncio
async def test_with_both_models(use_real_model):
    """Test with both mock and real models."""
    if use_real_model:
        from spark.models.openai import OpenAIModel
        model = OpenAIModel(model_id="gpt-4o-mini", enable_cache=True)
    else:
        from spark.models.testing import EchoModel
        model = EchoModel()

    agent = Agent(config=AgentConfig(model=model))
    response = await agent.process("Test query")

    assert response is not None

# Run fast tests with mock (default)
# pytest tests/

# Run comprehensive tests with real model
# pytest tests/ -k "use_real_model"
```

## Best Practices

### 1. Use EchoModel for Fast Tests

```python
@pytest.mark.asyncio
async def test_fast_with_echo():
    """Fast test with echo model."""
    model = EchoModel()
    # Test runs in milliseconds
```

### 2. Use Cached Real Models for Accuracy

```python
@pytest.mark.asyncio
async def test_accurate_with_cache():
    """Accurate test with cached real model."""
    model = OpenAIModel(
        model_id="gpt-4o-mini",
        enable_cache=True
    )
    # First run: API call
    # Subsequent runs: Cached (fast)
```

### 3. Separate Fast and Slow Tests

```python
# Fast tests (echo model)
@pytest.mark.fast
@pytest.mark.asyncio
async def test_logic_with_echo():
    model = EchoModel()
    # Test logic, not model quality

# Slow tests (real model)
@pytest.mark.slow
@pytest.mark.asyncio
async def test_quality_with_real():
    model = OpenAIModel(model_id="gpt-4o-mini")
    # Test model quality

# Run fast tests: pytest -m fast
# Run all tests: pytest
```

### 4. Mock Tool Calling Specifically

```python
class MockToolCallingModel(Model):
    """Mock model with controlled tool calling."""

    def __init__(self, tools_to_call: list):
        super().__init__(model_id="mock-tool")
        self.tools_to_call = tools_to_call
        self.step = 0

    async def get_text(self, messages, tool_specs=None, **kwargs):
        if self.step < len(self.tools_to_call):
            tool_call = self.tools_to_call[self.step]
            self.step += 1

            return ModelResponse(
                content=[{"toolUse": tool_call}],
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            )
        else:
            return ModelResponse(
                content="Done",
                stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
            )
```

### 5. Provide Meaningful Test Responses

```python
class SmartEchoModel(Model):
    """Echo model with smart responses."""

    async def get_text(self, messages, **kwargs):
        user_message = messages[-1]["content"][0]["text"].lower()

        # Provide contextual responses
        if "calculate" in user_message or "+" in user_message:
            response = "The result is 42."
        elif "weather" in user_message:
            response = "The weather is sunny and 72°F."
        elif "time" in user_message:
            response = "The current time is 12:00 PM."
        else:
            response = f"Echo: {messages[-1]['content'][0]['text']}"

        return ModelResponse(
            content=response,
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        )
```

## Next Steps

- **[Model Abstraction](abstraction.md)**: Understand the model interface
- **[OpenAI Models](openai.md)**: Learn about real model implementation
- **[Response Caching](caching.md)**: Use caching for deterministic tests
- **[Agent System](../agents/README.md)**: Test agents without API calls
- **[Custom Providers](custom-providers.md)**: Create custom test models
