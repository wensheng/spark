---
title: Phase 3. Automated A/B Testing
parent: RSI
nav_order: 3
---
# Phase 3: Automated A/B Testing

## Overview

Phase 3 implements rigorous automated A/B testing of improvement hypotheses with statistical analysis. This phase ensures that proposed changes genuinely improve graph performance before deployment.

**Key Component**:
- `HypothesisTesterNode`: Automated A/B testing framework with statistical significance testing

## HypothesisTesterNode

The `HypothesisTesterNode` compares baseline and candidate graphs through repeated execution and statistical analysis.

### Purpose

- Run baseline graph multiple times to collect metrics
- Apply hypothesis changes to create candidate graph
- Run candidate graph multiple times
- Compare performance with statistical significance
- Determine if hypothesis improves the graph

### Configuration

```python
from spark.rsi import HypothesisTesterNode

tester = HypothesisTesterNode(
    name="HypothesisTester",
    num_baseline_runs=20,
    num_candidate_runs=20,
    success_criteria={
        'min_success_rate_improvement': 0.05,  # 5% improvement
        'max_latency_increase': 0.1,            # 10% increase tolerated
        'confidence_level': 0.95                # 95% confidence
    },
    confidence_level=0.95,
    enable_mock_mode=False  # Set True for testing
)
```

**Parameters**:
- `num_baseline_runs` (int): Number of times to run baseline graph. Default: 20.
- `num_candidate_runs` (int): Number of times to run candidate graph. Default: 20.
- `success_criteria` (Dict): Criteria for hypothesis success.
- `confidence_level` (float): Statistical confidence level (0.0-1.0). Default: 0.95.
- `enable_mock_mode` (bool): Use mock testing without running graphs. Default: False.

### Success Criteria

Default success criteria:

```python
{
    'min_success_rate_improvement': 0.0,   # Any improvement
    'max_latency_increase': 0.2,           # 20% increase tolerated
    'min_confidence_level': 0.95           # 95% statistical confidence
}
```

Custom criteria:

```python
tester = HypothesisTesterNode(
    num_baseline_runs=30,
    num_candidate_runs=30,
    success_criteria={
        'min_success_rate_improvement': 0.10,  # Require 10% improvement
        'max_latency_increase': 0.05,          # Only 5% latency increase allowed
        'max_cost_increase': 0.0,              # No cost increase allowed
        'min_quality_score': 0.8,              # Minimum quality threshold
        'confidence_level': 0.99               # 99% confidence
    }
)
```

### Usage

```python
from spark.rsi import HypothesisTesterNode
from spark.rsi.types import TestStatus

# Create tester
tester = HypothesisTesterNode(
    num_baseline_runs=20,
    num_candidate_runs=20,
    success_criteria={
        'min_success_rate_improvement': 0.05,
        'confidence_level': 0.95
    }
)

# Test hypothesis
result = await tester.run({
    'hypothesis': approved_hypothesis,
    'graph': production_graph,
    'test_inputs': test_dataset  # Optional: specific test inputs
})

# Check results
test_result = result['test_result']
if test_result.status == TestStatus.PASSED:
    print("✓ Hypothesis passed testing!")
    print(f"  Success rate improvement: {test_result.comparison.success_rate_delta:+.1%}")
    print(f"  Latency change: {test_result.comparison.avg_duration_delta:+.3f}s")
    print(f"  Statistical confidence: {test_result.comparison.confidence_level:.1%}")
elif test_result.status == TestStatus.FAILED:
    print("✗ Hypothesis failed testing")
    print(f"  Reason: {test_result.comparison.summary}")
elif test_result.status == TestStatus.INCONCLUSIVE:
    print("~ Hypothesis testing inconclusive")
    print(f"  Need more test runs or clearer signal")
```

### Input Format

```python
{
    'hypothesis': ImprovementHypothesis,  # Required
    'graph': BaseGraph,                    # Required
    'test_inputs': List[Any]              # Optional: specific test inputs
}
```

### Output Format

```python
{
    'test_result': TestResult,
    'status': str,           # 'passed', 'failed', 'inconclusive', 'error'
    'passed': bool,
    'is_improvement': bool
}
```

### TestResult Structure

```python
@dataclass
class TestResult:
    hypothesis_id: str
    test_id: str
    status: TestStatus        # PASSED, FAILED, INCONCLUSIVE, ERROR

    # Test configuration
    num_baseline_runs: int
    num_candidate_runs: int
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Results
    comparison: ComparisonResult

    # Success criteria
    success_criteria_met: bool
    success_criteria: Dict[str, Any]

    # Error info
    error_message: Optional[str]

    # Recommendations
    recommendations: List[str]
```

### ComparisonResult Structure

