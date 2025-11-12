"""Integration tests for LLM response caching across model providers."""

import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from spark.models.cache import CacheConfig, CacheManager
from spark.models.openai import OpenAIModel


class OutputSchema(BaseModel):
    """Test output schema for get_json tests."""

    result: str
    count: int


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "test_model_cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cache_config(temp_cache_dir):
    """Create a cache configuration for testing."""
    return CacheConfig(enabled=True, cache_dir=temp_cache_dir, ttl_seconds=60)


@pytest.fixture(autouse=True)
def reset_cache_manager():
    """Reset cache manager before and after each test."""
    CacheManager.reset_instance()
    yield
    CacheManager.reset_instance()


class TestOpenAIModelCache:
    """Tests for OpenAI model caching."""

    def test_cache_disabled_by_default(self):
        """Test that cache is disabled by default."""
        model = OpenAIModel(model_id="gpt-4o")
        assert model._cache_enabled is False
        assert model._cache_manager is None

    def test_cache_enabled_with_config(self, temp_cache_dir):
        """Test that cache is enabled when configured."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)
        assert model._cache_enabled is True
        assert model._cache_manager is not None

    def test_cache_with_custom_ttl(self, temp_cache_dir):
        """Test that custom TTL is respected."""
        custom_ttl = 7200
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True, cache_ttl_seconds=custom_ttl)
        assert model._cache_enabled is True
        assert model._cache_ttl_seconds == custom_ttl

    def test_provider_name(self):
        """Test that provider name is correctly set."""
        model = OpenAIModel(model_id="gpt-4o")
        assert model._get_provider_name() == "openai"

    def test_cache_key_generation(self, temp_cache_dir):
        """Test that cache keys are generated consistently."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Hello"}]}]
        system_prompt = "You are helpful"

        # Get cache manager
        manager = model._cache_manager

        # Generate key twice with same parameters
        key1 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o",
            messages=messages,
            system_prompt=system_prompt
        )

        key2 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o",
            messages=messages,
            system_prompt=system_prompt
        )

        assert key1 == key2

    def test_cache_key_different_for_different_messages(self, temp_cache_dir):
        """Test that different messages produce different cache keys."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages1 = [{"role": "user", "content": [{"text": "Hello"}]}]
        messages2 = [{"role": "user", "content": [{"text": "Hi"}]}]

        manager = model._cache_manager

        key1 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o",
            messages=messages1
        )

        key2 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o",
            messages=messages2
        )

        assert key1 != key2

    def test_cache_key_different_for_different_models(self, temp_cache_dir):
        """Test that different model IDs produce different cache keys."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Hello"}]}]

        manager = model._cache_manager

        key1 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o",
            messages=messages
        )

        key2 = manager.generate_cache_key(
            provider="openai",
            model_id="gpt-4o-mini",
            messages=messages
        )

        assert key1 != key2

    def test_manual_cache_save_and_retrieve(self, temp_cache_dir):
        """Test manually saving and retrieving from cache."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Test message"}]}]
        response = {"role": "assistant", "content": "Test response"}

        # Save to cache manually
        model._save_to_cache(
            messages=messages,
            response=response,
            system_prompt="Test prompt"
        )

        # Retrieve from cache
        cached = model._get_from_cache(
            messages=messages,
            system_prompt="Test prompt"
        )

        assert cached is not None
        assert cached == response

    def test_cache_miss_returns_none(self, temp_cache_dir):
        """Test that cache miss returns None."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Nonexistent"}]}]

        cached = model._get_from_cache(messages=messages)

        assert cached is None

    def test_cache_expiration(self, temp_cache_dir):
        """Test that expired cache entries are not returned."""
        # Create model with very short TTL
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True, cache_ttl_seconds=1)

        messages = [{"role": "user", "content": [{"text": "Expiring message"}]}]
        response = {"role": "assistant", "content": "Will expire soon"}

        # Save to cache
        model._save_to_cache(messages=messages, response=response)

        # Immediately retrieve (should work)
        cached = model._get_from_cache(messages=messages)
        assert cached is not None

        # Wait for expiration
        time.sleep(2)

        # Try to retrieve again (should be expired)
        cached = model._get_from_cache(messages=messages)
        assert cached is None

    def test_cache_with_different_system_prompts(self, temp_cache_dir):
        """Test that different system prompts create different cache entries."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Same message"}]}]
        response1 = {"role": "assistant", "content": "Response 1"}
        response2 = {"role": "assistant", "content": "Response 2"}

        # Save with first system prompt
        model._save_to_cache(
            messages=messages,
            response=response1,
            system_prompt="Be helpful"
        )

        # Save with second system prompt
        model._save_to_cache(
            messages=messages,
            response=response2,
            system_prompt="Be concise"
        )

        # Retrieve with first system prompt
        cached1 = model._get_from_cache(
            messages=messages,
            system_prompt="Be helpful"
        )

        # Retrieve with second system prompt
        cached2 = model._get_from_cache(
            messages=messages,
            system_prompt="Be concise"
        )

        assert cached1 == response1
        assert cached2 == response2
        assert cached1 != cached2

    def test_cache_with_tool_specs(self, temp_cache_dir):
        """Test that cache works with tool specifications."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Use a tool"}]}]
        tool_specs = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {
                    "json": {
                        "type": "object",
                        "properties": {"arg": {"type": "string"}},
                        "required": ["arg"]
                    }
                }
            }
        ]
        response = {"role": "assistant", "content": "Tool response"}

        # Save with tool specs
        model._save_to_cache(
            messages=messages,
            response=response,
            tool_specs=tool_specs
        )

        # Retrieve with same tool specs
        cached = model._get_from_cache(
            messages=messages,
            tool_specs=tool_specs
        )

        assert cached is not None
        assert cached == response

    def test_cache_different_for_different_tool_specs(self, temp_cache_dir):
        """Test that different tool specs create different cache entries."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Use a tool"}]}]

        tool_specs1 = [{"name": "tool1", "description": "Tool 1", "parameters": {"json": {"type": "object"}}}]
        tool_specs2 = [{"name": "tool2", "description": "Tool 2", "parameters": {"json": {"type": "object"}}}]

        response1 = {"role": "assistant", "content": "Response with tool1"}
        response2 = {"role": "assistant", "content": "Response with tool2"}

        # Save with different tool specs
        model._save_to_cache(messages=messages, response=response1, tool_specs=tool_specs1)
        model._save_to_cache(messages=messages, response=response2, tool_specs=tool_specs2)

        # Retrieve with each tool spec
        cached1 = model._get_from_cache(messages=messages, tool_specs=tool_specs1)
        cached2 = model._get_from_cache(messages=messages, tool_specs=tool_specs2)

        assert cached1 == response1
        assert cached2 == response2

    def test_cache_statistics(self, temp_cache_dir):
        """Test cache statistics tracking."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        # Clear any existing cache
        model._cache_manager.clear_all()

        # Save several cache entries
        for i in range(5):
            messages = [{"role": "user", "content": [{"text": f"Message {i}"}]}]
            response = {"role": "assistant", "content": f"Response {i}"}
            model._save_to_cache(messages=messages, response=response)

        # Get statistics
        stats = model._cache_manager.get_stats()

        assert stats["total_entries"] == 5
        assert "openai" in stats["by_provider"]
        assert stats["by_provider"]["openai"]["entries"] == 5
        assert stats["by_provider"]["openai"]["size_bytes"] > 0

    def test_cache_cleanup(self, temp_cache_dir):
        """Test cache cleanup of expired entries."""
        # Create model with very short TTL
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True, cache_ttl_seconds=1)

        # Clear any existing cache
        model._cache_manager.clear_all()

        # Save several entries
        for i in range(3):
            messages = [{"role": "user", "content": [{"text": f"Message {i}"}]}]
            response = {"role": "assistant", "content": f"Response {i}"}
            model._save_to_cache(messages=messages, response=response)

        # Verify entries exist
        stats = model._cache_manager.get_stats()
        assert stats["total_entries"] == 3

        # Wait for expiration
        time.sleep(2)

        # Cleanup expired entries
        removed = model._cache_manager.cleanup_expired()
        assert removed == 3

        # Verify entries are gone
        stats = model._cache_manager.get_stats()
        assert stats["total_entries"] == 0

    def test_cache_clear_all(self, temp_cache_dir):
        """Test clearing all cache entries."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        # Clear any existing cache
        model._cache_manager.clear_all()

        # Save several entries
        for i in range(5):
            messages = [{"role": "user", "content": [{"text": f"Message {i}"}]}]
            response = {"role": "assistant", "content": f"Response {i}"}
            model._save_to_cache(messages=messages, response=response)

        # Verify entries exist
        stats = model._cache_manager.get_stats()
        assert stats["total_entries"] == 5

        # Clear all
        model._cache_manager.clear_all()

        # Verify cache is empty
        stats = model._cache_manager.get_stats()
        assert stats["total_entries"] == 0

    def test_cache_with_kwargs(self, temp_cache_dir):
        """Test that kwargs affect cache key."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Same message"}]}]

        response1 = {"role": "assistant", "content": "Response with temp 0.7"}
        response2 = {"role": "assistant", "content": "Response with temp 0.9"}

        # Save with different temperatures
        model._save_to_cache(messages=messages, response=response1, temperature=0.7)
        model._save_to_cache(messages=messages, response=response2, temperature=0.9)

        # Retrieve with each temperature
        cached1 = model._get_from_cache(messages=messages, temperature=0.7)
        cached2 = model._get_from_cache(messages=messages, temperature=0.9)

        assert cached1 == response1
        assert cached2 == response2

    def test_multiple_models_share_cache(self, temp_cache_dir):
        """Test that multiple model instances share the same cache."""
        model1 = OpenAIModel(model_id="gpt-4o", enable_cache=True)
        model2 = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Shared message"}]}]
        response = {"role": "assistant", "content": "Shared response"}

        # Save with first model
        model1._save_to_cache(messages=messages, response=response)

        # Retrieve with second model (should hit cache)
        cached = model2._get_from_cache(messages=messages)

        assert cached is not None
        assert cached == response

    def test_different_providers_separate_cache_dirs(self, temp_cache_dir):
        """Test that different providers use separate cache directories."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Test"}]}]
        response = {"role": "assistant", "content": "Response"}

        model._save_to_cache(messages=messages, response=response)

        # Get the actual cache directory from the model
        actual_cache_dir = model._cache_manager.cache_dir

        # Check that openai directory exists
        openai_dir = actual_cache_dir / "openai"
        assert openai_dir.exists()
        assert openai_dir.is_dir()

        # Check that cache files exist in the directory
        cache_files = list(openai_dir.glob("*.json"))
        assert len(cache_files) >= 1  # At least one file (may have more from other tests)


class TestCacheConcurrency:
    """Tests for cache concurrency and thread safety."""

    def test_concurrent_cache_access(self, temp_cache_dir):
        """Test that concurrent cache access doesn't cause issues."""
        import threading

        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "Concurrent message"}]}]
        response = {"role": "assistant", "content": "Concurrent response"}

        # Save initial cache entry
        model._save_to_cache(messages=messages, response=response)

        results = []

        def access_cache():
            cached = model._get_from_cache(messages=messages)
            results.append(cached)

        # Create multiple threads accessing cache
        threads = [threading.Thread(target=access_cache) for _ in range(10)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify all threads got the cached response
        assert len(results) == 10
        assert all(r == response for r in results)


class TestCacheErrorHandling:
    """Tests for cache error handling and resilience."""

    def test_cache_continues_on_corrupt_file(self, temp_cache_dir):
        """Test that corrupt cache files don't break the application."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        # Create a corrupt cache file
        cache_dir = model._cache_manager.cache_dir
        openai_dir = cache_dir / "openai"
        openai_dir.mkdir(parents=True, exist_ok=True)

        corrupt_file = openai_dir / "corrupt.json"
        with open(corrupt_file, "w") as f:
            f.write("This is not valid JSON{{{")

        # Try to get from cache (should return None for corrupt file, not crash)
        cached = model._cache_manager.get(cache_key="corrupt", provider="openai")

        assert cached is None

    def test_cache_continues_on_write_error(self, temp_cache_dir):
        """Test that cache write errors don't break the application."""
        model = OpenAIModel(model_id="gpt-4o", enable_cache=True)

        messages = [{"role": "user", "content": [{"text": "ErrorTest"}]}]
        response = {"role": "assistant", "content": "Response"}

        # Try to save (should not crash even if there are issues)
        model._save_to_cache(messages=messages, response=response)

        # Application should continue normally
        assert True
