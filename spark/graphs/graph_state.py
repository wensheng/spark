"""Graph-level state management with thread-safe operations."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any


class GraphState:
    """thread-safe graph state.

    This class provides safe concurrent access to a shared state dictionary
    across all nodes in a graph. In sequential mode, no locking is used for
    performance. In concurrent mode (LONG_RUNNING tasks), all operations are
    protected by an asyncio.Lock.

    Usage:
        state = GraphState({'counter': 0})
        state.enable_concurrent_mode()

        # In a node's process method:
        counter = await state.get('counter', 0)
        await state.set('counter', counter + 1)

        # For atomic multi-operation updates:
        async with state.transaction() as s:
            s['x'] = s.get('x', 0) + 1
            s['y'] = s.get('y', 0) + 1
    """

    def __init__(self, initial_state: dict[str, Any] | None = None):
        """Initialize the thread-safe graph state.

        Args:
            initial_state: Optional dictionary to initialize the state with.
        """
        self._state: dict[str, Any] = dict(initial_state or {})
        self._lock: asyncio.Lock = asyncio.Lock()
        self._concurrent_mode: bool = False

    def enable_concurrent_mode(self) -> None:
        """Enable thread-safe operations for LONG_RUNNING mode.

        When enabled, all state operations will acquire a lock before
        accessing the internal state dictionary.
        """
        self._concurrent_mode = True

    def disable_concurrent_mode(self) -> None:
        """Disable locking for sequential mode.

        When disabled, state operations access the internal dictionary
        directly without locking, improving performance for sequential flows.
        """
        self._concurrent_mode = False

    async def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe get operation.

        Args:
            key: The key to retrieve.
            default: Default value if key doesn't exist.

        Returns:
            The value associated with the key, or default if not found.
        """
        if self._concurrent_mode:
            async with self._lock:
                return self._state.get(key, default)
        return self._state.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        """Thread-safe set operation.

        Args:
            key: The key to set.
            value: The value to associate with the key.
        """
        if self._concurrent_mode:
            async with self._lock:
                self._state[key] = value
        else:
            self._state[key] = value

    async def update(self, updates: dict[str, Any]) -> None:
        """Thread-safe batch update.

        Args:
            updates: Dictionary of key-value pairs to update.
        """
        if self._concurrent_mode:
            async with self._lock:
                self._state.update(updates)
        else:
            self._state.update(updates)

    async def delete(self, key: str) -> None:
        """Thread-safe delete operation.

        Args:
            key: The key to delete. Does nothing if key doesn't exist.
        """
        if self._concurrent_mode:
            async with self._lock:
                self._state.pop(key, None)
        else:
            self._state.pop(key, None)

    async def has(self, key: str) -> bool:
        """Check if a key exists in the state.

        Args:
            key: The key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        if self._concurrent_mode:
            async with self._lock:
                return key in self._state
        return key in self._state

    async def keys(self) -> list[str]:
        """Get all keys in the state.

        Returns:
            List of all keys in the state.
        """
        if self._concurrent_mode:
            async with self._lock:
                return list(self._state.keys())
        return list(self._state.keys())

    @asynccontextmanager
    async def transaction(self):
        """Context manager for atomic multi-operation transactions.

        Yields the internal state dictionary for direct manipulation.
        All operations within the context manager are atomic.

        Usage:
            async with state.transaction() as s:
                s['x'] = s.get('x', 0) + 1
                s['y'] = s.get('y', 0) + 1
        """
        if self._concurrent_mode:
            async with self._lock:
                yield self._state
        else:
            yield self._state

    def get_snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of current state (non-blocking).

        Note: This method does not acquire a lock in concurrent mode,
        so the snapshot may not be consistent if accessed during concurrent
        modifications. Use transaction() for consistent reads.

        Returns:
            A shallow copy of the state dictionary.
        """
        return dict(self._state)

    def get_raw(self) -> dict[str, Any]:
        """Direct access to internal state (use with caution).

        Warning: This bypasses all locking mechanisms. Only use this
        when you're certain no concurrent modifications are happening,
        or when you're managing synchronization externally.

        Returns:
            The internal state dictionary.
        """
        return self._state

    def clear(self) -> None:
        """Clear all state (non-async, for initialization/reset).

        Warning: Not thread-safe. Should only be called during
        initialization or when the graph is not running.
        """
        self._state.clear()

    def __repr__(self) -> str:
        """Return a string representation of the state."""
        mode = "concurrent" if self._concurrent_mode else "sequential"
        return f"GraphState(mode={mode}, keys={list(self._state.keys())})"
