"""
Example: Comprehensive Telemetry for Spark Graphs

This example demonstrates the telemetry system for observability:
- Automatic tracing of graph execution
- Span tracking for node operations
- Event collection for graph and node lifecycle
- Metrics recording
- SQLite storage for persistence
- Query API for telemetry analysis

Requirements:
    pip install aiosqlite  # For SQLite backend
"""

import asyncio
import os
from pathlib import Path

from spark.nodes import Node
from spark.graphs import Graph
from spark.telemetry import TelemetryConfig, TelemetryManager, EventType, SpanKind

# Check for optional dependencies
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False


# Define some example nodes

class DataFetchNode(Node):
    """Simulates fetching data from a source."""

    async def process(self, context):
        print("[DataFetch] Fetching data...")
        await asyncio.sleep(0.1)  # Simulate API call
        return {
            'data': ['item1', 'item2', 'item3'],
            'fetch_status': 'success'
        }


class TransformNode(Node):
    """Transforms the data."""

    async def process(self, context):
        print("[Transform] Transforming data...")
        data = context.inputs.content.get('data', [])
        await asyncio.sleep(0.05)  # Simulate processing

        transformed = [item.upper() for item in data]

        return {
            'transformed_data': transformed,
            'transform_status': 'success',
            'items_processed': len(transformed)
        }


class ValidationNode(Node):
    """Validates the transformed data."""

    async def process(self, context):
        print("[Validation] Validating data...")
        data = context.inputs.content.get('transformed_data', [])

        # Validation logic
        is_valid = all(isinstance(item, str) for item in data)

        return {
            'validated_data': data,
            'validation_status': 'passed' if is_valid else 'failed',
            'is_valid': is_valid
        }


class SaveNode(Node):
    """Saves the final result."""

    async def process(self, context):
        print("[Save] Saving data...")
        data = context.inputs.content.get('validated_data', [])
        await asyncio.sleep(0.1)  # Simulate database write

        return {
            'save_status': 'success',
            'items_saved': len(data),
            'result': 'Data processing complete'
        }


async def example_basic_telemetry():
    """Basic telemetry with in-memory storage."""
    print("\n" + "="*60)
    print("Example 1: Basic Telemetry (In-Memory)")
    print("="*60 + "\n")

    # Reset manager for clean state
    TelemetryManager.reset_instance()

    # Create telemetry configuration (in-memory for quick testing)
    config = TelemetryConfig.create_memory(
        sampling_rate=1.0,  # Sample 100% of traces
        enable_metrics=True,
        enable_events=True,
    )

    # Build graph
    fetch = DataFetchNode(name="DataFetch")
    transform = TransformNode(name="Transform")
    validate = ValidationNode(name="Validate")
    save = SaveNode(name="Save")

    fetch >> transform >> validate >> save

    # Create graph with telemetry
    graph = Graph(start=fetch, telemetry_config=config)

    # Run graph
    result = await graph.run()
    print(f"\nGraph result: {result.content}\n")

    # Get telemetry manager
    manager = TelemetryManager.get_instance()

    # Flush to ensure data is written
    await manager.flush()

    # Query traces
    traces = await manager.query_traces()
    print(f"Total traces: {len(traces)}")

    for trace in traces:
        print(f"\nTrace: {trace.name}")
        print(f"  ID: {trace.trace_id}")
        print(f"  Duration: {trace.duration:.3f}s")
        print(f"  Status: {trace.status.value}")

        # Query spans for this trace
        spans = await manager.query_spans(trace_id=trace.trace_id)
        print(f"  Spans: {len(spans)}")
        for span in spans[:5]:  # Show first 5
            print(f"    - {span.name} ({span.kind.value}): {span.duration:.3f}s" if span.duration else f"    - {span.name} ({span.kind.value}): active")

        # Query events for this trace
        events = await manager.query_events(trace_id=trace.trace_id)
        print(f"  Events: {len(events)}")
        for event in events[:5]:  # Show first 5
            print(f"    - {event.type.value}: {event.name}")


async def example_sqlite_persistence():
    """Telemetry with SQLite persistence."""
    print("\n" + "="*60)
    print("Example 2: SQLite Persistence")
    print("="*60 + "\n")

    # Reset manager
    TelemetryManager.reset_instance()

    # Create temporary database file
    db_path = "/tmp/spark_telemetry_example.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create telemetry configuration with SQLite
    config = TelemetryConfig.create_sqlite(
        db_path=db_path,
        sampling_rate=1.0,
        buffer_size=10,
        export_interval=1.0,
    )

    # Build graph
    fetch = DataFetchNode(name="DataFetch")
    transform = TransformNode(name="Transform")
    validate = ValidationNode(name="Validate")
    save = SaveNode(name="Save")

    fetch >> transform >> validate >> save

    # Create graph with telemetry
    graph = Graph(start=fetch, telemetry_config=config)

    # Run graph multiple times
    print("Running graph 3 times...\n")
    for i in range(3):
        print(f"Run {i+1}:")
        await graph.run()

    # Flush telemetry to ensure all data is written
    manager = TelemetryManager.get_instance()
    await manager.flush()

    # Query all traces
    traces = await manager.query_traces(limit=10)
    print(f"\nTotal traces in database: {len(traces)}")

    # Analyze execution times
    durations = [t.duration for t in traces if t.duration]
    if durations:
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        print(f"\nExecution Time Analysis:")
        print(f"  Average: {avg_duration:.3f}s")
        print(f"  Min: {min_duration:.3f}s")
        print(f"  Max: {max_duration:.3f}s")

    print(f"\nTelemetry database saved to: {db_path}")

    # Cleanup
    await manager.shutdown()


