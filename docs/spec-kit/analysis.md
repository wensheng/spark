---
title: Graph Analysis
nav_order: 13
---
# Graph Analysis

The Spark graph analyzer (`spark/kit/analysis.py`) provides comprehensive analysis of graph specifications, including complexity metrics, topology analysis, bottleneck identification, and optimization suggestions. This enables developers to understand, optimize, and validate graph structures before deployment.

## Overview

The `GraphAnalyzer` class analyzes GraphSpec instances to provide:

- **Complexity Metrics**: Node count, edge count, depth, branching factor
- **Topology Analysis**: Cycle detection, connectivity, reachability
- **Critical Path Analysis**: Identifying longest execution paths
- **Bottleneck Identification**: Finding potential performance issues
- **Optimization Suggestions**: Actionable recommendations for improvements
- **Semantic Validation**: Beyond-schema logical validation

## Basic Usage

### Command Line

```bash
# Basic analysis
spark-spec analyze workflow.json

# Generate HTML report
spark-spec analyze workflow.json --report analysis.html

# Fail on high complexity
spark-spec analyze workflow.json --fail-on "complexity>10"

# JSON output
spark-spec analyze workflow.json --format json > analysis.json
```

### Python API

```python
from spark.nodes.serde import load_graph_spec
from spark.kit.analysis import GraphAnalyzer

# Load specification
spec = load_graph_spec("workflow.json")

# Create analyzer
analyzer = GraphAnalyzer(spec)

# Run analysis
metrics = analyzer.analyze_complexity()
bottlenecks = analyzer.identify_bottlenecks()
suggestions = analyzer.suggest_optimizations()

# Print results
print(f"Node count: {metrics['node_count']}")
print(f"Max depth: {metrics['max_depth']}")
print(f"Cyclic: {metrics['cyclic']}")
```

## Complexity Metrics

### analyze_complexity()

Compute comprehensive complexity metrics.

```python
metrics = analyzer.analyze_complexity()
```

**Returns**:
```python
{
    'node_count': 10,               # Total nodes
    'edge_count': 15,               # Total edges
    'max_depth': 5,                 # Longest path from start
    'avg_depth': 3.2,               # Average path depth
    'branching_factor': 1.5,        # Avg outgoing edges per node
    'cyclic': True,                 # Contains cycles
    'cycle_count': 2,               # Number of cycles
    'cycles': [['A', 'B', 'C', 'A']], # Actual cycles
    'connected_components': 1,      # Number of disconnected components
    'unreachable_nodes': [],        # Nodes unreachable from start
    'leaf_nodes': ['output1', 'output2'],  # Nodes with no outgoing edges
    'fan_out_nodes': ['router'],    # Nodes with multiple outgoing edges
    'fan_in_nodes': ['joiner']      # Nodes with multiple incoming edges
}
```

**Metrics Explained**:

- **node_count**: Total number of nodes in the graph
- **edge_count**: Total number of edges connecting nodes
- **max_depth**: Maximum distance from start node to any other node
- **avg_depth**: Average distance from start node across all reachable nodes
- **branching_factor**: Average number of outgoing edges per node (higher = more parallel paths)
- **cyclic**: Whether the graph contains any cycles
- **cycle_count**: Number of distinct cycles detected
- **cycles**: List of cycles as node ID sequences
- **connected_components**: Number of disconnected subgraphs (should be 1 for valid graphs)
- **unreachable_nodes**: Nodes that cannot be reached from start node
- **leaf_nodes**: Terminal nodes with no outgoing edges
- **fan_out_nodes**: Nodes with multiple outgoing edges (branching points)
- **fan_in_nodes**: Nodes with multiple incoming edges (merge points)

### Interpreting Metrics

**High Complexity Indicators**:
- `max_depth > 10`: Deep execution paths may be slow
- `branching_factor > 3`: High parallelization or complex routing
- `cyclic = True`: Contains loops (may be intentional or problematic)
- `cycle_count > 2`: Multiple feedback loops
- `unreachable_nodes` not empty: Dead code or configuration issues
- `fan_out_nodes` many: Complex routing logic
- `fan_in_nodes` many: Synchronization bottlenecks

## Topology Analysis

### detect_cycles()

Detect cycles in the graph.

```python
cyclic, cycle_count, cycles = analyzer.detect_cycles()

if cyclic:
    print(f"Found {cycle_count} cycles:")
    for cycle in cycles:
        print(f"  {' -> '.join(cycle)}")
```

**Returns**: Tuple of `(bool, int, List[List[str]])`
- Boolean: Whether cycles exist
- Integer: Number of cycles
- List: Actual cycle paths

