"""
In-memory telemetry backend for testing.

This backend stores telemetry data in memory, making it ideal for
unit tests and development environments where persistence is not needed.
"""

import asyncio
from typing import List, Optional

from spark.telemetry.backends.base import BaseTelemetryBackend
from spark.telemetry.types import Event, EventType, Metric, Span, SpanKind, SpanStatus, Trace


class MemoryBackend(BaseTelemetryBackend):
    """In-memory storage backend for telemetry data.

    All data is stored in Python lists and is lost when the process ends.
    Thread-safe for concurrent access.

    Usage:
        backend = MemoryBackend()
        await backend.write_spans([span1, span2])
        spans = await backend.query_spans(trace_id="abc123")
    """

    def __init__(self):
        """Initialize memory backend."""
        self._traces: List[Trace] = []
        self._spans: List[Span] = []
        self._events: List[Event] = []
        self._metrics: List[Metric] = []
        self._lock = asyncio.Lock()

    async def write_traces(self, traces: List[Trace]) -> None:
        """Write traces to memory.

        Args:
            traces: List of Trace objects to store
        """
        async with self._lock:
            self._traces.extend(traces)

    async def write_spans(self, spans: List[Span]) -> None:
        """Write spans to memory.

        Args:
            spans: List of Span objects to store
        """
        async with self._lock:
            self._spans.extend(spans)

    async def write_events(self, events: List[Event]) -> None:
        """Write events to memory.

        Args:
            events: List of Event objects to store
        """
        async with self._lock:
            self._events.extend(events)

    async def write_metrics(self, metrics: List[Metric]) -> None:
        """Write metrics to memory.

        Args:
            metrics: List of Metric objects to store
        """
        async with self._lock:
            self._metrics.extend(metrics)

    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Query traces from memory.

        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            status: Status filter
            limit: Maximum number of results

        Returns:
            List of Trace objects
        """
        async with self._lock:
            results = []
            for trace in self._traces:
                # Apply filters
                if start_time is not None and trace.start_time < start_time:
                    continue
                if end_time is not None and trace.start_time > end_time:
                    continue
                if status is not None and trace.status != status:
                    continue

                results.append(trace)

                if len(results) >= limit:
                    break

            return results

    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Query spans from memory.

        Args:
            trace_id: Filter by trace ID
            kind: Filter by span kind
            limit: Maximum number of results

        Returns:
            List of Span objects
        """
        async with self._lock:
            results = []
            for span in self._spans:
                # Apply filters
                if trace_id is not None and span.trace_id != trace_id:
                    continue
                if kind is not None and span.kind != kind:
                    continue

                results.append(span)

                if len(results) >= limit:
                    break

            return results

    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Query events from memory.

        Args:
            trace_id: Filter by trace ID
            type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of Event objects
        """
        async with self._lock:
            results = []
            for event in self._events:
                # Apply filters
                if trace_id is not None and event.trace_id != trace_id:
                    continue
                if type is not None and event.type != type:
                    continue

                results.append(event)

                if len(results) >= limit:
                    break

            return results

    async def clear(self) -> None:
        """Clear all data from memory (for testing)."""
        async with self._lock:
            self._traces.clear()
            self._spans.clear()
            self._events.clear()
            self._metrics.clear()

    async def close(self) -> None:
        """Close backend (no-op for memory backend)."""
        pass

    def get_stats(self) -> dict:
        """Get statistics about stored data.

        Returns:
            Dictionary with counts of stored items
        """
        return {
            'traces': len(self._traces),
            'spans': len(self._spans),
            'events': len(self._events),
            'metrics': len(self._metrics),
        }
