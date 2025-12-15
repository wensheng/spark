---
title: Memory Management
parent: Agent
nav_order: 2
---
# Memory Management
---

Memory management in Spark agents controls how conversation history is stored, accessed, and managed over time. Different memory policies allow agents to handle conversations of varying lengths while balancing context preservation with token efficiency and cost.

Key capabilities:
- Multiple memory policy implementations
- Automatic history management
- Token-based windowing
- Automatic summarization
- Custom memory policy creation
- Thread-safe operations

## MemoryManager

The `MemoryManager` class orchestrates memory operations for agents. It provides a unified interface for different memory policies and handles conversation history lifecycle.

### Creating MemoryManager

```python
from spark.agents.memory import MemoryManager, MemoryPolicy

# Default: full memory
memory_manager = MemoryManager()

# With specific policy
memory_manager = MemoryManager(
    policy=MemoryPolicy.SLIDING_WINDOW,
    config={"window_size": 4000}
)

# With custom memory implementation
from spark.agents.memory import RollingWindowMemory
memory_impl = RollingWindowMemory(window_size=8000)
memory_manager = MemoryManager(memory=memory_impl)
```

### MemoryManager Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `add_message(message)` | Add message to history | `None` |
| `get_messages()` | Get all messages in current window | `List[Message]` |
| `clear()` | Clear all history | `None` |
| `get_summary()` | Get memory summary stats | `dict` |
| `should_summarize()` | Check if summarization needed | `bool` |
| `summarize()` | Trigger summarization | `None` |

## AbstractMemory Interface

All memory implementations extend the `AbstractMemory` base class:

```python
from abc import ABC, abstractmethod
from typing import List

class AbstractMemory(ABC):
    """Base class for memory implementations."""

    @abstractmethod
    def add_message(self, message: dict) -> None:
        """Add a message to memory."""
        pass

    @abstractmethod
    def get_messages(self) -> List[dict]:
        """Retrieve messages from memory."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all messages."""
        pass

    @abstractmethod
    def get_summary(self) -> dict:
        """Get memory statistics."""
        pass
```

## Conversation History Structure

### Message Format

Messages follow Spark's unified format:

```python
message = {
    "role": "user",  # or "assistant"
    "content": [
        {"text": "Hello, how are you?"}
    ]
}

# Assistant message with tool use
assistant_message = {
    "role": "assistant",
    "content": [
        {"text": "Let me check that for you."},
        {
            "toolUse": {
                "toolUseId": "call_123",
                "name": "search_web",
                "input": {"query": "weather"}
            }
        }
    ]
}

# Tool result message
tool_result_message = {
    "role": "user",
    "content": [
        {
            "toolResult": {
                "toolUseId": "call_123",
                "content": [{"text": "Sunny, 72°F"}]
            }
        }
    ]
}
```

### Accessing History

```python
from spark.agents import Agent

agent = Agent()
await agent.run(user_message="Hello")
await agent.run(user_message="How are you?")

# Get full history
history = agent.get_history()
for msg in history:
    print(f"{msg['role']}: {msg['content'][0]['text']}")

# Output:
# user: Hello
# assistant: Hello! How can I help you?
# user: How are you?
# assistant: I'm doing well, thank you!
```

## Memory Implementations

### Full Memory

Keeps complete conversation history with no truncation.

**Use Cases**:
- Short conversations
- Complete context required
- Cost is not a concern
- Legal/compliance requirements

**Configuration**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy

config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL
)

agent = Agent(config=config)
```

**Characteristics**:
- ✅ Complete context preservation
- ✅ Simple implementation
- ✅ No information loss
- ❌ Unbounded token growth
- ❌ May hit context limits
- ❌ Higher API costs

**Example**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.FULL,
    system_prompt="You are a legal assistant. Maintain complete conversation records."
)

agent = Agent(config=config)

# All messages preserved
for i in range(100):
    await agent.run(user_message=f"Question {i}")

history = agent.get_history()
print(f"Messages in history: {len(history)}")  # 200+ messages
```

### RollingWindowMemory

Maintains a sliding window of recent messages based on token count.

**Use Cases**:
- Long conversations
- Bounded memory requirements
- Recent context is sufficient
- Cost-conscious applications

**Configuration**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy

config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={
        "window_size": 4000  # tokens
    }
)

agent = Agent(config=config)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_size` | `int` | `4000` | Maximum tokens in window |

**Characteristics**:
- ✅ Bounded token usage
- ✅ Predictable costs
- ✅ Handles long conversations
- ❌ Loses old context
- ❌ May forget important information
- ❌ Approximate token counting

**Example**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SLIDING_WINDOW,
    memory_config={
        "window_size": 8000  # Keep last 8K tokens
    }
)

agent = Agent(config=config)

# Simulate long conversation
for i in range(100):
    await agent.run(user_message=f"Tell me about topic {i}")

# History size bounded
history = agent.get_history()
print(f"Messages in history: {len(history)}")  # Much less than 200
```