**Use Cases**:
- Identifying infinite loops
- Finding feedback paths
- Validating DAG requirements
- Understanding control flow

### find_unreachable_nodes()

Find nodes not reachable from start.

```python
unreachable = analyzer.find_unreachable_nodes()

if unreachable:
    print("Unreachable nodes (dead code):")
    for node_id in unreachable:
        print(f"  - {node_id}")
```

**Use Cases**:
- Identifying dead code
- Detecting disconnected subgraphs
- Validating graph connectivity
- Finding configuration errors

### count_connected_components()

Count disconnected subgraphs.

```python
components = analyzer.count_connected_components()

if components > 1:
    print(f"Warning: Graph has {components} disconnected components")
```

**Expected**: Should always be 1 for valid graphs

**Use Cases**:
- Validating graph connectivity
- Detecting isolated subgraphs
- Finding configuration errors

## Critical Path Analysis

### compute_critical_path()

Identify the longest execution path.

```python
critical_path = analyzer.compute_critical_path()

print("Critical path:")
for i, node_id in enumerate(critical_path):
    print(f"  {i+1}. {node_id}")

print(f"Critical path length: {len(critical_path)}")
```

**Returns**: List of node IDs representing the longest path

**Use Cases**:
- Identifying potential bottlenecks
- Understanding maximum execution time
- Prioritizing optimization efforts
- Resource planning

### estimate_execution_time()

Estimate graph execution time (requires node timing metadata).

```python
estimated_time = analyzer.estimate_execution_time()
print(f"Estimated execution time: {estimated_time:.2f}s")
```

**Requires**: Node specifications with `execution_time` metadata

## Bottleneck Identification

### identify_bottlenecks()

Find potential performance bottlenecks.

```python
bottlenecks = analyzer.identify_bottlenecks()

for bottleneck in bottlenecks:
    print(f"Bottleneck: {bottleneck['node_id']}")
    print(f"  Type: {bottleneck['type']}")
    print(f"  Severity: {bottleneck['severity']}")
    print(f"  Reason: {bottleneck['reason']}")
```

**Bottleneck Types**:
- **fan-in**: Multiple edges converging (synchronization point)
- **fan-out**: Multiple edges diverging (branching point)
- **critical-path**: Node on the critical path
- **high-degree**: Node with many connections
- **isolated**: Leaf node or isolated cluster

**Severity Levels**: `low`, `medium`, `high`

### analyze_parallelization_opportunities()

Identify opportunities for parallel execution.

```python
opportunities = analyzer.analyze_parallelization_opportunities()

for opp in opportunities:
    print(f"Parallelization opportunity:")
    print(f"  Nodes: {', '.join(opp['nodes'])}")
    print(f"  Benefit: {opp['benefit']}")
    print(f"  Feasibility: {opp['feasibility']}")
```

**Use Cases**:
- Finding independent operations
- Optimizing execution time
- Resource utilization improvements

## Optimization Suggestions

### suggest_optimizations()

Generate actionable optimization recommendations.

```python
suggestions = analyzer.suggest_optimizations()

for suggestion in suggestions:
    print(f"\nOptimization: {suggestion['type']}")
    print(f"  Priority: {suggestion['priority']}")
    print(f"  Description: {suggestion['description']}")
    print(f"  Impact: {suggestion['expected_impact']}")
    if 'nodes_affected' in suggestion:
        print(f"  Nodes: {', '.join(suggestion['nodes_affected'])}")
```

**Suggestion Types**:
- **remove-unreachable**: Remove dead code
- **parallelize**: Convert sequential to parallel
- **simplify-edges**: Simplify complex conditions
- **merge-nodes**: Combine similar nodes
- **cache**: Add caching to expensive operations
- **batch**: Batch similar operations
- **reduce-fan-out**: Simplify branching logic
- **add-join**: Add synchronization for parallel paths

### validate_semantics()

Perform semantic validation beyond schema.

```python
errors = analyzer.validate_semantics()

if errors:
    print("Semantic validation errors:")
    for error in errors:
        print(f"  - {error['type']}: {error['message']}")
        if 'location' in error:
            print(f"    Location: {error['location']}")
```

**Validation Checks**:
- Edge references valid nodes
- Start node exists
- No unreachable nodes (optional)
- No cycles in DAG (optional)
- Fan-in nodes have join logic
- Tool references valid

## Analysis Reports

### Generate HTML Report

```bash
spark-spec analyze workflow.json --report analysis.html
```

**Report Sections**:
- Executive summary
- Complexity metrics table
- Topology visualization
- Bottleneck list
- Optimization suggestions
- Critical path diagram
- Node and edge tables

