# Phase 6: Advanced Optimization

## Overview

Phase 6 introduces advanced structural transformations and multi-objective optimization capabilities for sophisticated graph improvements.

**Key Components**:
- `NodeReplacementAnalyzer`: Identifies better node alternatives
- `EdgeOptimizer`: Optimizes graph topology
- `ParallelizationAnalyzer`: Converts sequential to parallel execution
- `HumanReviewNode`: Human-in-the-loop for high-risk changes
- `GraphDiffer`: Visualizes graph changes
- `MultiObjectiveOptimizer`: Balances competing objectives

## NodeReplacementAnalyzer

Identifies opportunities to replace nodes with more efficient alternatives.

### Purpose

- Find better node alternatives (faster, cheaper, more accurate)
- Analyze semantic equivalence
- Assess compatibility
- Estimate performance improvement

### Usage

```python
from spark.rsi.node_replacement import NodeReplacementAnalyzer

analyzer = NodeReplacementAnalyzer()

# Analyze replacement opportunities
candidates = await analyzer.analyze_replacements(
    graph=production_graph,
    node_id="slow_llm_node",
    diagnostic_report=report
)

for candidate in candidates:
    print(f"Replacement: {candidate.replacement_node_name}")
    print(f"  Compatibility: {candidate.compatibility_score:.1%}")
    print(f"  Expected improvement: {candidate.expected_improvement}")
    print(f"  Risk factors: {candidate.risk_factors}")
```

### Replacement Examples

- Replace expensive LLM with cheaper alternative
- Upgrade to newer/better model
- Add caching layer
- Replace slow computation with faster implementation

## EdgeOptimizer

Optimizes graph topology through edge modifications.

### Purpose

- Identify redundant paths
- Find shortcut opportunities
- Simplify edge conditions
- Remove unnecessary branches

### Usage

```python
from spark.rsi.edge_optimizer import EdgeOptimizer

optimizer = EdgeOptimizer()

# Analyze edge optimization opportunities
opportunities = await optimizer.analyze_edges(
    graph=production_graph,
    telemetry_data=telemetry
)

# Shortcut opportunities
for shortcut in opportunities['shortcuts']:
    print(f"Shortcut: {shortcut.from_node} → {shortcut.to_node}")
    print(f"  Skips: {shortcut.skipped_nodes}")
    print(f"  Latency savings: {shortcut.potential_latency_savings:.2f}s")

# Redundant edges
for redundant in opportunities['redundant']:
    print(f"Redundant: {redundant.from_node} → {redundant.to_node}")
    print(f"  Traversal rate: {redundant.traversal_rate:.1%}")
```

## ParallelizationAnalyzer

Identifies opportunities to convert sequential execution to parallel.

### Purpose

- Detect independent operations
- Analyze node dependencies
- Estimate speedup from parallelization
- Generate parallel graph structures

### Usage

```python
from spark.rsi.parallelization_analyzer import ParallelizationAnalyzer

analyzer = ParallelizationAnalyzer()

# Analyze parallelization opportunities
opportunities = await analyzer.analyze_parallelization(
    graph=production_graph,
    introspector=introspector
)

for seq in opportunities:
    print(f"Parallelizable sequence:")
    print(f"  Nodes: {seq.sequential_nodes}")
    print(f"  Entry: {seq.entry_node}")
    print(f"  Exit: {seq.exit_node}")
    print(f"  Estimated speedup: {seq.estimated_speedup}x")
    print(f"  Has dependencies: {seq.has_dependencies}")
    print(f"  Confidence: {seq.confidence:.1%}")
```

## HumanReviewNode

Provides human-in-the-loop review for high-risk changes.

### Purpose

- Gate high-risk hypotheses for human review
- Capture human feedback
- Integrate learnings into experience database
- Provide CLI-based review interface

### Configuration

```python
from spark.rsi.human_review import HumanReviewNode, HumanReviewConfig

review_config = HumanReviewConfig(
    require_review_threshold=0.7,  # Risk score threshold
    review_timeout_seconds=3600,    # 1 hour timeout
    auto_reject_on_timeout=False
)

review_node = HumanReviewNode(config=review_config)
```

### Usage

