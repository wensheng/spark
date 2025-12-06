# Model Response Caching

Spark's model response caching system dramatically speeds up development and testing by caching LLM responses locally. When enabled, identical requests return cached responses instantly instead of making expensive API calls.

## Overview

The caching system provides:

- **100-500x speedup**: Cached responses return in milliseconds vs seconds for API calls
- **Cost savings**: Avoid repeated API charges during development
- **Deterministic testing**: Consistent responses for test suites
- **Thread-safe**: Safe for concurrent access
- **Automatic expiration**: TTL-based cache invalidation
- **Provider-agnostic**: Works with all model providers

## Quick Start

Enable caching when creating a model:

```python
from spark.models.openai import OpenAIModel

# Create model with caching enabled
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

# First call hits API and caches response
response1 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "What is Python?"}]}]
)
print("First call: API request made")

# Second identical call returns cached response (instant!)
response2 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "What is Python?"}]}]
)
print("Second call: Cache hit! No API request")

# Responses are identical
assert response1.content == response2.content
```

## When to Use Caching

### Ideal Use Cases

**Development and Debugging**:
```python
# Avoid repeated API calls while iterating on code
dev_model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=7200  # 2 hours
)
```

**Testing**:
```python
# Deterministic test responses without mocking
test_model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=86400  # 24 hours
)
```

**Prototyping**:
```python
# Fast iteration during prototyping
prototype_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)
```

**Repeated Queries**:
```python
# Cache frequently asked questions
faq_model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=86400  # 24 hours
)
```

### When to Avoid Caching

**Production Systems**:
```python
# Disable caching for fresh responses
prod_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False  # Default
)
```

**Time-Sensitive Data**:
```python
# Don't cache when responses need to be current
realtime_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False
)
```

**User-Specific Responses**:
```python
# Don't cache personalized responses
# (unless you include user ID in cache key via messages)
personalized_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False
)
```

## Configuration

### Cache Parameters

Configure caching behavior via model constructor:

```python
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,           # Enable/disable caching
    cache_ttl_seconds=86400      # Cache lifetime (default: 24 hours)
)
```

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `enable_cache` | bool | Enable response caching | False |
| `cache_ttl_seconds` | int | Time-to-live in seconds | 86400 (24h) |

### TTL Examples

```python
# 1 hour cache (rapid development)
model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=3600
)

# 24 hours cache (default, good for testing)
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=86400
)

# 7 days cache (long-term prototyping)
model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=604800
)

# Effectively permanent (1 year)
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=31536000
)
```

## Cache Key Generation

The cache system generates unique keys based on request parameters:

### Key Components

Cache keys are generated from:

1. **Provider**: Model provider (openai, bedrock, etc.)
2. **Model ID**: Specific model identifier (gpt-4o, claude-3, etc.)
3. **Messages**: Full conversation history
4. **System Prompt**: System instructions
5. **Tools**: Tool specifications (if using tool calling)
6. **Parameters**: Temperature, max_tokens, top_p, etc.

### Example Cache Keys

```python
# Key 1: Simple text completion
messages1 = [{"role": "user", "content": [{"text": "Hello"}]}]
# Cache key includes: openai|gpt-4o|messages_hash|no_system|no_tools|temp_0.7

# Key 2: Different message (different key)
messages2 = [{"role": "user", "content": [{"text": "Goodbye"}]}]
# Different cache key due to different message

# Key 3: Same message, different temperature (different key)
messages3 = [{"role": "user", "content": [{"text": "Hello"}]}]
# Different cache key due to temperature parameter
```

### Cache Key Sensitivity

The cache is sensitive to:

```python
# Same request = cache hit
response1 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "Hello"}]}],
    temperature=0.7
)

response2 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "Hello"}]}],
    temperature=0.7
)
# Cache hit! Same key

# Different parameter = cache miss
response3 = await model.get_text(
    messages=[{"role": "user", "content": [{"text": "Hello"}]}],
    temperature=0.9  # Different temperature
)
# Cache miss! Different key
```

### Order Matters

Message order affects cache keys:

```python
# These are different cache keys
messages_a = [
    {"role": "user", "content": [{"text": "First"}]},
    {"role": "assistant", "content": [{"text": "Second"}]}
]

messages_b = [
    {"role": "assistant", "content": [{"text": "Second"}]},
    {"role": "user", "content": [{"text": "First"}]}
]

# Different order = different cache keys
```

