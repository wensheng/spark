# RSIMetaGraphConfig Reference

This document provides a complete reference for `RSIMetaGraphConfig`, the configuration class used to customize Recursive Self-Improvement (RSI) behavior in Spark.

## Overview

`RSIMetaGraphConfig` is a dataclass that controls RSI meta-graph behavior including analysis settings, hypothesis generation, testing parameters, deployment strategies, and safety thresholds. The RSI system enables graphs to autonomously analyze, improve, and deploy optimizations.

**Import**:
```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig
from spark.rsi import ExperienceDatabase
```

**Basic Usage**:
```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase
from spark.models.openai import OpenAIModel
from spark.graphs import Graph

# Create experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Create RSI configuration
config = RSIMetaGraphConfig(
    graph_id="production_workflow",
    graph_version="1.0.0",
    analysis_window_hours=24,
    max_hypotheses=3,
    deployment_strategy="canary"
)

# Create RSI meta-graph
model = OpenAIModel(model_id="gpt-4o")
rsi = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model
)

# Run improvement cycle
result = await rsi.run(target_graph=my_graph)
```

## Complete Field Reference

### Target Graph Configuration

#### `graph_id`

**Type**: `str` (required)
**Default**: None (must be provided)
**Description**: Identifier for the graph to improve.

**Usage**:
```python
config = RSIMetaGraphConfig(
    graph_id="ml_pipeline_v2",
    graph_version="1.0.0"
)
```

**Notes**:
- Used to identify telemetry data for analysis
- Must match the graph ID in telemetry records
- Used for tracking improvement history
- Should be unique per workflow

#### `graph_version`

**Type**: `str`
**Default**: `"1.0.0"`
**Description**: Current version of the target graph.

**Usage**:
```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    graph_version="2.3.1"
)
```

**Notes**:
- Follows semantic versioning convention
- Incremented with each successful deployment
- Used for rollback and version tracking
- Recorded in experience database

### Analysis Configuration

#### `analysis_window_hours`

**Type**: `int`
**Default**: `24`
**Description**: Hours of telemetry data to analyze for performance issues.

**Usage**:
```python
# Analyze last 24 hours (default)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24
)

# Analyze last 7 days
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=168  # 7 * 24
)

# Analyze last hour (for fast-changing workloads)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=1
)
```

**Notes**:
- Determines temporal scope of performance analysis
- Larger windows provide more data but may dilute recent trends
- Smaller windows detect recent issues faster
- Should align with workload patterns (daily, weekly)
- Requires sufficient telemetry data for meaningful analysis

**Example - Window Selection**:
```python
# Low-traffic workflow: analyze longer period
analysis_window_hours = 168  # 7 days

# High-traffic workflow: analyze recent period
analysis_window_hours = 6  # 6 hours

# Development: quick feedback
analysis_window_hours = 1  # 1 hour

# Production: standard period
analysis_window_hours = 24  # 1 day
```

### Hypothesis Generation Configuration

#### `max_hypotheses`

**Type**: `int`
**Default**: `3`
**Description**: Maximum number of improvement hypotheses to generate per cycle.

**Usage**:
```python
# Conservative: few focused hypotheses
config = RSIMetaGraphConfig(
    graph_id="workflow",
    max_hypotheses=1
)

# Balanced: multiple hypotheses
config = RSIMetaGraphConfig(
    graph_id="workflow",
    max_hypotheses=3
)

# Aggressive: many hypotheses
config = RSIMetaGraphConfig(
    graph_id="workflow",
    max_hypotheses=10
)
```

**Notes**:
- Controls breadth vs. depth of improvement exploration
- More hypotheses = more testing overhead
- Fewer hypotheses = more focused improvements
- Consider testing infrastructure capacity
- Balance with `max_steps` to avoid excessive iteration

**Example - Hypothesis Count Strategies**:
```python
# Early optimization: explore many options
max_hypotheses = 10

# Mature system: focused improvements
max_hypotheses = 2

# Critical system: single safe improvement
max_hypotheses = 1

# Experimental: broad exploration
max_hypotheses = 20
```

#### `hypothesis_types`

**Type**: `List[str]`
**Default**: `["prompt_optimization"]`
**Description**: Types of hypotheses to consider.

**Usage**:
```python
# Only prompt optimizations (safe, low-risk)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    hypothesis_types=["prompt_optimization"]
)

# Prompt and config changes
config = RSIMetaGraphConfig(
    graph_id="workflow",
    hypothesis_types=["prompt_optimization", "config_change"]
)

# All improvement types (requires Phase 6)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    hypothesis_types=[
        "prompt_optimization",
        "config_change",
        "node_replacement",
        "edge_optimization",
        "parallelization"
    ]
)
```

**Available Hypothesis Types**:

