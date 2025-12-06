---
title: Phase 4. Safe Deployment
parent: RSI
nav_order: 4
---
# Phase 4: Safe Deployment

## Overview

Phase 4 implements safe deployment of tested hypotheses with continuous monitoring and automatic rollback capabilities. This phase ensures improvements are deployed safely to production.

**Key Components**:
- `ChangeApplicator`: Applies hypothesis changes to graph specifications
- `DeploymentControllerNode`: Orchestrates safe deployment with monitoring and rollback

## ChangeApplicator

Applies hypothesis changes to create new graph versions.

### Purpose

- Apply hypothesis changes to graph specifications
- Create new immutable graph versions
- Preserve audit trail of all changes
- Support multiple change types

### Usage

```python
from spark.rsi import ChangeApplicator
from spark.nodes.serde import graph_to_spec

applicator = ChangeApplicator()

# Get baseline spec
baseline_spec = graph_to_spec(production_graph)

# Apply hypothesis changes
candidate_spec = await applicator.apply_changes(
    baseline_spec=baseline_spec,
    hypothesis=approved_hypothesis
)

# candidate_spec is now a new version with changes applied
```

### Supported Change Types

- `node_config_update`: Update node configuration values
- `node_add`: Add new nodes to graph
- `node_remove`: Remove nodes from graph
- `edge_add`: Add new edges
- `edge_remove`: Remove edges
- `edge_modify`: Modify edge conditions

## DeploymentControllerNode

Orchestrates safe deployment with monitoring and rollback.

### Configuration

```python
from spark.rsi import DeploymentControllerNode, DeploymentConfig

deployment_config = DeploymentConfig(
    strategy="direct",                     # Deployment strategy
    monitoring_duration_seconds=300.0,     # Monitor for 5 minutes
    monitoring_interval_seconds=10.0,      # Check every 10 seconds
    max_error_rate_increase=0.5,          # Rollback if errors increase 50%
    max_latency_multiplier=2.0,           # Rollback if latency doubles
    min_success_rate=0.7                  # Rollback if success rate < 70%
)

controller = DeploymentControllerNode(
    deployment_config=deployment_config,
    experience_db=experience_db,
    enable_monitoring=True,
    enable_rollback=True
)
```

### Deployment Strategies

**Direct Deployment** (Phase 4):
- Immediate full deployment
- Suitable for low-risk changes
- Fastest deployment method
- Requires good monitoring

**Canary Deployment** (Phase 5+):
- Gradual rollout with staged traffic increases
- Start with 10% traffic, increase to 25%, 50%, 100%
- Stop and rollback if issues detected
- Best for medium-risk changes

**Shadow Deployment** (Phase 5+):
- Run alongside production without affecting output
- Compare results without user impact
- Validate in real conditions
- Best for high-risk changes

### DeploymentConfig

```python
@dataclass
class DeploymentConfig:
    strategy: str = "direct"
    monitoring_duration_seconds: float = 300.0
    monitoring_interval_seconds: float = 10.0

    # Rollback thresholds
    max_error_rate_increase: float = 0.5    # 50% increase
    max_latency_multiplier: float = 2.0      # 2x latency
    min_success_rate: float = 0.7            # Below 70%

    # Canary config (future)
    canary_percentage: float = 0.10
    canary_stages: list = [0.10, 0.25, 0.50, 1.0]
```

### Usage

```python
from spark.rsi import DeploymentControllerNode, DeploymentConfig
from spark.rsi.types import TestStatus

# Create deployment controller
deployment_config = DeploymentConfig(
    strategy="direct",
    monitoring_duration_seconds=300,
    max_error_rate_increase=0.3,
    max_latency_multiplier=1.5
)

controller = DeploymentControllerNode(
    deployment_config=deployment_config,
    experience_db=experience_db,
    enable_monitoring=True,
    enable_rollback=True
)

# Deploy tested hypothesis
result = await controller.run({
    'hypothesis': hypothesis,
    'test_result': test_result,
    'baseline_spec': baseline_spec
})

if result['success']:
    print("✓ Deployment successful")
    print(f"  Deployment ID: {result['deployment_id']}")
    print(f"  New version: {result['new_version']}")
    print(f"  Monitoring status: {result['monitoring_status']}")
else:
    print("✗ Deployment failed")
    print(f"  Reason: {result['error']}")
    if result.get('rolled_back'):
        print("  Rolled back to baseline")
```

