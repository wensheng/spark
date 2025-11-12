"""Tests for LLM response caching system."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from spark.models.cache import CacheConfig, CacheEntry, CacheManager


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cache_config(temp_cache_dir):
    """Create a cache configuration for testing."""
    return CacheConfig(enabled=True, cache_dir=temp_cache_dir, ttl_seconds=60)


@pytest.fixture
def cache_manager(cache_config):
    """Create a cache manager instance for testing."""
    # Reset singleton before each test
    CacheManager.reset_instance()
    manager = CacheManager(cache_config)
    yield manager
    # Reset after test
    CacheManager.reset_instance()


class TestCacheConfig:
    """Tests for CacheConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CacheConfig()
        assert config.enabled is False
        assert config.cache_dir is None
        assert config.ttl_seconds == 86400
        assert config.max_cache_size_mb == 1000
        assert config.cleanup_interval_seconds == 3600

    def test_custom_config(self, temp_cache_dir):
        """Test custom configuration values."""
        config = CacheConfig(
            enabled=True, cache_dir=temp_cache_dir, ttl_seconds=3600, max_cache_size_mb=500, cleanup_interval_seconds=1800
        )
        assert config.enabled is True
        assert config.cache_dir == temp_cache_dir
        assert config.ttl_seconds == 3600
        assert config.max_cache_size_mb == 500
        assert config.cleanup_interval_seconds == 1800


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        now = datetime.now()
        expires = now + timedelta(seconds=3600)

        entry = CacheEntry(
            cache_key="test_key",
            provider="openai",
            model_id="gpt-4o",
            cached_at=now,
            expires_at=expires,
            request={"messages": [{"role": "user", "content": [{"text": "Hello"}]}]},
            response={"role": "assistant", "content": "Hi there!"},
        )

        assert entry.cache_key == "test_key"
        assert entry.provider == "openai"
        assert entry.model_id == "gpt-4o"
        assert entry.cached_at == now
        assert entry.expires_at == expires
        assert entry.access_count == 0
        assert entry.last_accessed is None