**Token Counting**:

Rolling window uses approximate token counting:

```python
def estimate_tokens(text: str) -> int:
    """Estimate tokens (roughly 4 chars = 1 token)."""
    return len(text) // 4
```

For production use with accurate counting, consider integrating `tiktoken`:

```python
import tiktoken

def count_tokens(text: str, model: str = "gpt-5-mini") -> int:
    """Count tokens accurately."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))
```

### SummaryMemory

Automatically summarizes old context when token limit reached.

**Use Cases**:
- Long conversations requiring context
- Balance between detail and token cost
- Gradual information distillation
- Complex multi-topic discussions

**Configuration**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy

config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.SUMMARIZATION,
    memory_config={
        "max_tokens": 4000,  # Trigger threshold
        "summary_ratio": 0.3,  # Target 30% of original
        "summary_model": lightweight_model  # Optional
    }
)

agent = Agent(config=config)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_tokens` | `int` | `4000` | Token threshold for summarization |
| `summary_ratio` | `float` | `0.3` | Target summary length (0.0-1.0) |
| `summary_model` | `Model` | `None` | Optional model for summaries (uses main model if None) |

**Characteristics**:
- ✅ Retains important information
- ✅ Bounded token usage
- ✅ Handles long conversations
- ✅ Preserves key facts
- ❌ Information loss through summarization
- ❌ Additional API calls for summaries
- ❌ Slower than rolling window

**Example**:

```python
from spark.agents import Agent, AgentConfig, MemoryPolicy
from spark.models.openai import OpenAIModel

# Main model for conversation
main_model = OpenAIModel(model_id="gpt-5-mini")

# Lightweight model for summaries (optional)
summary_model = OpenAIModel(model_id="gpt-5-mini-mini")

config = AgentConfig(
    model=main_model,
    memory_policy=MemoryPolicy.SUMMARIZATION,
    memory_config={
        "max_tokens": 6000,  # Summarize after 6K tokens
        "summary_ratio": 0.25,  # Compress to 25%
        "summary_model": summary_model
    }
)

agent = Agent(config=config)

# Long conversation
await agent.run(user_message="Tell me about the history of Python programming language.")
# ... many more exchanges ...
await agent.run(user_message="What key points have we discussed?")
# Agent can reference summarized early context
```

**Summarization Process**:

1. Monitor token count of conversation history
2. When `max_tokens` exceeded, trigger summarization
3. Use LLM to summarize older messages
4. Replace old messages with summary
5. Continue with recent messages + summary

**Summary Message Structure**:

```python
summary_message = {
    "role": "assistant",
    "content": [
        {
            "text": "Previous conversation summary: The user asked about..."
        }
    ],
    "metadata": {
        "is_summary": True,
        "original_message_count": 42,
        "summary_date": "2025-12-05T10:30:00Z"
    }
}
```

### VectorMemory (Future)

Semantic search-based memory using embeddings (planned feature).

**Planned Use Cases**:
- Long-term memory across sessions
- Retrieve relevant past context
- Knowledge base integration
- Personalization

**Planned Configuration**:

```python
# Future API
config = AgentConfig(
    model=model,
    memory_policy=MemoryPolicy.VECTOR,
    memory_config={
        "vector_store": "pinecone",
        "top_k": 5,  # Retrieve top 5 relevant messages
        "embedding_model": "text-embedding-ada-002"
    }
)
```

## Memory Policies

### MemoryPolicy Enum

```python
from spark.agents.memory import MemoryPolicy

class MemoryPolicy(Enum):
    """Memory management strategies."""
    FULL = "full"  # Keep everything
    SLIDING_WINDOW = "sliding_window"  # Rolling window
    SUMMARIZATION = "summarization"  # Auto-summarize
    # VECTOR = "vector"  # Future: semantic search
```

### Policy Selection Guide

| Scenario | Recommended Policy | Configuration |
|----------|-------------------|---------------|
| Short Q&A (< 10 exchanges) | FULL | Default |
| Customer support (bounded) | SLIDING_WINDOW | window_size=8000 |
| Long technical discussions | SUMMARIZATION | max_tokens=6000 |
| Multi-session chatbot | FULL + checkpointing | Save/restore state |
| Cost-sensitive app | SLIDING_WINDOW | Small window_size |
| Compliance/audit | FULL | Archive externally |

### Comparing Policies

```python
import asyncio
from spark.agents import Agent, AgentConfig, MemoryPolicy
from spark.models.openai import OpenAIModel

