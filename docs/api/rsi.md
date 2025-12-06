---
title: RSI Classes
parent: API
nav_order: 6
---
# RSI Classes

This document provides comprehensive API reference for Spark's RSI (Recursive Self-Improvement) system. These classes enable autonomous graph optimization through performance analysis, hypothesis generation, automated testing, safe deployment, and continuous learning.

## Table of Contents

- [Overview](#overview)
- [RSI Meta-Graph](#rsi-meta-graph)
  - [RSIMetaGraph](#rsimetagraph)
  - [RSIMetaGraphConfig](#rsimetagraphconfig)
- [Phase 1: Performance Analysis](#phase-1-performance-analysis)
  - [PerformanceAnalyzerNode](#performanceanalyzernode)
  - [GraphIntrospector](#graphintrospector)
  - [ExperienceDatabase](#experiencedatabase)
- [Phase 2: Hypothesis Generation & Validation](#phase-2-hypothesis-generation--validation)
  - [HypothesisGeneratorNode](#hypothesisgeneratornode)
  - [ChangeValidatorNode](#changevalidatornode)
- [Phase 3: Automated Testing](#phase-3-automated-testing)
  - [HypothesisTesterNode](#hypothesistesternode)
- [Phase 4: Deployment](#phase-4-deployment)
  - [ChangeApplicator](#changeapplicator)
  - [DeploymentControllerNode](#deploymentcontrollernode)
  - [DeploymentConfig](#deploymentconfig)
- [Phase 5: Pattern Learning](#phase-5-pattern-learning)
  - [PatternExtractor](#patternextractor)
- [Phase 6: Advanced Optimization](#phase-6-advanced-optimization)
  - [NodeReplacementAnalyzer](#nodereplacementanalyzer)
  - [EdgeOptimizer](#edgeoptimizer)
  - [ParallelizationAnalyzer](#parallelizationanalyzer)
  - [HumanReviewNode](#humanreviewnode)
  - [GraphDiffer](#graphdiffer)
  - [MultiObjectiveOptimizer](#multiobjectiveoptimizer)
- [Data Types](#data-types)
- [CLI Tools](#cli-tools)

---

## Overview

The RSI system implements a complete feedback loop for autonomous graph improvement:

1. **Phase 1**: Analyze performance and identify bottlenecks
2. **Phase 2**: Generate and validate improvement hypotheses
3. **Phase 3**: Test hypotheses with statistical A/B testing
4. **Phase 4**: Deploy successful changes with monitoring and rollback
5. **Phase 5**: Extract patterns from historical improvements
6. **Phase 6**: Apply structural optimizations (node replacement, edge optimization, parallelization)

**Key Principles**:
- **Immutable Versions**: Graphs are never modified in-place
- **Safety First**: Multiple validation layers prevent unsafe changes
- **Observable**: Every decision and change is tracked
- **Reversible**: Automatic rollback on performance regression
- **Incremental**: Start simple (prompts), expand to structural changes

---

## RSI Meta-Graph

### RSIMetaGraph

**Module**: `spark.rsi.rsi_meta_graph`

### Overview

`RSIMetaGraph` orchestrates the complete RSI workflow as a graph that connects all RSI components. It manages the continuous improvement loop and can run in single-cycle or continuous modes.

### Class Signature

```python
class RSIMetaGraph:
    """RSI Meta-Graph for autonomous graph improvement."""
```

### Constructor

```python
def __init__(
    self,
    config: RSIMetaGraphConfig,
    experience_db: Optional[ExperienceDatabase] = None,
    model: Optional[Any] = None,
    **kwargs
) -> None
```

**Parameters**:
- `config`: RSIMetaGraphConfig with settings for the improvement loop
- `experience_db`: ExperienceDatabase for learning from history
- `model`: LLM model for hypothesis generation (OpenAIModel or BedrockModel)
- `**kwargs`: Additional configuration options

### Key Methods

#### `run_single_cycle()`

Run a single improvement cycle: analyze → generate → validate → test → deploy.

```python
async def run_single_cycle(
    self,
    target_graph: Optional[Graph] = None
) -> Dict[str, Any]
```

**Returns**: Dict with improvements deployed and cycle results

#### `run_continuous_improvement()`

Run continuous improvement loop until stopped.

```python
async def run_continuous_improvement(
    self,
    target_graph: Optional[Graph] = None,
    max_cycles: Optional[int] = None
) -> Dict[str, Any]
```

**Parameters**:
- `target_graph`: Optional graph to improve
- `max_cycles`: Maximum cycles to run (None for infinite)

**Returns**: Dict with total improvements and cycle history

### Example

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase
from spark.models.openai import OpenAIModel
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Enable telemetry on production graph
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)
production_graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Run production graph to collect telemetry
for i in range(100):
    await production_graph.run()

# Create experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Create RSI meta-graph
model = OpenAIModel(model_id="gpt-4o")
config = RSIMetaGraphConfig(
    graph_id="production_workflow",
    graph_version="1.0.0",
    max_hypotheses=3,
    enable_pattern_learning=True,
    deployment_strategy="canary"
)

rsi = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model
)

# Run single improvement cycle
result = await rsi.run_single_cycle()
if result['improvements_deployed']:
    print(f"Deployed {result['num_improvements']} improvements")

# Or run continuous improvement
result = await rsi.run_continuous_improvement(max_cycles=10)
```

---

### RSIMetaGraphConfig

**Module**: `spark.rsi.rsi_meta_graph`

### Overview

Configuration dataclass for RSI meta-graph with analysis, generation, testing, and deployment settings.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `graph_id` | `str` | - | ID of the graph to improve (required) |
| `graph_version` | `str` | `"1.0.0"` | Current version of the graph |
| `analysis_window_hours` | `int` | `24` | Hours of telemetry to analyze |
| `max_hypotheses` | `int` | `3` | Maximum hypotheses to generate |
| `hypothesis_types` | `List[str]` | `["prompt_optimization"]` | Types of hypotheses to consider |
| `enable_pattern_learning` | `bool` | `True` | Use pattern-based learning |
| `deployment_strategy` | `str` | `"direct"` | Deployment strategy (direct, canary) |
| `auto_deploy` | `bool` | `True` | Auto-deploy successful hypotheses |
| `enable_mock_mode` | `bool` | `False` | Use mock generation/testing |

---

## Phase 1: Performance Analysis

### PerformanceAnalyzerNode

**Module**: `spark.rsi.performance_analyzer`

**Inheritance**: `Node`

### Overview

Analyzes telemetry data to identify performance bottlenecks and failure patterns. Queries the telemetry system to aggregate metrics and generate diagnostic reports.

### Constructor

```python
def __init__(
    self,
    name: str = "PerformanceAnalyzer",
    analysis_window_hours: int = 24,
    min_executions: int = 10,
    **kwargs
) -> None
```

**Parameters**:
- `name`: Node name
- `analysis_window_hours`: Hours of historical data to analyze
- `min_executions`: Minimum executions needed for reliable analysis
- `**kwargs`: Additional node configuration

### Process Method

```python
async def process(self, context: ExecutionContext) -> Dict[str, Any]
```

**Expected Inputs**:
- `graph_id`: ID of graph to analyze (required)
- `graph_version`: Version tag (optional)
- `start_time`: Override start time (optional)
- `end_time`: Override end time (optional)

**Returns**:
- `has_issues`: bool indicating if issues found
- `report`: DiagnosticReport with bottlenecks and failure patterns
- `reason`: str if no analysis performed

### Example

```python
from spark.rsi import PerformanceAnalyzerNode

analyzer = PerformanceAnalyzerNode(
    analysis_window_hours=24,
    min_executions=10
)

result = await analyzer.run({'graph_id': 'my_graph'})
if result['has_issues']:
    report = result['report']
    print(f"Found {len(report.bottlenecks)} bottlenecks")
    for bottleneck in report.bottlenecks:
        print(f"  - {bottleneck.node_name}: {bottleneck.severity}")
```

---

### GraphIntrospector

**Module**: `spark.rsi.introspection`

### Overview

Introspects graph structure and complexity to provide insights for optimization opportunities. Analyzes node depth, branching factors, cycles, and critical paths.

### Constructor

```python
def __init__(self, graph: BaseGraph) -> None
```

### Key Methods

#### `get_complexity_metrics()`

Get graph complexity metrics.

```python
def get_complexity_metrics(self) -> Dict[str, Any]
```

**Returns**: Dict with max_depth, branching_factor, num_nodes, num_edges, has_cycles, etc.

#### `get_critical_path()`

Identify the critical path through the graph.

```python
def get_critical_path(self) -> List[str]
```

**Returns**: List of node IDs on the critical path

#### `get_spec()`

Get GraphSpec representation of the graph.

```python
def get_spec(self, spark_version: str = "2.0") -> GraphSpec
```

---

### ExperienceDatabase

**Module**: `spark.rsi.experience_db`

### Overview

Stores learning data from improvement attempts including hypotheses, test results, deployment outcomes, and lessons learned. Provides query API for pattern extraction.

### Constructor

```python
def __init__(self, db_path: str = ":memory:") -> None
```

**Parameters**:
- `db_path`: Path to SQLite database (":memory:" for in-memory)

### Key Methods

#### `initialize()`

Initialize database schema.

```python
async def initialize(self) -> None
```

#### `record_hypothesis()`

Record a generated hypothesis.

```python
async def record_hypothesis(
    self,
    hypothesis: ImprovementHypothesis,
    context: Dict[str, Any]
) -> None
```

#### `record_test_result()`

Record test results for a hypothesis.

```python
async def record_test_result(
    self,
    hypothesis_id: str,
    test_result: TestResult
) -> None
```

#### `record_deployment()`

Record deployment outcome.

```python
async def record_deployment(
    self,
    hypothesis_id: str,
    deployment_record: DeploymentRecord
) -> None
```

#### `query_hypotheses()`

Query hypotheses by filters.

```python
async def query_hypotheses(
    self,
    hypothesis_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100
) -> List[ImprovementHypothesis]
```

---

## Phase 2: Hypothesis Generation & Validation

### HypothesisGeneratorNode

**Module**: `spark.rsi.hypothesis_generator`

**Inheritance**: `Node`

### Overview

Generates improvement hypotheses using LLM reasoning based on diagnostic reports and learned patterns. Proposes changes like prompt optimization, config tuning, and structural modifications.

### Constructor

```python
def __init__(
    self,
    model: Optional[Any] = None,
    name: str = "HypothesisGenerator",
    max_hypotheses: int = 3,
    hypothesis_types: Optional[List[str]] = None,
    pattern_extractor: Optional[PatternExtractor] = None,
    experience_db: Optional[ExperienceDatabase] = None,
    enable_pattern_learning: bool = True,
    node_replacement_analyzer: Optional[Any] = None,
    edge_optimizer: Optional[Any] = None,
    parallelization_analyzer: Optional[Any] = None,
    enable_structural_improvements: bool = True,
    **kwargs
) -> None
```

**Parameters**:
- `model`: LLM model for hypothesis generation (OpenAIModel or BedrockModel)
- `max_hypotheses`: Maximum number of hypotheses to generate
- `hypothesis_types`: Types to generate (default: ["prompt_optimization"])
- `enable_pattern_learning`: Use patterns from experience database
- `enable_structural_improvements`: Enable Phase 6 structural optimizations
- Analyzers for structural improvements (Phase 6)

### Process Method

```python
async def process(self, context: ExecutionContext) -> Dict[str, Any]
```

**Expected Inputs**:
- `diagnostic_report`: DiagnosticReport (required)
- `graph`: Graph object (optional, for introspection)
- `introspector`: GraphIntrospector (optional)

**Returns**:
- `hypotheses`: List[ImprovementHypothesis]
- `count`: int
- `generation_method`: str (llm or mock)
- `patterns_used`: List[ExtractedPattern] (if pattern learning enabled)

### Example

```python
from spark.rsi import HypothesisGeneratorNode
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")
generator = HypothesisGeneratorNode(
    model=model,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization", "parameter_tuning"],
    enable_pattern_learning=True,
    experience_db=experience_db
)

result = await generator.run({
    'diagnostic_report': report,
    'graph': graph
})

hypotheses = result['hypotheses']
for hyp in hypotheses:
    print(f"{hyp.hypothesis_type}: {hyp.rationale}")
```

---

### ChangeValidatorNode

**Module**: `spark.rsi.change_validator`

**Inheritance**: `Node`

### Overview

Validates improvement hypotheses for safety and correctness before testing. Applies multiple validation rules to ensure proposed changes won't break the graph or violate constraints.

### Constructor

```python
def __init__(
    self,
    name: str = "ChangeValidator",
    max_nodes_added: int = 5,
    max_nodes_removed: int = 2,
    max_prompt_length: int = 10000,
    protected_nodes: Optional[List[str]] = None,
    allowed_hypothesis_types: Optional[List[str]] = None,
    auto_approve_risk_threshold: float = 0.3,
    **kwargs
) -> None
```

**Parameters**:
- `max_nodes_added`: Maximum nodes that can be added
- `max_nodes_removed`: Maximum nodes that can be removed
- `max_prompt_length`: Maximum prompt length
- `protected_nodes`: List of protected node IDs/names
- `allowed_hypothesis_types`: Allowed hypothesis types
- `auto_approve_risk_threshold`: Risk threshold for auto-approval (0.0-1.0)

### Process Method

```python
async def process(self, context: ExecutionContext) -> Dict[str, Any]
```

**Expected Inputs**:
- `hypothesis`: ImprovementHypothesis (required)
- `graph`: Graph object (optional)
- `introspector`: GraphIntrospector (optional)

**Returns**:
- `validation`: ValidationResult
- `approved`: bool
- `risk_score`: float
- `risk_level`: str

### Example

```python
from spark.rsi import ChangeValidatorNode

validator = ChangeValidatorNode(
    max_nodes_added=5,
    max_nodes_removed=2,
    protected_nodes=["authentication", "payment"],
    auto_approve_risk_threshold=0.3
)

result = await validator.run({
    'hypothesis': hypothesis,
    'graph': graph
})

if result['approved']:
    print(f"Hypothesis approved with risk score {result['risk_score']:.2f}")
else:
    print(f"Hypothesis rejected: {result['validation'].violations}")
```

---

## Phase 3: Automated Testing

### HypothesisTesterNode

**Module**: `spark.rsi.hypothesis_tester`

**Inheritance**: `Node`

### Overview

Tests improvement hypotheses through automated A/B testing. Runs baseline and candidate graphs multiple times, collects metrics, and performs statistical comparison.

### Constructor

```python
def __init__(
    self,
    name: str = "HypothesisTester",
    num_baseline_runs: int = 20,
    num_candidate_runs: int = 20,
    success_criteria: Optional[Dict[str, Any]] = None,
    confidence_level: float = 0.95,
    enable_mock_mode: bool = False,
    **kwargs
) -> None
```

**Parameters**:
- `num_baseline_runs`: Number of times to run baseline graph
- `num_candidate_runs`: Number of times to run candidate graph
- `success_criteria`: Dict of success criteria for improvements
- `confidence_level`: Statistical confidence level (e.g., 0.95 for 95%)
- `enable_mock_mode`: Use mock testing without running graphs

### Process Method

```python
async def process(self, context: ExecutionContext) -> Dict[str, Any]
```

**Expected Inputs**:
- `hypothesis`: ImprovementHypothesis (required)
- `graph`: BaseGraph (required)
- `test_inputs`: Optional list of test inputs

**Returns**:
- `test_result`: TestResult with metrics and comparison
- `status`: str (TestStatus enum value)
- `passed`: bool
- `is_improvement`: bool

### Success Criteria

Default success criteria:
```python
{
    'min_success_rate_improvement': 0.0,  # Any improvement
    'max_latency_increase': 0.2,  # 20% increase tolerated
    'min_confidence_level': 0.95  # 95% confidence required
}
```

### Example

```python
from spark.rsi import HypothesisTesterNode

tester = HypothesisTesterNode(
    num_baseline_runs=20,
    num_candidate_runs=20,
    success_criteria={
        'min_success_rate_improvement': 0.05,  # 5% improvement required
        'max_latency_increase': 0.1,  # 10% increase tolerated
        'confidence_level': 0.95
    }
)

result = await tester.run({
    'hypothesis': hypothesis,
    'graph': graph
})

test_result = result['test_result']
if test_result.status == TestStatus.PASSED:
    print(f"Hypothesis passed with {test_result.comparison.improvement_percentage:.1f}% improvement")
else:
    print(f"Hypothesis failed: {test_result.failure_reason}")
```

---

## Phase 4: Deployment

### ChangeApplicator

**Module**: `spark.rsi.change_applicator`

### Overview

Applies hypothesis changes to graph specifications to create new versions. Supports prompt updates, config changes, and node replacements while maintaining immutability.

### Key Methods

#### `apply_hypothesis()`

Apply hypothesis changes to a graph specification.

```python
def apply_hypothesis(
    self,
    baseline_spec: GraphSpec,
    hypothesis: ImprovementHypothesis
) -> GraphSpec
```

**Parameters**:
- `baseline_spec`: Current graph specification
- `hypothesis`: Hypothesis with changes to apply

**Returns**: New GraphSpec with changes applied

**Raises**: `ValueError` if changes cannot be applied

### Example

```python
from spark.rsi import ChangeApplicator
from spark.nodes.serde import graph_to_spec

applicator = ChangeApplicator()

# Get current graph spec
baseline_spec = graph_to_spec(current_graph)

# Apply hypothesis
new_spec = applicator.apply_hypothesis(baseline_spec, hypothesis)

# new_spec is a new immutable version
```

---

### DeploymentControllerNode

**Module**: `spark.rsi.deployment_controller`

**Inheritance**: `Node`

### Overview

Deploys tested hypotheses with monitoring and automatic rollback. Supports multiple deployment strategies and records outcomes to the experience database.

### Constructor

```python
def __init__(
    self,
    name: str = "DeploymentController",
    deployment_config: Optional[DeploymentConfig] = None,
    experience_db: Optional[ExperienceDatabase] = None,
    enable_monitoring: bool = True,
    enable_rollback: bool = True,
    **kwargs
) -> None
```

**Parameters**:
- `deployment_config`: DeploymentConfig with strategy and thresholds
- `experience_db`: ExperienceDatabase for recording outcomes
- `enable_monitoring`: Monitor post-deployment performance
- `enable_rollback`: Enable automatic rollback on regression

### Process Method

```python
async def process(self, context: ExecutionContext) -> Dict[str, Any]
```

**Expected Inputs**:
- `hypothesis`: ImprovementHypothesis to deploy (required)
- `test_result`: TestResult from testing (required)
- `baseline_spec`: Current graph specification (optional)

**Returns**:
- `success`: bool
- `deployment_record`: DeploymentRecord
- `rolled_back`: bool
- `rollback_reason`: Optional[str]

### Example

```python
from spark.rsi import DeploymentControllerNode, DeploymentConfig

config = DeploymentConfig(
    strategy="direct",
    monitoring_duration_seconds=300,  # 5 minutes
    max_error_rate_increase=0.5,  # 50% increase triggers rollback
    max_latency_multiplier=2.0  # 2x latency triggers rollback
)

controller = DeploymentControllerNode(
    deployment_config=config,
    experience_db=experience_db,
    enable_monitoring=True,
    enable_rollback=True
)

result = await controller.run({
    'hypothesis': hypothesis,
    'test_result': test_result,
    'baseline_spec': baseline_spec
})

if result['success']:
    print(f"Deployment successful: {result['deployment_record'].deployed_version}")
elif result['rolled_back']:
    print(f"Rolled back: {result['rollback_reason']}")
```

---

### DeploymentConfig

**Module**: `spark.rsi.deployment_controller`

### Overview

Configuration dataclass for deployment with strategy, monitoring, and rollback settings.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | `str` | `"direct"` | Deployment strategy (direct, canary, shadow) |
| `monitoring_duration_seconds` | `float` | `300.0` | How long to monitor (5 minutes) |
| `monitoring_interval_seconds` | `float` | `10.0` | Check interval (10 seconds) |
| `max_error_rate_increase` | `float` | `0.5` | 50% error rate increase triggers rollback |
| `max_latency_multiplier` | `float` | `2.0` | 2x latency triggers rollback |
| `min_success_rate` | `float` | `0.7` | Below 70% success triggers rollback |
| `canary_percentage` | `float` | `0.10` | Start with 10% traffic for canary |
| `canary_stages` | `List[float]` | `[0.10, 0.25, 0.50, 1.0]` | Canary rollout stages |

---

## Phase 5: Pattern Learning

### PatternExtractor

**Module**: `spark.rsi.pattern_extractor`

### Overview

Learns from historical improvement attempts by extracting successful patterns and anti-patterns. Provides recommendations for future hypotheses based on what has worked.

### Constructor

```python
def __init__(self, experience_db: ExperienceDatabase) -> None
```

### Key Methods

#### `extract_patterns()`

Extract patterns from experience database.

```python
async def extract_patterns(
    self,
    min_occurrences: int = 3,
    min_success_rate: float = 0.7
) -> List[ExtractedPattern]
```

**Parameters**:
- `min_occurrences`: Minimum times pattern must occur
- `min_success_rate`: Minimum success rate (0.0-1.0)

**Returns**: List of ExtractedPattern objects

#### `get_recommendations()`

Get recommendations for a diagnostic report.

```python
async def get_recommendations(
    self,
    diagnostic_report: DiagnosticReport
) -> List[str]
```

**Returns**: List of recommendation strings based on patterns

### Example

```python
from spark.rsi import PatternExtractor

extractor = PatternExtractor(experience_db)

# Extract patterns
patterns = await extractor.extract_patterns(
    min_occurrences=3,
    min_success_rate=0.7
)

for pattern in patterns:
    print(f"Pattern: {pattern.pattern_type}")
    print(f"  Success rate: {pattern.success_rate:.1%}")
    print(f"  Occurrences: {pattern.occurrences}")

# Get recommendations for a report
recommendations = await extractor.get_recommendations(diagnostic_report)
for rec in recommendations:
    print(f"  - {rec}")
```

---

## Phase 6: Advanced Optimization

### NodeReplacementAnalyzer

**Module**: `spark.rsi.node_replacement`

### Overview

Identifies opportunities to replace nodes with more efficient alternatives. Considers semantic equivalence, performance characteristics, and suggests LLM model upgrades or caching strategies.

### Key Methods

#### `analyze()`

Analyze graph for node replacement opportunities.

```python
async def analyze(
    self,
    graph: BaseGraph,
    diagnostic_report: DiagnosticReport
) -> List[NodeReplacementSuggestion]
```

---

### EdgeOptimizer

**Module**: `spark.rsi.edge_optimizer`

### Overview

Optimizes graph topology by identifying shortcut opportunities, redundant paths, unnecessary branches, and edge condition simplifications.

### Key Methods

#### `analyze()`

Analyze graph for edge optimization opportunities.

```python
async def analyze(
    self,
    graph: BaseGraph
) -> List[EdgeOptimizationSuggestion]
```

---

### ParallelizationAnalyzer

**Module**: `spark.rsi.parallelization_analyzer`

### Overview

Identifies opportunities to convert sequential execution to parallel where safe. Analyzes node dependencies and data flow to detect independent operations.

### Key Methods

#### `analyze()`

Analyze graph for parallelization opportunities.

```python
async def analyze(
    self,
    graph: BaseGraph
) -> List[ParallelizationSuggestion]
```

---

### HumanReviewNode

**Module**: `spark.rsi.human_review`

**Inheritance**: `Node`

### Overview

Integrates human-in-the-loop review for high-risk changes. Presents changes for review and captures human feedback.

### Process Method

Expected inputs:
- `hypothesis`: ImprovementHypothesis (required)
- `risk_score`: float (required)
- `require_approval_threshold`: float (default: 0.7)

Returns:
- `approved`: bool
- `feedback`: Optional[str]
- `reviewer`: Optional[str]

---

### GraphDiffer

**Module**: `spark.rsi.graph_differ`

### Overview

Visualizes graph changes in multiple formats (text, JSON, HTML) for review and audit. Shows side-by-side comparison of baseline vs candidate.

### Key Methods

#### `diff()`

Generate diff between two graph specifications.

```python
def diff(
    self,
    baseline_spec: GraphSpec,
    candidate_spec: GraphSpec,
    format: str = "text"
) -> str
```

**Parameters**:
- `baseline_spec`: Original graph specification
- `candidate_spec`: Modified graph specification
- `format`: Output format ("text", "json", "html")

**Returns**: Formatted diff string

---

### MultiObjectiveOptimizer

**Module**: `spark.rsi.multi_objective_optimizer`

### Overview

Balances competing objectives (latency, cost, quality, reliability) when ranking hypotheses. Uses multi-objective scoring to identify Pareto-optimal solutions.

### Key Methods

#### `rank_hypotheses()`

Rank hypotheses using multi-objective optimization.

```python
def rank_hypotheses(
    self,
    hypotheses: List[ImprovementHypothesis],
    objectives: Dict[str, float]
) -> List[Tuple[ImprovementHypothesis, float]]
```

**Parameters**:
- `hypotheses`: List of hypotheses to rank
- `objectives`: Dict mapping objective names to weights

**Returns**: List of (hypothesis, score) tuples sorted by score

**Example Objectives**:
```python
objectives = {
    'latency': 0.4,    # 40% weight
    'cost': 0.3,       # 30% weight
    'quality': 0.2,    # 20% weight
    'reliability': 0.1  # 10% weight
}
```

---

## Data Types

### ImprovementHypothesis

**Module**: `spark.rsi.types`

Structured hypothesis proposing a specific improvement to the graph.

**Key Fields**:
- `hypothesis_id`: Unique identifier
- `hypothesis_type`: HypothesisType enum (prompt_optimization, parameter_tuning, etc.)
- `target_node_id`: Node to modify
- `proposed_change`: ChangeSpec with specific changes
- `rationale`: Explanation of why this should improve performance
- `expected_improvement`: ExpectedImprovement with metrics
- `risk_level`: RiskLevel enum (LOW, MEDIUM, HIGH, CRITICAL)

### DiagnosticReport

**Module**: `spark.rsi.types`

Comprehensive performance analysis report.

**Key Fields**:
- `graph_id`: Graph identifier
- `analysis_period`: AnalysisPeriod with time range
- `performance_summary`: PerformanceSummary with aggregate metrics
- `bottlenecks`: List[Bottleneck]
- `failure_patterns`: List[FailurePattern]
- `recommendations`: List[str]

### TestResult

**Module**: `spark.rsi.types`

Results from A/B testing a hypothesis.

**Key Fields**:
- `test_id`: Unique test identifier
- `hypothesis_id`: Hypothesis being tested
- `status`: TestStatus enum (PASSED, FAILED, INCONCLUSIVE)
- `baseline_metrics`: TestMetrics
- `candidate_metrics`: TestMetrics
- `comparison`: ComparisonResult with statistical analysis
- `confidence_level`: float

### ValidationResult

**Module**: `spark.rsi.types`

Results from validating a hypothesis.

**Key Fields**:
- `approved`: bool
- `risk_score`: float (0.0-1.0)
- `risk_level`: RiskLevel enum
- `violations`: List[ValidationViolation]

---

## CLI Tools

### review_cli

**Module**: `spark.rsi.review_cli`

Command-line interface for reviewing pending hypotheses.

**Commands**:

```bash
# List pending hypotheses
python -m spark.rsi.review_cli list

# Review specific hypothesis
python -m spark.rsi.review_cli review <hypothesis_id>

# Approve hypothesis
python -m spark.rsi.review_cli approve <hypothesis_id>

# Reject hypothesis
python -m spark.rsi.review_cli reject <hypothesis_id> --reason "..."
```

---

## Complete Example

```python
from spark.rsi import (
    RSIMetaGraph,
    RSIMetaGraphConfig,
    ExperienceDatabase,
    PerformanceAnalyzerNode,
)
from spark.models.openai import OpenAIModel
from spark.telemetry import TelemetryConfig
from spark.graphs import Graph

# Step 1: Enable telemetry on production graph
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="telemetry.db",
    sampling_rate=1.0
)
production_graph = Graph(start=my_node, telemetry_config=telemetry_config)

# Step 2: Run production graph to collect telemetry
for i in range(100):
    await production_graph.run()

# Step 3: Analyze performance (optional - meta-graph does this automatically)
analyzer = PerformanceAnalyzerNode()
result = await analyzer.run({
    'graph_id': 'production_workflow',
    'graph_version': '1.0.0'
})

if result['has_issues']:
    print(f"Found {len(result['report'].bottlenecks)} bottlenecks")

# Step 4: Set up RSI meta-graph for continuous improvement
experience_db = ExperienceDatabase()
await experience_db.initialize()

model = OpenAIModel(model_id="gpt-4o")
config = RSIMetaGraphConfig(
    graph_id="production_workflow",
    graph_version="1.0.0",
    analysis_window_hours=24,
    min_executions=50,
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization", "parameter_tuning"],
    enable_pattern_learning=True,
    deployment_strategy="canary"
)

rsi_graph = RSIMetaGraph(
    config=config,
    experience_db=experience_db,
    model=model
)

# Step 5: Run continuous improvement
result = await rsi_graph.run_continuous_improvement(
    target_graph=production_graph,
    max_cycles=10
)

print(f"Completed {result['total_cycles']} improvement cycles")
print(f"Deployed {result['total_improvements']} improvements")
```

---

## Best Practices

1. **Start Simple**: Begin with prompt optimization only, expand to structural changes later
2. **Collect Data**: Run production graph for sufficient time to collect meaningful telemetry
3. **Set Thresholds**: Configure appropriate risk thresholds and success criteria
4. **Monitor Closely**: Use monitoring and automatic rollback to prevent regressions
5. **Learn from History**: Enable pattern learning to improve over time
6. **Human Review**: Require human review for high-risk changes
7. **Incremental Deployment**: Use canary deployment for safer rollouts
8. **Track Everything**: Record all attempts to the experience database
9. **Balance Objectives**: Use multi-objective optimization when trading off latency vs cost vs quality
10. **Version Everything**: Maintain immutable versions for easy rollback
