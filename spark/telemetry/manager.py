"""
Central telemetry manager for Spark.

TelemetryManager is the main entry point for telemetry operations,
coordinating trace/span lifecycle, event collection, and backend storage.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from spark.telemetry.types import (
    Event,
    EventType,
    Metric,
    Span,
    SpanKind,
    SpanStatus,
    TelemetryContext,
    Trace,
)
from spark.telemetry.config import TelemetryConfig

logger = logging.getLogger(__name__)


class TelemetryManager:
    """Central coordinator for telemetry collection and storage.

    TelemetryManager manages the lifecycle of traces and spans, buffers
    telemetry data, and coordinates with storage backends.

    Usage:
        # Get singleton instance
        manager = TelemetryManager.get_instance(config)

        # Start a trace
        trace = manager.start_trace("graph_run")

        # Create spans
        async with manager.start_span("node_execution", trace.trace_id) as span:
            # Do work
            span.set_attribute("node_id", "abc123")

        # End trace
        manager.end_trace(trace.trace_id)

        # Query telemetry
        traces = await manager.query_traces()
    """

    _instance: Optional['TelemetryManager'] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[TelemetryConfig] = None):
        """Initialize TelemetryManager.

        Args:
            config: Telemetry configuration (default: disabled)
        """
        self.config = config or TelemetryConfig()
        self._backend: Optional[Any] = None
        self._traces: Dict[str, Trace] = {}
        self._spans: Dict[str, Span] = {}
        self._trace_buffer: List[Trace] = []
        self._event_buffer: List[Event] = []
        self._metric_buffer: List[Metric] = []
        self._span_buffer: List[Span] = []
        self._buffer_lock = asyncio.Lock()
        self._export_task: Optional[asyncio.Task] = None
        self._shutdown = False

        # Initialize backend if enabled
        if self.config.enabled:
            self._initialize_backend()

    @classmethod
    def get_instance(cls, config: Optional[TelemetryConfig] = None) -> 'TelemetryManager':
        """Get singleton instance of TelemetryManager.

        Args:
            config: Configuration to use if creating new instance

        Returns:
            TelemetryManager instance
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
            elif config is not None:
                logger.warning("TelemetryManager already initialized, ignoring new config")
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                # Clean up existing instance
                if cls._instance._export_task:
                    cls._instance._export_task.cancel()
            cls._instance = None

    def _initialize_backend(self) -> None:
        """Initialize storage backend based on configuration."""
        if self.config.backend == 'noop':
            from spark.telemetry.backends.base import NoOpBackend
            self._backend = NoOpBackend()
        elif self.config.backend == 'memory':
            from spark.telemetry.backends.memory import MemoryBackend
            self._backend = MemoryBackend()
        elif self.config.backend == 'sqlite':
            from spark.telemetry.backends.sqlite import SQLiteBackend
            self._backend = SQLiteBackend(self.config.backend_config)
        elif self.config.backend == 'postgresql':
            from spark.telemetry.backends.postgresql import PostgreSQLBackend
            self._backend = PostgreSQLBackend(self.config.backend_config)
        elif self.config.backend == 'otlp_http':
            from spark.telemetry.backends.otlp import OtlpHttpBackend
            self._backend = OtlpHttpBackend(self.config.backend_config)
        else:
            raise ValueError(f"Unknown backend: {self.config.backend}")

        logger.info(f"Initialized telemetry backend: {self.config.backend}")

    async def start_background_export(self) -> None:
        """Start background task for periodic export."""
        if not self.config.enabled or self._export_task is not None:
            return

        self._export_task = asyncio.create_task(self._export_loop())
        logger.info(f"Started telemetry export task (interval: {self.config.export_interval}s)")

    async def _export_loop(self) -> None:
        """Background task for periodic export."""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.export_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry export loop: {e}", exc_info=True)

    async def flush(self) -> None:
        """Flush buffered telemetry data to backend."""
        if not self.config.enabled or self._backend is None:
            return

        async with self._buffer_lock:
            await self._flush_internal()

    async def _flush_internal(self) -> None:
        """Internal flush implementation without lock acquisition.

        This method assumes the lock is already held by the caller.
        """
        if not self._trace_buffer and not self._span_buffer and not self._event_buffer and not self._metric_buffer:
            return

        # Export traces
        if self._trace_buffer:
            try:
                await self._backend.write_traces(self._trace_buffer)
                logger.debug(f"Flushed {len(self._trace_buffer)} traces")
                self._trace_buffer.clear()
            except Exception as e:
                logger.error(f"Error flushing traces: {e}", exc_info=True)

        # Export spans
        if self._span_buffer:
            try:
                await self._backend.write_spans(self._span_buffer)
                logger.debug(f"Flushed {len(self._span_buffer)} spans")
                self._span_buffer.clear()
            except Exception as e:
                logger.error(f"Error flushing spans: {e}", exc_info=True)

        # Export events
        if self._event_buffer:
            try:
                await self._backend.write_events(self._event_buffer)
                logger.debug(f"Flushed {len(self._event_buffer)} events")
                self._event_buffer.clear()
            except Exception as e:
                logger.error(f"Error flushing events: {e}", exc_info=True)

        # Export metrics
        if self._metric_buffer:
            try:
                await self._backend.write_metrics(self._metric_buffer)
                logger.debug(f"Flushed {len(self._metric_buffer)} metrics")
                self._metric_buffer.clear()
            except Exception as e:
                logger.error(f"Error flushing metrics: {e}", exc_info=True)

    def start_trace(
        self,
        name: str,
        trace_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Trace:
        """Start a new trace.

        Args:
            name: Trace name (e.g., "graph_run")
            trace_id: Optional trace ID (generated if not provided)
            attributes: Optional attributes

        Returns:
            New Trace object
        """
        if not self.config.enabled:
            return Trace(name=name)

        # Check sampling
        trace_id = trace_id or uuid4().hex
        if not self.config.should_sample(trace_id):
            logger.debug(f"Trace {trace_id} not sampled")
            return Trace(trace_id=trace_id, name=name)

        trace = Trace(
            trace_id=trace_id,
            name=name,
            attributes=attributes or {},
            resource=dict(self.config.resource_attributes),
        )

        # Add custom attributes
        trace.attributes.update(self.config.custom_attributes)

        self._traces[trace_id] = trace
        logger.debug(f"Started trace: {trace_id} ({name})")

        return trace

    def end_trace(
        self,
        trace_id: str,
        status: SpanStatus = SpanStatus.OK
    ) -> Optional[Trace]:
        """End a trace.

        Args:
            trace_id: Trace ID to end
            status: Final trace status

        Returns:
            Ended Trace object, or None if not found
        """
        if not self.config.enabled:
            return None

        trace = self._traces.get(trace_id)
        if trace is None:
            logger.warning(f"Trace not found: {trace_id}")
            return None

        trace.end(status)
        logger.debug(f"Ended trace: {trace_id} (duration: {trace.duration:.3f}s)")

        # Add trace to buffer
        if self._backend:
            self._trace_buffer.append(trace)

        return trace

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Get a trace by ID.

        Args:
            trace_id: Trace ID

        Returns:
            Trace object, or None if not found
        """
        return self._traces.get(trace_id)

    @asynccontextmanager
    async def start_span(
        self,
        name: str,
        trace_id: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Span, None]:
        """Start a span as an async context manager.

        Args:
            name: Span name
            trace_id: Associated trace ID
            kind: Span kind
            parent_span_id: Parent span ID (for hierarchical spans)
            attributes: Optional attributes

        Yields:
            Span object

        Usage:
            async with manager.start_span("process", trace_id) as span:
                span.set_attribute("node_id", "123")
                # Do work
        """
        span = Span(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            kind=kind,
            attributes=attributes or {},
        )

        if self.config.enabled:
            self._spans[span.span_id] = span
            logger.debug(f"Started span: {span.span_id} ({name})")

        try:
            yield span
        except Exception as e:
            span.end(status=SpanStatus.ERROR, error=e)
            raise
        else:
            span.end(status=SpanStatus.OK)
        finally:
            if self.config.enabled:
                await self._buffer_span(span)

    async def _buffer_span(self, span: Span) -> None:
        """Add span to buffer for export.

        Args:
            span: Span to buffer
        """
        async with self._buffer_lock:
            self._span_buffer.append(span)

            # Flush if buffer is full (use internal flush since we already hold the lock)
            if len(self._span_buffer) >= self.config.buffer_size:
                logger.debug("Span buffer full, flushing...")
                await self._flush_internal()

    def record_event(
        self,
        type: EventType,
        name: str,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Event:
        """Record a telemetry event.

        Args:
            type: Event type
            name: Event name
            trace_id: Associated trace ID
            span_id: Associated span ID
            attributes: Optional attributes

        Returns:
            Event object
        """
        event = Event(
            type=type,
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            attributes=attributes or {},
        )

        if self.config.enabled and self.config.enable_events:
            # Add directly to buffer (synchronous)
            self._event_buffer.append(event)
            logger.debug(f"Recorded event: {type.value} ({name})")

        return event

    async def _buffer_event(self, event: Event) -> None:
        """Add event to buffer for export.

        Args:
            event: Event to buffer
        """
        async with self._buffer_lock:
            self._event_buffer.append(event)

            # Flush if buffer is full (use internal flush since we already hold the lock)
            if len(self._event_buffer) >= self.config.buffer_size:
                logger.debug("Event buffer full, flushing...")
                await self._flush_internal()

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        attributes: Optional[Dict[str, Any]] = None,
        aggregation: str = "gauge"
    ) -> Metric:
        """Record a metric.

        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            attributes: Optional attributes (dimensions)
            aggregation: Aggregation type

        Returns:
            Metric object
        """
        metric = Metric(
            name=name,
            value=value,
            unit=unit,
            attributes=attributes or {},
            aggregation=aggregation,
        )

        if self.config.enabled and self.config.enable_metrics:
            # Add directly to buffer (synchronous)
            self._metric_buffer.append(metric)
            logger.debug(f"Recorded metric: {name} = {value} {unit}")

        return metric

    async def _buffer_metric(self, metric: Metric) -> None:
        """Add metric to buffer for export.

        Args:
            metric: Metric to buffer
        """
        async with self._buffer_lock:
            self._metric_buffer.append(metric)

            # Flush if buffer is full (use internal flush since we already hold the lock)
            if len(self._metric_buffer) >= self.config.buffer_size:
                logger.debug("Metric buffer full, flushing...")
                await self._flush_internal()

    def create_context(self, trace_id: str, span_id: Optional[str] = None) -> TelemetryContext:
        """Create a telemetry context.

        Args:
            trace_id: Trace ID
            span_id: Optional span ID

        Returns:
            TelemetryContext object
        """
        return TelemetryContext(trace_id=trace_id, span_id=span_id)

    async def shutdown(self) -> None:
        """Shutdown telemetry manager and flush remaining data."""
        logger.info("Shutting down telemetry manager...")
        self._shutdown = True

        # Cancel export task
        if self._export_task:
            self._export_task.cancel()
            try:
                await self._export_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self.flush()

        # Close backend
        if self._backend:
            await self._backend.close()

        logger.info("Telemetry manager shutdown complete")

    # Query API (delegated to backend)

    async def query_traces(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        status: Optional[SpanStatus] = None,
        limit: int = 100
    ) -> List[Trace]:
        """Query traces from backend.

        Args:
            start_time: Start timestamp filter
            end_time: End timestamp filter
            status: Status filter
            limit: Maximum number of results

        Returns:
            List of Trace objects
        """
        if not self.config.enabled or self._backend is None:
            return []

        return await self._backend.query_traces(
            start_time=start_time,
            end_time=end_time,
            status=status,
            limit=limit
        )

    async def query_spans(
        self,
        trace_id: Optional[str] = None,
        kind: Optional[SpanKind] = None,
        limit: int = 1000
    ) -> List[Span]:
        """Query spans from backend.

        Args:
            trace_id: Filter by trace ID
            kind: Filter by span kind
            limit: Maximum number of results

        Returns:
            List of Span objects
        """
        if not self.config.enabled or self._backend is None:
            return []

        return await self._backend.query_spans(
            trace_id=trace_id,
            kind=kind,
            limit=limit
        )

    async def query_events(
        self,
        trace_id: Optional[str] = None,
        type: Optional[EventType] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Query events from backend.

        Args:
            trace_id: Filter by trace ID
            type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of Event objects
        """
        if not self.config.enabled or self._backend is None:
            return []

        return await self._backend.query_events(
            trace_id=trace_id,
            type=type,
            limit=limit
        )