async def compare_policies():
    model = OpenAIModel(model_id="gpt-5-mini-mini", enable_cache=True)

    policies = [
        (MemoryPolicy.FULL, {}),
        (MemoryPolicy.SLIDING_WINDOW, {"window_size": 2000}),
        (MemoryPolicy.SUMMARIZATION, {"max_tokens": 2000})
    ]

    for policy, config in policies:
        agent_config = AgentConfig(
            model=model,
            memory_policy=policy,
            memory_config=config
        )
        agent = Agent(config=agent_config)

        # Simulate conversation
        for i in range(20):
            await agent.run(user_message=f"Tell me fact {i}")

        # Check memory usage
        stats = agent.get_cost_stats()
        history_len = len(agent.get_history())

        print(f"\n{policy.value}:")
        print(f"  Messages: {history_len}")
        print(f"  Total tokens: {stats.total_tokens:,}")
        print(f"  Cost: ${stats.total_cost:.4f}")

asyncio.run(compare_policies())
```

## Adding Messages Programmatically

### Basic Message Addition

```python
from spark.agents import Agent

agent = Agent()

# Add user message
agent.add_message_to_history({
    "role": "user",
    "content": [{"text": "Hello!"}]
})

# Add assistant message
agent.add_message_to_history({
    "role": "assistant",
    "content": [{"text": "Hi there!"}]
})

# Continue conversation
result = await agent.run(user_message="How are you?")
```

### Adding Context Messages

Inject context at conversation start:

```python
from spark.agents import Agent

agent = Agent()

# Add system context
agent.add_message_to_history({
    "role": "user",
    "content": [{"text": "My name is Alice and I work in data science."}]
})

agent.add_message_to_history({
    "role": "assistant",
    "content": [{"text": "Nice to meet you, Alice! I'd be happy to help with data science questions."}]
})

# Agent now has context
result = await agent.run(user_message="What's my name?")
print(result)  # "Your name is Alice."
```

### Adding Tool Traces

Manually add tool execution records:

```python
# Add tool call
agent.add_message_to_history({
    "role": "assistant",
    "content": [
        {"text": "Let me search for that."},
        {
            "toolUse": {
                "toolUseId": "call_123",
                "name": "search_web",
                "input": {"query": "Python tutorials"}
            }
        }
    ]
})

# Add tool result
agent.add_message_to_history({
    "role": "user",
    "content": [
        {
            "toolResult": {
                "toolUseId": "call_123",
                "content": [{"text": "Found 10 tutorials..."}]
            }
        }
    ]
})
```

## Clearing History

### Clear All History

```python
from spark.agents import Agent

agent = Agent()

# Use agent
await agent.run(user_message="Hello")
await agent.run(user_message="How are you?")

# Clear history
agent.clear_history()

# Fresh start
result = await agent.run(user_message="Hello")
# Agent has no memory of previous conversation
```

### Selective Clearing

Clear specific portions of history:

```python
from spark.agents import Agent

agent = Agent()

# Get current history
history = agent.get_history()

# Keep last N messages
recent_messages = history[-10:]

# Clear and restore
agent.clear_history()
for msg in recent_messages:
    agent.add_message_to_history(msg)
```

## Memory State Inspection

### Get Memory Statistics

```python
from spark.agents import Agent

agent = Agent()

# Use agent
for i in range(50):
    await agent.run(user_message=f"Question {i}")

# Inspect memory state
history = agent.get_history()
print(f"Messages in history: {len(history)}")

# Get cost statistics (includes token counts)
stats = agent.get_cost_stats()
print(f"Total input tokens: {stats.total_input_tokens:,}")
print(f"Total output tokens: {stats.total_output_tokens:,}")
print(f"Total tokens: {stats.total_tokens:,}")
```

### Memory Summary

Get detailed memory summary:

```python
from spark.agents.memory import MemoryManager, MemoryPolicy

memory_manager = MemoryManager(
    policy=MemoryPolicy.SLIDING_WINDOW,
    config={"window_size": 4000}
)

# Add messages...

# Get summary
summary = memory_manager.get_summary()
print(f"Message count: {summary['message_count']}")
print(f"Estimated tokens: {summary['estimated_tokens']}")
print(f"Policy: {summary['policy']}")
```

### Debugging Memory

```python
from spark.agents import Agent

agent = Agent()

# Add conversation
await agent.run(user_message="Hello")
await agent.run(user_message="Tell me about Python")