### Deployment Process

1. **Validate Inputs**: Ensure hypothesis passed testing
2. **Apply Changes**: Create new graph version with changes
3. **Deploy**: Switch to new version
4. **Monitor**: Continuously monitor performance metrics
5. **Evaluate**: Check metrics against rollback thresholds
6. **Rollback (if needed)**: Automatically rollback on regression
7. **Record**: Store deployment outcome in experience database

### Monitoring Metrics

During monitoring period, the controller tracks:

- **Error Rate**: Percentage of failed executions
- **Latency**: Average and p95 execution times
- **Success Rate**: Percentage of successful executions
- **Throughput**: Requests per second
- **Resource Usage**: CPU, memory (if available)

### Rollback Triggers

Automatic rollback occurs if:

1. **Error Rate Increase**: Error rate increases beyond threshold
   ```python
   if current_error_rate > baseline_error_rate * (1 + max_error_rate_increase):
       rollback()
   ```

2. **Latency Increase**: Latency exceeds threshold
   ```python
   if current_latency > baseline_latency * max_latency_multiplier:
       rollback()
   ```

3. **Success Rate Drop**: Success rate falls below minimum
   ```python
   if current_success_rate < min_success_rate:
       rollback()
   ```

4. **Continuous Failures**: Too many consecutive failures
   ```python
   if consecutive_failures > failure_threshold:
       rollback()
   ```

### DeploymentRecord

The controller maintains deployment records:

```python
@dataclass
class DeploymentRecord:
    deployment_id: str
    hypothesis_id: str
    baseline_version: str
    deployed_version: str
    strategy: str
    started_at: datetime
    completed_at: datetime
    status: str  # 'in_progress', 'completed', 'failed', 'rolled_back'
    baseline_metrics: Dict[str, Any]
    deployed_metrics: Dict[str, Any]
    rollback_reason: Optional[str]
    error_message: Optional[str]
```

## Complete Deployment Example

```python
from spark.rsi import (
    HypothesisTesterNode,
    DeploymentControllerNode,
    DeploymentConfig,
    ExperienceDatabase
)
from spark.rsi.types import TestStatus
from spark.nodes.serde import graph_to_spec

# Assume we have a tested hypothesis
# test_result.status == TestStatus.PASSED

# Step 1: Get baseline specification
baseline_spec = graph_to_spec(production_graph)

# Step 2: Initialize experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Step 3: Configure deployment
deployment_config = DeploymentConfig(
    strategy="direct",
    monitoring_duration_seconds=600,  # 10 minutes
    monitoring_interval_seconds=15,
    max_error_rate_increase=0.3,      # 30% increase triggers rollback
    max_latency_multiplier=1.5,       # 1.5x latency triggers rollback
    min_success_rate=0.80             # < 80% triggers rollback
)

controller = DeploymentControllerNode(
    deployment_config=deployment_config,
    experience_db=experience_db,
    enable_monitoring=True,
    enable_rollback=True
)

# Step 4: Deploy
print(f"Deploying hypothesis {hypothesis.hypothesis_id}...")
print(f"  Type: {hypothesis.hypothesis_type}")
print(f"  Rationale: {hypothesis.rationale}")
print(f"  Expected improvement: {hypothesis.expected_improvement}")

deploy_result = await controller.run({
    'hypothesis': hypothesis,
    'test_result': test_result,
    'baseline_spec': baseline_spec
})

# Step 5: Check deployment result
if deploy_result['success']:
    print("\n✓ Deployment successful!")
    print(f"  Deployment ID: {deploy_result['deployment_id']}")
    print(f"  New version: {deploy_result['new_version']}")
    print(f"  Strategy: {deploy_result['strategy']}")
    print(f"  Monitoring duration: {deploy_result['monitoring_duration']}s")
    print(f"  Status: {deploy_result['status']}")

    if 'baseline_metrics' in deploy_result and 'deployed_metrics' in deploy_result:
        baseline = deploy_result['baseline_metrics']
        deployed = deploy_result['deployed_metrics']

        print("\n  Baseline vs Deployed:")
        print(f"    Error rate: {baseline['error_rate']:.1%} → {deployed['error_rate']:.1%}")
        print(f"    Avg latency: {baseline['avg_latency']:.3f}s → {deployed['avg_latency']:.3f}s")
        print(f"    Success rate: {baseline['success_rate']:.1%} → {deployed['success_rate']:.1%}")

    # Record lessons learned
    await experience_db.update_deployment_outcome(
        hypothesis_id=hypothesis.hypothesis_id,
        deployed=True,
        outcome=deploy_result,
        lessons=[
            f"Successfully deployed {hypothesis.hypothesis_type}",
            f"Impact: {hypothesis.expected_improvement}"
        ],
        patterns=[hypothesis.hypothesis_type.value]
    )

else:
    print("\n✗ Deployment failed")
    print(f"  Error: {deploy_result.get('error')}")

    if deploy_result.get('rolled_back'):
        print("\n  Rolled back to baseline")
        print(f"  Rollback reason: {deploy_result.get('rollback_reason')}")

        # Record failed deployment
        await experience_db.update_deployment_outcome(
            hypothesis_id=hypothesis.hypothesis_id,
            deployed=False,
            outcome=deploy_result,
            lessons=[
                f"Deployment failed: {deploy_result.get('rollback_reason')}",
                "Review hypothesis and success criteria"
            ],
            patterns=[]
        )
```

