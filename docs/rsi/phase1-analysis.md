# Phase 1: Performance Analysis & Introspection

## Overview

Phase 1 establishes the data-driven foundation for RSI by providing tools to analyze graph performance, detect bottlenecks, and introspect graph structure. This phase collects the evidence needed to make informed improvement decisions in later phases.

**Key Components**:
- `PerformanceAnalyzerNode`: Analyzes telemetry data to detect bottlenecks and failure patterns
- `GraphIntrospector`: Introspects graph structure and complexity
- `ExperienceDatabase`: Stores learning data from improvement attempts

## PerformanceAnalyzerNode

The `PerformanceAnalyzerNode` queries telemetry data to identify performance issues and generate diagnostic reports.

### Purpose

- Detect bottlenecks (high latency nodes, high error rates)
- Identify failure patterns
- Analyze success rates and performance metrics
- Generate evidence-based improvement opportunities

### Configuration

```python
from spark.rsi import PerformanceAnalyzerNode

analyzer = PerformanceAnalyzerNode(
    name="PerformanceAnalyzer",
    analysis_window_hours=24,      # Hours of historical data to analyze
    min_executions=10,               # Minimum executions needed for analysis
    telemetry_manager=None           # Optional: provide TelemetryManager instance
)
```

**Parameters**:
- `analysis_window_hours` (int): Hours of historical telemetry data to analyze. Default: 24.
- `min_executions` (int): Minimum number of graph executions required for meaningful analysis. Default: 10.
- `telemetry_manager` (TelemetryManager): Optional telemetry manager instance. If not provided, uses singleton.

### Usage

```python
from spark.rsi import PerformanceAnalyzerNode
from spark.telemetry import TelemetryManager

# Create analyzer
analyzer = PerformanceAnalyzerNode(
    analysis_window_hours=24,
    min_executions=10
)

# Run analysis
result = await analyzer.run({
    'graph_id': 'production_workflow',
    'graph_version': '1.0.0'
})

# Check if issues found
if result['has_issues']:
    report = result['report']
    print(f"Found {len(report.bottlenecks)} bottlenecks")
    print(f"Success rate: {report.summary.success_rate:.1%}")
    print(f"Average duration: {report.summary.avg_duration:.3f}s")
```

### Input Format

The `PerformanceAnalyzerNode` expects inputs:

```python
{
    'graph_id': str,           # Required: ID of graph to analyze
    'graph_version': str,      # Optional: Version tag
    'start_time': float,       # Optional: Override start timestamp
    'end_time': float         # Optional: Override end timestamp
}
```

### Output Format

Returns a dictionary with:

```python
{
    'has_issues': bool,              # True if issues detected
    'report': DiagnosticReport,      # Full diagnostic report
    'summary': {                     # Quick summary
        'total_executions': int,
        'success_rate': float,
        'avg_duration': float,
        'bottlenecks_count': int,
        'failures_count': int
    },
    'reason': str                    # If no analysis performed
}
```

### Diagnostic Report Structure

The `DiagnosticReport` contains:

```python
@dataclass
class DiagnosticReport:
    graph_id: str
    graph_version: str
    analysis_period: AnalysisPeriod      # Start/end timestamps
    summary: PerformanceSummary          # Overall metrics
    node_metrics: Dict[str, NodeMetrics] # Per-node performance
    bottlenecks: List[Bottleneck]        # Identified issues
    failures: List[FailurePattern]       # Failure patterns
    opportunities: List[str]             # Improvement suggestions
    generated_at: datetime
```

#### PerformanceSummary

```python
@dataclass
class PerformanceSummary:
    total_executions: int    # Total graph runs
    success_rate: float      # 0.0 to 1.0
    avg_duration: float      # Average execution time (seconds)
    p50_duration: float      # Median duration
    p95_duration: float      # 95th percentile
    p99_duration: float      # 99th percentile
    total_cost: float        # Optional: Total LLM costs
```

#### NodeMetrics