## Cache Storage

### Location

Cache files are stored in:

```
~/.cache/spark/llm-responses/<provider>/
```

For example:
```
~/.cache/spark/llm-responses/openai/
~/.cache/spark/llm-responses/bedrock/
~/.cache/spark/llm-responses/gemini/
```

### Structure

Each cached response is stored as a JSON file:

```json
{
    "content": "The capital of France is Paris.",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 15,
        "output_tokens": 8,
        "total_tokens": 23
    },
    "timestamp": 1638360000.123,
    "ttl": 86400,
    "provider": "openai",
    "model_id": "gpt-4o"
}
```

### File Naming

Cache files are named using SHA-256 hashes of cache keys:

```
a1b2c3d4e5f6...789.json
```

This ensures:
- Unique filenames for unique requests
- Consistent filenames for identical requests
- No filename collision issues

## Cache Management

### CacheManager

The `CacheManager` singleton manages all cache operations:

```python
from spark.models.cache import CacheManager

# Get cache manager instance
manager = CacheManager.get_instance()
```

### Cache Statistics

Get information about cache usage:

```python
stats = manager.get_stats()

print(f"Total cache entries: {stats['total_entries']}")
print(f"Total size: {stats['total_size_bytes'] / 1024 / 1024:.2f} MB")

# Per-provider statistics
for provider, provider_stats in stats['by_provider'].items():
    print(f"{provider}: {provider_stats['entries']} entries, "
          f"{provider_stats['size_bytes'] / 1024:.2f} KB")
```

Example output:
```
Total cache entries: 142
Total size: 3.45 MB
openai: 128 entries, 2.89 MB
bedrock: 14 entries, 0.56 MB
```

### Cache Cleanup

Remove expired entries:

```python
# Cleanup expired entries across all providers
removed = manager.cleanup_expired()
print(f"Removed {removed} expired entries")

# Cleanup specific provider
removed = manager.cleanup_expired(provider="openai")
print(f"Removed {removed} expired OpenAI cache entries")
```

### Clear Cache

Remove all cache entries:

```python
# Clear entire cache
cleared = manager.clear_all()
print(f"Cleared {cleared} cache entries")

# Clear specific provider
cleared = manager.clear_provider("openai")
print(f"Cleared {cleared} OpenAI cache entries")
```

### Manual Cache Inspection

```python
import os
from pathlib import Path

# Get cache directory
cache_dir = Path.home() / ".cache" / "spark" / "llm-responses"

# List all cache files
for provider_dir in cache_dir.iterdir():
    if provider_dir.is_dir():
        files = list(provider_dir.glob("*.json"))
        print(f"{provider_dir.name}: {len(files)} cache files")
```

## Performance Benefits

### Speed Comparison

Typical performance comparison:

| Operation | Time | Speedup |
|-----------|------|---------|
| API call (OpenAI GPT-4o) | ~2-5 seconds | 1x |
| API call (network delay) | +0.5-2 seconds | - |
| Cache hit (local disk) | ~5-20 ms | 100-500x |
| Cache hit (warm) | ~1-5 ms | 500-2000x |

### Real-World Example

```python
import time

model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True
)

messages = [{"role": "user", "content": [{"text": "Explain caching"}]}]

# First call: API request
start = time.time()
response1 = await model.get_text(messages=messages)
api_time = time.time() - start
print(f"API call: {api_time:.2f}s")

# Second call: Cache hit
start = time.time()
response2 = await model.get_text(messages=messages)
cache_time = time.time() - start
print(f"Cache hit: {cache_time:.3f}s")

speedup = api_time / cache_time
print(f"Speedup: {speedup:.0f}x")
```

Output:
```
API call: 2.34s
Cache hit: 0.012s
Speedup: 195x
```

### Development Workflow Impact

Without caching:
```python
# Modify code, test, iterate
# Each run: 10 API calls × 2s = 20s waiting
# 50 iterations = 1000s = 16.7 minutes of API waiting
```

With caching:
```python
# First run: 10 API calls × 2s = 20s
# Subsequent runs: 10 cache hits × 0.01s = 0.1s
# 50 iterations = 20s + 49×0.1s = 24.9s total
# Savings: 16.1 minutes
```

## Thread Safety

