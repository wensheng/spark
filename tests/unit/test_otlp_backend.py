"""Tests for OTLP HTTP telemetry backend."""

import pytest

from spark.telemetry.backends.otlp import OtlpHttpBackend
from spark.telemetry.types import Span, SpanKind, SpanStatus, Event, EventType


@pytest.mark.asyncio
async def test_otlp_backend_sends_spans():
    payloads = []

    async def sender(endpoint, payload):
        payloads.append((endpoint, payload))

    backend = OtlpHttpBackend({'endpoint': 'https://collector/v1/traces', 'sender': sender})
    span = Span(
        span_id='span1',
        trace_id='trace1',
        parent_span_id=None,
        name='node',
        kind=SpanKind.NODE_EXECUTION,
        start_time=1.0,
        end_time=2.0,
        status=SpanStatus.OK,
        attributes={'node.id': '123'},
    )
    await backend.write_spans([span])
    assert payloads
    endpoint, payload = payloads[0]
    assert endpoint.endswith('/v1/traces')
    assert payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['name'] == 'node'


@pytest.mark.asyncio
async def test_otlp_backend_sends_events():
    payloads = []

    async def sender(endpoint, payload):
        payloads.append((endpoint, payload))

    backend = OtlpHttpBackend(
        {'endpoint': 'https://collector/v1/traces', 'logs_endpoint': 'https://collector/v1/logs', 'sender': sender}
    )
    event = Event(
        trace_id='trace1',
        span_id='span1',
        name='Node started',
        type=EventType.NODE_STARTED,
        timestamp=1.0,
        attributes={'node.id': '123'},
    )
    await backend.write_events([event])
    assert len(payloads) == 1
    endpoint, payload = payloads[0]
    assert endpoint.endswith('/v1/logs')
    log = payload['resourceLogs'][0]['scopeLogs'][0]['logRecords'][0]
    assert log['attributes'][0]['key'] == 'event.type'
