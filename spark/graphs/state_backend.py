"""State backend abstractions for GraphState."""

from __future__ import annotations

import asyncio
import inspect
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, ClassVar
from uuid import uuid4

from spark.graphs.serializers import StateSerializer, ensure_state_serializer

logger = logging.getLogger(__name__)

WatcherCallback = Callable[[str, Any, Any], Awaitable[None] | None]


def _diff_state(before: dict[str, Any], after: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Return list of (key, old, new) changes between two dictionaries."""
    changes: list[tuple[str, Any, Any]] = []
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    for key in after_keys:
        old = before.get(key)
        new = after[key]
        if old != new:
            changes.append((key, old, new))
    removed_keys = before_keys - after_keys
    for key in removed_keys:
        changes.append((key, before[key], None))
    return changes


@dataclass(slots=True)
class BlobHandle:
    """Metadata describing a persisted blob."""

    blob_id: str
    metadata: dict[str, Any] = None  # type: ignore[assignment]


class StateBackend(ABC):
    """Abstract storage backend for graph/agent state."""

    backend_name: ClassVar[str] = 'custom'

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        *,
        serializer: StateSerializer | str | None = None,
    ) -> None:
        self._initial_state = dict(initial_state or {})
        self._watchers: dict[str, list[WatcherCallback]] = {}
        self._serializer: StateSerializer = ensure_state_serializer(serializer)
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_stats: dict[str, dict[str, float]] = {}

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
    async def items(self) -> dict[str, Any]:
        """Return map of all state values."""

    @abstractmethod
    async def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        """Atomically set value if current matches expected."""

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[dict[str, Any]]:
        """Context manager for atomic updates."""

    @asynccontextmanager
    async def acquire_lock(self, name: str = 'global') -> AsyncIterator[dict[str, Any]]:
        """Acquire an async lock for coordinating GraphState access."""

        lock = self._locks.setdefault(name, asyncio.Lock())
        start = time.perf_counter()
        await lock.acquire()
        waited = time.perf_counter() - start
        stats = self._lock_stats.setdefault(
            name,
            {'wait_count': 0, 'total_wait_seconds': 0.0, 'last_wait_seconds': 0.0},
        )
        stats['wait_count'] += 1
        stats['total_wait_seconds'] += waited
        stats['last_wait_seconds'] = waited
        try:
            yield {'name': name, 'waited_seconds': waited}
        finally:
            lock.release()

    def describe(self) -> dict[str, Any]:
        """Return metadata describing backend configuration."""
        return {
            'name': self.backend_name,
            'config': {},
            'serializer': self._serializer.name,
            'locks': self.lock_stats(),
        }

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

    def register_watcher(self, key: str, callback: WatcherCallback) -> Callable[[], None]:
        """Register callback invoked when key changes."""
        watchers = self._watchers.setdefault(key, [])
        watchers.append(callback)

        def _remove() -> None:
            try:
                watchers.remove(callback)
            except ValueError:
                pass

        return _remove

    async def _notify_watchers(self, key: str, old: Any, new: Any) -> None:
        callbacks = list(self._watchers.get(key, [])) + list(self._watchers.get('*', []))
        for callback in callbacks:
            try:
                result = callback(key, old, new)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("State watcher failed for key=%s callback=%s", key, callback)

    def _serialize_value(self, value: Any) -> bytes:
        return self._serializer.dumps(value)

    def _deserialize_value(self, payload: bytes | str) -> Any:
        data = payload.encode('utf-8') if isinstance(payload, str) else payload
        return self._serializer.loads(data)

    def lock_stats(self) -> dict[str, dict[str, float]]:
        return {name: dict(stats) for name, stats in self._lock_stats.items()}

    def supports_blobs(self) -> bool:
        """Return True if backend implements streaming blob storage."""

        return False

    @asynccontextmanager
    async def open_blob_writer(
        self,
        *,
        blob_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Any]:
        """Stream data into a blob."""

        raise NotImplementedError("Blob storage not supported by backend")

    @asynccontextmanager
    async def open_blob_reader(self, blob_id: str) -> AsyncIterator[Any]:
        raise NotImplementedError("Blob storage not supported by backend")

    async def delete_blob(self, blob_id: str) -> None:
        raise NotImplementedError("Blob storage not supported by backend")

    async def list_blobs(self) -> list[str]:
        return []


class InMemoryStateBackend(StateBackend):
    """Async-lock backed in-memory store used as default GraphState backend."""

    backend_name = 'memory'

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        *,
        serializer: StateSerializer | str | None = None,
    ) -> None:
        super().__init__(initial_state, serializer=serializer)
        self._state: dict[str, Any] = dict(self._initial_state)
        self._lock = asyncio.Lock()
        self._concurrent_mode = False
        self._blobs: dict[str, bytes] = {}

    def enable_concurrent_mode(self) -> None:
        self._concurrent_mode = True

    def disable_concurrent_mode(self) -> None:
        self._concurrent_mode = False

    async def get(self, key: str, default: Any = None) -> Any:
        if self._concurrent_mode:
            async with self._lock:
                return self._state.get(key, default)
        return self._state.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        if self._concurrent_mode:
            async with self._lock:
                old = self._state.get(key)
                self._state[key] = value
        else:
            old = self._state.get(key)
            self._state[key] = value
        await self._notify_watchers(key, old, value)

    async def update(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        if self._concurrent_mode:
            async with self._lock:
                old_values = {key: self._state.get(key) for key in updates.keys()}
                self._state.update(updates)
        else:
            old_values = {key: self._state.get(key) for key in updates.keys()}
            self._state.update(updates)
        for key, value in updates.items():
            await self._notify_watchers(key, old_values.get(key), value)

    async def delete(self, key: str) -> None:
        if self._concurrent_mode:
            async with self._lock:
                old = self._state.pop(key, None)
        else:
            old = self._state.pop(key, None)
        await self._notify_watchers(key, old, None)

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

    async def items(self) -> dict[str, Any]:
        if self._concurrent_mode:
            async with self._lock:
                return dict(self._state)
        return dict(self._state)

    async def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        if self._concurrent_mode:
            async with self._lock:
                current = self._state.get(key)
                if current != expected:
                    return False
                self._state[key] = value
        else:
            current = self._state.get(key)
            if current != expected:
                return False
            self._state[key] = value
        await self._notify_watchers(key, expected, value)
        return True

    @asynccontextmanager
    async def transaction(self):
        if self._concurrent_mode:
            async with self._lock:
                before = dict(self._state)
                yield self._state
                after = dict(self._state)
        else:
            before = dict(self._state)
            yield self._state
            after = dict(self._state)
        changes = _diff_state(before, after)
        for key, old, new in changes:
            await self._notify_watchers(key, old, new)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state)

    def get_raw_state(self) -> dict[str, Any]:
        return self._state

    def clear(self) -> None:
        self._state.clear()

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data['config'] = {'concurrent': self._concurrent_mode}
        return data

    def supports_blobs(self) -> bool:
        return True

    @asynccontextmanager
    async def open_blob_writer(
        self,
        *,
        blob_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Any]:
        key = blob_id or uuid4().hex
        buffer = bytearray()

        class _Writer:
            blob_id = key  # type: ignore[assignment]

            async def write(self_inner, data: bytes) -> None:
                buffer.extend(data)

        writer = _Writer()
        try:
            yield writer
            self._blobs[key] = bytes(buffer)
        finally:
            buffer.clear()

    @asynccontextmanager
    async def open_blob_reader(self, blob_id: str) -> AsyncIterator[Any]:
        if blob_id not in self._blobs:
            raise KeyError(f"Blob '{blob_id}' not found")
        data = self._blobs[blob_id]

        class _Reader:
            def __init__(self_inner) -> None:
                self_inner._pos = 0

            async def read(self_inner, size: int = -1) -> bytes:
                if size is None or size < 0:
                    chunk = data[self_inner._pos :]
                    self_inner._pos = len(data)
                    return chunk
                end = min(self_inner._pos + size, len(data))
                chunk = data[self_inner._pos : end]
                self_inner._pos = end
                return chunk

        reader = _Reader()
        yield reader

    async def delete_blob(self, blob_id: str) -> None:
        self._blobs.pop(blob_id, None)

    async def list_blobs(self) -> list[str]:
        return list(self._blobs.keys())


class SQLiteStateBackend(StateBackend):
    """SQLite backed state store for durable mission data."""

    backend_name = 'sqlite'

    def __init__(
        self,
        db_path: str | Path,
        *,
        table_name: str = "graph_state",
        initial_state: dict[str, Any] | None = None,
        serializer: StateSerializer | str | None = None,
    ) -> None:
        super().__init__(initial_state, serializer=serializer)
        self.db_path = str(db_path)
        self.table_name = table_name
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._state_cache: dict[str, Any] = dict(self._initial_state)
        blob_dir_name = f"{Path(self.db_path).stem}_blobs"
        self._blob_dir = Path(self.db_path).parent / blob_dir_name
        self._blob_index_path = self._blob_dir / "index.json"
        self._blob_index: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            f"CREATE TABLE IF NOT EXISTS {self.table_name} (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
        )
        await self._init_blob_store()
        self._conn.commit()
        rows = self._conn.execute(f"SELECT key, value FROM {self.table_name}").fetchall()
        for key, value in rows:
            if key in self._state_cache:
                continue
            payload = value if isinstance(value, (bytes, bytearray)) else str(value).encode('utf-8')
            self._state_cache[key] = self._deserialize_value(payload)
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
                payload = sqlite3.Binary(self._serialize_value(value))
                cur.execute(
                    f"INSERT INTO {self.table_name}(key, value) VALUES(?, ?) "
                    f"ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, payload),
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
            before = {key: self._state_cache.get(key) for key in updates.keys()}
            self._state_cache.update(updates)
        await self._write_many(updates)
        for key, value in updates.items():
            await self._notify_watchers(key, before.get(key), value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            existed = key in self._state_cache
            old = self._state_cache.pop(key, None)
        if existed:
            await self._delete_keys([key])
        await self._notify_watchers(key, old, None)

    async def has(self, key: str) -> bool:
        async with self._lock:
            return key in self._state_cache

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._state_cache.keys())

    async def items(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._state_cache)

    async def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        async with self._lock:
            current = self._state_cache.get(key)
            if current != expected:
                return False
            self._state_cache[key] = value
        await self._write_many({key: value})
        await self._notify_watchers(key, expected, value)
        return True

    @asynccontextmanager
    async def transaction(self):
        await self.initialize()
        async with self._lock:
            working_copy = dict(self._state_cache)
        yield working_copy
        async with self._lock:
            before = dict(self._state_cache)
            self._state_cache = dict(working_copy)
        await self._replace_all(working_copy)
        changes = _diff_state(before, working_copy)
        for key, old, new in changes:
            await self._notify_watchers(key, old, new)

    async def _replace_all(self, new_state: dict[str, Any]) -> None:
        conn = self._ensure_conn()

        def _replace():
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {self.table_name}")
            cur.executemany(
                f"INSERT INTO {self.table_name}(key, value) VALUES(?, ?)",
                ((key, sqlite3.Binary(self._serialize_value(value))) for key, value in new_state.items()),
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

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data['config'] = {'db_path': self.db_path, 'table': self.table_name}
        return data

    def supports_blobs(self) -> bool:
        return True

    async def _init_blob_store(self) -> None:
        await asyncio.to_thread(self._blob_dir.mkdir, parents=True, exist_ok=True)
        if self._blob_index_path.exists():
            try:
                text = await asyncio.to_thread(self._blob_index_path.read_text, encoding='utf-8')
                self._blob_index = json.loads(text)
            except Exception:
                logger.exception("Failed to load blob index %s", self._blob_index_path)
                self._blob_index = {}

    async def _persist_blob_index(self) -> None:
        payload = json.dumps(self._blob_index, indent=2)
        await asyncio.to_thread(self._blob_index_path.write_text, payload, encoding='utf-8')

    @asynccontextmanager
    async def open_blob_writer(
        self,
        *,
        blob_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Any]:
        blob_key = blob_id or uuid4().hex
        path = self._blob_dir / blob_key
        fh = open(path, 'wb')

        class _Writer:
            blob_id = blob_key  # type: ignore[assignment]

            async def write(self_inner, data: bytes) -> None:
                await asyncio.to_thread(fh.write, data)

        try:
            yield _Writer()
            await asyncio.to_thread(fh.flush)
            self._blob_index[blob_key] = metadata or {}
            await self._persist_blob_index()
        finally:
            await asyncio.to_thread(fh.close)

    @asynccontextmanager
    async def open_blob_reader(self, blob_id: str) -> AsyncIterator[Any]:
        path = self._blob_dir / blob_id
        if not path.exists():
            raise KeyError(f"Blob '{blob_id}' not found")
        fh = open(path, 'rb')

        class _Reader:
            async def read(self_inner, size: int = -1) -> bytes:
                return await asyncio.to_thread(fh.read, size)

        try:
            yield _Reader()
        finally:
            await asyncio.to_thread(fh.close)

    async def delete_blob(self, blob_id: str) -> None:
        path = self._blob_dir / blob_id
        if path.exists():
            try:
                os.remove(path)
            except OSError:
                logger.exception("Failed to delete blob %s", blob_id)
        self._blob_index.pop(blob_id, None)
        await self._persist_blob_index()

    async def list_blobs(self) -> list[str]:
        return list(self._blob_index.keys())


class JSONFileStateBackend(StateBackend):
    """File-backed backend storing JSON payload."""

    backend_name = 'file'

    def __init__(
        self,
        path: str | Path,
        initial_state: dict[str, Any] | None = None,
        *,
        serializer: StateSerializer | str | None = None,
    ) -> None:
        super().__init__(initial_state, serializer=serializer)
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._state_cache: dict[str, Any] = {}
        self._blob_dir = self.path.parent / f"{self.path.stem}_blobs"
        self._blob_index_path = self._blob_dir / "index.json"
        self._blob_index: dict[str, str] = {}

    async def initialize(self) -> None:
        if self.path.exists():
            try:
                data = self.path.read_bytes()
                if data:
                    contents = self._deserialize_value(data)
                    if isinstance(contents, dict):
                        self._state_cache = contents
            except Exception:
                logger.exception("Failed to load state file %s", self.path)
        if self._initial_state:
            self._state_cache.update(self._initial_state)
            await self._write_file()
        await self._init_blob_store()

    async def _write_file(self) -> None:
        await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)

        def _write():
            payload = self._serialize_value(self._state_cache)
            if self._serializer.binary:
                self.path.write_bytes(payload)
            else:
                self.path.write_text(payload.decode('utf-8'), encoding='utf-8')

        await asyncio.to_thread(_write)

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._state_cache.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            old = self._state_cache.get(key)
            self._state_cache[key] = value
        await self._write_file()
        await self._notify_watchers(key, old, value)

    async def update(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        async with self._lock:
            before = {k: self._state_cache.get(k) for k in updates.keys()}
            self._state_cache.update(updates)
        await self._write_file()
        for key, value in updates.items():
            await self._notify_watchers(key, before.get(key), value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            old = self._state_cache.pop(key, None)
        await self._write_file()
        await self._notify_watchers(key, old, None)

    async def has(self, key: str) -> bool:
        async with self._lock:
            return key in self._state_cache

    async def keys(self) -> list[str]:
        async with self._lock:
            return list(self._state_cache.keys())

    async def items(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._state_cache)

    async def compare_and_set(self, key: str, expected: Any, value: Any) -> bool:
        async with self._lock:
            current = self._state_cache.get(key)
            if current != expected:
                return False
            self._state_cache[key] = value
        await self._write_file()
        await self._notify_watchers(key, expected, value)
        return True

    @asynccontextmanager
    async def transaction(self):
        async with self._lock:
            working_copy = dict(self._state_cache)
        yield working_copy
        async with self._lock:
            before = dict(self._state_cache)
            self._state_cache = dict(working_copy)
        await self._write_file()
        changes = _diff_state(before, working_copy)
        for key, old, new in changes:
            await self._notify_watchers(key, old, new)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._state_cache)

    def get_raw_state(self) -> dict[str, Any]:
        return self._state_cache

    def clear(self) -> None:
        self._state_cache.clear()
        try:
            self.path.unlink()
        except FileNotFoundError:
            return

    def describe(self) -> dict[str, Any]:
        data = super().describe()
        data['config'] = {'path': str(self.path)}
        return data

    def supports_blobs(self) -> bool:
        return True

    async def _init_blob_store(self) -> None:
        await asyncio.to_thread(self._blob_dir.mkdir, parents=True, exist_ok=True)
        if self._blob_index_path.exists():
            try:
                text = await asyncio.to_thread(self._blob_index_path.read_text, encoding='utf-8')
                self._blob_index = json.loads(text)
            except Exception:
                logger.exception("Failed to load blob index %s", self._blob_index_path)
                self._blob_index = {}

    async def _persist_blob_index(self) -> None:
        payload = json.dumps(self._blob_index, indent=2)
        await asyncio.to_thread(self._blob_index_path.write_text, payload, encoding='utf-8')

    @asynccontextmanager
    async def open_blob_writer(
        self,
        *,
        blob_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[Any]:
        blob_key = blob_id or uuid4().hex
        path = self._blob_dir / blob_key
        fh = open(path, 'wb')

        class _Writer:
            blob_id = blob_key  # type: ignore[assignment]

            async def write(self_inner, data: bytes) -> None:
                await asyncio.to_thread(fh.write, data)

        try:
            yield _Writer()
            await asyncio.to_thread(fh.flush)
            self._blob_index[blob_key] = metadata or {}
            await self._persist_blob_index()
        finally:
            await asyncio.to_thread(fh.close)

    @asynccontextmanager
    async def open_blob_reader(self, blob_id: str) -> AsyncIterator[Any]:
        path = self._blob_dir / blob_id
        if not path.exists():
            raise KeyError(f"Blob '{blob_id}' not found")
        fh = open(path, 'rb')

        class _Reader:
            async def read(self_inner, size: int = -1) -> bytes:
                return await asyncio.to_thread(fh.read, size)

        try:
            yield _Reader()
        finally:
            await asyncio.to_thread(fh.close)

    async def delete_blob(self, blob_id: str) -> None:
        path = self._blob_dir / blob_id
        if path.exists():
            try:
                os.remove(path)
            except OSError:
                logger.exception("Failed to delete blob %s", blob_id)
        self._blob_index.pop(blob_id, None)
        await self._persist_blob_index()

    async def list_blobs(self) -> list[str]:
        return list(self._blob_index.keys())


_BACKEND_REGISTRY: dict[str, type[StateBackend]] = {}


def register_state_backend(name: str, backend_cls: type[StateBackend]) -> None:
    """Register a backend class."""
    _BACKEND_REGISTRY[name] = backend_cls


def get_backend_class(name: str) -> type[StateBackend] | None:
    """Return backend class by name."""
    return _BACKEND_REGISTRY.get(name)


def create_state_backend(
    name: str,
    *,
    options: dict[str, Any] | None = None,
    initial_state: dict[str, Any] | None = None,
    serializer: StateSerializer | str | None = None,
) -> StateBackend:
    """Instantiate backend based on registry entry."""
    backend_cls = _BACKEND_REGISTRY.get(name)
    if backend_cls is None:
        raise ValueError(f"Unknown state backend '{name}'. Registered: {list(_BACKEND_REGISTRY)}")
    options = dict(options or {})
    serializer = serializer or options.pop('serializer', None)
    sig = inspect.signature(backend_cls.__init__)
    valid_options: dict[str, Any] = {}
    for key, value in options.items():
        if key in sig.parameters:
            valid_options[key] = value
        else:
            logger.debug("Ignoring unsupported backend option '%s' for %s", key, name)
    return backend_cls(initial_state=initial_state, serializer=serializer, **valid_options)


register_state_backend('memory', InMemoryStateBackend)
register_state_backend('sqlite', SQLiteStateBackend)
register_state_backend('file', JSONFileStateBackend)