The cache system is thread-safe and supports concurrent access:

```python
import asyncio

model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True
)

async def make_request(i):
    """Make concurrent requests."""
    messages = [{"role": "user", "content": [{"text": f"Question {i}"}]}]
    response = await model.get_text(messages=messages)
    return response.content

# Safe concurrent access
tasks = [make_request(i) for i in range(10)]
results = await asyncio.gather(*tasks)
```

### Thread Safety Features

- **File locking**: Optional `filelock` package for atomic writes
- **Graceful fallback**: Works without `filelock` (best-effort)
- **Atomic operations**: Read and write operations are atomic
- **Race condition handling**: Concurrent cache misses handled safely

### Installing File Locking

For maximum thread safety:

```bash
pip install filelock
```

Without `filelock`, the cache still works but with slightly reduced safety guarantees in highly concurrent scenarios.

## Testing with Cache

### Deterministic Tests

Use caching for deterministic test responses:

```python
import pytest
from spark.models.openai import OpenAIModel

@pytest.fixture
def cached_model():
    """Model with caching for deterministic tests."""
    return OpenAIModel(
        model_id="gpt-4o-mini",
        enable_cache=True,
        cache_ttl_seconds=86400  # 24 hours
    )

async def test_agent_behavior(cached_model):
    """Test runs fast after first execution."""
    from spark.agents import Agent, AgentConfig

    agent = Agent(config=AgentConfig(model=cached_model))

    # First run: API call
    # Subsequent runs: Cache hit (instant)
    response = await agent.process("What is 2+2?")
    assert "4" in response
```

### Cache Warmup

Pre-populate cache for test suites:

```python
async def warmup_cache(model, test_cases):
    """Warmup cache with test cases."""
    print("Warming up cache...")

    for i, case in enumerate(test_cases):
        messages = [{"role": "user", "content": [{"text": case}]}]
        await model.get_text(messages=messages)
        print(f"Cached {i+1}/{len(test_cases)}")

    print("Cache warmup complete!")

# Run once before test suite
test_cases = [
    "What is Python?",
    "Explain asyncio",
    "How does caching work?"
]

model = OpenAIModel(model_id="gpt-4o-mini", enable_cache=True)
await warmup_cache(model, test_cases)

# Now tests run instantly
```

### Cleaning Test Cache

```python
def pytest_sessionstart(session):
    """Clear cache before test session."""
    from spark.models.cache import CacheManager

    manager = CacheManager.get_instance()
    manager.clear_all()
    print("Test cache cleared")

def pytest_sessionfinish(session):
    """Optionally keep or clear cache after tests."""
    # Keep cache for faster subsequent runs
    pass
```

## Advanced Usage

### Selective Caching

Cache some calls but not others:

```python
# Model with caching disabled by default
model = OpenAIModel(model_id="gpt-4o", enable_cache=False)

# Enable for specific expensive calls
expensive_model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

# Use different models based on need
if is_expensive_query:
    response = await expensive_model.get_text(messages=messages)
else:
    response = await model.get_text(messages=messages)
```

### Context-Aware Cache Keys

Include context in messages to create distinct cache keys:

```python
def create_contextual_messages(user_id: str, query: str):
    """Create messages with user context."""
    return [
        {
            "role": "system",
            "content": [{"text": f"User ID: {user_id}"}]
        },
        {
            "role": "user",
            "content": [{"text": query}]
        }
    ]

# Different users get different cache keys
messages_user1 = create_contextual_messages("user_1", "Hello")
messages_user2 = create_contextual_messages("user_2", "Hello")

# These will be cached separately
response1 = await model.get_text(messages=messages_user1)
response2 = await model.get_text(messages=messages_user2)
```

### Cache Monitoring

Monitor cache hit rates:

```python
class CacheMonitor:
    def __init__(self):
        self.hits = 0
        self.misses = 0

    async def get_with_monitoring(self, model, messages):
        """Monitor cache hits/misses."""
        import time

        start = time.time()
        response = await model.get_text(messages=messages)
        elapsed = time.time() - start

        # Assume cache hit if response is very fast
        if elapsed < 0.1:
            self.hits += 1
        else:
            self.misses += 1

        return response

    def get_hit_rate(self):
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0

# Use monitor
monitor = CacheMonitor()
model = OpenAIModel(model_id="gpt-4o-mini", enable_cache=True)

for query in queries:
    messages = [{"role": "user", "content": [{"text": query}]}]
    await monitor.get_with_monitoring(model, messages)

print(f"Cache hit rate: {monitor.get_hit_rate():.1%}")
```