```python
# In RSI workflow
result = await review_node.run({
    'hypothesis': high_risk_hypothesis,
    'validation_result': validation,
    'test_result': test_result
})

if result['approved']:
    # Proceed with deployment
    pass
else:
    # Hypothesis rejected
    print(f"Rejected: {result['rejection_reason']}")
```

### CLI Review Interface

Use the CLI to review pending hypotheses:

```bash
# List pending reviews
python -m spark.rsi.review_cli list

# Review specific hypothesis
python -m spark.rsi.review_cli review <hypothesis_id>

# Approve hypothesis
python -m spark.rsi.review_cli approve <hypothesis_id> --comments "Looks good"

# Reject hypothesis
python -m spark.rsi.review_cli reject <hypothesis_id> --reason "Too risky"
```

## GraphDiffer

Visualizes graph changes in multiple formats.

### Purpose

- Compare baseline vs candidate graphs
- Highlight additions, deletions, modifications
- Generate side-by-side comparisons
- Support text, JSON, and HTML output

### Usage

```python
from spark.rsi.graph_differ import GraphDiffer

differ = GraphDiffer()

# Create diff
diff = differ.diff(
    baseline_spec=baseline_spec,
    candidate_spec=candidate_spec
)

# Text format
print(differ.format_text(diff))

# JSON format
json_diff = differ.format_json(diff)

# HTML format (for web display)
html = differ.format_html(diff)
```

### Diff Output

```
Graph Diff: v1.0.0 → v1.1.0

Nodes:
  + Added: caching_node
  ~ Modified: agent_node (config.prompt_template)
  - Removed: legacy_node

Edges:
  + Added: input_node → caching_node
  ~ Modified: agent_node → output_node (condition changed)

Complexity:
  Nodes: 5 → 5 (0)
  Edges: 4 → 5 (+1)
  Depth: 3 → 3 (0)
```

## MultiObjectiveOptimizer

Balances competing objectives (latency, cost, quality, reliability).

### Purpose

- Rank hypotheses by multiple objectives
- Find Pareto-optimal solutions
- Balance trade-offs
- Configure objective weights

### Configuration

```python
from spark.rsi.multi_objective_optimizer import (
    MultiObjectiveOptimizer,
    OptimizationObjectives
)

objectives = OptimizationObjectives(
    latency_weight=0.4,      # 40% weight
    cost_weight=0.3,         # 30% weight
    quality_weight=0.2,      # 20% weight
    reliability_weight=0.1   # 10% weight
)

optimizer = MultiObjectiveOptimizer(objectives=objectives)
```

### Usage

```python
# Rank multiple hypotheses
ranked = optimizer.rank_hypotheses(
    hypotheses=hypotheses,
    current_metrics=baseline_metrics
)

for rank in ranked:
    print(f"Rank {rank.rank}: {rank.hypothesis.hypothesis_id}")
    print(f"  Score: {rank.total_score:.3f}")
    print(f"  Latency score: {rank.latency_score:.3f}")
    print(f"  Cost score: {rank.cost_score:.3f}")
    print(f"  Quality score: {rank.quality_score:.3f}")
    print(f"  Reliability score: {rank.reliability_score:.3f}")
    print(f"  Is Pareto optimal: {rank.is_pareto_optimal}")

# Find Pareto frontier
frontier = optimizer.pareto_frontier(ranked)
print(f"\nPareto frontier: {len(frontier.solutions)} solutions")
```

### Pareto Optimality

A solution is Pareto optimal if no other solution is better in all objectives.

Example:
- Solution A: Fast but expensive
- Solution B: Cheap but slow
- Both are Pareto optimal (trade-off between latency and cost)

## Integration Example

Complete Phase 6 workflow:

