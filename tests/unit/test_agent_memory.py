"""
Tests for Agent memory management.
"""

import pytest
import tempfile
from pathlib import Path

from spark.agents.memory import MemoryManager, MemoryConfig, MemoryPolicyType


class TestMemoryManager:
    """Test memory manager functionality."""

    def test_memory_manager_init_defaults(self):
        """Test default memory manager initialization."""
        manager = MemoryManager()

        assert manager.policy == MemoryPolicyType.ROLLING_WINDOW
        assert manager.window == 10
        assert manager.memory == []

    def test_memory_manager_with_config(self):
        """Test memory manager with custom config."""
        config = MemoryConfig(
            policy=MemoryPolicyType.NULL,
            window=5
        )
        manager = MemoryManager(config)

        assert manager.policy == MemoryPolicyType.NULL
        assert manager.window == 5

    def test_rolling_window_policy(self):
        """Test rolling window memory policy."""
        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.ROLLING_WINDOW,
            window=3
        ))

        # Add messages
        for i in range(5):
            manager.add_message({'role': 'user', 'content': f'Message {i}'})

        # Should only keep last 3 messages
        assert len(manager.memory) == 3
        assert manager.memory[0]['content'] == 'Message 2'
        assert manager.memory[2]['content'] == 'Message 4'

    def test_null_policy(self):
        """Test null memory policy (no storage)."""
        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.NULL
        ))

        # Add messages
        manager.add_message({'role': 'user', 'content': 'Message 1'})
        manager.add_message({'role': 'assistant', 'content': 'Response 1'})

        # Should not store any messages
        assert len(manager.memory) == 0

    def test_custom_policy(self):
        """Test custom memory policy with callable."""
        # Custom policy that adds message to memory and keeps only user messages
        def only_user_messages(memory):
            # Custom policies need to handle adding new messages themselves
            # For this test, we'll just return the filtered memory
            return [m for m in memory if m.get('role') == 'user']

        config = MemoryConfig(
            policy=MemoryPolicyType.CUSTOM,
            callable=only_user_messages
        )
        manager = MemoryManager(config)

        # Manually populate memory since CUSTOM policy delegates to callable
        manager.memory = [
            {'role': 'user', 'content': 'User 1'},
            {'role': 'assistant', 'content': 'Assistant 1'},
            {'role': 'user', 'content': 'User 2'}
        ]

        # Now call add_message - the callable should filter
        manager.add_message({'role': 'system', 'content': 'System'})

        # Should only have user messages (callable filters out others)
        assert len(manager.memory) == 2
        assert all(m['role'] == 'user' for m in manager.memory)

    def test_summarize_policy_basic(self):
        """Test summarize policy with default summarization."""
        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.SUMMARIZE,
            window=3,
            summary_max_chars=100
        ))

        # Add messages that exceed window
        for i in range(5):
            manager.add_message({'role': 'user', 'content': f'Message {i}'})

        # Should have summary + recent messages
        # Window is 3, so we keep 2 recent + 1 summary
        assert len(manager.memory) <= 3
        # First message should be summary
        assert manager.memory[0]['role'] == 'system'
        assert 'Summary' in manager.memory[0]['content']

    def test_summarize_policy_with_custom_callable(self):
        """Test summarize policy with custom summarization callable."""
        def custom_summarizer(memory):
            # Just keep last 2 messages
            return memory[-2:]

        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.SUMMARIZE,
            window=3,
            callable=custom_summarizer
        ))

        # Add many messages
        for i in range(6):
            manager.add_message({'role': 'user', 'content': f'Message {i}'})

        # Custom summarizer should keep only last 2
        assert len(manager.memory) == 2

    def test_export_to_dict(self):
        """Test exporting memory to dict."""
        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.ROLLING_WINDOW,
            window=5
        ))

        manager.add_message({'role': 'user', 'content': 'Hello'})
        manager.add_message({'role': 'assistant', 'content': 'Hi'})

        exported = manager.export_to_dict()

        assert 'policy' in exported
        assert 'window' in exported
        assert 'memory' in exported
        assert exported['policy'] == 'rolling_window'
        assert exported['window'] == 5
        assert len(exported['memory']) == 2

    def test_save_and_load(self):
        """Test saving and loading memory."""
        manager = MemoryManager(config=MemoryConfig(
            policy=MemoryPolicyType.ROLLING_WINDOW,
            window=5
        ))

        manager.add_message({'role': 'user', 'content': 'Hello'})
        manager.add_message({'role': 'assistant', 'content': 'Hi'})

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name

        try:
            manager.save(temp_path)

            # Load into new manager
            new_manager = MemoryManager()
            new_manager.load(temp_path)

            assert len(new_manager.memory) == 2
            assert new_manager.memory[0]['content'] == 'Hello'
            assert new_manager.memory[1]['content'] == 'Hi'
            assert new_manager.window == 5
        finally:
            Path(temp_path).unlink()

    def test_load_plain_list_format(self):
        """Test loading plain list of messages (legacy format)."""
        import json

        messages = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi'}
        ]

        # Save as plain list
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(messages, f)
            temp_path = f.name

        try:
            manager = MemoryManager()
            manager.load(temp_path)

            assert len(manager.memory) == 2
            assert manager.memory[0]['content'] == 'Hello'
        finally:
            Path(temp_path).unlink()

    def test_memory_clear(self):
        """Test clearing memory."""
        manager = MemoryManager()

        manager.add_message({'role': 'user', 'content': 'Hello'})
        manager.add_message({'role': 'assistant', 'content': 'Hi'})

        assert len(manager.memory) == 2

        manager.memory.clear()
        assert len(manager.memory) == 0


class TestMemoryConfig:
    """Test memory configuration."""

    def test_memory_config_defaults(self):
        """Test default memory configuration."""
        config = MemoryConfig()

        assert config.policy == MemoryPolicyType.ROLLING_WINDOW
        assert config.window == 10
        assert config.summary_max_chars == 1000
        assert config.callable is None

    def test_memory_config_custom(self):
        """Test custom memory configuration."""
        config = MemoryConfig(
            policy=MemoryPolicyType.SUMMARIZE,
            window=20,
            summary_max_chars=500
        )

        assert config.policy == MemoryPolicyType.SUMMARIZE
        assert config.window == 20
        assert config.summary_max_chars == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