```python
@dataclass
class NodeMetrics:
    node_id: str
    node_name: str
    executions: int          # Number of times node ran
    successes: int
    failures: int
    success_rate: float      # 0.0 to 1.0
    error_rate: float        # 0.0 to 1.0
    avg_duration: float      # Average execution time
    p95_duration: float      # 95th percentile duration
```

#### Bottleneck

```python
@dataclass
class Bottleneck:
    node_id: str
    node_name: str
    issue: str               # 'high_latency' or 'high_error_rate'
    severity: str            # 'low', 'medium', 'high', 'critical'
    impact_score: float      # Quantified impact
    metrics: Dict[str, Any]  # Supporting metrics
```

**Bottleneck Detection Rules**:
- **High Latency**: Node avg_duration > 2x overall average node duration
- **High Error Rate**: Node error_rate > 5%
- **Severity Levels**:
  - Low: Minor impact
  - Medium: 2-5x slower than average
  - High: 5x+ slower, or error rate > 5%
  - Critical: Error rate > 20%

#### FailurePattern

```python
@dataclass
class FailurePattern:
    node_id: str
    node_name: str
    error_type: str          # Error classification
    count: int               # Number of occurrences
    sample_messages: List[str]  # Up to 3 sample error messages
```

### Analysis Process

The `PerformanceAnalyzerNode` follows these steps:

1. **Query Telemetry**: Retrieve traces from the analysis window
2. **Validate Data**: Ensure minimum executions threshold is met
3. **Calculate Summary**: Aggregate overall performance metrics
4. **Analyze Per-Node**: Calculate metrics for each node from spans
5. **Identify Bottlenecks**: Detect high-latency and high-error-rate nodes
6. **Analyze Failures**: Extract and categorize failure patterns
7. **Generate Opportunities**: Suggest improvements based on findings

### Example: Complete Analysis

```python
from spark.rsi import PerformanceAnalyzerNode
from spark.telemetry import TelemetryConfig, TelemetryManager
from spark.graphs import Graph

# Step 1: Enable telemetry on production graph
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)

production_graph = Graph(
    start=my_node,
    telemetry_config=telemetry_config
)

# Step 2: Run production graph to collect data
for i in range(100):
    await production_graph.run()

# Step 3: Analyze performance
analyzer = PerformanceAnalyzerNode(
    analysis_window_hours=24,
    min_executions=50
)

result = await analyzer.run({
    'graph_id': 'production_workflow',
    'graph_version': '1.0.0'
})

# Step 4: Inspect results
if result['has_issues']:
    report = result['report']

    print(f"Analysis Period: {report.analysis_period.start} to {report.analysis_period.end}")
    print(f"\nOverall Performance:")
    print(f"  Executions: {report.summary.total_executions}")
    print(f"  Success Rate: {report.summary.success_rate:.1%}")
    print(f"  Avg Duration: {report.summary.avg_duration:.3f}s")
    print(f"  P95 Duration: {report.summary.p95_duration:.3f}s")

    if report.bottlenecks:
        print(f"\nBottlenecks ({len(report.bottlenecks)}):")
        for bottleneck in report.bottlenecks:
            print(f"  - {bottleneck.node_name}: {bottleneck.issue} ({bottleneck.severity})")
            print(f"    Impact Score: {bottleneck.impact_score:.2f}")
            print(f"    Metrics: {bottleneck.metrics}")

    if report.failures:
        print(f"\nFailure Patterns ({len(report.failures)}):")
        for failure in report.failures:
            print(f"  - {failure.node_name}: {failure.error_type}")
            print(f"    Count: {failure.count}")
            print(f"    Samples: {failure.sample_messages[:1]}")

    if report.opportunities:
        print(f"\nImprovement Opportunities:")
        for opp in report.opportunities:
            print(f"  - {opp}")
```

### Metrics and Thresholds

| Metric | Threshold | Severity |
|--------|-----------|----------|
| Error Rate | > 5% | High |
| Error Rate | > 20% | Critical |
| Latency | > 2x avg | Medium |
| Latency | > 5x avg | High |
| Success Rate | < 95% | Issues detected |
| Minimum Executions | < 10 | Insufficient data |

