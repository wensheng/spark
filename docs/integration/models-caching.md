---
title: Models and Caching
parent: Integration
nav_order: 7
---
# Models and Caching
---

This guide covers LLM response caching across model providers, including configuration, cache sharing, invalidation strategies, cost analysis, and best practices for development vs. production environments.

## Table of Contents

- [Overview](#overview)
- [Enabling Response Caching](#enabling-response-caching)
- [Cache Configuration Per Model](#cache-configuration-per-model)
- [Cache Sharing Across Agents](#cache-sharing-across-agents)
- [Cache Invalidation Strategies](#cache-invalidation-strategies)
- [Cost Savings Analysis](#cost-savings-analysis)
- [Development vs Production Caching](#development-vs-production-caching)

## Overview

Spark's response caching system provides a unified caching layer across all model providers (OpenAI, Bedrock, Gemini). Caching identical API requests can dramatically reduce costs and latency during development and testing.

**Key Benefits**:
- **Cost Savings**: Avoid redundant API calls (100-500x cheaper)
- **Faster Development**: Instant responses for cached queries
- **Consistent Testing**: Deterministic responses for test suites
- **Provider Agnostic**: Works across all model providers

**Default Behavior**: Caching is **disabled by default** for safety and predictability.

## Enabling Response Caching

### Basic Cache Configuration

```python
from spark.models.openai import OpenAIModel

# Enable caching with default settings
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True  # Enable response caching
)

# First call hits API and caches response
response1 = await model.get_text(
    messages=[{"role": "user", "content": "What is AI?"}]
)

# Second identical call returns cached response instantly
response2 = await model.get_text(
    messages=[{"role": "user", "content": "What is AI?"}]
)

# response1 == response2, but response2 was instant and free
```

### Custom Cache Configuration

```python
from spark.models.cache import CacheConfig
from pathlib import Path

# Custom cache configuration
cache_config = CacheConfig(
    enabled=True,
    cache_dir=Path("./my_cache"),  # Custom cache directory
    ttl_seconds=7200,               # 2 hour TTL (default: 24 hours)
    max_cache_size_mb=500,          # 500MB limit (default: 1GB)
)

model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_config=cache_config
)
```

### Cache Key Generation

Cache keys are deterministic and based on:

```python
# Cache key includes:
# - Provider name (openai, bedrock, gemini)
# - Model ID (gpt-4o, claude-3-sonnet, etc.)
# - Messages/prompts (complete conversation)
# - System prompts
# - Tool specifications
# - Temperature and other parameters

# These will have DIFFERENT cache keys:
response1 = await model.get_text(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7
)

response2 = await model.get_text(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.9  # Different temperature = different cache key
)

# These will have the SAME cache key:
response1 = await model.get_text(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7
)

response2 = await model.get_text(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7  # Identical parameters = cache hit
)
```

## Cache Configuration Per Model

Different models can have different cache configurations:

### Model-Specific Caching

```python
# Expensive model: long TTL, aggressive caching
gpt4_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=86400  # 24 hours
)

# Cheap model: shorter TTL, less aggressive
gpt3_model = OpenAIModel(
    model_id="gpt-3.5-turbo",
    enable_cache=True,
    cache_ttl_seconds=3600  # 1 hour
)

# No caching for production real-time model
realtime_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False  # No caching
)
```

### Provider-Specific Caching

```python
from spark.models.openai import OpenAIModel
from spark.models.bedrock import BedrockModel
from spark.models.gemini import GeminiModel

# Each provider gets its own cache namespace
openai_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True
)

bedrock_model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    enable_cache=True
)

gemini_model = GeminiModel(
    model_id="gemini-pro",
    enable_cache=True
)

# Cache organized by provider:
# ~/.cache/spark/llm-responses/
#   openai/
#     gpt-4o/
#       {cache_key}.json
#   bedrock/
#     claude-sonnet-4-5/
#       {cache_key}.json
#   gemini/
#     gemini-pro/
#       {cache_key}.json
```

### Environment-Based Configuration

```python
import os

# Load cache settings from environment
ENABLE_CACHE = os.getenv("SPARK_ENABLE_CACHE", "false").lower() == "true"
CACHE_TTL = int(os.getenv("SPARK_CACHE_TTL", "3600"))

model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=ENABLE_CACHE,
    cache_ttl_seconds=CACHE_TTL
)

# Development: SPARK_ENABLE_CACHE=true SPARK_CACHE_TTL=86400
# Production: SPARK_ENABLE_CACHE=false (or not set)
```

## Cache Sharing Across Agents

Share cache across multiple agents for maximum benefit:

### Shared Cache Manager

```python
from spark.models.cache import CacheManager

# Global cache manager (singleton)
cache_manager = CacheManager.get_instance()

# All models share the same cache by default
agent1 = Agent(config=AgentConfig(
    model=OpenAIModel(model_id="gpt-4o", enable_cache=True),
    name="Agent1"
))

agent2 = Agent(config=AgentConfig(
    model=OpenAIModel(model_id="gpt-4o", enable_cache=True),
    name="Agent2"
))

# If Agent1 makes a query, Agent2 gets it from cache
await agent1.run("What is Python?")  # Hits API
await agent2.run("What is Python?")  # Cache hit!
```

### Cache Statistics

Monitor cache effectiveness:

```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# Get cache statistics
stats = manager.get_stats()

print(f"Cache Statistics:")
print(f"  Total entries: {stats['total_entries']}")
print(f"  Total size: {stats['total_size_bytes'] / 1024 / 1024:.2f} MB")
print(f"  Hit rate: {stats['hit_rate']:.2%}")
print(f"  Entries by provider:")
for provider, count in stats['entries_by_provider'].items():
    print(f"    {provider}: {count}")
```

### Selective Cache Sharing

Share cache between some agents but not others:

```python
from spark.models.cache import CacheConfig
from pathlib import Path

# Development agents share cache
dev_cache = CacheConfig(
    enabled=True,
    cache_dir=Path("./dev_cache")
)

dev_agent1 = Agent(config=AgentConfig(
    model=OpenAIModel(
        model_id="gpt-4o",
        enable_cache=True,
        cache_config=dev_cache
    )
))

dev_agent2 = Agent(config=AgentConfig(
    model=OpenAIModel(
        model_id="gpt-4o",
        enable_cache=True,
        cache_config=dev_cache
    )
))

# Production agent has separate cache (or no cache)
prod_agent = Agent(config=AgentConfig(
    model=OpenAIModel(
        model_id="gpt-4o",
        enable_cache=False  # No cache in production
    )
))
```

## Cache Invalidation Strategies

Manage cache freshness and validity:

### Time-Based Invalidation (TTL)

```python
# Short TTL for frequently changing data
news_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=300  # 5 minutes
)

# Long TTL for static content
docs_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=604800  # 1 week
)

# Cache entries automatically expire after TTL
```

### Manual Cache Clearing

```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# Clear all cache
manager.clear_all()

# Clear cache for specific provider
manager.clear_provider('openai')

# Clear cache for specific model
manager.clear_model('openai', 'gpt-4o')

# Remove expired entries
removed_count = manager.cleanup_expired()
print(f"Removed {removed_count} expired cache entries")
```

### Conditional Invalidation

```python
class ConditionalCacheModel:
    """Model with conditional cache invalidation."""

    def __init__(self, model):
        self.model = model
        self.cache_manager = CacheManager.get_instance()

    async def get_text_with_freshness(
        self,
        messages,
        require_fresh=False,
        **kwargs
    ):
        """Get text with optional cache bypass."""

        if require_fresh:
            # Clear cache for this specific query
            cache_key = self.cache_manager.generate_cache_key(
                provider='openai',
                model_id=self.model.model_id,
                messages=messages,
                **kwargs
            )
            self.cache_manager.remove_entry(cache_key)

        return await self.model.get_text(messages, **kwargs)

# Usage
model = ConditionalCacheModel(OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True
))

# Use cache
response = await model.get_text_with_freshness(messages, require_fresh=False)

# Bypass cache
response = await model.get_text_with_freshness(messages, require_fresh=True)
```

### Version-Based Invalidation

```python
class VersionedCacheModel:
    """Model with version-based cache invalidation."""

    def __init__(self, model, cache_version="v1"):
        self.model = model
        self.cache_version = cache_version

    async def get_text(self, messages, **kwargs):
        """Get text with version in cache key."""

        # Add version to messages for cache key
        versioned_messages = [
            {"role": "system", "content": f"cache_version:{self.cache_version}"},
            *messages
        ]

        return await self.model.get_text(versioned_messages, **kwargs)

# Usage
model_v1 = VersionedCacheModel(
    OpenAIModel(model_id="gpt-4o", enable_cache=True),
    cache_version="v1"
)

# When you update prompts or logic, bump version
model_v2 = VersionedCacheModel(
    OpenAIModel(model_id="gpt-4o", enable_cache=True),
    cache_version="v2"  # Different version = different cache
)
```

## Cost Savings Analysis

Measure and track cache cost savings:

### Cache Savings Tracker

```python
class CacheSavingsTracker:
    """Track cost savings from caching."""

    def __init__(self):
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_savings = 0.0

    async def track_call(self, model, messages, **kwargs):
        """Track a model call and calculate savings."""

        # Check if this would be a cache hit
        cache_key = CacheManager.get_instance().generate_cache_key(
            provider=model.provider,
            model_id=model.model_id,
            messages=messages,
            **kwargs
        )

        is_cache_hit = CacheManager.get_instance().has_entry(cache_key)

        # Make the call
        response = await model.get_text(messages, **kwargs)

        # Track savings
        if is_cache_hit:
            self.cache_hits += 1
            # Estimate cost savings (example rates)
            estimated_cost = self.estimate_cost(model.model_id, messages, response)
            self.total_savings += estimated_cost
        else:
            self.cache_misses += 1

        return response

    def estimate_cost(self, model_id, messages, response):
        """Estimate API call cost."""
        # Rough estimates (replace with actual pricing)
        pricing = {
            'gpt-4o': {'input': 5.00, 'output': 15.00},  # per 1M tokens
            'gpt-3.5-turbo': {'input': 0.50, 'output': 1.50}
        }

        # Estimate tokens (very rough)
        input_tokens = sum(len(m['content'].split()) * 1.3 for m in messages)
        output_tokens = len(response.split()) * 1.3

        rates = pricing.get(model_id, {'input': 5.00, 'output': 15.00})
        cost = (
            (input_tokens / 1_000_000) * rates['input'] +
            (output_tokens / 1_000_000) * rates['output']
        )

        return cost

    def get_report(self):
        """Get savings report."""
        total_calls = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total_calls if total_calls > 0 else 0

        return {
            'total_calls': total_calls,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate,
            'total_savings': self.total_savings
        }

# Usage
tracker = CacheSavingsTracker()
model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

# Track calls
for query in queries:
    await tracker.track_call(model, [{"role": "user", "content": query}])

# Get report
report = tracker.get_report()
print(f"Cache Statistics:")
print(f"  Total calls: {report['total_calls']}")
print(f"  Cache hits: {report['cache_hits']}")
print(f"  Hit rate: {report['hit_rate']:.1%}")
print(f"  Total savings: ${report['total_savings']:.4f}")
```

### Integration with Agent Cost Tracking

```python
from spark.agents import Agent, AgentConfig

class CacheAwareAgent(Agent):
    """Agent that tracks cache savings."""

    def __init__(self, config):
        super().__init__(config)
        self.cache_savings = 0.0

    async def run(self, query, **kwargs):
        """Run agent and track cache savings."""

        # Get cost before
        cost_before = self.get_cost_stats().total_cost

        # Run agent
        result = await super().run(query, **kwargs)

        # Get cost after
        cost_after = self.get_cost_stats().total_cost

        # If no cost increase, it was a cache hit
        if cost_after == cost_before:
            # Estimate what it would have cost
            estimated_cost = 0.01  # Rough estimate
            self.cache_savings += estimated_cost

        return result

    def get_savings_report(self):
        """Get cache savings report."""
        actual_cost = self.get_cost_stats().total_cost
        total_cost_without_cache = actual_cost + self.cache_savings

        return {
            'actual_cost': actual_cost,
            'cache_savings': self.cache_savings,
            'total_cost_without_cache': total_cost_without_cache,
            'savings_percentage': (
                self.cache_savings / total_cost_without_cache * 100
                if total_cost_without_cache > 0 else 0
            )
        }
```

## Development vs Production Caching

Different caching strategies for different environments:

### Development Configuration

```python
# Development: Aggressive caching
dev_config = {
    'enable_cache': True,
    'cache_ttl_seconds': 86400,  # 24 hours
    'cache_dir': Path("./dev_cache"),
}

dev_model = OpenAIModel(
    model_id="gpt-4o",
    **dev_config
)

# Benefits:
# - Fast iteration (instant responses)
# - Reduced API costs during development
# - Consistent behavior for debugging
# - Shareable cache across team
```

### Testing Configuration

```python
# Testing: Very aggressive caching + deterministic
test_config = {
    'enable_cache': True,
    'cache_ttl_seconds': 2592000,  # 30 days
    'cache_dir': Path("./test_cache"),
}

test_model = OpenAIModel(
    model_id="gpt-4o",
    **test_config
)

# Benefits:
# - Deterministic tests (same inputs = same outputs)
# - Fast test execution
# - No API costs for tests
# - Can commit cache to version control for CI/CD
```

### Staging Configuration

```python
# Staging: Moderate caching
staging_config = {
    'enable_cache': True,
    'cache_ttl_seconds': 3600,  # 1 hour
    'cache_dir': Path("/var/cache/spark/staging"),
}

staging_model = OpenAIModel(
    model_id="gpt-4o",
    **staging_config
)

# Benefits:
# - Some cost savings
# - More realistic behavior than dev
# - Shorter TTL to catch freshness issues
```

### Production Configuration

```python
# Production: No caching (default)
prod_model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=False  # Explicit no cache
)

# Benefits:
# - Always fresh responses
# - No stale data
# - Predictable behavior
# - No cache management overhead

# Exception: Production caching for specific use cases
# (e.g., embedding generation, static content)
prod_embedding_model = OpenAIModel(
    model_id="text-embedding-3-small",
    enable_cache=True,
    cache_ttl_seconds=604800  # 1 week (embeddings don't change)
)
```

### Environment Detection

```python
import os

def get_model_config():
    """Get model config based on environment."""

    env = os.getenv("ENVIRONMENT", "development")

    configs = {
        'development': {
            'enable_cache': True,
            'cache_ttl_seconds': 86400,
        },
        'testing': {
            'enable_cache': True,
            'cache_ttl_seconds': 2592000,
        },
        'staging': {
            'enable_cache': True,
            'cache_ttl_seconds': 3600,
        },
        'production': {
            'enable_cache': False,
        }
    }

    return configs.get(env, configs['production'])

# Usage
config = get_model_config()
model = OpenAIModel(model_id="gpt-4o", **config)
```

## Best Practices

1. **Disable in Production**: Unless you have specific caching requirements
2. **Enable in Development**: Save costs and speed up iteration
3. **Deterministic Tests**: Use caching for consistent test behavior
4. **Monitor Hit Rates**: Track cache effectiveness
5. **Regular Cleanup**: Remove expired entries to manage disk space
6. **Version Cache Keys**: Include version info for breaking changes
7. **Secure Cache**: Encrypt cache if it contains sensitive data
8. **Document Caching**: Make caching behavior clear to team members
9. **Environment Variables**: Use env vars for cache configuration
10. **Test Without Cache**: Periodically test with caching disabled

## Cache Management Commands

```python
from spark.models.cache import CacheManager

manager = CacheManager.get_instance()

# Inspect cache
stats = manager.get_stats()
print(f"Cache size: {stats['total_size_bytes'] / 1024 / 1024:.2f} MB")

# Clean expired entries
removed = manager.cleanup_expired()
print(f"Removed {removed} expired entries")

# Clear all cache
manager.clear_all()

# Clear specific provider
manager.clear_provider('openai')

# Get cache location
cache_dir = manager.cache_dir
print(f"Cache directory: {cache_dir}")

# List cache files
import os
for root, dirs, files in os.walk(cache_dir):
    for file in files:
        filepath = os.path.join(root, file)
        size = os.path.getsize(filepath)
        print(f"{filepath}: {size / 1024:.2f} KB")
```

## Related Documentation

- [Models System Reference](/docs/models/abstraction.md) - Model configuration
- [Model Response Caching](/docs/models/caching.md) - Detailed caching guide
- [Agent Cost Tracking](/docs/agents/cost-tracking.md) - Cost monitoring
- [Testing Strategies](/docs/best-practices/testing.md) - Testing with cache
- [Configuration Reference](/docs/config/environment.md) - Environment config
