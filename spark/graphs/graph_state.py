"""Graph-level state management with pluggable backends."""

from contextlib import asynccontextmanager
from typing import Any

from spark.graphs.state_backend import InMemoryStateBackend, StateBackend


class GraphState:
    """Thread-safe graph state with backend abstraction.

    Provides safe concurrent access to mission state regardless of where it is stored.
    Default backend is in-memory; durable backends can be supplied for checkpoints.
    """

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        """Initialize the graph state wrapper.

        Args:
            initial_state: Optional dictionary to initialize state.
            backend: Optional custom backend. Defaults to in-memory backend.
        """
        self._backend = backend or InMemoryStateBackend(initial_state)
        self._initialized = False
        self._pending_initial_state: dict[str, Any] = {}
        if backend and initial_state:
            self._pending_initial_state = dict(initial_state)

    async def initialize(self) -> None:
        """Initialize the backend once graph runtime is ready."""
        if self._initialized:
            return
        await self._backend.initialize()
        if self._pending_initial_state:
            await self._backend.update(self._pending_initial_state)
            self._pending_initial_state.clear()
        self._initialized = True

    def enable_concurrent_mode(self) -> None:
        """Enable backend synchronization for long running tasks."""
        self._backend.enable_concurrent_mode()

    def disable_concurrent_mode(self) -> None:
        """Disable backend synchronization for sequential tasks."""
        self._backend.disable_concurrent_mode()

    async def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe get operation."""
        return await self._backend.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        """Thread-safe set operation."""
        await self._backend.set(key, value)

    async def update(self, updates: dict[str, Any]) -> None:
        """Thread-safe batch update."""
        await self._backend.update(updates)

    async def delete(self, key: str) -> None:
        """Thread-safe delete operation."""
        await self._backend.delete(key)

    async def has(self, key: str) -> bool:
        """Check if a key exists."""
        return await self._backend.has(key)

    async def keys(self) -> list[str]:
        """Return all keys."""
        return await self._backend.keys()

    @asynccontextmanager
    async def transaction(self):
        """Context manager for atomic multi-operation transactions."""
        async with self._backend.transaction() as state_dict:
            yield state_dict

    def get_snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of current state (non-blocking)."""
        return self._backend.snapshot()

    def get_raw(self) -> dict[str, Any]:
        """Direct access to internal state (use with caution)."""
        return self._backend.get_raw_state()

    def clear(self) -> None:
        """Clear all state."""
        self._backend.clear()

    async def reset(self, new_state: dict[str, Any] | None = None) -> None:
        """Replace entire state content atomically."""
        async with self.transaction() as state_dict:
            state_dict.clear()
            if new_state:
                state_dict.update(new_state)

    def __repr__(self) -> str:
        """Return a string representation of the state."""
        snapshot = self.get_snapshot()
        mode = (
            "concurrent"
            if hasattr(self._backend, "_concurrent_mode") and getattr(self._backend, "_concurrent_mode")
            else "sequential"
        )
        return f"GraphState(mode={mode}, keys={list(snapshot.keys())})"
