---
title: RSI Meta-Graph
parent: RSI
nav_order: 7
---
# RSI Meta-Graph

## Overview

The RSI Meta-Graph is a complete autonomous workflow orchestration system that connects all RSI phases into a continuous improvement loop. It provides both single-cycle and continuous improvement modes.

## Architecture

The RSI Meta-Graph connects all RSI components with gate nodes controlling flow:

```
PerformanceAnalyzer → AnalysisGate → HypothesisGenerator → ChangeValidator
  → ValidationGate → HypothesisTester → TestGate → DeploymentController
```

### Gate Nodes

**AnalysisGate**:
- Checks if performance analysis found issues
- Continues if bottlenecks or failures detected
- Stops if no issues found (no optimization needed)

**ValidationGate**:
- Filters to only approved hypotheses
- Continues if at least one hypothesis approved
- Stops if all hypotheses rejected

**TestGate**:
- Filters to only hypotheses that passed testing
- Continues if at least one test passed
- Stops if all tests failed

## Configuration

```python
from spark.rsi import RSIMetaGraphConfig

config = RSIMetaGraphConfig(
    # Target graph
    graph_id="production_workflow",
    graph_version="1.0.0",

    # Analysis configuration
    analysis_window_hours=24,

    # Hypothesis generation
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization"],

    # Learning
    enable_pattern_learning=True,

    # Deployment
    deployment_strategy="direct",
    auto_deploy=True,

    # Testing
    enable_mock_mode=False
)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `graph_id` | str | Required | ID of graph to improve |
| `graph_version` | str | "1.0.0" | Current graph version |
| `analysis_window_hours` | int | 24 | Hours of telemetry to analyze |
| `max_hypotheses` | int | 3 | Max hypotheses per cycle |
| `hypothesis_types` | List[str] | ["prompt_optimization"] | Types to generate |
| `enable_pattern_learning` | bool | True | Use historical patterns |
| `deployment_strategy` | str | "direct" | Deployment strategy |
| `auto_deploy` | bool | True | Auto-deploy successful tests |
| `enable_mock_mode` | bool | False | Use mock mode for testing |

## Usage

### Single Cycle

Run RSI loop once:

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase
from spark.models.openai import OpenAIModel
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Enable telemetry
telemetry_config = TelemetryConfig.create_sqlite("telemetry.db")
production_graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Run production graph to collect data
for i in range(100):
    await production_graph.run()

# Initialize experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Configure RSI
model = OpenAIModel(model_id="gpt-4o")
config = RSIMetaGraphConfig(
    graph_id="production_workflow",
    max_hypotheses=5,
    hypothesis_types=["prompt_optimization", "parameter_tuning"]
)

# Create RSI meta-graph
rsi_graph = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model
)

# Run single cycle
result = await rsi_graph.run(target_graph=production_graph)

if result['success']:
    print(f"✓ RSI cycle completed")
    print(f"  Hypotheses deployed: {result.get('hypotheses_deployed', 0)}")
```

### Continuous Mode

Run RSI loop continuously:

```python
# Run continuously every hour
results = await rsi_graph.run_continuous(
    target_graph=production_graph,
    interval_seconds=3600,      # 1 hour
    max_iterations=None         # Run forever
)

# Or with iteration limit
results = await rsi_graph.run_continuous(
    target_graph=production_graph,
    interval_seconds=3600,
    max_iterations=24           # Run for 24 hours
)

# Review results
total_deployments = sum(r.get('hypotheses_deployed', 0) for r in results)
print(f"Total deployments: {total_deployments}")
```

### Result Structure

```python
{
    'success': bool,
    'graph_id': str,
    'graph_version': str,
    'hypotheses_deployed': int,        # If deployments occurred
    'deployments': List[Dict],         # Deployment details
    'error': str                       # If failed
}
```

## Execution Flow

### Step 1: Performance Analysis

```python
analyzer = PerformanceAnalyzerNode(
    analysis_window_hours=config.analysis_window_hours
)
```

Analyzes telemetry to detect bottlenecks and issues.

**Output**: `DiagnosticReport` with bottlenecks and failures

### Step 2: Analysis Gate

```python
if not has_issues:
    return {'should_continue': False, 'reason': 'No issues found'}
```

Stops if no issues detected.

### Step 3: Hypothesis Generation

```python
generator = HypothesisGeneratorNode(
    model=model,
    max_hypotheses=config.max_hypotheses,
    hypothesis_types=config.hypothesis_types
)
```

Generates improvement hypotheses using LLM.

