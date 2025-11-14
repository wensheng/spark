"""Unit tests for RSI PerformanceAnalyzerNode."""

import pytest
import pytest_asyncio
import asyncio
from spark.rsi.performance_analyzer import PerformanceAnalyzerNode
from spark.telemetry import TelemetryManager, TelemetryConfig, SpanStatus
from spark.nodes.types import NodeMessage, ExecutionContext
from spark.graphs import Graph
from spark.nodes import Node


@pytest_asyncio.fixture
async def telemetry_manager():
    """Create telemetry manager for testing."""
    TelemetryManager.reset_instance()
    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)
    yield manager
    await manager.shutdown()
    TelemetryManager.reset_instance()


@pytest_asyncio.fixture
async def sample_telemetry_data(telemetry_manager):
    """Generate sample telemetry data with known performance characteristics."""

    # Create 20 sample traces with varying performance
    for i in range(20):
        trace = telemetry_manager.start_trace(
            name="test_graph",
            attributes={'graph.id': 'test_graph'}
        )

        # Node A: Fast, reliable
        async with telemetry_manager.start_span(
            "node_a",
            trace.trace_id,
            attributes={'node.id': 'node_a', 'node.name': 'NodeA'}
        ) as span:
            await asyncio.sleep(0.01)  # 10ms

        # Node B: Slow (bottleneck)
        async with telemetry_manager.start_span(
            "node_b",
            trace.trace_id,
            attributes={'node.id': 'node_b', 'node.name': 'NodeB'}
        ) as span:
            await asyncio.sleep(0.2)  # 200ms - intentionally slow (much slower than other nodes)

        # Node C: Fails 20% of the time
        try:
            async with telemetry_manager.start_span(
                "node_c",
                trace.trace_id,
                attributes={'node.id': 'node_c', 'node.name': 'NodeC'}
            ) as span:
                if i % 5 == 0:  # Fail every 5th execution (20%)
                    raise ValueError("Simulated error")
                await asyncio.sleep(0.01)
        except ValueError:
            # Record the event for failed node
            from spark.telemetry import EventType
            telemetry_manager.record_event(
                type=EventType.NODE_FAILED,
                name='node_failed',
                trace_id=trace.trace_id,
                attributes={
                    'node.id': 'node_c',
                    'node.name': 'NodeC',
                    'error.type': 'ValueError',
                    'error.message': 'Simulated error'
                }
            )

        # End trace
        status = SpanStatus.ERROR if i % 5 == 0 else SpanStatus.OK
        telemetry_manager.end_trace(trace.trace_id, status)

    # Flush to ensure data is available
    await telemetry_manager.flush()
    await asyncio.sleep(0.1)  # Allow async operations to complete

    return telemetry_manager


@pytest.mark.asyncio
async def test_performance_analyzer_initialization():
    """Test PerformanceAnalyzerNode initialization."""
    node = PerformanceAnalyzerNode(
        analysis_window_hours=24,
        min_executions=10
    )

    assert node.name == "PerformanceAnalyzer"
    assert node.analysis_window_hours == 24
    assert node.min_executions == 10


@pytest.mark.asyncio
async def test_performance_analyzer_insufficient_data(telemetry_manager):
    """Test analyzer with insufficient data."""
    node = PerformanceAnalyzerNode(min_executions=100)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    assert result['has_issues'] is False
    assert 'Insufficient data' in result['reason']
    assert result['report'] is None


@pytest.mark.asyncio
async def test_performance_analyzer_missing_graph_id(telemetry_manager):
    """Test analyzer without graph_id."""
    node = PerformanceAnalyzerNode()

    context = ExecutionContext(
        inputs=NodeMessage(content={})  # Missing graph_id
    )

    await node.on_start(context)
    result = await node.process(context)

    assert result['has_issues'] is False
    assert 'graph_id is required' in result['reason']
    assert result['report'] is None


@pytest.mark.asyncio
async def test_performance_analyzer_with_data(sample_telemetry_data):
    """Test analyzer with sample data."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    assert 'report' in result
    report = result['report']

    # Check report structure
    assert report.graph_id == 'test_graph'
    assert report.summary is not None
    assert report.node_metrics is not None
    assert report.bottlenecks is not None
    assert report.failures is not None
    assert report.opportunities is not None

    # Check summary metrics
    summary = report.summary
    assert summary.total_executions == 20
    assert 0 < summary.success_rate <= 1.0
    assert summary.avg_duration > 0

    # Check node metrics
    assert 'node_b' in report.node_metrics  # Slow node should be tracked
    assert 'node_c' in report.node_metrics  # Failing node should be tracked

    # Check bottlenecks identified
    assert len(report.bottlenecks) > 0

    # Check opportunities generated
    assert len(report.opportunities) > 0


@pytest.mark.asyncio
async def test_performance_analyzer_identifies_high_latency(sample_telemetry_data):
    """Test that analyzer identifies high latency bottlenecks."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    bottlenecks = result['report'].bottlenecks

    # Should identify NodeB as high latency (100ms vs 10ms average)
    high_latency_bottlenecks = [
        b for b in bottlenecks
        if b.issue == 'high_latency' and b.node_id == 'node_b'
    ]

    assert len(high_latency_bottlenecks) > 0
    bottleneck = high_latency_bottlenecks[0]
    assert bottleneck.severity in ['medium', 'high']
    assert bottleneck.impact_score > 2.0  # Should be significantly higher than average


