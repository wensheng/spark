"""OTLP HTTP backend for telemetry export."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Iterable

from spark.telemetry.backends.base import BaseTelemetryBackend
from spark.telemetry.types import Event, EventType, Span, SpanKind, SpanStatus

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None  # type: ignore


Sender = Callable[[str, dict], Awaitable[None] | None]


class OtlpHttpBackend(BaseTelemetryBackend):
    """Minimal OTLP exporter using HTTP JSON payloads."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._endpoint: str | None = config.get('endpoint')
        self._logs_endpoint: str | None = config.get('logs_endpoint', None)
        if not self._logs_endpoint and self._endpoint:
            self._logs_endpoint = self._endpoint.replace('/v1/traces', '/v1/logs')
        self._headers: dict[str, str] = config.get('headers', {})
        self._resource_attributes: dict[str, Any] = config.get(
            'resource_attributes', {'service.name': 'spark'}
        )
        self._timeout: float = float(config.get('timeout', 5.0))
        self._sender: Sender | None = config.get('sender')
        if self._sender is None and self._endpoint is None:
            raise ValueError("OTLP backend requires 'endpoint' or custom 'sender'.")

    async def write_spans(self, spans: list[Span]) -> None:
        if not spans or (self._endpoint is None and self._sender is None):
            return
        payload = {
            'resourceSpans': [
                {
                    'resource': {'attributes': _encode_attributes(self._resource_attributes)},
                    'scopeSpans': [
                        {
                            'scope': {'name': 'spark.runtime'},
                            'spans': [_span_to_otlp(span) for span in spans],
                        }
                    ],
                }
            ]
        }
        await self._post(self._endpoint, payload)

    async def write_traces(self, traces: list[Any]) -> None:  # pragma: no cover - not used
        return None

    async def write_events(self, events: list[Event]) -> None:
        if not events or (self._logs_endpoint is None and self._sender is None):
            return
        payload = {
            'resourceLogs': [
                {
                    'resource': {'attributes': _encode_attributes(self._resource_attributes)},
                    'scopeLogs': [
                        {
                            'scope': {'name': 'spark.events'},
                            'logRecords': [_event_to_otlp(event) for event in events],
                        }
                    ],
                }
            ]
        }
        endpoint = self._logs_endpoint or (self._endpoint and self._endpoint.replace('/v1/traces', '/v1/logs'))
        if endpoint:
            await self._post(endpoint, payload)

    async def write_metrics(self, metrics: list[Any]) -> None:  # pragma: no cover - not used
        return None

    async def query_traces(self, *args: Any, **kwargs: Any) -> list[Any]:  # pragma: no cover - exporter only
        return []

    async def query_spans(self, *args: Any, **kwargs: Any) -> list[Any]:  # pragma: no cover
        return []

    async def query_events(self, *args: Any, **kwargs: Any) -> list[Any]:  # pragma: no cover
        return []

    async def clear(self) -> None:  # pragma: no cover
        return None

    async def close(self) -> None:  # pragma: no cover
        return None

    async def _post(self, endpoint: str | None, payload: dict[str, Any]) -> None:
        if not endpoint:
            return
        if self._sender is not None:
            result = self._sender(endpoint, payload)
            if asyncio.iscoroutine(result):
                await result
            return
        if httpx is None:
            raise RuntimeError("httpx is required for OTLP HTTP backend")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            await client.post(endpoint, json=payload, headers=self._headers)


def _span_to_otlp(span: Span) -> dict[str, Any]:
    return {
        'traceId': span.trace_id,
        'spanId': span.span_id,
        'parentSpanId': span.parent_span_id,
        'name': span.name,
        'kind': _map_span_kind(span.kind),
        'startTimeUnixNano': _to_nanos(span.start_time),
        'endTimeUnixNano': _to_nanos(span.end_time),
        'status': {'code': _map_status(span.status), 'message': span.error or ''},
        'attributes': _encode_attributes(span.attributes),
    }


def _event_to_otlp(event: Event) -> dict[str, Any]:
    return {
        'timeUnixNano': _to_nanos(event.timestamp),
        'body': {'stringValue': event.name},
        'attributes': _encode_attributes(
            {'event.type': event.type.value if isinstance(event.type, EventType) else str(event.type), **(event.attributes or {})}
        ),
    }


def _encode_attributes(attributes: dict[str, Any] | None) -> list[dict[str, Any]]:
    encoded = []
    for key, value in (attributes or {}).items():
        encoded.append({'key': str(key), 'value': {'stringValue': _to_string(value)}})
    return encoded


def _to_string(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return repr(value)


def _to_nanos(timestamp: float | None) -> int:
    if timestamp is None:
        timestamp = time.time()
    return int(timestamp * 1_000_000_000)


def _map_span_kind(kind: SpanKind | None) -> int:
    mapping = {
        SpanKind.INTERNAL: 1,
        SpanKind.GRAPH_RUN: 1,
        SpanKind.NODE_EXECUTION: 1,
        SpanKind.EDGE_TRANSITION: 1,
        SpanKind.STATE_CHANGE: 1,
        SpanKind.TOOL_CALL: 3,
        SpanKind.LLM_CALL: 3,
    }
    return mapping.get(kind, 1)


def _map_status(status: SpanStatus | None) -> int:
    mapping = {
        SpanStatus.UNSET: 0,
        SpanStatus.OK: 1,
        SpanStatus.ERROR: 2,
    }
    return mapping.get(status, 0)