| Type | Description | Risk Level | Phase |
|------|-------------|------------|-------|
| `prompt_optimization` | Improve system/user prompts | Low | 2+ |
| `config_change` | Modify node configurations | Medium | 2+ |
| `node_replacement` | Replace nodes with better alternatives | High | 6+ |
| `edge_optimization` | Optimize graph topology | Medium | 6+ |
| `parallelization` | Convert sequential to parallel | High | 6+ |
| `model_upgrade` | Switch to better/cheaper models | Medium | 6+ |

**Notes**:
- Start with low-risk types (prompt optimization)
- Gradually add higher-risk types as confidence grows
- Structural changes (node replacement, parallelization) require Phase 6
- Some types require additional validation

**Example - Progressive Enabling**:
```python
# Phase 1: Start safe
hypothesis_types = ["prompt_optimization"]

# Phase 2: Add configuration
hypothesis_types = ["prompt_optimization", "config_change"]

# Phase 3: Add structural changes
hypothesis_types = [
    "prompt_optimization",
    "config_change",
    "edge_optimization"
]

# Phase 4: Full autonomy
hypothesis_types = [
    "prompt_optimization",
    "config_change",
    "node_replacement",
    "edge_optimization",
    "parallelization",
    "model_upgrade"
]
```

### Learning Configuration

#### `enable_pattern_learning`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to use pattern-based learning from experience database.

**Usage**:
```python
# Enable pattern learning (default)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    enable_pattern_learning=True
)

# Disable pattern learning (fresh start)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    enable_pattern_learning=False
)
```

**Notes**:
- When `True`, learns from historical successes and failures
- Improves hypothesis quality over time
- Requires populated experience database
- Disable for clean-slate experimentation
- See [Pattern Learning](../rsi/pattern-learning.md) for details

**Pattern Learning Benefits**:
- **Better Hypotheses**: Learn which types of changes succeed
- **Faster Convergence**: Avoid previously failed approaches
- **Context-Aware**: Apply lessons from similar graphs
- **Continuous Improvement**: Gets smarter with each cycle

### Deployment Configuration

#### `deployment_strategy`

**Type**: `str`
**Default**: `"direct"`
**Description**: Strategy for deploying validated hypotheses.

**Usage**:
```python
# Direct deployment (immediate full deployment)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    deployment_strategy="direct"
)

# Canary deployment (gradual rollout)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    deployment_strategy="canary"
)

# Shadow deployment (parallel without impact)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    deployment_strategy="shadow"
)
```

**Deployment Strategies**:

| Strategy | Description | Risk | Speed | Use Case |
|----------|-------------|------|-------|----------|
| `direct` | Immediate full deployment | High | Fast | Low-risk changes, development |
| `canary` | Gradual traffic increase | Low | Slow | Production, critical systems |
| `shadow` | Run parallel, no impact | Very Low | Slow | High-risk changes, validation |
| `blue-green` | Full environment swap | Medium | Fast | Zero-downtime deployments |

**Direct Deployment**:
```python
# Best for: Development, low-risk changes
deployment_strategy = "direct"

# Characteristics:
# - Immediate deployment
# - No gradual rollout
# - Fast feedback
# - Higher risk
```

**Canary Deployment**:
```python
# Best for: Production, critical systems
deployment_strategy = "canary"

# Characteristics:
# - Gradual traffic increase (10%, 25%, 50%, 100%)
# - Monitor at each stage
# - Automatic rollback on issues
# - Lower risk, slower rollout
```

**Shadow Deployment**:
```python
# Best for: High-risk changes, validation
deployment_strategy = "shadow"

# Characteristics:
# - Runs in parallel with production
# - No user impact
# - Compare outputs
# - Very safe, resource-intensive
```

**Notes**:
- Start with `"direct"` for low-risk environments
- Use `"canary"` for production deployments
- Use `"shadow"` for high-risk structural changes
- Strategy affects deployment duration and resource usage

#### `auto_deploy`

**Type**: `bool`
**Default**: `True`
**Description**: Whether to automatically deploy successful hypotheses.

**Usage**:
```python
# Automatic deployment (default)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    auto_deploy=True
)

# Manual deployment (require approval)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    auto_deploy=False
)
```

**Notes**:
- When `True`, deployments happen automatically after successful testing
- When `False`, hypotheses stop at testing phase (manual deployment)
- Disable for human review of high-risk changes
- Use with `enable_human_review` for additional safety

**Example - Deployment Control**:
```python
# Full automation (development)
auto_deploy = True

# Semi-automation (production with review)
auto_deploy = True
enable_human_review = True  # Requires approval for high-risk changes

# Manual control (critical systems)
auto_deploy = False  # All deployments require manual action
```

### Testing Configuration

Testing parameters are configured via individual RSI components (not top-level RSIMetaGraphConfig), but can be influenced by:

#### `enable_mock_mode`

