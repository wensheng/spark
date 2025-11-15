"""Unit tests for GraphState."""

import asyncio
from contextlib import asynccontextmanager

import pytest

from spark.graphs.graph_state import GraphState
from spark.graphs.state_backend import InMemoryStateBackend, StateBackend


def _is_concurrent(state: GraphState) -> bool:
    backend = getattr(state, '_backend', None)
    return bool(getattr(backend, '_concurrent_mode', False))


class RecordingBackend(StateBackend):
    """Simple backend used for testing initialization + persistence."""

    def __init__(self, initial_state: dict | None = None) -> None:
        super().__init__(initial_state)
        self._state = dict(initial_state or {})
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def get(self, key: str, default=None):
        return self._state.get(key, default)

    async def set(self, key: str, value) -> None:
        self._state[key] = value

    async def update(self, updates: dict) -> None:
        self._state.update(updates)

    async def delete(self, key: str) -> None:
        self._state.pop(key, None)

    async def has(self, key: str) -> bool:
        return key in self._state

    async def keys(self) -> list[str]:
        return list(self._state.keys())

    @asynccontextmanager
    async def transaction(self):
        yield self._state

    def snapshot(self) -> dict:
        return dict(self._state)

    def get_raw_state(self) -> dict:
        return self._state

    def clear(self) -> None:
        self._state.clear()