```python
from spark.rsi import (
    HypothesisGeneratorNode,
    ChangeValidatorNode,
    HypothesisTesterNode
)
from spark.rsi.node_replacement import NodeReplacementAnalyzer
from spark.rsi.edge_optimizer import EdgeOptimizer
from spark.rsi.parallelization_analyzer import ParallelizationAnalyzer
from spark.rsi.multi_objective_optimizer import (
    MultiObjectiveOptimizer,
    OptimizationObjectives
)
from spark.rsi.human_review import HumanReviewNode
from spark.models.openai import OpenAIModel

# Step 1: Initialize analyzers
node_analyzer = NodeReplacementAnalyzer()
edge_optimizer = EdgeOptimizer()
parallel_analyzer = ParallelizationAnalyzer()

# Step 2: Generate structural hypotheses
model = OpenAIModel(model_id="gpt-4o")
generator = HypothesisGeneratorNode(
    model=model,
    hypothesis_types=[
        "prompt_optimization",
        "node_replacement",
        "edge_modification",
        "parallelization"
    ],
    node_replacement_analyzer=node_analyzer,
    edge_optimizer=edge_optimizer,
    parallelization_analyzer=parallel_analyzer,
    enable_structural_improvements=True
)

result = await generator.run({
    'diagnostic_report': report,
    'graph': production_graph
})

# Step 3: Multi-objective ranking
objectives = OptimizationObjectives(
    latency_weight=0.3,
    cost_weight=0.3,
    quality_weight=0.3,
    reliability_weight=0.1
)

optimizer = MultiObjectiveOptimizer(objectives=objectives)
ranked = optimizer.rank_hypotheses(
    hypotheses=result['hypotheses'],
    current_metrics=baseline_metrics
)

print(f"\nTop hypotheses (multi-objective ranking):")
for i, rank in enumerate(ranked[:5]):
    hyp = rank.hypothesis
    print(f"{i+1}. {hyp.hypothesis_id}")
    print(f"   Type: {hyp.hypothesis_type}")
    print(f"   Score: {rank.total_score:.3f}")
    print(f"   Pareto optimal: {rank.is_pareto_optimal}")

# Step 4: Validate and test top hypotheses
validator = ChangeValidatorNode()
tester = HypothesisTesterNode()

for rank in ranked[:3]:  # Top 3
    hypothesis = rank.hypothesis

    # Validate
    val_result = await validator.run({
        'hypothesis': hypothesis,
        'graph': production_graph
    })

    if not val_result['approved']:
        continue

    # High risk hypotheses require human review
    if val_result['risk_level'] == 'HIGH':
        review_node = HumanReviewNode()
        review_result = await review_node.run({
            'hypothesis': hypothesis,
            'validation_result': val_result
        })

        if not review_result['approved']:
            print(f"Human rejected: {hypothesis.hypothesis_id}")
            continue

    # Test
    test_result = await tester.run({
        'hypothesis': hypothesis,
        'graph': production_graph
    })

    if test_result['passed']:
        print(f"✓ Passed: {hypothesis.hypothesis_id}")
        # Deploy via DeploymentController
```

## Best Practices

### Structural Improvements

1. **Start Simple**: Begin with prompt/config before structural
2. **Incremental Changes**: One structural change at a time
3. **Thorough Testing**: More test iterations for structural changes
4. **Staging Environment**: Test structural changes in staging first
5. **Rollback Plan**: Always have rollback plan for structural changes

### Multi-Objective Optimization

1. **Define Weights**: Set objective weights based on business priorities
2. **Review Pareto Solutions**: Manually review Pareto-optimal solutions
3. **Trade-off Analysis**: Understand trade-offs between objectives
4. **Update Weights**: Adjust weights based on changing priorities
5. **Validate Improvements**: Verify multi-objective improvements in production

### Human Review

1. **Set Appropriate Thresholds**: Review HIGH and CRITICAL risk
2. **Timely Review**: Set reasonable review timeouts
3. **Feedback Loop**: Capture and integrate review feedback
4. **Training**: Train reviewers on graph architecture
5. **Escalation**: Have escalation path for complex reviews

## Troubleshooting

### No Structural Opportunities

- Verify analyzers are properly initialized
- Check if graph has opportunities for optimization
- Review diagnostic report for structural issues
- Enable verbose logging

### Poor Multi-Objective Rankings

- Review objective weights
- Verify metrics are accurate
- Check hypothesis quality
- Consider adjusting weights

### Human Review Bottleneck

- Increase `require_review_threshold`
- Enable auto-approval for LOW risk
- Set reasonable review timeouts
- Add more reviewers

## Next Steps

With all 6 phases complete, configure and run the complete RSI system:

**Meta-Graph**: [RSI Meta-Graph](meta-graph.md) - Complete autonomous workflow

## Related Documentation

- [Phase 5: Pattern Extraction](phase5-patterns.md)
- [RSI Meta-Graph](meta-graph.md)
- [RSI CLI & Tools](cli.md)
- [RSI Overview](overview.md)
- [API Reference: RSI](../api/rsi.md)