**Output**: List of `ImprovementHypothesis`

### Step 4: Validation

```python
validator = ChangeValidatorNode(
    allowed_hypothesis_types=config.hypothesis_types
)
```

Validates each hypothesis for safety.

**Output**: List of `ValidationResult`

### Step 5: Validation Gate

```python
approved = [h for h, v in zip(hypotheses, validations) if v.approved]
if not approved:
    return {'should_continue': False, 'reason': 'No hypotheses approved'}
```

Filters to approved hypotheses.

### Step 6: Testing

```python
tester = HypothesisTesterNode()
```

A/B tests each approved hypothesis.

**Output**: List of `TestResult`

### Step 7: Test Gate

```python
passed = [r for r in test_results if r.status == TestStatus.PASSED]
if not passed:
    return {'should_continue': False, 'reason': 'No tests passed'}
```

Filters to passed tests.

### Step 8: Deployment

```python
deployer = DeploymentControllerNode(
    deployment_config=DeploymentConfig(strategy=config.deployment_strategy)
)
```

Deploys passed hypotheses with monitoring.

**Output**: List of `DeploymentRecord`

## Complete Example with All Phases

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase
from spark.models.openai import OpenAIModel
from spark.telemetry import TelemetryConfig, TelemetryManager
from spark.graphs import Graph

# Production graph with telemetry
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="production_telemetry.db",
    sampling_rate=1.0
)

production_graph = Graph(
    start=my_start_node,
    telemetry_config=telemetry_config
)

# Run production graph
print("Running production graph to collect telemetry...")
for i in range(100):
    result = await production_graph.run()
print(f"Collected telemetry from 100 executions")

# Initialize RSI system
experience_db = ExperienceDatabase()
await experience_db.initialize()

model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True
)

# Configure all RSI phases
rsi_config = RSIMetaGraphConfig(
    # Target
    graph_id="production_workflow",
    graph_version="1.0.0",

    # Phase 1: Analysis
    analysis_window_hours=24,

    # Phase 2: Hypothesis Generation
    max_hypotheses=5,
    hypothesis_types=[
        "prompt_optimization",
        "parameter_tuning",
        "node_replacement"
    ],

    # Phase 5: Pattern Learning
    enable_pattern_learning=True,

    # Phase 4: Deployment
    deployment_strategy="direct",
    auto_deploy=True
)

# Create RSI meta-graph
rsi_graph = RSIMetaGraph(
    config=rsi_config,
    experience_db=experience_db,
    model=model,
    telemetry_manager=TelemetryManager.get_instance()
)

# Single improvement cycle
print("\n=== Single RSI Cycle ===")
result = await rsi_graph.run(target_graph=production_graph)

if result['success']:
    print(f"✓ RSI cycle completed")
    if 'deployments' in result:
        print(f"\nDeployed {result['hypotheses_deployed']} improvements:")
        for deployment in result['deployments']:
            print(f"  - {deployment.get('hypothesis_id')}")
else:
    print(f"✗ RSI cycle failed: {result.get('error')}")

# Continuous improvement (24 hours)
print("\n=== Continuous RSI (24 hours) ===")
results = await rsi_graph.run_continuous(
    target_graph=production_graph,
    interval_seconds=3600,  # Every hour
    max_iterations=24
)

# Analyze continuous results
successful_iterations = sum(1 for r in results if r['success'])
total_deployments = sum(r.get('hypotheses_deployed', 0) for r in results)

print(f"\nContinuous RSI Summary:")
print(f"  Total iterations: {len(results)}")
print(f"  Successful iterations: {successful_iterations}")
print(f"  Total deployments: {total_deployments}")
print(f"  Avg deployments/iteration: {total_deployments/len(results):.2f}")