```python
@dataclass
class ComparisonResult:
    baseline_metrics: TestMetrics
    candidate_metrics: TestMetrics

    # Deltas (candidate - baseline)
    success_rate_delta: float      # e.g., +0.10 = 10% improvement
    avg_duration_delta: float      # Seconds (negative = faster)
    p95_duration_delta: float

    # Statistical significance
    is_significant: bool
    confidence_level: float        # e.g., 0.95 = 95% confidence

    # Verdict
    is_improvement: bool           # True if candidate is better
    is_regression: bool            # True if candidate is worse
    meets_success_criteria: bool   # True if meets all criteria

    # Optional
    cost_delta: Optional[float]    # Cost difference
    p_value: Optional[float]       # Statistical p-value
    summary: str                   # Human-readable summary
    warnings: List[str]            # Any warnings
```

### TestMetrics Structure

```python
@dataclass
class TestMetrics:
    num_runs: int
    success_count: int
    failure_count: int
    success_rate: float           # 0.0 to 1.0
    avg_duration: float           # Average execution time
    p50_duration: float           # Median
    p95_duration: float           # 95th percentile
    p99_duration: float           # 99th percentile
    total_cost: Optional[float]   # Total LLM costs
    error_types: Dict[str, int]   # Error type counts
```

## Testing Process

The `HypothesisTesterNode` follows these steps:

### 1. Run Baseline Graph

Execute the baseline graph `num_baseline_runs` times:

```python
baseline_metrics = await self._run_baseline(
    graph=baseline_graph,
    num_runs=num_baseline_runs,
    test_inputs=test_inputs
)
```

**Collected Metrics**:
- Success/failure count
- Execution durations (avg, p50, p95, p99)
- Error types and frequencies
- Total costs (if tracking enabled)

### 2. Apply Changes

Apply hypothesis changes to create candidate graph:

```python
candidate_graph = await self._apply_changes(
    baseline_graph=baseline_graph,
    hypothesis=hypothesis
)
```

### 3. Run Candidate Graph

Execute the candidate graph `num_candidate_runs` times:

```python
candidate_metrics = await self._run_candidate(
    graph=candidate_graph,
    num_runs=num_candidate_runs,
    test_inputs=test_inputs
)
```

### 4. Compare Metrics

Calculate deltas and statistical significance:

```python
comparison = self._compare_metrics(
    baseline=baseline_metrics,
    candidate=candidate_metrics,
    confidence_level=confidence_level
)
```

**Comparison Metrics**:
- Success rate delta (candidate - baseline)
- Average duration delta
- P95 duration delta
- Cost delta (if available)
- Statistical significance (t-test, confidence interval)

### 5. Evaluate Success Criteria

Check if candidate meets all success criteria:

```python
meets_criteria = (
    comparison.success_rate_delta >= min_success_rate_improvement and
    comparison.avg_duration_delta <= max_latency_increase and
    comparison.is_significant and
    comparison.confidence_level >= min_confidence_level
)
```

### 6. Determine Status

Based on results:
- **PASSED**: Meets all success criteria and shows significant improvement
- **FAILED**: Fails success criteria or shows regression
- **INCONCLUSIVE**: Results not statistically significant
- **ERROR**: Testing encountered errors

## Statistical Analysis

### Significance Testing

The tester uses statistical methods to ensure results are significant:

**T-Test**: Compares means of baseline and candidate durations
- Null hypothesis: No difference between baseline and candidate
- Alternative hypothesis: Candidate is different from baseline
- Reject null if p-value < (1 - confidence_level)

**Confidence Intervals**: Calculate confidence intervals for deltas
- 95% confidence: We're 95% confident the true delta is in this range
- If confidence interval doesn't include 0, difference is significant

**Example**:
```
Baseline avg duration: 2.50s ± 0.30s (95% CI)
Candidate avg duration: 2.00s ± 0.25s (95% CI)
Delta: -0.50s ± 0.39s (95% CI)

Since CI doesn't include 0, improvement is statistically significant.
```

### Minimum Sample Size

For reliable statistics:
- **Minimum**: 10 runs per variant
- **Recommended**: 20+ runs per variant
- **High confidence**: 50+ runs per variant

Larger sample sizes increase:
- Statistical power (ability to detect real differences)
- Confidence in results
- Stability of metrics

## Complete Testing Example