## GraphIntrospector

The `GraphIntrospector` analyzes graph structure and provides insights into complexity and topology.

### Purpose

- Introspect graph structure and node configuration
- Analyze graph complexity (depth, branching factor)
- Identify cycles and unreachable nodes
- Generate graph specifications for modification

### Usage

```python
from spark.rsi import GraphIntrospector
from spark.graphs import Graph

# Create introspector
introspector = GraphIntrospector(graph)

# Get node IDs
node_ids = introspector.get_node_ids()
print(f"Graph has {len(node_ids)} nodes")

# Analyze specific node
node_spec = introspector.get_node_spec("my_node_id")
node_config = introspector.get_node_config("my_node_id")

# Get edges from node
edges = introspector.get_edges_from_node("my_node_id")

# Analyze graph depth
depth = introspector.get_graph_depth()
print(f"Graph depth: {depth}")

# Find cycles
cycles = introspector.find_cycles()
if cycles:
    print(f"Found {len(cycles)} cycles")

# Get graph complexity metrics
complexity = introspector.analyze_complexity()
print(f"Complexity score: {complexity['score']}")
```

### Key Methods

**Node Inspection**:
- `get_node_ids()`: List all node IDs
- `get_node_spec(node_id)`: Get NodeSpec for a node
- `get_node_config(node_id)`: Get configuration dict
- `get_node_type(node_id)`: Get node type/class

**Edge Inspection**:
- `get_edges_from_node(node_id)`: Outgoing edges
- `get_edges_to_node(node_id)`: Incoming edges
- `get_all_edges()`: All edges in graph

**Structure Analysis**:
- `get_graph_depth()`: Maximum depth from start node
- `find_cycles()`: Detect cycles in graph
- `get_reachable_nodes()`: Nodes reachable from start
- `get_unreachable_nodes()`: Orphaned nodes
- `analyze_complexity()`: Complexity metrics

### Complexity Analysis

The introspector calculates graph complexity based on:
- Number of nodes
- Number of edges
- Graph depth (max path length)
- Branching factor (avg outgoing edges per node)
- Cycles present
- Unreachable nodes

```python
complexity = introspector.analyze_complexity()
# Returns:
{
    'num_nodes': int,
    'num_edges': int,
    'depth': int,
    'avg_branching_factor': float,
    'has_cycles': bool,
    'num_cycles': int,
    'num_unreachable': int,
    'score': float  # Overall complexity score
}
```

## ExperienceDatabase

The `ExperienceDatabase` stores outcomes of improvement attempts for learning and pattern extraction.

### Purpose

- Store hypothesis proposals and outcomes
- Track test results and deployments
- Record lessons learned
- Provide data for pattern extraction (Phase 5)

### Usage

```python
from spark.rsi import ExperienceDatabase

# Create and initialize database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Store a hypothesis
await experience_db.store_hypothesis(
    hypothesis_id="hyp_001",
    graph_id="production_workflow",
    graph_version_baseline="1.0.0",
    hypothesis_type="prompt_optimization",
    proposal={
        'rationale': "Improve prompt clarity",
        'changes': [...]
    },
    target_node="agent_node_1"
)

# Update with test results
await experience_db.update_test_results(
    hypothesis_id="hyp_001",
    test_results={
        'status': 'passed',
        'improvement': 0.15,  # 15% improvement
        'confidence': 0.95
    }
)

# Update with deployment outcome
await experience_db.update_deployment_outcome(
    hypothesis_id="hyp_001",
    deployed=True,
    outcome={
        'success': True,
        'impact': 'positive',
        'metrics_delta': {...}
    },
    lessons=[
        "Prompt clarity improves accuracy",
        "Small changes can have significant impact"
    ],
    patterns=[
        "agent_prompt_optimization",
        "clarity_improvement"
    ]
)

# Query experiences
successful = await experience_db.get_successful_hypotheses(
    graph_id="production_workflow",
    hypothesis_type="prompt_optimization"
)
```