# Query experience database for learning
successful_hypotheses = await experience_db.get_successful_hypotheses(
    graph_id="production_workflow"
)
print(f"\n  Total successful hypotheses in DB: {len(successful_hypotheses)}")
```

## Best Practices

### Configuration

1. **Start Conservative**:
   - Begin with `hypothesis_types=["prompt_optimization"]`
   - Use `max_hypotheses=3`
   - Set `auto_deploy=False` initially

2. **Expand Gradually**:
   - Add hypothesis types after confidence builds
   - Increase `max_hypotheses` as system matures
   - Enable `auto_deploy` for LOW risk types

3. **Monitor Actively**:
   - Review RSI outcomes regularly
   - Track deployment success rates
   - Monitor experience database growth
   - Alert on RSI failures

### Continuous Mode

1. **Appropriate Intervals**:
   - 1-6 hours for active development
   - 6-24 hours for stable production
   - Avoid < 30 minutes (too frequent)

2. **Resource Management**:
   - Monitor LLM API costs
   - Track compute resource usage
   - Set appropriate rate limits
   - Use caching to reduce costs

3. **Stop Conditions**:
   - Set `max_iterations` for controlled runs
   - Implement external stop signals
   - Monitor for degradation
   - Have manual override capability

### Safety

1. **Protected Nodes**:
   - Always configure protected nodes
   - Protect critical business logic
   - Protect authentication/security nodes
   - Review protection list regularly

2. **Human Review**:
   - Enable for HIGH risk hypotheses
   - Set appropriate review thresholds
   - Train reviewers on architecture
   - Document review criteria

3. **Rollback Capability**:
   - Enable automatic rollback
   - Test rollback procedures
   - Monitor post-deployment metrics
   - Keep rollback history

## Troubleshooting

### RSI Stops Early

**Symptoms**: RSI completes but deploys nothing

**Causes**:
- No issues found in analysis (gate stops)
- All hypotheses rejected (validation gate stops)
- All tests failed (test gate stops)

**Solutions**:
```python
# Check analysis results
analyzer_result = await analyzer.run({'graph_id': 'production_workflow'})
print(f"Has issues: {analyzer_result['has_issues']}")
print(f"Bottlenecks: {len(analyzer_result.get('report', {}).get('bottlenecks', []))}")

# Lower validation thresholds
validator = ChangeValidatorNode(
    auto_approve_risk_threshold=0.5  # Higher threshold
)

# Review test success criteria
tester = HypothesisTesterNode(
    success_criteria={
        'min_success_rate_improvement': 0.0  # Accept any improvement
    }
)
```

### No Continuous Improvement

**Symptoms**: First iteration succeeds, subsequent iterations find no issues

**Causes**:
- Telemetry not updating between iterations
- Analysis window too short
- Issues already fixed

**Solutions**:
```python
# Ensure production graph continues running
# Run in background while RSI operates

# Increase analysis window
config = RSIMetaGraphConfig(
    analysis_window_hours=48  # Longer window
)

# Add delay between iterations
await rsi_graph.run_continuous(
    interval_seconds=7200  # 2 hours
)
```

### High LLM Costs

**Symptoms**: RSI costs are high

**Solutions**:
```python
# Enable caching
model = OpenAIModel(
    model_id="gpt-4o",
    enable_cache=True,
    cache_ttl_seconds=86400  # 24 hours
)

# Use cheaper model
model = OpenAIModel(
    model_id="gpt-4o-mini"  # Cheaper alternative
)

# Reduce max_hypotheses
config = RSIMetaGraphConfig(
    max_hypotheses=2  # Fewer hypotheses
)

# Increase interval
await rsi_graph.run_continuous(
    interval_seconds=7200  # Less frequent
)
```

## Monitoring

### Key Metrics to Track

1. **RSI Success Rate**: Percentage of successful cycles
2. **Hypotheses per Cycle**: Average hypotheses generated
3. **Approval Rate**: Percentage of hypotheses approved
4. **Test Pass Rate**: Percentage of tests passed
5. **Deployment Success Rate**: Percentage of successful deployments
6. **Improvement Impact**: Aggregate performance improvement
7. **LLM Costs**: Total API costs
8. **Cycle Duration**: Time per RSI cycle

### Alerting

Set up alerts for:
- RSI cycle failures
- Low hypothesis approval rates
- All tests failing
- Deployment failures or rollbacks
- High LLM costs
- Long cycle durations

## Next Steps

- Review [Phase 1-6 documentation](overview.md) for component details
- Set up [RSI CLI](cli.md) for hypothesis review
- Configure [telemetry](../telemetry/overview.md) for RSI
- Review [API reference](../api/rsi.md) for advanced usage

## Related Documentation

- [RSI Overview](overview.md)
- [Phase 1: Performance Analysis](phase1-analysis.md)
- [Phase 2: Hypothesis Generation](phase2-hypothesis.md)
- [Phase 3: Automated A/B Testing](phase3-testing.md)
- [Phase 4: Safe Deployment](phase4-deployment.md)
- [Phase 5: Pattern Extraction](phase5-patterns.md)
- [Phase 6: Advanced Optimization](phase6-advanced.md)
- [RSI CLI & Tools](cli.md)
- [API Reference: RSI](../api/rsi.md)
