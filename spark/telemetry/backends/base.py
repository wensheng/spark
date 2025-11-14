"""
Base backend interface for telemetry storage.

This module defines the abstract interface that all telemetry backends
must implement for storing and querying telemetry data.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from spark.telemetry.types import Event, EventType, Metric, Span, SpanKind, SpanStatus, Trace


class BaseTelemetryBackend(ABC):
    """Abstract base class for telemetry storage backends.

    All backends must implement these methods for storing and querying
    traces, spans, events, and metrics.
    """

    @abstractmethod
    async def write_traces(self, traces: List[Trace]) -> None:
        """Write traces to storage.

        Args:
            traces: List of Trace objects to store
        """
        pass

    @abstractmethod
    async def write_spans(self, spans: List[Span]) -> None:
        """Write spans to storage.

        Args:
            spans: List of Span objects to store
        """
        pass

    @abstractmethod
    async def write_events(self, events: List[Event]) -> None:
        """Write events to storage.

        Args:
            events: List of Event objects to store
        """
        pass

    @abstractmethod
    async def write_metrics(self, metrics: List[Metric]) -> None:
        """Write metrics to storage.

        Args:
            metrics: List of Metric objects to store
        """
        pass

    @abstractmethod
    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Query traces from storage.

        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            status: Status filter
            limit: Maximum number of results

        Returns:
            List of Trace objects
        """
        pass

    @abstractmethod
    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Query spans from storage.

        Args:
            trace_id: Filter by trace ID
            kind: Filter by span kind
            limit: Maximum number of results

        Returns:
            List of Span objects
        """
        pass

    @abstractmethod
    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Query events from storage.

        Args:
            trace_id: Filter by trace ID
            type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of Event objects
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close backend connections and cleanup resources."""
        pass


class NoOpBackend(BaseTelemetryBackend):
    """No-operation backend that discards all telemetry data.

    Used when telemetry is disabled.
    """

    async def write_traces(self, traces: List[Trace]) -> None:
        """No-op write."""
        pass

    async def write_spans(self, spans: List[Span]) -> None:
        """No-op write."""
        pass

    async def write_events(self, events: List[Event]) -> None:
        """No-op write."""
        pass

    async def write_metrics(self, metrics: List[Metric]) -> None:
        """No-op write."""
        pass

    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Return empty list."""
        return []

    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Return empty list."""
        return []

    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Return empty list."""
        return []

    async def close(self) -> None:
        """No-op close."""
        pass