@pytest.mark.asyncio
async def test_performance_analyzer_identifies_high_error_rate(sample_telemetry_data):
    """Test that analyzer identifies high error rate issues."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    bottlenecks = result['report'].bottlenecks

    # Should identify NodeC as high error rate (20% failure rate)
    high_error_bottlenecks = [
        b for b in bottlenecks
        if b.issue == 'high_error_rate' and b.node_id == 'node_c'
    ]

    assert len(high_error_bottlenecks) > 0
    bottleneck = high_error_bottlenecks[0]
    assert bottleneck.severity in ['high', 'critical']
    assert bottleneck.metrics['error_rate'] > 0.05  # Above 5% threshold


@pytest.mark.asyncio
async def test_performance_analyzer_has_issues_flag(sample_telemetry_data):
    """Test has_issues flag is set correctly."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    # Should have issues due to bottlenecks
    assert result['has_issues'] is True

    # Summary should be provided
    assert 'summary' in result
    assert result['summary']['bottlenecks_count'] > 0


@pytest.mark.asyncio
async def test_performance_analyzer_node_metrics(sample_telemetry_data):
    """Test that node metrics are calculated correctly."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    node_metrics = result['report'].node_metrics

    # Check NodeA (fast and reliable)
    if 'node_a' in node_metrics:
        node_a = node_metrics['node_a']
        assert node_a.executions == 20
        assert node_a.success_rate > 0.95  # Should be very reliable
        assert node_a.avg_duration < 0.05  # Should be fast

    # Check NodeB (slow)
    if 'node_b' in node_metrics:
        node_b = node_metrics['node_b']
        assert node_b.executions == 20
        assert node_b.avg_duration > 0.05  # Should be slow

    # Check NodeC (fails sometimes)
    if 'node_c' in node_metrics:
        node_c = node_metrics['node_c']
        assert node_c.executions == 20
        assert node_c.error_rate > 0  # Should have some errors


@pytest.mark.asyncio
async def test_performance_analyzer_percentile_calculation():
    """Test percentile calculation utility."""
    node = PerformanceAnalyzerNode()

    # Test with known data
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

    p50 = node._percentile(data, 0.50)
    p95 = node._percentile(data, 0.95)
    p99 = node._percentile(data, 0.99)

    assert 4.0 <= p50 <= 6.0  # Median should be around 5
    assert p95 >= 9.0  # 95th percentile should be high
    assert p99 >= 9.5  # 99th percentile should be even higher

    # Test with empty data
    assert node._percentile([], 0.95) == 0.0

    # Test with single value
    assert node._percentile([5.0], 0.95) == 5.0


@pytest.mark.asyncio
async def test_performance_analyzer_custom_time_window(sample_telemetry_data):
    """Test analyzer with custom time window."""
    node = PerformanceAnalyzerNode(min_executions=5)

    # Use explicit time range
    import time
    end_time = time.time()
    start_time = end_time - 3600  # 1 hour ago

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'graph_id': 'test_graph',
            'start_time': start_time,
            'end_time': end_time
        })
    )

    await node.on_start(context)
    result = await node.process(context)

    # Should still analyze the data within time window
    assert result['report'] is not None
    assert result['report'].summary.total_executions > 0


@pytest.mark.asyncio
async def test_performance_analyzer_opportunities_generation(sample_telemetry_data):
    """Test that opportunities are generated from bottlenecks."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    await node.on_start(context)
    result = await node.process(context)

    opportunities = result['report'].opportunities

    # Should generate opportunities
    assert len(opportunities) > 0

    # Opportunities should mention node names and issues
    opp_text = ' '.join(opportunities)
    assert 'NodeB' in opp_text or 'NodeC' in opp_text
    assert 'latency' in opp_text.lower() or 'error' in opp_text.lower()


@pytest.mark.asyncio
async def test_performance_analyzer_with_version(sample_telemetry_data):
    """Test analyzer with graph version specified."""
    node = PerformanceAnalyzerNode(min_executions=10)

    context = ExecutionContext(
        inputs=NodeMessage(content={
            'graph_id': 'test_graph',
            'graph_version': '1.2.3'
        })
    )

    await node.on_start(context)
    result = await node.process(context)

    assert result['report'].graph_version == '1.2.3'


@pytest.mark.asyncio
async def test_performance_analyzer_no_telemetry():
    """Test analyzer behavior when telemetry is not available."""
    # Create node without telemetry initialized
    node = PerformanceAnalyzerNode()
    node.telemetry_manager = None  # Simulate no telemetry

    context = ExecutionContext(
        inputs=NodeMessage(content={'graph_id': 'test_graph'})
    )

    result = await node.process(context)

    assert result['has_issues'] is False
    assert 'Telemetry system not available' in result['reason']
    assert result['report'] is None