# Debug history
history = agent.get_history()
for i, msg in enumerate(history):
    role = msg["role"]
    content_items = msg["content"]

    print(f"\nMessage {i} ({role}):")
    for item in content_items:
        if "text" in item:
            print(f"  Text: {item['text'][:50]}...")
        elif "toolUse" in item:
            print(f"  Tool call: {item['toolUse']['name']}")
        elif "toolResult" in item:
            print(f"  Tool result: {item['toolResult']['toolUseId']}")
```

## Custom Memory Policies

### Implementing Custom Memory

Create custom memory by extending `AbstractMemory`:

```python
from spark.agents.memory import AbstractMemory
from typing import List
from collections import deque

class RecentNMemory(AbstractMemory):
    """Keep only the most recent N messages."""

    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self.messages = deque(maxlen=max_messages)

    def add_message(self, message: dict) -> None:
        """Add message (automatically drops oldest if full)."""
        self.messages.append(message)

    def get_messages(self) -> List[dict]:
        """Get all messages in memory."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    def get_summary(self) -> dict:
        """Get memory statistics."""
        return {
            "message_count": len(self.messages),
            "max_messages": self.max_messages,
            "policy": "recent_n"
        }
```

### Using Custom Memory

```python
from spark.agents import Agent, AgentConfig
from spark.agents.memory import MemoryManager

# Create custom memory
custom_memory = RecentNMemory(max_messages=20)

# Create memory manager with custom implementation
memory_manager = MemoryManager(memory=custom_memory)

# Use in agent (requires manual integration)
agent = Agent()
agent._memory_manager = memory_manager

# Agent now uses custom memory policy
```

### Advanced Custom Memory: Priority-Based

```python
from spark.agents.memory import AbstractMemory
from typing import List
import heapq

class PriorityMemory(AbstractMemory):
    """Keep messages based on importance scores."""

    def __init__(self, max_messages: int = 50):
        self.max_messages = max_messages
        self.messages = []
        self.counter = 0

    def add_message(self, message: dict, priority: float = 1.0) -> None:
        """Add message with priority."""
        # Use counter for stable sorting
        heapq.heappush(
            self.messages,
            (-priority, self.counter, message)  # Negative for max-heap
        )
        self.counter += 1

        # Trim if exceeds max
        while len(self.messages) > self.max_messages:
            heapq.heappop(self.messages)

    def get_messages(self) -> List[dict]:
        """Get messages sorted by priority."""
        return [msg for _, _, msg in sorted(self.messages, key=lambda x: x[1])]

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self.counter = 0

    def get_summary(self) -> dict:
        """Get memory statistics."""
        return {
            "message_count": len(self.messages),
            "max_messages": self.max_messages,
            "policy": "priority_based"
        }
```

## Best Practices

### 1. Choose Appropriate Policy

Match policy to use case:

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

### 2. Monitor Memory Usage

Track token counts in production:

```python
agent = Agent(config=config)
result = await agent.run(user_message="...")

stats = agent.get_cost_stats()
if stats.total_tokens > 50000:
    logger.warning(f"High token usage: {stats.total_tokens:,}")
```

### 3. Clear History Periodically

For long-running agents:

```python
# Clear after N exchanges
if len(agent.get_history()) > 100:
    agent.clear_history()

# Or clear after time period
if time.time() - session_start > 3600:  # 1 hour
    agent.clear_history()
```

### 4. Use Checkpointing for Sessions

Persist memory across sessions:

```python
# Save at end of session
agent.save_checkpoint("session.json")

# Restore in new session
agent = Agent.load_checkpoint("session.json", config)
```

### 5. Test Memory Policies

Test different policies for your use case:

```python
import pytest
from spark.agents import Agent, AgentConfig, MemoryPolicy

@pytest.mark.asyncio
async def test_memory_policies():
    """Test different memory policies."""
    test_messages = [f"Message {i}" for i in range(100)]

    for policy in [MemoryPolicy.FULL, MemoryPolicy.SLIDING_WINDOW]:
        agent = Agent(config=AgentConfig(
            model=model,
            memory_policy=policy,
            memory_config={"window_size": 2000} if policy == MemoryPolicy.SLIDING_WINDOW else {}
        ))

        for msg in test_messages:
            await agent.run(user_message=msg)

        history_len = len(agent.get_history())
        print(f"{policy.value}: {history_len} messages retained")
```

## Next Steps

- Review [Agent Configuration](configuration.md) for memory policy configuration
- See [Checkpointing Reference](checkpointing.md) for state persistence
- Learn about [Cost Tracking](cost-tracking.md) for monitoring token usage
- Explore [Agent Fundamentals](fundamentals.md) for general agent usage
