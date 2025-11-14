"""
PostgreSQL telemetry backend for production storage.

This backend stores telemetry data in a PostgreSQL database,
providing scalable, production-grade persistent storage for distributed deployments.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from spark.telemetry.backends.base import BaseTelemetryBackend
from spark.telemetry.types import Event, EventType, Metric, Span, SpanKind, SpanStatus, Trace

logger = logging.getLogger(__name__)

# Check for asyncpg availability
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not available, PostgreSQLBackend will not work. Install with: pip install asyncpg")


class PostgreSQLBackend(BaseTelemetryBackend):
    """PostgreSQL storage backend for telemetry data.

    Stores traces, spans, events, and metrics in a PostgreSQL database
    with appropriate indexes for efficient querying and JSONB support
    for flexible attribute storage.

    Usage:
        config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'spark_telemetry',
            'user': 'postgres',
            'password': 'password'
        }
        backend = PostgreSQLBackend(config)
        await backend.initialize()
        await backend.write_spans([span1, span2])

    Schema:
        - traces: trace_id, name, start_time, end_time, status, attributes (JSONB), resource (JSONB)
        - spans: span_id, trace_id, parent_span_id, name, kind, start_time, end_time, status, attributes (JSONB), events (JSONB), error (JSONB)
        - events: event_id, timestamp, type, name, attributes (JSONB), span_id, trace_id
        - metrics: metric_id, timestamp, name, value, unit, attributes (JSONB), aggregation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize PostgreSQL backend.

        Args:
            config: Configuration dict with connection parameters

        Raises:
            ImportError: If asyncpg is not installed
        """
        if not ASYNCPG_AVAILABLE:
            raise ImportError("asyncpg is required for PostgreSQLBackend. Install with: pip install asyncpg")

        self.host = config.get('host', 'localhost')
        self.port = config.get('port', 5432)
        self.database = config.get('database', 'spark_telemetry')
        self.user = config.get('user')
        self.password = config.get('password')
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=2,
                max_size=10,
            )
            await self._initialize_schema()
        return self._pool

    async def _initialize_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        if self._initialized:
            return

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # Traces table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    start_time DOUBLE PRECISION NOT NULL,
                    end_time DOUBLE PRECISION,
                    duration DOUBLE PRECISION,
                    status TEXT NOT NULL,
                    attributes JSONB,
                    resource JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_start_time ON traces(start_time)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_attributes ON traces USING GIN(attributes)")

            # Spans table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    start_time DOUBLE PRECISION NOT NULL,
                    end_time DOUBLE PRECISION,
                    duration DOUBLE PRECISION,
                    status TEXT NOT NULL,
                    attributes JSONB,
                    events JSONB,
                    error JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_kind ON spans(kind)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_start_time ON spans(start_time)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_attributes ON spans USING GIN(attributes)")

            # Events table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp DOUBLE PRECISION NOT NULL,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    attributes JSONB,
                    span_id TEXT,
                    trace_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (span_id) REFERENCES spans(span_id) ON DELETE CASCADE,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_attributes ON events USING GIN(attributes)")

            # Metrics table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    metric_id SERIAL PRIMARY KEY,
                    timestamp DOUBLE PRECISION NOT NULL,
                    name TEXT NOT NULL,
                    value DOUBLE PRECISION NOT NULL,
                    unit TEXT,
                    attributes JSONB,
                    aggregation TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_attributes ON metrics USING GIN(attributes)")

        self._initialized = True
        logger.info(f"Initialized PostgreSQL telemetry database: {self.database}")

    async def write_traces(self, traces: List[Trace]) -> None:
        """Write traces to PostgreSQL.

        Args:
            traces: List of Trace objects to store
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO traces
                (trace_id, name, start_time, end_time, duration, status, attributes, resource)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (trace_id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    duration = EXCLUDED.duration,
                    status = EXCLUDED.status
                """,
                [
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
                    for trace in traces
                ]
            )

        logger.debug(f"Wrote {len(traces)} traces to PostgreSQL")

    async def write_spans(self, spans: List[Span]) -> None:
        """Write spans to PostgreSQL.

        Args:
            spans: List of Span objects to store
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO spans
                (span_id, trace_id, parent_span_id, name, kind, start_time, end_time, duration,
                 status, attributes, events, error)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (span_id) DO UPDATE SET
                    end_time = EXCLUDED.end_time,
                    duration = EXCLUDED.duration,
                    status = EXCLUDED.status,
                    events = EXCLUDED.events,
                    error = EXCLUDED.error
                """,
                [
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
                    for span in spans
                ]
            )

        logger.debug(f"Wrote {len(spans)} spans to PostgreSQL")

    async def write_events(self, events: List[Event]) -> None:
        """Write events to PostgreSQL.

        Args:
            events: List of Event objects to store
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO events
                (event_id, timestamp, type, name, attributes, span_id, trace_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [
                    (
                        event.event_id,
                        event.timestamp,
                        event.type.value,
                        event.name,
                        json.dumps(event.attributes),
                        event.span_id,
                        event.trace_id,
                    )
                    for event in events
                ]
            )

        logger.debug(f"Wrote {len(events)} events to PostgreSQL")

    async def write_metrics(self, metrics: List[Metric]) -> None:
        """Write metrics to PostgreSQL.

        Args:
            metrics: List of Metric objects to store
        """
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO metrics
                (timestamp, name, value, unit, attributes, aggregation)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [
                    (
                        metric.timestamp,
                        metric.name,
                        metric.value,
                        metric.unit,
                        json.dumps(metric.attributes),
                        metric.aggregation,
                    )
                    for metric in metrics
                ]
            )

        logger.debug(f"Wrote {len(metrics)} metrics to PostgreSQL")

    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Query traces from PostgreSQL.

        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            status: Status filter
            limit: Maximum number of results

        Returns:
            List of Trace objects
        """
        pool = await self._get_pool()

        query = "SELECT * FROM traces WHERE 1=1"
        params = []
        param_idx = 1

        if start_time is not None:
            query += f" AND start_time >= ${param_idx}"
            params.append(start_time)
            param_idx += 1

        if end_time is not None:
            query += f" AND start_time <= ${param_idx}"
            params.append(end_time)
            param_idx += 1

        if status is not None:
            query += f" AND status = ${param_idx}"
            params.append(status.value)
            param_idx += 1

        query += f" ORDER BY start_time DESC LIMIT ${param_idx}"
        params.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        traces = []
        for row in rows:
            trace = Trace(
                trace_id=row['trace_id'],
                name=row['name'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                status=SpanStatus(row['status']),
                attributes=json.loads(row['attributes']) if row['attributes'] else {},
                resource=json.loads(row['resource']) if row['resource'] else {},
            )
            traces.append(trace)

        return traces

    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Query spans from PostgreSQL.

        Args:
            trace_id: Filter by trace ID
            kind: Filter by span kind
            limit: Maximum number of results

        Returns:
            List of Span objects
        """
        pool = await self._get_pool()

        query = "SELECT * FROM spans WHERE 1=1"
        params = []
        param_idx = 1

        if trace_id is not None:
            query += f" AND trace_id = ${param_idx}"
            params.append(trace_id)
            param_idx += 1

        if kind is not None:
            query += f" AND kind = ${param_idx}"
            params.append(kind.value)
            param_idx += 1

        query += f" ORDER BY start_time DESC LIMIT ${param_idx}"
        params.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        spans = []
        for row in rows:
            events_data = json.loads(row['events']) if row['events'] else []
            events = [Event(**e) for e in events_data]

            span = Span(
                span_id=row['span_id'],
                trace_id=row['trace_id'],
                parent_span_id=row['parent_span_id'],
                name=row['name'],
                kind=SpanKind(row['kind']),
                start_time=row['start_time'],
                end_time=row['end_time'],
                status=SpanStatus(row['status']),
                attributes=json.loads(row['attributes']) if row['attributes'] else {},
                events=events,
                error=json.loads(row['error']) if row['error'] else None,
            )
            spans.append(span)

        return spans

    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Query events from PostgreSQL.

        Args:
            trace_id: Filter by trace ID
            type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of Event objects
        """
        pool = await self._get_pool()

        query = "SELECT * FROM events WHERE 1=1"
        params = []
        param_idx = 1

        if trace_id is not None:
            query += f" AND trace_id = ${param_idx}"
            params.append(trace_id)
            param_idx += 1

        if type is not None:
            query += f" AND type = ${param_idx}"
            params.append(type.value)
            param_idx += 1

        query += f" ORDER BY timestamp DESC LIMIT ${param_idx}"
        params.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        events = []
        for row in rows:
            event = Event(
                event_id=row['event_id'],
                timestamp=row['timestamp'],
                type=EventType(row['type']),
                name=row['name'],
                attributes=json.loads(row['attributes']) if row['attributes'] else {},
                span_id=row['span_id'],
                trace_id=row['trace_id'],
            )
            events.append(event)

        return events

    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Closed PostgreSQL telemetry database connection pool")