### Generate Markdown Report

```python
from spark.kit.analysis import GraphAnalyzer

analyzer = GraphAnalyzer(spec)
report = analyzer.generate_markdown_report()

with open("analysis.md", "w") as f:
    f.write(report)
```

**Markdown Output**:
```markdown
# Graph Analysis Report

## Summary
- **Nodes**: 10
- **Edges**: 15
- **Max Depth**: 5
- **Cyclic**: Yes

## Complexity Metrics
| Metric | Value |
|--------|-------|
| Node count | 10 |
| Edge count | 15 |
...

## Bottlenecks
1. **Node: processor**
   - Type: fan-in
   - Severity: high
   - Reason: Multiple edges converging

## Optimization Suggestions
...
```

## Advanced Analysis

### Custom Metrics

Define custom analysis metrics.

```python
from spark.kit.analysis import GraphAnalyzer

class CustomAnalyzer(GraphAnalyzer):
    def analyze_agent_complexity(self):
        """Custom metric: agent node complexity."""
        agent_nodes = [n for n in self.spec.nodes if n.type == "Agent"]
        total_tools = sum(len(n.config.get("tools", [])) for n in agent_nodes)
        return {
            "agent_count": len(agent_nodes),
            "total_tools": total_tools,
            "avg_tools_per_agent": total_tools / len(agent_nodes) if agent_nodes else 0
        }
```

### Graph Comparison

Compare two graph versions.

```python
from spark.kit.analysis import compare_graphs

old_spec = load_graph_spec("workflow_v1.json")
new_spec = load_graph_spec("workflow_v2.json")

comparison = compare_graphs(old_spec, new_spec)

print(f"Nodes added: {comparison['nodes_added']}")
print(f"Nodes removed: {comparison['nodes_removed']}")
print(f"Complexity change: {comparison['complexity_delta']}")
```

### Visualization

Generate graph visualizations.

```python
analyzer = GraphAnalyzer(spec)

# Generate DOT format
dot = analyzer.to_dot()
with open("graph.dot", "w") as f:
    f.write(dot)

# Generate Mermaid diagram
mermaid = analyzer.to_mermaid()
with open("graph.mmd", "w") as f:
    f.write(mermaid)
```

## CI/CD Integration

### Complexity Threshold Enforcement

```bash
#!/bin/bash
# enforce_complexity.sh

spark-spec analyze workflow.json --format json > analysis.json

# Check max depth
MAX_DEPTH=$(jq '.max_depth' analysis.json)
if [ "$MAX_DEPTH" -gt 10 ]; then
    echo "Error: Max depth $MAX_DEPTH exceeds limit of 10"
    exit 1
fi

# Check for unreachable nodes
UNREACHABLE=$(jq '.unreachable_nodes | length' analysis.json)
if [ "$UNREACHABLE" -gt 0 ]; then
    echo "Error: Found $UNREACHABLE unreachable nodes"
    exit 1
fi

echo "Complexity checks passed"
```

### Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

for spec in specs/*.json; do
    spark-spec analyze "$spec" --fail-on "complexity>8" || exit 1
done
```

## Best Practices

**Run Early**: Analyze specs during development, not just before deployment.

**Set Thresholds**: Define complexity thresholds for your project.

**Automate**: Integrate analysis into CI/CD pipelines.

**Review Suggestions**: Carefully review optimization suggestions before applying.

**Track Metrics**: Monitor complexity metrics over time.

**Document Decisions**: Document why high complexity is acceptable if needed.

**Use Reports**: Generate reports for code reviews and documentation.

## Performance Considerations

**Analysis Speed**: Fast for typical graphs (< 1 second for 1000 nodes)

**Memory Usage**: Low memory footprint (specs are lightweight)

**Incremental Analysis**: Not supported - always full graph analysis

## Troubleshooting

**Large Graphs**: For very large graphs (> 10,000 nodes), analysis may be slow.

**Complex Conditions**: Edge condition complexity is not analyzed.

**Dynamic Behavior**: Cannot analyze runtime dynamic behavior.

**Estimation Accuracy**: Execution time estimates require node timing metadata.

## Next Steps

- **[Specification Models](./models.md)**: Understanding analyzed structures
- **[Code Generation](./codegen.md)**: Generating optimized code
- **[Mission System](./missions.md)**: Analyzing complete missions
- **[Best Practices](../best-practices/graphs.md)**: Graph design patterns

## Related Documentation

- [Best Practices: Graph Design](../best-practices/graphs.md)
- [Troubleshooting: Performance Issues](../troubleshooting/performance.md)
- [Examples: Complex Workflows](../examples/advanced.md)
