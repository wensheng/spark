"""State backend abstractions for GraphState."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable


class StateBackend(ABC):
    """Abstract storage backend for graph/agent state."""

    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self._initial_state = dict(initial_state or {})

    async def initialize(self) -> None:
        """Optional async initialization hook."""
        return None

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from state storage."""

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """Persist a value."""

    @abstractmethod
    async def update(self, updates: dict[str, Any]) -> None:
        """Batch update keys."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key."""

    @abstractmethod
    async def has(self, key: str) -> bool:
        """Return True if key exists."""

    @abstractmethod
    async def keys(self) -> list[str]:
        """Return list of keys."""

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[dict[str, Any]]:
        """Context manager for atomic updates."""

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of the underlying state."""
        raise NotImplementedError("snapshot() not implemented for backend")

    def get_raw_state(self) -> dict[str, Any]:
        """Unsafe direct access to backend state."""
        raise NotImplementedError("get_raw_state() not implemented for backend")

    def clear(self) -> None:
        """Clear all stored state."""
        raise NotImplementedError("clear() not implemented for backend")

    def enable_concurrent_mode(self) -> None:
        """Enable synchronization for concurrent access."""
        return None

    def disable_concurrent_mode(self) -> None:
        """Disable synchronization for sequential access."""
        return None


class InMemoryStateBackend(StateBackend):
    """Async-lock backed in-memory store used as default GraphState backend."""

    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        super().__init__(initial_state)
        self._state: dict[str, Any] = dict(self._initial_state)
        self._lock = asyncio.Lock()
        self._concurrent_mode = False

    def enable_concurrent_mode(self) -> None:
        self._concurrent_mode = True

    def disable_concurrent_mode(self) -> None:
        self._concurrent_mode = False

    async def _with_lock(self) -> asyncio.Lock:
        return self._lock

    async def get(self, key: str, default: Any = None) -> Any:
        if self._concurrent_mode:
            async with self._lock:
                return self._state.get(key, default)
        return self._state.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        if self._concurrent_mode:
            async with self._lock:
                self._state[key] = value
                return
        self._state[key] = value

    async def update(self, updates: dict[str, Any]) -> None:
        if self._concurrent_mode:
            async with self._lock:
                self._state.update(updates)
                return
        self._state.update(updates)

    async def delete(self, key: str) -> None:
        if self._concurrent_mode:
            async with self._lock:
                self._state.pop(key, None)
                return
        self._state.pop(key, None)

    async def has(self, key: str) -> bool:
        if self._concurrent_mode:
            async with self._lock:
                return key in self._state
        return key in self._state

    async def keys(self) -> list[str]:
        if self._concurrent_mode:
            async with self._lock:
                return list(self._state.keys())
        return list(self._state.keys())

    @asynccontextmanager
    async def transaction(self):
        if self._concurrent_mode:
            async with self._lock:
                yield self._state
                return
        yield self._state

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    def get_raw_state(self) -> dict[str, Any]:
        return self._state

    def clear(self) -> None:
        self._state.clear()


class SQLiteStateBackend(StateBackend):
    """SQLite backed state store for durable mission data."""

    def __init__(self, db_path: str | Path, *, table_name: str = "graph_state", initial_state: dict[str, Any] | None = None) -> None:
        super().__init__(initial_state)
        self.db_path = str(db_path)
        self.table_name = table_name
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._state_cache: dict[str, Any] = dict(self._initial_state)

    async def initialize(self) -> None:
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()
        rows = self._conn.execute(f"SELECT key, value FROM {self.table_name}").fetchall()
        for key, value in rows:
            if key not in self._state_cache:
                self._state_cache[key] = json.loads(value)
        if self._initial_state:
            await self.update(self._initial_state)

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteStateBackend not initialized. Call await graph.state.initialize() first.")
        return self._conn

    async def _write_many(self, items: dict[str, Any]) -> None:
        conn = self._ensure_conn()
        def _write():
            cur = conn.cursor()
            for key, value in items.items():
                cur.execute(
                    f"INSERT INTO {self.table_name}(key, value) VALUES(?, ?) "
                    f"ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, json.dumps(value)),
                )
            conn.commit()
        await asyncio.to_thread(_write)

    async def _delete_keys(self, keys: list[str]) -> None:
        if not keys:
            return
        conn = self._ensure_conn()
        def _delete():
            cur = conn.cursor()
            cur.executemany(f"DELETE FROM {self.table_name} WHERE key = ?", ((key,) for key in keys))
            conn.commit()
        await asyncio.to_thread(_delete)

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._state_cache.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        await self.update({key: value})

    async def update(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        async with self._lock:
            self._state_cache.update(updates)
        await self._write_many(updates)

    async def delete(self, key: str) -> None:
        async with self._lock:
            existed = key in self._state_cache
            self._state_cache.pop(key, None)
        if existed:
            await self._delete_keys([key])

    async def has(self, key: str) -> bool:
        async with self._lock:
            return key in self._state_cache

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._state_cache.keys())

    @asynccontextmanager
    async def transaction(self):
        await self.initialize()
        async with self._lock:
            working_copy = dict(self._state_cache)
        yield working_copy
        async with self._lock:
            self._state_cache = dict(working_copy)
        await self._replace_all(working_copy)

    async def _replace_all(self, new_state: dict[str, Any]) -> None:
        conn = self._ensure_conn()
        def _replace():
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {self.table_name}")
            cur.executemany(
                f"INSERT INTO {self.table_name}(key, value) VALUES(?, ?)",
                ((key, json.dumps(value)) for key, value in new_state.items()),
            )
            conn.commit()
        await asyncio.to_thread(_replace)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state_cache)

    def get_raw_state(self) -> dict[str, Any]:
        return self._state_cache

    def clear(self) -> None:
        self._state_cache.clear()
        if self._conn is None:
            return
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {self.table_name}")
        self._conn.commit()
