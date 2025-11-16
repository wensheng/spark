"""Graph-level state management with pluggable backends."""

from contextlib import asynccontextmanager
from typing import Any, Type

from pydantic import BaseModel

from spark.graphs.state_backend import InMemoryStateBackend, StateBackend


class GraphState:
    """Thread-safe graph state with backend abstraction.

    Provides safe concurrent access to mission state regardless of where it is stored.
    Default backend is in-memory; durable backends can be supplied for checkpoints.
    """

    _SCHEMA_VERSION_KEY = '__schema_version__'
    _MAILBOX_PREFIX = '__mailbox__'

    def __init__(
        self,
        initial_state: dict[str, Any] | None = None,
        backend: StateBackend | None = None,
        schema_model: Type[BaseModel] | BaseModel | None = None,
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
        self._schema_cls = self._normalize_schema(schema_model)
        self._schema_metadata = self._build_schema_metadata(self._schema_cls)

    def _normalize_schema(self, schema_model: Type[BaseModel] | BaseModel | None) -> Type[BaseModel] | None:
        if schema_model is None:
            return None
        if isinstance(schema_model, type) and issubclass(schema_model, BaseModel):
            return schema_model
        if isinstance(schema_model, BaseModel):
            return schema_model.__class__
        raise TypeError(f"Invalid schema model: {schema_model!r}")

    def _build_schema_metadata(self, schema_cls: Type[BaseModel] | None) -> dict[str, Any] | None:
        if schema_cls is None:
            return None
        metadata = {
            'name': getattr(schema_cls, 'schema_name', schema_cls.__name__),
            'version': getattr(schema_cls, 'schema_version', '1.0'),
            'module': f"{schema_cls.__module__}:{schema_cls.__name__}",
            'json_schema': schema_cls.model_json_schema(),
        }
        return metadata

    def _validate_state(self, candidate: dict[str, Any]) -> None:
        if self._schema_cls is None:
            return
        self._schema_cls.model_validate(candidate)

    async def initialize(self) -> None:
        """Initialize the backend once graph runtime is ready."""
        if self._initialized:
            return
        await self._backend.initialize()
        if self._pending_initial_state:
            await self._backend.update(self._pending_initial_state)
            self._pending_initial_state.clear()
        await self._ensure_schema_version()
        self._initialized = True

    def _mailbox_storage_key(self, mailbox_id: str) -> str:
        return f"{self._MAILBOX_PREFIX}:{mailbox_id}"

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
        snapshot = self.get_snapshot()
        snapshot[key] = value
        self._validate_state(snapshot)
        await self._backend.set(key, value)

    async def update(self, updates: dict[str, Any]) -> None:
        """Thread-safe batch update."""
        if not updates:
            return
        snapshot = self.get_snapshot()
        snapshot.update(updates)
        self._validate_state(snapshot)
        await self._backend.update(updates)

    async def delete(self, key: str) -> None:
        """Thread-safe delete operation."""
        snapshot = self.get_snapshot()
        snapshot.pop(key, None)
        self._validate_state(snapshot)
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
            version = state_dict.get(self._SCHEMA_VERSION_KEY)
            if self._schema_cls:
                state_dict.pop(self._SCHEMA_VERSION_KEY, None)
            yield state_dict
            if self._schema_cls:
                state_dict[self._SCHEMA_VERSION_KEY] = self._schema_cls.schema_version
            elif version is not None:
                state_dict[self._SCHEMA_VERSION_KEY] = version
        self._validate_state(self.get_snapshot())

    @asynccontextmanager
    async def lock(self, name: str = 'global'):
        """Acquire a named lock shared across GraphState users."""

        async with self._backend.acquire_lock(name) as metadata:
            yield metadata

    def get_lock_stats(self) -> dict[str, Any]:
        """Return lock wait statistics from the backend."""

        return self._backend.lock_stats()

    def get_snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of current state (non-blocking)."""
        snapshot = self._backend.snapshot()
        return self._strip_metadata(snapshot)

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
            if self._schema_cls:
                state_dict[self._SCHEMA_VERSION_KEY] = self._schema_cls.schema_version
        self._pending_initial_state.clear()
        self._validate_state(self.get_snapshot())
        await self._ensure_schema_version()

    def describe_backend(self) -> dict[str, Any]:
        """Return backend metadata for serialization."""
        return self._backend.describe()

    def describe_schema(self) -> dict[str, Any] | None:
        """Return schema metadata if configured."""
        return dict(self._schema_metadata) if self._schema_metadata else None

    def __repr__(self) -> str:
        """Return a string representation of the state."""
        snapshot = self.get_snapshot()
        mode = (
            "concurrent"
            if hasattr(self._backend, "_concurrent_mode") and getattr(self._backend, "_concurrent_mode")
            else "sequential"
        )
        return f"GraphState(mode={mode}, keys={list(snapshot.keys())})"

    async def load_mailbox_messages(self, mailbox_id: str) -> list[Any]:
        """Load persisted mailbox entries for the given mailbox identifier."""
        key = self._mailbox_storage_key(mailbox_id)
        stored = await self._backend.get(key, None)
        if not stored:
            return []
        if isinstance(stored, list):
            return list(stored)
        return []

    async def persist_mailbox_messages(self, mailbox_id: str, entries: list[Any]) -> None:
        """Persist the provided mailbox entries atomically."""
        key = self._mailbox_storage_key(mailbox_id)
        if entries:
            await self._backend.set(key, list(entries))
        else:
            await self._backend.delete(key)

    async def clear_mailboxes(self) -> None:
        """Remove all persisted mailbox queues."""
        prefix = f"{self._MAILBOX_PREFIX}:"
        keys = await self._backend.keys()
        for key in keys:
            if key.startswith(prefix):
                await self._backend.delete(key)

    async def mailbox_snapshot(self) -> dict[str, list[Any]]:
        """Return serialized queues for every persisted mailbox."""
        prefix = f"{self._MAILBOX_PREFIX}:"
        snapshot: dict[str, list[Any]] = {}
        keys = await self._backend.keys()
        for key in keys:
            if not key.startswith(prefix):
                continue
            mailbox_id = key[len(prefix) :]
            stored = await self._backend.get(key, None) or []
            if isinstance(stored, list) and stored:
                snapshot[mailbox_id] = list(stored)
        return snapshot

    async def restore_mailboxes(self, payload: dict[str, list[Any]] | None) -> None:
        """Replace all persisted mailboxes with the provided payload."""
        await self.clear_mailboxes()
        if not payload:
            return
        for mailbox_id, entries in payload.items():
            await self.persist_mailbox_messages(mailbox_id, list(entries))

    def supports_blobs(self) -> bool:
        """Return True if backend exposes streaming blob storage."""

        return self._backend.supports_blobs()

    @asynccontextmanager
    async def open_blob_writer(
        self,
        *,
        blob_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        if not self.supports_blobs():
            raise RuntimeError("State backend does not support blob storage")
        async with self._backend.open_blob_writer(blob_id=blob_id, metadata=metadata) as writer:
            yield writer

    @asynccontextmanager
    async def open_blob_reader(self, blob_id: str):
        if not self.supports_blobs():
            raise RuntimeError("State backend does not support blob storage")
        async with self._backend.open_blob_reader(blob_id) as reader:
            yield reader

    async def delete_blob(self, blob_id: str) -> None:
        if not self.supports_blobs():
            raise RuntimeError("State backend does not support blob storage")
        await self._backend.delete_blob(blob_id)

    async def list_blobs(self) -> list[str]:
        if not self.supports_blobs():
            return []
        return await self._backend.list_blobs()

    def _strip_metadata(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        data = dict(snapshot)
        data.pop(self._SCHEMA_VERSION_KEY, None)
        if not data:
            return data
        prefix = f"{self._MAILBOX_PREFIX}:"
        remove_keys = [key for key in data.keys() if key.startswith(prefix)]
        for key in remove_keys:
            data.pop(key, None)
        return data

    async def _ensure_schema_version(self) -> None:
        if not self._schema_cls:
            return
        raw_snapshot = self._backend.snapshot()
        current_version = raw_snapshot.get(self._SCHEMA_VERSION_KEY)
        target_version = self._schema_cls.schema_version
        sanitized = self._strip_metadata(raw_snapshot)
        if current_version == target_version and current_version is not None:
            if self._SCHEMA_VERSION_KEY not in raw_snapshot:
                async with self._backend.transaction() as data:
                    data[self._SCHEMA_VERSION_KEY] = target_version
            return
        migrated_state, final_version = self._schema_cls.migrate_state(
            sanitized,
            current_version=current_version,
        )
        async with self._backend.transaction() as data:
            data.clear()
            data.update(migrated_state)
            data[self._SCHEMA_VERSION_KEY] = final_version