class TestCacheManager:
    """Tests for CacheManager."""

    def test_singleton_instance(self, cache_config):
        """Test that CacheManager uses singleton pattern."""
        CacheManager.reset_instance()
        manager1 = CacheManager.get_instance(cache_config)
        manager2 = CacheManager.get_instance()
        assert manager1 is manager2

    def test_cache_dir_creation(self, temp_cache_dir):
        """Test that cache directory is created."""
        cache_dir = temp_cache_dir / "new_cache"
        config = CacheConfig(enabled=True, cache_dir=cache_dir)
        CacheManager.reset_instance()
        CacheManager(config)
        assert cache_dir.exists()

    def test_generate_cache_key_deterministic(self, cache_manager):
        """Test that cache key generation is deterministic."""
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]

        key1 = cache_manager.generate_cache_key(
            provider="openai", model_id="gpt-4o", messages=messages, system_prompt="You are helpful"
        )

        key2 = cache_manager.generate_cache_key(
            provider="openai", model_id="gpt-4o", messages=messages, system_prompt="You are helpful"
        )

        assert key1 == key2

    def test_generate_cache_key_different_messages(self, cache_manager):
        """Test that different messages produce different cache keys."""
        messages1 = [{"role": "user", "content": [{"text": "Hello"}]}]
        messages2 = [{"role": "user", "content": [{"text": "Hi"}]}]

        key1 = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages1)

        key2 = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages2)

        assert key1 != key2

    def test_generate_cache_key_different_providers(self, cache_manager):
        """Test that different providers produce different cache keys."""
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]

        key1 = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        key2 = cache_manager.generate_cache_key(provider="bedrock", model_id="claude-3", messages=messages)

        assert key1 != key2

    def test_generate_cache_key_different_params(self, cache_manager):
        """Test that different parameters produce different cache keys."""
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]

        key1 = cache_manager.generate_cache_key(
            provider="openai", model_id="gpt-4o", messages=messages, temperature=0.7
        )

        key2 = cache_manager.generate_cache_key(
            provider="openai", model_id="gpt-4o", messages=messages, temperature=0.9
        )

        assert key1 != key2

    def test_set_and_get_cache(self, cache_manager):
        """Test setting and getting a cache entry."""
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        cache_key = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        request = {"messages": messages}
        response = {"role": "assistant", "content": "Hi there!"}

        # Set cache
        cache_manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Get cache
        cached_response = cache_manager.get(cache_key=cache_key, provider="openai")

        assert cached_response is not None
        assert cached_response == response

    def test_get_cache_miss(self, cache_manager):
        """Test getting a non-existent cache entry."""
        cached_response = cache_manager.get(cache_key="non_existent_key", provider="openai")
        assert cached_response is None

    def test_cache_expiration(self, temp_cache_dir):
        """Test that expired cache entries are not returned."""
        # Create cache with very short TTL
        config = CacheConfig(enabled=True, cache_dir=temp_cache_dir, ttl_seconds=1)
        CacheManager.reset_instance()
        manager = CacheManager(config)

        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        cache_key = manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        request = {"messages": messages}
        response = {"role": "assistant", "content": "Hi there!"}

        # Set cache
        manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Verify cache hit immediately
        cached_response = manager.get(cache_key=cache_key, provider="openai")
        assert cached_response is not None

        # Wait for expiration
        time.sleep(2)

        # Verify cache miss after expiration
        cached_response = manager.get(cache_key=cache_key, provider="openai")
        assert cached_response is None

    def test_cache_access_count(self, cache_manager):
        """Test that access count is incremented on cache hits."""
        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        cache_key = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        request = {"messages": messages}
        response = {"role": "assistant", "content": "Hi there!"}

        # Set cache
        cache_manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Access cache multiple times
        for i in range(3):
            cached_response = cache_manager.get(cache_key=cache_key, provider="openai")
            assert cached_response is not None

        # Read the cache file directly to verify access count
        cache_file = cache_manager._get_cache_file_path("openai", cache_key)
        with open(cache_file, "r") as f:
            entry_data = json.load(f)

        assert entry_data["metadata"]["access_count"] == 3

    def test_cleanup_expired(self, temp_cache_dir):
        """Test cleanup of expired cache entries."""
        # Create cache with very short TTL
        config = CacheConfig(enabled=True, cache_dir=temp_cache_dir, ttl_seconds=1)
        CacheManager.reset_instance()
        manager = CacheManager(config)

        # Create multiple cache entries
        for i in range(3):
            messages = [{"role": "user", "content": [{"text": f"Hello {i}"}]}]
            cache_key = manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

            request = {"messages": messages}
            response = {"role": "assistant", "content": f"Hi there {i}!"}

            manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Wait for expiration
        time.sleep(2)

        # Cleanup expired entries
        removed_count = manager.cleanup_expired()

        assert removed_count == 3

    def test_clear_all(self, cache_manager):
        """Test clearing all cache entries."""
        # Create multiple cache entries
        for i in range(3):
            messages = [{"role": "user", "content": [{"text": f"Hello {i}"}]}]
            cache_key = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

            request = {"messages": messages}
            response = {"role": "assistant", "content": f"Hi there {i}!"}

            cache_manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Verify entries exist
        stats = cache_manager.get_stats()
        assert stats["total_entries"] == 3

        # Clear all
        cache_manager.clear_all()

        # Verify cache is empty
        stats = cache_manager.get_stats()
        assert stats["total_entries"] == 0

    def test_get_stats(self, cache_manager):
        """Test getting cache statistics."""
        # Create entries for multiple providers
        providers = ["openai", "bedrock", "gemini"]
        entries_per_provider = 2

        for provider in providers:
            for i in range(entries_per_provider):
                messages = [{"role": "user", "content": [{"text": f"Hello {i}"}]}]
                cache_key = cache_manager.generate_cache_key(provider=provider, model_id="model-1", messages=messages)

                request = {"messages": messages}
                response = {"role": "assistant", "content": f"Hi there {i}!"}

                cache_manager.set(cache_key=cache_key, provider=provider, model_id="model-1", request=request, response=response)

        # Get stats
        stats = cache_manager.get_stats()

        assert stats["total_entries"] == len(providers) * entries_per_provider
        assert len(stats["by_provider"]) == len(providers)

        for provider in providers:
            assert stats["by_provider"][provider]["entries"] == entries_per_provider

    def test_cache_disabled(self, temp_cache_dir):
        """Test that cache operations are no-ops when disabled."""
        config = CacheConfig(enabled=False, cache_dir=temp_cache_dir)
        CacheManager.reset_instance()
        manager = CacheManager(config)

        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        cache_key = manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        request = {"messages": messages}
        response = {"role": "assistant", "content": "Hi there!"}

        # Try to set cache (should be no-op)
        manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Try to get cache (should return None)
        cached_response = manager.get(cache_key=cache_key, provider="openai")
        assert cached_response is None

    def test_serialize_deserialize_entry(self, cache_manager):
        """Test serialization and deserialization of cache entries."""
        now = datetime.now()
        expires = now + timedelta(seconds=3600)

        entry = CacheEntry(
            cache_key="test_key",
            provider="openai",
            model_id="gpt-4o",
            cached_at=now,
            expires_at=expires,
            request={"messages": [{"role": "user", "content": [{"text": "Hello"}]}]},
            response={"role": "assistant", "content": "Hi there!"},
            access_count=5,
            last_accessed=now,
        )

        # Serialize
        serialized = cache_manager._serialize_entry(entry)

        assert serialized["version"] == "1.0"
        assert serialized["metadata"]["provider"] == "openai"
        assert serialized["metadata"]["model_id"] == "gpt-4o"
        assert serialized["metadata"]["access_count"] == 5

        # Deserialize
        deserialized = cache_manager._deserialize_entry(serialized)

        assert deserialized.cache_key == entry.cache_key
        assert deserialized.provider == entry.provider
        assert deserialized.model_id == entry.model_id
        assert deserialized.access_count == entry.access_count
        assert deserialized.request == entry.request
        assert deserialized.response == entry.response

    def test_concurrent_access(self, cache_manager):
        """Test that concurrent access to cache is handled correctly."""
        import threading

        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        cache_key = cache_manager.generate_cache_key(provider="openai", model_id="gpt-4o", messages=messages)

        request = {"messages": messages}
        response = {"role": "assistant", "content": "Hi there!"}

        # Set initial cache
        cache_manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Function to access cache multiple times
        def access_cache():
            for _ in range(5):
                cache_manager.get(cache_key=cache_key, provider="openai")

        # Create multiple threads
        threads = [threading.Thread(target=access_cache) for _ in range(3)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify cache is still valid
        cached_response = cache_manager.get(cache_key=cache_key, provider="openai")
        assert cached_response is not None

    def test_invalid_cache_file(self, cache_manager, temp_cache_dir):
        """Test handling of corrupted cache files."""
        # Create an invalid cache file
        provider_dir = temp_cache_dir / "openai"
        provider_dir.mkdir(exist_ok=True)

        cache_file = provider_dir / "invalid_key.json"
        with open(cache_file, "w") as f:
            f.write("invalid json content")

        # Try to get cache (should return None gracefully)
        cached_response = cache_manager.get(cache_key="invalid_key", provider="openai")
        assert cached_response is None

    def test_cache_with_tool_specs(self, cache_manager):
        """Test caching with tool specifications."""
        messages = [{"role": "user", "content": [{"text": "Search for something"}]}]
        tool_specs = [{"name": "web_search", "description": "Search the web", "parameters": {"json": {"type": "object"}}}]

        cache_key = cache_manager.generate_cache_key(
            provider="openai", model_id="gpt-4o", messages=messages, tool_specs=tool_specs
        )

        request = {"messages": messages, "tool_specs": tool_specs}
        response = {"role": "assistant", "content": "Searching...", "tool_calls": [{"id": "123", "name": "web_search"}]}

        # Set cache
        cache_manager.set(cache_key=cache_key, provider="openai", model_id="gpt-4o", request=request, response=response)

        # Get cache
        cached_response = cache_manager.get(cache_key=cache_key, provider="openai")

        assert cached_response is not None
        assert cached_response["content"] == "Searching..."
        assert len(cached_response["tool_calls"]) == 1