### Storage

**Phase 1**: In-memory storage (current implementation)
- Fast access
- Suitable for development and testing
- Data lost on restart

**Future Phases**: Persistent storage
- SQLite backend for local persistence
- PostgreSQL backend for production deployments
- Shared learning across RSI instances

### Query Methods

- `get_hypothesis(hypothesis_id)`: Retrieve specific hypothesis
- `get_successful_hypotheses(graph_id, hypothesis_type)`: Get successful attempts
- `get_failed_hypotheses(graph_id, hypothesis_type)`: Get failed attempts
- `get_recent_hypotheses(limit, graph_id)`: Recent attempts
- `get_patterns()`: Stored patterns
- `get_lessons()`: Stored lessons

## Integration Example

Here's how Phase 1 components work together:

```python
from spark.rsi import (
    PerformanceAnalyzerNode,
    GraphIntrospector,
    ExperienceDatabase
)
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Step 1: Enable telemetry on production graph
telemetry_config = TelemetryConfig.create_sqlite("telemetry.db")
production_graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Run graph to collect data
for i in range(100):
    await production_graph.run()

# Step 2: Initialize experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Step 3: Analyze performance
analyzer = PerformanceAnalyzerNode(analysis_window_hours=24)
result = await analyzer.run({
    'graph_id': 'production_workflow',
    'graph_version': '1.0.0'
})

if result['has_issues']:
    report = result['report']
    print(f"Found {len(report.bottlenecks)} bottlenecks")

    # Step 4: Introspect graph structure
    introspector = GraphIntrospector(production_graph)

    for bottleneck in report.bottlenecks:
        node_id = bottleneck.node_id

        # Get node details
        node_config = introspector.get_node_config(node_id)
        edges = introspector.get_edges_from_node(node_id)

        print(f"\nBottleneck: {bottleneck.node_name}")
        print(f"  Issue: {bottleneck.issue} ({bottleneck.severity})")
        print(f"  Config: {node_config}")
        print(f"  Outgoing edges: {len(edges)}")

    # Analysis complete - ready for Phase 2 (hypothesis generation)
```

## Best Practices

### Telemetry Configuration

1. **Sampling Rate**: Use 1.0 (100%) for RSI to ensure complete data
2. **Buffer Size**: Increase for high-throughput graphs
3. **Backend**: Use SQLite or PostgreSQL for persistence
4. **Retention**: Keep at least 7 days of telemetry data

```python
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0,
    enable_metrics=True,
    enable_events=True,
    buffer_size=1000
)
```

### Analysis Timing

- Run analysis after significant traffic (100+ executions)
- Use appropriate analysis windows (24-72 hours)
- Consider time-of-day patterns
- Analyze after incidents or changes

### Data Quality

- Ensure telemetry is enabled before deploying graphs
- Verify minimum execution thresholds
- Check for complete traces (no partial data)
- Monitor telemetry backend health

## Troubleshooting

### No Issues Detected

If analysis reports no issues:
- Verify telemetry is collecting data
- Check if minimum executions threshold is met
- Review if thresholds are appropriate for your use case
- Consider lowering thresholds for detection

### Insufficient Data

If you see "Insufficient data":
- Run more executions (need at least 10, recommend 100+)
- Expand analysis window
- Check telemetry configuration

### Performance

For large datasets:
- Use appropriate analysis windows
- Consider sampling if > 100K traces
- Use PostgreSQL backend for better query performance
- Monitor telemetry query times

## Next Steps

Once you have a diagnostic report with identified issues, proceed to:

**Phase 2**: [Hypothesis Generation & Validation](phase2-hypothesis.md) - Generate improvement proposals

## Related Documentation

- [RSI Overview](overview.md)
- [Telemetry System](../telemetry/overview.md)
- [RSI Meta-Graph](meta-graph.md)
- [API Reference: RSI](../api/rsi.md)