class TestThreadSafeGraphState:
    """Test suite for ThreadSafeGraphState class."""

    def test_initialization_empty(self):
        """Test initialization with no initial state."""
        state = GraphState()
        assert state.get_snapshot() == {}
        assert isinstance(state._backend, InMemoryStateBackend)
        assert not _is_concurrent(state)

    def test_initialization_with_data(self):
        """Test initialization with initial state."""
        initial = {'counter': 0, 'name': 'test'}
        state = GraphState(initial)
        assert state.get_snapshot() == initial

    @pytest.mark.asyncio
    async def test_get_set_sequential_mode(self):
        """Test get/set operations in sequential mode."""
        state = GraphState()

        # Test set and get
        await state.set('key1', 'value1')
        result = await state.get('key1')
        assert result == 'value1'

        # Test get with default
        result = await state.get('nonexistent', 'default')
        assert result == 'default'

    @pytest.mark.asyncio
    async def test_get_set_concurrent_mode(self):
        """Test get/set operations in concurrent mode."""
        state = GraphState()
        state.enable_concurrent_mode()

        await state.set('key1', 'value1')
        result = await state.get('key1')
        assert result == 'value1'

    @pytest.mark.asyncio
    async def test_update_operation(self):
        """Test batch update operation."""
        state = GraphState({'a': 1})

        await state.update({'b': 2, 'c': 3})

        assert await state.get('a') == 1
        assert await state.get('b') == 2
        assert await state.get('c') == 3

    @pytest.mark.asyncio
    async def test_delete_operation(self):
        """Test delete operation."""
        state = GraphState({'key1': 'value1', 'key2': 'value2'})

        await state.delete('key1')

        assert await state.get('key1') is None
        assert await state.get('key2') == 'value2'

        # Deleting non-existent key should not raise error
        await state.delete('nonexistent')

    @pytest.mark.asyncio
    async def test_has_operation(self):
        """Test has operation to check key existence."""
        state = GraphState({'key1': 'value1'})

        assert await state.has('key1')
        assert not await state.has('nonexistent')

    @pytest.mark.asyncio
    async def test_keys_operation(self):
        """Test keys operation."""
        state = GraphState({'a': 1, 'b': 2, 'c': 3})

        keys = await state.keys()
        assert set(keys) == {'a', 'b', 'c'}

    @pytest.mark.asyncio
    async def test_transaction_sequential(self):
        """Test transaction context manager in sequential mode."""
        state = GraphState({'x': 0, 'y': 0})

        async with state.transaction() as s:
            s['x'] = s.get('x', 0) + 1
            s['y'] = s.get('y', 0) + 1

        assert await state.get('x') == 1
        assert await state.get('y') == 1

    @pytest.mark.asyncio
    async def test_transaction_concurrent(self):
        """Test transaction context manager in concurrent mode."""
        state = GraphState({'x': 0, 'y': 0})
        state.enable_concurrent_mode()

        async with state.transaction() as s:
            s['x'] = s.get('x', 0) + 1
            s['y'] = s.get('y', 0) + 1

        assert await state.get('x') == 1
        assert await state.get('y') == 1

    @pytest.mark.asyncio
    async def test_concurrent_access_without_race(self):
        """Test that separate get/set operations can still have race conditions.

        Note: Even with locking, get() and set() are separate operations, so
        read-modify-write patterns need transactions for atomicity.
        """
        state = GraphState({'counter': 0})
        state.enable_concurrent_mode()

        async def increment_unsafe():
            """This can have race conditions even with locking."""
            for _ in range(100):
                counter = await state.get('counter', 0)
                await asyncio.sleep(0)  # Yield control
                await state.set('counter', counter + 1)

        # Run multiple concurrent tasks
        await asyncio.gather(increment_unsafe(), increment_unsafe(), increment_unsafe())

        # Final count will be less than 300 due to race conditions
        final_count = await state.get('counter')
        assert final_count < 300  # Race condition occurred
        assert final_count >= 100  # But at least one task completed

    @pytest.mark.asyncio
    async def test_concurrent_transaction_atomicity(self):
        """Test that transactions are atomic in concurrent mode."""
        state = GraphState({'x': 0, 'y': 0})
        state.enable_concurrent_mode()

        async def atomic_increment():
            for _ in range(50):
                async with state.transaction() as s:
                    x = s.get('x', 0)
                    y = s.get('y', 0)
                    await asyncio.sleep(0)  # Yield control
                    s['x'] = x + 1
                    s['y'] = y + 1

        await asyncio.gather(atomic_increment(), atomic_increment())

        # Both should have same value due to atomic transactions
        x_val = await state.get('x')
        y_val = await state.get('y')
        assert x_val == y_val == 100

    def test_enable_disable_concurrent_mode(self):
        """Test enabling and disabling concurrent mode."""
        state = GraphState()

        assert not _is_concurrent(state)

        state.enable_concurrent_mode()
        assert _is_concurrent(state)

        state.disable_concurrent_mode()
        assert not _is_concurrent(state)

    def test_get_snapshot(self):
        """Test get_snapshot returns a copy."""
        state = GraphState({'key': 'value'})

        snapshot = state.get_snapshot()
        snapshot['key'] = 'modified'

        # Original state should be unchanged
        assert state.get_raw()['key'] == 'value'

    def test_get_raw(self):
        """Test get_raw returns direct reference."""
        state = GraphState({'key': 'value'})

        raw = state.get_raw()
        raw['key'] = 'modified'

        # Original state should be modified
        assert state.get_raw()['key'] == 'modified'

    def test_clear(self):
        """Test clear operation."""
        state = GraphState({'a': 1, 'b': 2})

        state.clear()

        assert state.get_snapshot() == {}

    def test_repr(self):
        """Test string representation."""
        state = GraphState({'key1': 'value1', 'key2': 'value2'})

        repr_str = repr(state)
        assert 'GraphState' in repr_str
        assert 'sequential' in repr_str
        assert 'key1' in repr_str or 'key2' in repr_str

        state.enable_concurrent_mode()
        repr_str = repr(state)
        assert 'concurrent' in repr_str

    @pytest.mark.asyncio
    async def test_complex_nested_data(self):
        """Test with complex nested data structures."""
        state = GraphState()

        complex_data = {
            'users': [
                {'id': 1, 'name': 'Alice'},
                {'id': 2, 'name': 'Bob'}
            ],
            'config': {
                'timeout': 30,
                'retries': 3
            }
        }

        await state.set('data', complex_data)
        result = await state.get('data')

        assert result == complex_data
        assert result['users'][0]['name'] == 'Alice'

    @pytest.mark.asyncio
    async def test_multiple_keys_concurrent(self):
        """Test multiple independent keys being accessed concurrently."""
        state = GraphState()
        state.enable_concurrent_mode()

        async def update_key(key: str, iterations: int):
            for i in range(iterations):
                await state.set(key, i)
                await asyncio.sleep(0)

        # Update different keys concurrently
        await asyncio.gather(
            update_key('key1', 10),
            update_key('key2', 10),
            update_key('key3', 10)
        )

        # All keys should have final values
        assert await state.get('key1') == 9
        assert await state.get('key2') == 9
        assert await state.get('key3') == 9

    @pytest.mark.asyncio
    async def test_custom_backend_initialization(self):
        """Ensure custom backend is initialized and seeded with data."""
        backend = RecordingBackend()
        state = GraphState(initial_state={'foo': 'bar'}, backend=backend)

        await state.initialize()
        assert backend.initialized
        assert await state.get('foo') == 'bar'

        await state.set('foo', 'baz')
        assert backend.get_raw_state()['foo'] == 'baz'

    @pytest.mark.asyncio
    async def test_custom_backend_existing_data(self):
        """Backend-provided initial state should be readable."""
        backend = RecordingBackend({'seed': 5})
        state = GraphState(backend=backend)

        await state.initialize()
        assert await state.get('seed') == 5

    @pytest.mark.asyncio
    async def test_custom_backend_snapshot_and_clear(self):
        """Snapshot and clear should proxy to backend."""
        backend = RecordingBackend({'alpha': 1})
        state = GraphState(backend=backend)

        await state.initialize()
        assert state.get_snapshot() == {'alpha': 1}
        state.clear()
        assert state.get_snapshot() == {}
        assert backend.snapshot() == {}