**Type**: `bool`
**Default**: `False`
**Description**: Use mock hypothesis generation and testing (for testing RSI system itself).

**Usage**:
```python
# Production mode (default)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    enable_mock_mode=False
)

# Testing mode (mock LLM and testing)
config = RSIMetaGraphConfig(
    graph_id="workflow",
    enable_mock_mode=True
)
```

**Notes**:
- When `True`, uses mock components instead of real LLM and tests
- Useful for testing RSI infrastructure without API costs
- Not for production use
- Faster feedback during RSI development

## DeploymentConfig Reference

The `deployment_strategy` field references `DeploymentConfig` which provides detailed deployment control:

**Import**:
```python
from spark.rsi.deployment_controller import DeploymentConfig
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | str | "direct" | Deployment strategy (direct, canary, shadow) |
| `monitoring_duration_seconds` | float | 300.0 | How long to monitor after deployment |
| `monitoring_interval_seconds` | float | 10.0 | How often to check metrics |
| `max_error_rate_increase` | float | 0.5 | Error rate increase that triggers rollback (50%) |
| `max_latency_multiplier` | float | 2.0 | Latency multiplier that triggers rollback (2x) |
| `min_success_rate` | float | 0.7 | Minimum success rate (70%) |
| `canary_percentage` | float | 0.10 | Initial canary traffic percentage |
| `canary_stages` | list | [0.10, 0.25, 0.50, 1.0] | Canary rollout stages |

**Usage**:
```python
from spark.rsi.deployment_controller import DeploymentControllerNode, DeploymentConfig

# Custom deployment configuration
deployment_config = DeploymentConfig(
    strategy="canary",
    monitoring_duration_seconds=600.0,  # 10 minutes
    monitoring_interval_seconds=30.0,  # Check every 30 seconds
    max_error_rate_increase=0.3,  # 30% increase triggers rollback
    max_latency_multiplier=1.5,  # 1.5x latency triggers rollback
    min_success_rate=0.9,  # 90% success rate required
    canary_stages=[0.05, 0.10, 0.25, 0.50, 1.0]  # More gradual rollout
)

# Use in RSI meta-graph (requires custom RSIMetaGraph construction)
controller = DeploymentControllerNode(
    deployment_config=deployment_config
)
```

**Notes**:
- Deployment config is typically used internally by RSI meta-graph
- Can be customized for specific deployment requirements
- Rollback thresholds should be tuned based on workload characteristics

## Complete Configuration Example

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase
from spark.models.openai import OpenAIModel
from spark.graphs import Graph

# Create experience database for learning
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Production RSI configuration
config = RSIMetaGraphConfig(
    # Target graph
    graph_id="ml_pipeline",
    graph_version="2.1.0",

    # Analysis settings
    analysis_window_hours=24,  # Analyze last 24 hours

    # Hypothesis generation
    max_hypotheses=3,  # Generate up to 3 hypotheses
    hypothesis_types=[
        "prompt_optimization",  # Safe improvements
        "config_change"  # Medium-risk improvements
    ],

    # Learning
    enable_pattern_learning=True,  # Learn from history

    # Deployment
    deployment_strategy="canary",  # Gradual rollout
    auto_deploy=True,  # Automatic deployment

    # Testing/Development
    enable_mock_mode=False  # Use real LLM and testing
)

# Create RSI meta-graph
model = OpenAIModel(model_id="gpt-4o")
rsi = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model
)

# Run single improvement cycle
result = await rsi.run(target_graph=production_graph)

if result['success']:
    print(f"Deployed {result.get('hypotheses_deployed', 0)} improvements")
else:
    print(f"RSI failed: {result.get('error')}")

# Or run continuous improvement
results = await rsi.run_continuous(
    interval_seconds=3600,  # Every hour
    max_iterations=None  # Run indefinitely
)
```

## Configuration Patterns

### Development Configuration

```python
# Fast iteration, safe changes only
config = RSIMetaGraphConfig(
    graph_id="dev_workflow",
    graph_version="0.1.0",
    analysis_window_hours=1,  # Short window
    max_hypotheses=5,  # Explore broadly
    hypothesis_types=["prompt_optimization"],  # Safe only
    enable_pattern_learning=False,  # Start fresh
    deployment_strategy="direct",  # Fast deployment
    auto_deploy=True,
    enable_mock_mode=True  # Fast testing
)
```

### Staging Configuration

```python
# Realistic testing, moderate safety
config = RSIMetaGraphConfig(
    graph_id="staging_workflow",
    graph_version="1.0.0",
    analysis_window_hours=12,
    max_hypotheses=3,
    hypothesis_types=[
        "prompt_optimization",
        "config_change"
    ],
    enable_pattern_learning=True,
    deployment_strategy="canary",
    auto_deploy=True,
    enable_mock_mode=False
)
```

