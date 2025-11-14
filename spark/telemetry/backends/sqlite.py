"""
SQLite telemetry backend for local storage.

This backend stores telemetry data in a local SQLite database file,
providing persistent storage for development and single-machine deployments.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from spark.telemetry.backends.base import BaseTelemetryBackend
from spark.telemetry.types import Event, EventType, Metric, Span, SpanKind, SpanStatus, Trace

logger = logging.getLogger(__name__)

# Check for aiosqlite availability
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    logger.warning("aiosqlite not available, SQLiteBackend will not work. Install with: pip install aiosqlite")


class SQLiteBackend(BaseTelemetryBackend):
    """SQLite storage backend for telemetry data.

    Stores traces, spans, events, and metrics in a local SQLite database
    with appropriate indexes for efficient querying.

    Usage:
        backend = SQLiteBackend({'db_path': 'telemetry.db'})
        await backend.initialize()
        await backend.write_spans([span1, span2])

    Schema:
        - traces: trace_id, name, start_time, end_time, status, attributes, resource
        - spans: span_id, trace_id, parent_span_id, name, kind, start_time, end_time, status, attributes, events, error
        - events: event_id, timestamp, type, name, attributes, span_id, trace_id
        - metrics: metric_id, timestamp, name, value, unit, attributes, aggregation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize SQLite backend.

        Args:
            config: Configuration dict with 'db_path' key

        Raises:
            ImportError: If aiosqlite is not installed
        """
        if not AIOSQLITE_AVAILABLE:
            raise ImportError("aiosqlite is required for SQLiteBackend. Install with: pip install aiosqlite")

        self.db_path = config.get('db_path', 'spark_telemetry.db')
        self._db: Optional[Any] = None
        self._initialized = False

    async def _get_connection(self) -> Any:
        """Get or create database connection."""
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._initialize_schema()
        return self._db

    async def _initialize_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        if self._initialized:
            return

        db = await self._get_connection()

        # Traces table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                duration REAL,
                status TEXT NOT NULL,
                attributes TEXT,
                resource TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_traces_start_time ON traces(start_time)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")

        # Spans table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                parent_span_id TEXT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                duration REAL,
                status TEXT NOT NULL,
                attributes TEXT,
                events TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_spans_kind ON spans(kind)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_spans_start_time ON spans(start_time)")

        # Events table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                attributes TEXT,
                span_id TEXT,
                trace_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (span_id) REFERENCES spans(span_id),
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")

        # Metrics table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                attributes TEXT,
                aggregation TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")

        await db.commit()
        self._initialized = True
        logger.info(f"Initialized SQLite telemetry database: {self.db_path}")

    async def write_traces(self, traces: List[Trace]) -> None:
        """Write traces to SQLite.

        Args:
            traces: List of Trace objects to store
        """
        db = await self._get_connection()

        for trace in traces:
            await db.execute(
                """
                INSERT OR REPLACE INTO traces
                (trace_id, name, start_time, end_time, duration, status, attributes, resource)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.name,
                    trace.start_time,
                    trace.end_time,
                    trace.duration,
                    trace.status.value,
                    json.dumps(trace.attributes),
                    json.dumps(trace.resource),
                )
            )

        await db.commit()
        logger.debug(f"Wrote {len(traces)} traces to SQLite")

    async def write_spans(self, spans: List[Span]) -> None:
        """Write spans to SQLite.

        Args:
            spans: List of Span objects to store
        """
        db = await self._get_connection()

        for span in spans:
            await db.execute(
                """
                INSERT OR REPLACE INTO spans
                (span_id, trace_id, parent_span_id, name, kind, start_time, end_time, duration,
                 status, attributes, events, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.name,
                    span.kind.value,
                    span.start_time,
                    span.end_time,
                    span.duration,
                    span.status.value,
                    json.dumps(span.attributes),
                    json.dumps([e.to_dict() for e in span.events]),
                    json.dumps(span.error) if span.error else None,
                )
            )

        await db.commit()
        logger.debug(f"Wrote {len(spans)} spans to SQLite")

    async def write_events(self, events: List[Event]) -> None:
        """Write events to SQLite.

        Args:
            events: List of Event objects to store
        """
        db = await self._get_connection()

        for event in events:
            await db.execute(
                """
                INSERT OR REPLACE INTO events
                (event_id, timestamp, type, name, attributes, span_id, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.type.value,
                    event.name,
                    json.dumps(event.attributes),
                    event.span_id,
                    event.trace_id,
                )
            )

        await db.commit()
        logger.debug(f"Wrote {len(events)} events to SQLite")

    async def write_metrics(self, metrics: List[Metric]) -> None:
        """Write metrics to SQLite.

        Args:
            metrics: List of Metric objects to store
        """
        db = await self._get_connection()

        for metric in metrics:
            await db.execute(
                """
                INSERT INTO metrics
                (timestamp, name, value, unit, attributes, aggregation)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.timestamp,
                    metric.name,
                    metric.value,
                    metric.unit,
                    json.dumps(metric.attributes),
                    metric.aggregation,
                )
            )

        await db.commit()
        logger.debug(f"Wrote {len(metrics)} metrics to SQLite")

    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Query traces from SQLite.

        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            status: Status filter
            limit: Maximum number of results

        Returns:
            List of Trace objects
        """
        db = await self._get_connection()

        query = "SELECT * FROM traces WHERE 1=1"
        params = []

        if start_time is not None:
            query += " AND start_time >= ?"
            params.append(start_time)

        if end_time is not None:
            query += " AND start_time <= ?"
            params.append(end_time)

        if status is not None:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        traces = []
        for row in rows:
            trace = Trace(
                trace_id=row[0],
                name=row[1],
                start_time=row[2],
                end_time=row[3],
                status=SpanStatus(row[5]),
                attributes=json.loads(row[6]) if row[6] else {},
                resource=json.loads(row[7]) if row[7] else {},
            )
            traces.append(trace)

        return traces

    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Query spans from SQLite.

        Args:
            trace_id: Filter by trace ID
            kind: Filter by span kind
            limit: Maximum number of results

        Returns:
            List of Span objects
        """
        db = await self._get_connection()

        query = "SELECT * FROM spans WHERE 1=1"
        params = []

        if trace_id is not None:
            query += " AND trace_id = ?"
            params.append(trace_id)

        if kind is not None:
            query += " AND kind = ?"
            params.append(kind.value)

        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        spans = []
        for row in rows:
            events_data = json.loads(row[10]) if row[10] else []
            events = [Event(**e) for e in events_data]

            span = Span(
                span_id=row[0],
                trace_id=row[1],
                parent_span_id=row[2],
                name=row[3],
                kind=SpanKind(row[4]),
                start_time=row[5],
                end_time=row[6],
                status=SpanStatus(row[8]),
                attributes=json.loads(row[9]) if row[9] else {},
                events=events,
                error=json.loads(row[11]) if row[11] else None,
            )
            spans.append(span)

        return spans

    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Query events from SQLite.

        Args:
            trace_id: Filter by trace ID
            type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of Event objects
        """
        db = await self._get_connection()

        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if trace_id is not None:
            query += " AND trace_id = ?"
            params.append(trace_id)

        if type is not None:
            query += " AND type = ?"
            params.append(type.value)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        events = []
        for row in rows:
            event = Event(
                event_id=row[0],
                timestamp=row[1],
                type=EventType(row[2]),
                name=row[3],
                attributes=json.loads(row[4]) if row[4] else {},
                span_id=row[5],
                trace_id=row[6],
            )
            events.append(event)

        return events

    async def close(self) -> None:
        """Close database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("Closed SQLite telemetry database connection")