### Development/Production Toggle

```python
import os

def create_model(model_id="gpt-4o"):
    """Create model with environment-aware caching."""
    is_dev = os.getenv("ENV", "development") != "production"

    return OpenAIModel(
        model_id=model_id,
        enable_cache=is_dev,  # Cache in dev, not in prod
        cache_ttl_seconds=3600 if is_dev else 0
    )

# Usage
model = create_model()
```

## Best Practices

### 1. Enable During Development

```python
# Development
dev_model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=7200
)
```

### 2. Disable in Production

```python
# Production
prod_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False
)
```

### 3. Use Appropriate TTL

```python
# Short TTL for changing data (1 hour)
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600
)

# Long TTL for stable data (7 days)
model = OpenAIModel(
    model_id="gpt-4o-mini",
    enable_cache=True,
    cache_ttl_seconds=604800
)
```

### 4. Clean Up Regularly

```python
# In CI/CD pipeline or maintenance script
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# Remove expired entries
removed = manager.cleanup_expired()

# Optionally clear old caches
if cache_size > MAX_SIZE:
    manager.clear_all()
```

### 5. Monitor Cache Size

```python
from spark.models.cache import CacheManager

def check_cache_size():
    """Alert if cache grows too large."""
    manager = CacheManager.get_instance()
    stats = manager.get_stats()

    size_mb = stats['total_size_bytes'] / 1024 / 1024

    if size_mb > 1000:  # 1 GB
        print(f"Warning: Cache size is {size_mb:.0f} MB")
        manager.cleanup_expired()

# Run periodically
check_cache_size()
```

### 6. Version Cache Keys

Include version in system prompt to invalidate cache:

```python
VERSION = "v1.2.0"

response = await model.get_text(
    messages=messages,
    system_prompt=f"Version {VERSION}: You are a helpful assistant."
)

# Changing VERSION creates new cache keys
```

## Troubleshooting

### Cache Not Working

**Symptom**: Requests always hit API, never cached

**Causes and Solutions**:

1. **Caching not enabled**:
   ```python
   # Fix: Enable caching
   model = OpenAIModel(model_id="gpt-4o", enable_cache=True)
   ```

2. **Parameters changing**:
   ```python
   # Problem: Random temperature
   response = await model.get_text(messages=messages, temperature=random.random())

   # Fix: Use consistent parameters
   response = await model.get_text(messages=messages, temperature=0.7)
   ```

3. **Messages not identical**:
   ```python
   # Problem: Timestamps in messages
   messages = [{"role": "user", "content": [{"text": f"Time: {time.time()}"}]}]

   # Fix: Remove dynamic content
   messages = [{"role": "user", "content": [{"text": "Static content"}]}]
   ```

### Cache Files Growing Large

**Symptom**: ~/.cache/spark/llm-responses/ consuming too much disk space

**Solutions**:

```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# 1. Cleanup expired entries
manager.cleanup_expired()

# 2. Clear specific provider
manager.clear_provider("openai")

# 3. Clear all
manager.clear_all()

# 4. Reduce TTL
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=3600  # Shorter TTL
)
```

### Permission Errors

**Symptom**: Permission denied writing to cache directory

**Solution**:

```bash
# Fix permissions
chmod -R u+w ~/.cache/spark/llm-responses/

# Or set custom cache location
export SPARK_CACHE_DIR="/tmp/spark-cache"
```

### Stale Cache Data

**Symptom**: Cached responses are outdated

**Solution**:

```python
# 1. Reduce TTL
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=1800  # 30 minutes
)

# 2. Clear cache manually
from spark.models.cache import CacheManager
CacheManager.get_instance().clear_all()

# 3. Disable caching for fresh data
model = OpenAIModel(model_id="gpt-4o", enable_cache=False)
```

## Next Steps

- **[OpenAI Models](openai.md)**: Learn about the OpenAI model implementation
- **[Model Abstraction](abstraction.md)**: Understand the model abstraction layer
- **[Testing Models](testing.md)**: Use caching with test models
- **[Agent System](../agents/README.md)**: Use cached models with agents
