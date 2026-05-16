"""Durable journal interfaces and built-in implementations."""

from __future__ import annotations

import asyncio
import pickle
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One persisted event for a persistent actor."""

    persistence_id: str
    sequence: int
    event: Any
    timestamp: float


@dataclass(frozen=True, slots=True)
class JournalSnapshot:
    """Snapshot for a persistent actor."""

    persistence_id: str
    sequence: int
    state: Any
    timestamp: float


@dataclass(frozen=True, slots=True)
class DurableTimer:
    """Durable timer owned by a persistent actor."""

    persistence_id: str
    timer_id: str
    due_time: float
    payload: Any = None


class Journal(Protocol):
    """Persistence journal used by opt-in persistent actors."""

    async def append_event(self, persistence_id: str, event: Any) -> JournalEvent:
        """Append one event and return its assigned sequence."""
        ...

    async def read_events(self, persistence_id: str, *, after_sequence: int = 0) -> Sequence[JournalEvent]:
        """Read events after a sequence number."""
        ...

    async def save_snapshot(self, persistence_id: str, sequence: int, state: Any) -> None:
        """Persist a compact actor snapshot."""
        ...

    async def load_snapshot(self, persistence_id: str) -> JournalSnapshot | None:
        """Load the latest actor snapshot."""
        ...

    async def upsert_timer(self, timer: DurableTimer) -> None:
        """Create or replace one durable timer."""
        ...

    async def delete_timer(self, persistence_id: str, timer_id: str) -> None:
        """Delete one durable timer."""
        ...

    async def list_timers(self, persistence_id: str) -> Sequence[DurableTimer]:
        """List all durable timers for one persistence id."""
        ...

    async def close(self) -> None:
        """Close journal resources."""
        ...


class InMemoryJournal:
    """In-memory journal useful for tests and single-process experiments."""

    def __init__(self) -> None:
        self._events: dict[str, list[JournalEvent]] = {}
        self._snapshots: dict[str, JournalSnapshot] = {}
        self._timers: dict[tuple[str, str], DurableTimer] = {}
        self._lock = asyncio.Lock()

    async def append_event(self, persistence_id: str, event: Any) -> JournalEvent:
        async with self._lock:
            events = self._events.setdefault(persistence_id, [])
            entry = JournalEvent(
                persistence_id=persistence_id,
                sequence=len(events) + 1,
                event=event,
                timestamp=time.time(),
            )
            events.append(entry)
            return entry

    async def read_events(self, persistence_id: str, *, after_sequence: int = 0) -> Sequence[JournalEvent]:
        async with self._lock:
            return tuple(event for event in self._events.get(persistence_id, ()) if event.sequence > after_sequence)

    async def save_snapshot(self, persistence_id: str, sequence: int, state: Any) -> None:
        async with self._lock:
            self._snapshots[persistence_id] = JournalSnapshot(persistence_id, sequence, state, time.time())

    async def load_snapshot(self, persistence_id: str) -> JournalSnapshot | None:
        async with self._lock:
            return self._snapshots.get(persistence_id)

    async def upsert_timer(self, timer: DurableTimer) -> None:
        async with self._lock:
            self._timers[(timer.persistence_id, timer.timer_id)] = timer

    async def delete_timer(self, persistence_id: str, timer_id: str) -> None:
        async with self._lock:
            self._timers.pop((persistence_id, timer_id), None)

    async def list_timers(self, persistence_id: str) -> Sequence[DurableTimer]:
        async with self._lock:
            return tuple(timer for timer in self._timers.values() if timer.persistence_id == persistence_id)

    async def close(self) -> None:
        return None


class SQLiteJournal:
    """SQLite-backed journal for local durable actors and timers."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._conn is not None:
            return
        path = Path(self.path)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        await asyncio.to_thread(self._create_schema)

    def _create_schema(self) -> None:
        conn = self._ensure_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spark_journal_events (
                persistence_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                event BLOB NOT NULL,
                PRIMARY KEY (persistence_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS spark_journal_snapshots (
                persistence_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                state BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spark_journal_timers (
                persistence_id TEXT NOT NULL,
                timer_id TEXT NOT NULL,
                due_time REAL NOT NULL,
                payload BLOB,
                PRIMARY KEY (persistence_id, timer_id)
            );
            """)
        conn.commit()

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteJournal is closed or not initialized")
        return self._conn

    async def append_event(self, persistence_id: str, event: Any) -> JournalEvent:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()

            def _append() -> JournalEvent:
                cur = conn.cursor()
                row = cur.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM spark_journal_events WHERE persistence_id = ?",
                    (persistence_id,),
                ).fetchone()
                sequence = int(row[0])
                timestamp = time.time()
                cur.execute(
                    """
                    INSERT INTO spark_journal_events(persistence_id, sequence, timestamp, event)
                    VALUES(?, ?, ?, ?)
                    """,
                    (persistence_id, sequence, timestamp, sqlite3.Binary(pickle.dumps(event))),
                )
                conn.commit()
                return JournalEvent(persistence_id, sequence, event, timestamp)

            return await asyncio.to_thread(_append)

    async def read_events(self, persistence_id: str, *, after_sequence: int = 0) -> Sequence[JournalEvent]:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()

            def _read() -> tuple[JournalEvent, ...]:
                rows = conn.execute(
                    """
                    SELECT sequence, timestamp, event
                    FROM spark_journal_events
                    WHERE persistence_id = ? AND sequence > ?
                    ORDER BY sequence ASC
                    """,
                    (persistence_id, after_sequence),
                ).fetchall()
                return tuple(
                    JournalEvent(persistence_id, int(sequence), pickle.loads(event), float(timestamp))
                    for sequence, timestamp, event in rows
                )

            return await asyncio.to_thread(_read)

    async def save_snapshot(self, persistence_id: str, sequence: int, state: Any) -> None:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()
            timestamp = time.time()
            payload = sqlite3.Binary(pickle.dumps(state))
            await asyncio.to_thread(
                conn.execute,
                """
                INSERT INTO spark_journal_snapshots(persistence_id, sequence, timestamp, state)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(persistence_id) DO UPDATE SET
                    sequence = excluded.sequence,
                    timestamp = excluded.timestamp,
                    state = excluded.state
                """,
                (persistence_id, sequence, timestamp, payload),
            )
            await asyncio.to_thread(conn.commit)

    async def load_snapshot(self, persistence_id: str) -> JournalSnapshot | None:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()

            def _load() -> JournalSnapshot | None:
                row = conn.execute(
                    "SELECT sequence, timestamp, state FROM spark_journal_snapshots WHERE persistence_id = ?",
                    (persistence_id,),
                ).fetchone()
                if row is None:
                    return None
                sequence, timestamp, state = row
                return JournalSnapshot(persistence_id, int(sequence), pickle.loads(state), float(timestamp))

            return await asyncio.to_thread(_load)

    async def upsert_timer(self, timer: DurableTimer) -> None:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()
            await asyncio.to_thread(
                conn.execute,
                """
                INSERT INTO spark_journal_timers(persistence_id, timer_id, due_time, payload)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(persistence_id, timer_id) DO UPDATE SET
                    due_time = excluded.due_time,
                    payload = excluded.payload
                """,
                (
                    timer.persistence_id,
                    timer.timer_id,
                    timer.due_time,
                    sqlite3.Binary(pickle.dumps(timer.payload)),
                ),
            )
            await asyncio.to_thread(conn.commit)

    async def delete_timer(self, persistence_id: str, timer_id: str) -> None:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()
            await asyncio.to_thread(
                conn.execute,
                "DELETE FROM spark_journal_timers WHERE persistence_id = ? AND timer_id = ?",
                (persistence_id, timer_id),
            )
            await asyncio.to_thread(conn.commit)

    async def list_timers(self, persistence_id: str) -> Sequence[DurableTimer]:
        await self.initialize()
        async with self._lock:
            conn = self._ensure_conn()

            def _list() -> tuple[DurableTimer, ...]:
                rows = conn.execute(
                    """
                    SELECT timer_id, due_time, payload
                    FROM spark_journal_timers
                    WHERE persistence_id = ?
                    ORDER BY due_time ASC
                    """,
                    (persistence_id,),
                ).fetchall()
                return tuple(
                    DurableTimer(persistence_id, str(timer_id), float(due_time), pickle.loads(payload))
                    for timer_id, due_time, payload in rows
                )

            return await asyncio.to_thread(_list)

    async def close(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is not None:
            await asyncio.to_thread(conn.close)