## Best Practices

### Deployment Configuration

1. **Start Conservative**: Use strict rollback thresholds initially
2. **Monitor Adequately**: At least 5-10 minutes for most changes
3. **Set Realistic Thresholds**: Based on baseline variability
4. **Test in Staging**: Deploy to staging environment first
5. **Off-Peak Deployment**: Deploy during low-traffic periods

### Monitoring Strategy

1. **Comprehensive Metrics**: Track multiple metrics, not just one
2. **Baseline Comparison**: Always compare against baseline
3. **Statistical Significance**: Ensure differences are significant
4. **Alert on Anomalies**: Set up alerts for unusual patterns
5. **Manual Review**: Have humans review HIGH risk deployments

### Rollback Strategy

1. **Automatic Rollback**: Enable for all deployments
2. **Fast Rollback**: Ensure rollback is quick (< 1 minute)
3. **Preserve Data**: Don't lose data during rollback
4. **Record Reasons**: Always record why rollback occurred
5. **Learn from Rollbacks**: Analyze and improve

## Troubleshooting

### Frequent Rollbacks

- Review rollback thresholds (may be too strict)
- Check baseline metrics for stability
- Verify test results were accurate
- Consider longer monitoring period
- Review hypothesis quality

### Slow Deployments

- Reduce `monitoring_duration_seconds`
- Increase `monitoring_interval_seconds`
- Optimize change application process
- Consider canary deployment for large changes

### Monitoring Not Working

- Verify telemetry is enabled
- Check telemetry backend connectivity
- Ensure metrics are being collected
- Review monitoring query logic

## Integration with Experience Database

The deployment controller integrates with the experience database to enable learning:

```python
# After successful deployment
await experience_db.update_deployment_outcome(
    hypothesis_id=hypothesis.hypothesis_id,
    deployed=True,
    outcome={
        'success': True,
        'deployment_id': deployment_id,
        'metrics': deployed_metrics
    },
    lessons=[
        "Prompt optimization improved accuracy by 15%",
        "No latency impact observed"
    ],
    patterns=[
        "prompt_optimization_success",
        "agent_accuracy_improvement"
    ]
)
```

This data feeds into Phase 5 (Pattern Extraction) for future improvements.

## Next Steps

After deploying hypotheses:

**Phase 5**: [Pattern Extraction](phase5-patterns.md) - Learn from deployment outcomes

## Related Documentation

- [Phase 3: Automated A/B Testing](phase3-testing.md)
- [Phase 5: Pattern Extraction](phase5-patterns.md)
- [RSI Overview](overview.md)
- [RSI Meta-Graph](meta-graph.md)
- [API Reference: RSI](../api/rsi.md)