async def example_custom_spans_and_metrics():
    """Custom spans and metrics."""
    print("\n" + "="*60)
    print("Example 3: Custom Spans and Metrics")
    print("="*60 + "\n")

    # Reset manager
    TelemetryManager.reset_instance()

    config = TelemetryConfig.create_memory()
    manager = TelemetryManager.get_instance(config)

    # Start a trace manually
    trace = manager.start_trace(
        name="custom_operation",
        attributes={
            'user_id': 'user123',
            'operation_type': 'data_processing'
        }
    )

    print(f"Started trace: {trace.trace_id}")

    # Create custom spans
    async with manager.start_span("step1", trace.trace_id, kind=SpanKind.INTERNAL) as span:
        span.set_attribute("step", "initialization")
        await asyncio.sleep(0.1)
        manager.record_metric(
            name="step1.duration",
            value=0.1,
            unit="seconds",
            aggregation="gauge"
        )

    async with manager.start_span("step2", trace.trace_id, kind=SpanKind.INTERNAL) as span:
        span.set_attribute("step", "processing")
        await asyncio.sleep(0.2)
        manager.record_metric(
            name="step2.duration",
            value=0.2,
            unit="seconds",
            aggregation="gauge"
        )

    # Record custom events
    manager.record_event(
        type=EventType.CUSTOM,
        name="processing_milestone",
        trace_id=trace.trace_id,
        attributes={
            'milestone': 'halfway',
            'progress': 50
        }
    )

    async with manager.start_span("step3", trace.trace_id, kind=SpanKind.INTERNAL) as span:
        span.set_attribute("step", "finalization")
        await asyncio.sleep(0.15)
        manager.record_metric(
            name="step3.duration",
            value=0.15,
            unit="seconds",
            aggregation="gauge"
        )

    # End trace
    manager.end_trace(trace.trace_id)

    print(f"Ended trace: {trace.trace_id}")
    print(f"Total duration: {trace.duration:.3f}s")

    # Query spans
    spans = await manager.query_spans(trace_id=trace.trace_id)
    print(f"\nCustom spans created: {len(spans)}")
    for span in spans:
        print(f"  - {span.name}: {span.duration:.3f}s")
        print(f"    Attributes: {span.attributes}")

    # Flush
    await manager.flush()


async def example_sampling():
    """Sampling traces to reduce overhead."""
    print("\n" + "="*60)
    print("Example 4: Sampling (50% sample rate)")
    print("="*60 + "\n")

    # Reset manager
    TelemetryManager.reset_instance()

    # Create config with 50% sampling
    config = TelemetryConfig.create_memory(
        sampling_rate=0.5,  # Sample 50% of traces
    )

    # Build graph
    fetch = DataFetchNode(name="DataFetch")
    transform = TransformNode(name="Transform")
    fetch >> transform

    graph = Graph(start=fetch, telemetry_config=config)

    # Run graph multiple times
    print("Running graph 10 times with 50% sampling...\n")
    for i in range(10):
        await graph.run()

    # Check how many traces were collected
    manager = TelemetryManager.get_instance()
    await manager.flush()

    traces = await manager.query_traces(limit=100)
    print(f"Traces collected: {len(traces)} out of 10 runs")
    print("(Due to sampling, approximately 5 should be collected)")


async def main():
    """Run all examples."""
    print("\n" + "#"*60)
    print("#  Spark Telemetry System Examples")
    print("#"*60)

    try:
        await example_basic_telemetry()

        if AIOSQLITE_AVAILABLE:
            await example_sqlite_persistence()
        else:
            print("\n" + "="*60)
            print("Example 2: SQLite Persistence - SKIPPED")
            print("="*60)
            print("(aiosqlite not installed. Install with: pip install aiosqlite)\n")

        await example_custom_spans_and_metrics()
        await example_sampling()
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "#"*60)
    print("#  Examples Complete!")
    print("#"*60 + "\n")

    print("Summary:")
    print("  - Telemetry automatically captures graph and node execution")
    print("  - Traces track complete workflows")
    print("  - Spans track individual operations")
    print("  - Events capture lifecycle moments")
    print("  - Metrics record numerical measurements")
    print("  - Backends support in-memory, SQLite, and PostgreSQL storage")
    print("  - Query API enables analysis and visualization")


if __name__ == "__main__":
    asyncio.run(main())