### Production Configuration

```python
# Safe, gradual improvements
config = RSIMetaGraphConfig(
    graph_id="prod_workflow",
    graph_version="2.0.0",
    analysis_window_hours=24,  # Full day
    max_hypotheses=2,  # Focused improvements
    hypothesis_types=["prompt_optimization"],  # Safest only
    enable_pattern_learning=True,
    deployment_strategy="canary",  # Gradual rollout
    auto_deploy=True,
    enable_mock_mode=False
)
```

### Aggressive Optimization

```python
# Maximum autonomy (Phase 6+)
config = RSIMetaGraphConfig(
    graph_id="experimental_workflow",
    graph_version="1.0.0",
    analysis_window_hours=24,
    max_hypotheses=10,  # Many options
    hypothesis_types=[
        "prompt_optimization",
        "config_change",
        "node_replacement",
        "edge_optimization",
        "parallelization",
        "model_upgrade"
    ],
    enable_pattern_learning=True,
    deployment_strategy="shadow",  # Safe exploration
    auto_deploy=False,  # Manual review
    enable_mock_mode=False
)
```

## Progressive RSI Adoption

### Phase 1: Analysis Only

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=0,  # No hypotheses yet
    auto_deploy=False
)
```

### Phase 2: Generate and Validate

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization"],
    auto_deploy=False  # Manual review
)
```

### Phase 3: Automated Testing

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization"],
    auto_deploy=False  # Still manual deployment
)
```

### Phase 4: Automated Deployment

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization"],
    deployment_strategy="canary",
    auto_deploy=True  # Full automation
)
```

### Phase 5: Pattern Learning

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization", "config_change"],
    enable_pattern_learning=True,  # Learn from history
    deployment_strategy="canary",
    auto_deploy=True
)
```

### Phase 6: Structural Optimization

```python
config = RSIMetaGraphConfig(
    graph_id="workflow",
    analysis_window_hours=24,
    max_hypotheses=5,
    hypothesis_types=[
        "prompt_optimization",
        "config_change",
        "node_replacement",
        "edge_optimization",
        "parallelization"
    ],
    enable_pattern_learning=True,
    deployment_strategy="shadow",  # Safe for structural changes
    auto_deploy=True
)
```

## Safety Considerations

### Risk Mitigation

```python
# Conservative configuration for critical systems
config = RSIMetaGraphConfig(
    graph_id="critical_workflow",

    # Limited scope
    max_hypotheses=1,  # One change at a time
    hypothesis_types=["prompt_optimization"],  # Safest changes only

    # Manual controls
    auto_deploy=False,  # Require approval

    # Safe deployment
    deployment_strategy="shadow",  # No user impact

    # Long monitoring
    # (via DeploymentConfig)
    # monitoring_duration_seconds=1800.0  # 30 minutes
)
```

### Monitoring and Alerting

```python
# Ensure comprehensive monitoring
config = RSIMetaGraphConfig(
    graph_id="workflow",

    # Enable telemetry
    # (via Graph configuration, not RSI config)

    # Conservative thresholds
    # (via DeploymentConfig)
    # max_error_rate_increase=0.1  # 10% increase max
    # max_latency_multiplier=1.2   # 1.2x latency max
    # min_success_rate=0.95        # 95% success required
)
```

## Validation

RSIMetaGraphConfig validates during `__post_init__()` (currently minimal validation):

**Current Validation**:
- Field types checked by dataclass
- Default values applied

**Best Practices**:
- Ensure `graph_id` matches telemetry records
- Keep `max_hypotheses` reasonable (1-10)
- Use `"direct"` deployment cautiously in production
- Start with safe `hypothesis_types` and expand gradually

## Usage with RSIMetaGraph

```python
# Create RSI meta-graph
rsi = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model,
    telemetry_manager=telemetry_manager  # Optional
)

# Run single cycle
result = await rsi.run(
    target_graph=my_graph,
    target_graph_spec=graph_spec  # Optional
)

# Run continuously
results = await rsi.run_continuous(
    target_graph=my_graph,
    interval_seconds=3600,  # Every hour
    max_iterations=24  # Run for 24 hours
)
```

## See Also

- [RSI Guide](../rsi/rsi.md) - RSI architecture and workflow
- [Performance Analysis](../rsi/performance-analysis.md) - Analysis phase
- [Hypothesis Generation](../rsi/hypothesis-generation.md) - Generation phase
- [Hypothesis Testing](../rsi/hypothesis-testing.md) - Testing phase
- [Deployment Strategies](../rsi/deployment.md) - Deployment phase
- [Pattern Learning](../rsi/pattern-learning.md) - Learning system
- [Experience Database](../rsi/experience-db.md) - Historical data storage
- [Telemetry Configuration](telemetry-config.md) - Telemetry setup for RSI