```python
from spark.rsi import (
    PerformanceAnalyzerNode,
    HypothesisGeneratorNode,
    ChangeValidatorNode,
    HypothesisTesterNode
)
from spark.rsi.types import TestStatus
from spark.models.openai import OpenAIModel

# Phase 1: Analyze
analyzer = PerformanceAnalyzerNode()
analysis = await analyzer.run({'graph_id': 'prod_workflow'})
report = analysis['report']

# Phase 2: Generate & Validate
model = OpenAIModel(model_id="gpt-4o")
generator = HypothesisGeneratorNode(model=model, max_hypotheses=3)
gen_result = await generator.run({
    'diagnostic_report': report,
    'graph': production_graph
})

validator = ChangeValidatorNode(protected_nodes=["auth_node"])
approved_hypotheses = []

for hypothesis in gen_result['hypotheses']:
    val_result = await validator.run({
        'hypothesis': hypothesis,
        'graph': production_graph
    })
    if val_result['approved']:
        approved_hypotheses.append(hypothesis)

print(f"Testing {len(approved_hypotheses)} approved hypotheses...")

# Phase 3: Test
tester = HypothesisTesterNode(
    num_baseline_runs=30,
    num_candidate_runs=30,
    success_criteria={
        'min_success_rate_improvement': 0.05,
        'max_latency_increase': 0.1,
        'confidence_level': 0.95
    }
)

passed_hypotheses = []

for hypothesis in approved_hypotheses:
    print(f"\nTesting hypothesis {hypothesis.hypothesis_id}:")
    print(f"  Type: {hypothesis.hypothesis_type}")
    print(f"  Rationale: {hypothesis.rationale}")

    # Test hypothesis
    test_result_output = await tester.run({
        'hypothesis': hypothesis,
        'graph': production_graph
    })

    test_result = test_result_output['test_result']

    # Report results
    print(f"  Status: {test_result.status.value}")

    if test_result.comparison:
        comp = test_result.comparison
        print(f"  Baseline Success Rate: {comp.baseline_metrics.success_rate:.1%}")
        print(f"  Candidate Success Rate: {comp.candidate_metrics.success_rate:.1%}")
        print(f"  Success Rate Delta: {comp.success_rate_delta:+.1%}")
        print(f"  Baseline Avg Duration: {comp.baseline_metrics.avg_duration:.3f}s")
        print(f"  Candidate Avg Duration: {comp.candidate_metrics.avg_duration:.3f}s")
        print(f"  Duration Delta: {comp.avg_duration_delta:+.3f}s")
        print(f"  Statistically Significant: {comp.is_significant}")
        print(f"  Confidence Level: {comp.confidence_level:.1%}")

    if test_result.status == TestStatus.PASSED:
        print("  ✓ PASSED - Ready for deployment")
        passed_hypotheses.append({
            'hypothesis': hypothesis,
            'test_result': test_result
        })
    elif test_result.status == TestStatus.FAILED:
        print("  ✗ FAILED - Hypothesis rejected")
    elif test_result.status == TestStatus.INCONCLUSIVE:
        print("  ~ INCONCLUSIVE - Need more data")
        if test_result.recommendations:
            for rec in test_result.recommendations:
                print(f"    • {rec}")

print(f"\n{len(passed_hypotheses)} hypotheses passed testing")

# Proceed to Phase 4 (Deployment)
```

## Best Practices

### Test Configuration

1. **Sample Size**: Use 20-30 runs minimum for reliability
2. **Test Inputs**: Provide representative test inputs
3. **Success Criteria**: Set realistic thresholds based on goals
4. **Confidence Level**: Use 95% (0.95) for production changes
5. **Cost Tracking**: Enable if optimizing for costs

### Interpreting Results

1. **Statistical Significance**: Don't trust results without significance
2. **Effect Size**: Small improvements may not be worth deploying
3. **Variance**: High variance indicates need for more runs
4. **Regression**: Always check for performance regression
5. **Trade-offs**: Consider latency vs. accuracy vs. cost

### Test Reliability

1. **Stable Environment**: Test in consistent conditions
2. **Warm-up Runs**: Exclude first few runs if needed
3. **Outlier Handling**: Use percentiles (p95) not just averages
4. **Error Handling**: Track error types, not just counts
5. **Reproducibility**: Use same test inputs for baseline and candidate

## Troubleshooting

### Inconclusive Results

- Increase `num_baseline_runs` and `num_candidate_runs`
- Check for high variance in metrics
- Verify test inputs are representative
- Consider if improvement is too small to detect

### High Variance

- Add more test runs
- Use more consistent test inputs
- Check for external factors (network, API rate limits)
- Consider using percentiles instead of averages

### All Tests Failing

- Review success criteria (may be too strict)
- Check if hypotheses address real bottlenecks
- Verify baseline graph is running correctly
- Review hypothesis generation quality

## Next Steps

After testing hypotheses:

**Phase 4**: [Safe Deployment](phase4-deployment.md) - Deploy passed hypotheses with monitoring

## Related Documentation

- [Phase 2: Hypothesis Generation](phase2-hypothesis.md)
- [Phase 4: Safe Deployment](phase4-deployment.md)
- [RSI Overview](overview.md)
- [API Reference: RSI](../api/rsi.md)
