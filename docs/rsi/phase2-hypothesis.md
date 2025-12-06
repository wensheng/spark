---
title: Phase 2. Hypothesis Generation & Validation
parent: RSI
nav_order: 2
---
# Phase 2: Hypothesis Generation & Validation

## Overview

Phase 2 uses LLM reasoning to generate improvement hypotheses from diagnostic reports and validates them for safety before testing. This phase transforms performance analysis into actionable improvement proposals.

**Key Components**:
- `HypothesisGeneratorNode`: Uses LLMs to generate evidence-based improvement hypotheses
- `ChangeValidatorNode`: Validates hypotheses for safety and correctness

## HypothesisGeneratorNode

Generates improvement hypotheses using LLM reasoning based on diagnostic reports.

### Configuration

```python
from spark.rsi import HypothesisGeneratorNode
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o")

generator = HypothesisGeneratorNode(
    model=model,
    name="HypothesisGenerator",
    max_hypotheses=3,
    hypothesis_types=["prompt_optimization"],
    enable_pattern_learning=True,
    experience_db=experience_db  # Optional: for pattern-based learning
)
```

**Parameters**:
- `model` (Model): LLM model for hypothesis generation (OpenAIModel or BedrockModel)
- `max_hypotheses` (int): Maximum number of hypotheses to generate per run. Default: 3.
- `hypothesis_types` (List[str]): Types of hypotheses to generate. Default: `["prompt_optimization"]`.
- `enable_pattern_learning` (bool): Use patterns from experience database. Default: True.
- `experience_db` (ExperienceDatabase): Optional experience database for learning
- `pattern_extractor` (PatternExtractor): Optional pattern extractor instance

**Supported Hypothesis Types**:
- `prompt_optimization`: Improve agent/LLM prompts
- `parameter_tuning`: Adjust node parameters
- `node_replacement`: Replace nodes with better alternatives (Phase 6)
- `edge_modification`: Optimize graph edges (Phase 6)
- `parallelization`: Convert sequential to parallel (Phase 6)
- `caching`: Add caching strategies
- `tool_addition`: Add new tools to agents
- `custom`: Custom improvements

### Usage

```python
from spark.rsi import HypothesisGeneratorNode, PerformanceAnalyzerNode
from spark.models.openai import OpenAIModel

# Step 1: Analyze performance
analyzer = PerformanceAnalyzerNode()
analysis_result = await analyzer.run({
    'graph_id': 'production_workflow',
    'graph_version': '1.0.0'
})

report = analysis_result['report']

# Step 2: Generate hypotheses
model = OpenAIModel(model_id="gpt-4o")
generator = HypothesisGeneratorNode(
    model=model,
    max_hypotheses=3
)

result = await generator.run({
    'diagnostic_report': report,
    'graph': production_graph,
    'graph_spec': graph_spec  # Optional
})

# Step 3: Review generated hypotheses
for hypothesis in result['hypotheses']:
    print(f"\nHypothesis: {hypothesis.hypothesis_id}")
    print(f"Type: {hypothesis.hypothesis_type}")
    print(f"Rationale: {hypothesis.rationale}")
    print(f"Risk Level: {hypothesis.risk_level}")
    print(f"Expected Improvement: {hypothesis.expected_improvement}")
    print(f"Changes: {len(hypothesis.changes)}")
```

### Input Format

```python
{
    'diagnostic_report': DiagnosticReport,  # Required: from Phase 1
    'graph': Graph,                          # Optional: for introspection
    'graph_spec': GraphSpec,                 # Optional: graph specification
    'introspector': GraphIntrospector       # Optional: custom introspector
}
```

### Output Format

```python
{
    'hypotheses': List[ImprovementHypothesis],
    'count': int,
    'generation_method': str,  # 'llm' or 'mock'
    'patterns_used': List[ExtractedPattern]  # If pattern learning enabled
}
```

### ImprovementHypothesis Structure

```python
@dataclass
class ImprovementHypothesis:
    hypothesis_id: str
    graph_id: str
    graph_version_baseline: str
    hypothesis_type: HypothesisType
    target_node: Optional[str]

    # Reasoning
    rationale: str
    diagnostic_evidence: Dict[str, Any]

    # Expected outcomes
    expected_improvement: ExpectedImprovement

    # Changes to apply
    changes: List[ChangeSpec]

    # Risk assessment
    risk_level: RiskLevel
    risk_factors: List[str]

    # Metadata
    created_at: datetime
    created_by: str
```

### ChangeSpec Structure

Specifies an individual change to apply:

```python
@dataclass
class ChangeSpec:
    type: str                    # Type of change
    target_node_id: str          # Node to modify
    config_path: str             # Path to config value
    old_value: Any               # Current value
    new_value: Any               # Proposed value
    additional_params: Dict
```

**Common Change Types**:
- `node_config_update`: Update node configuration
- `node_add`: Add new node
- `node_remove`: Remove node
- `edge_add`: Add edge
- `edge_remove`: Remove edge
- `edge_modify`: Modify edge condition

### Pattern-Based Learning

When `enable_pattern_learning=True` and `experience_db` is provided, the generator uses historical success patterns:

```python
# Generator learns from past successes
generator = HypothesisGeneratorNode(
    model=model,
    enable_pattern_learning=True,
    experience_db=experience_db
)

# Patterns influence hypothesis generation
result = await generator.run({
    'diagnostic_report': report,
    'graph': graph
})

# See which patterns were used
for pattern in result['patterns_used']:
    print(f"Pattern: {pattern.name}")
    print(f"Success Rate: {pattern.success_rate:.1%}")
    print(f"Avg Improvement: {pattern.avg_improvement:.2f}")
```

## ChangeValidatorNode

Validates hypotheses for safety and correctness before testing.

### Configuration

```python
from spark.rsi import ChangeValidatorNode

validator = ChangeValidatorNode(
    name="ChangeValidator",
    max_nodes_added=5,
    max_nodes_removed=2,
    max_prompt_length=10000,
    protected_nodes=["authentication", "payment"],
    allowed_hypothesis_types=["prompt_optimization", "parameter_tuning"],
    auto_approve_risk_threshold=0.3
)
```

**Parameters**:
- `max_nodes_added` (int): Maximum nodes that can be added. Default: 5.
- `max_nodes_removed` (int): Maximum nodes that can be removed. Default: 2.
- `max_prompt_length` (int): Maximum prompt length in characters. Default: 10000.
- `protected_nodes` (List[str]): Node IDs/names that cannot be modified.
- `allowed_hypothesis_types` (List[str]): Allowed hypothesis types.
- `auto_approve_risk_threshold` (float): Risk score threshold for auto-approval (0.0-1.0). Default: 0.3.

### Usage

```python
from spark.rsi import ChangeValidatorNode

# Create validator with safety rules
validator = ChangeValidatorNode(
    max_nodes_added=3,
    max_nodes_removed=1,
    protected_nodes=["critical_auth_node", "payment_gateway"],
    allowed_hypothesis_types=["prompt_optimization"]
)

# Validate hypothesis
result = await validator.run({
    'hypothesis': hypothesis,
    'graph': production_graph
})

# Check validation result
if result['approved']:
    print(f"✓ Hypothesis approved (risk: {result['risk_level']})")
    print(f"  Risk score: {result['risk_score']:.2f}")
else:
    print(f"✗ Hypothesis rejected")
    for violation in result['validation'].violations:
        print(f"  - {violation.message}")
```

### Validation Rules

The validator applies multiple safety checks:

#### 1. Hypothesis Type Check
- Verifies hypothesis type is in `allowed_hypothesis_types`
- Rejects unsupported types

#### 2. Protected Node Check
- Ensures protected nodes are not modified or removed
- Checks all change specs for protected node references

#### 3. Structural Limits
- Enforces `max_nodes_added` limit
- Enforces `max_nodes_removed` limit
- Prevents excessive structural changes

#### 4. Prompt Length Check
- Validates prompt length ≤ `max_prompt_length`
- Prevents token limit issues with LLM APIs

#### 5. Type Compatibility Check
- Verifies type compatibility for parameter changes
- Checks value types match configuration schemas

#### 6. Semantic Preservation
- Ensures changes don't break graph semantics
- Validates edge conditions remain valid
- Checks input/output compatibility

### ValidationResult Structure

```python
@dataclass
class ValidationResult:
    approved: bool                       # Overall approval status
    risk_level: RiskLevel               # LOW, MEDIUM, HIGH, CRITICAL
    risk_score: float                    # 0.0 to 1.0+ (higher = riskier)
    violations: List[ValidationViolation]  # Rule violations
    recommendations: List[str]           # Improvement suggestions
```

### ValidationViolation Structure

```python
@dataclass
class ValidationViolation:
    rule: str              # Rule that was violated
    severity: str          # 'error' or 'warning'
    message: str           # Human-readable message
    details: Dict[str, Any]  # Additional context
```

### Risk Assessment

Risk score is calculated based on:
- Number of nodes added/removed: +0.1 per node
- Structural changes: +0.2 for topology modifications
- Protected node proximity: +0.3 if near protected nodes
- Hypothesis type: +0.1 to +0.5 based on type
- Violations: +1.0 per error violation

**Risk Levels**:
- `LOW` (< 0.3): Safe for auto-approval and testing
- `MEDIUM` (0.3-0.6): Requires review before testing
- `HIGH` (0.6-0.8): Requires approval and careful monitoring
- `CRITICAL` (> 0.8): Requires senior review and staged rollout

## Integration Example

Complete Phase 2 workflow:

```python
from spark.rsi import (
    PerformanceAnalyzerNode,
    HypothesisGeneratorNode,
    ChangeValidatorNode,
    ExperienceDatabase
)
from spark.models.openai import OpenAIModel

# Step 1: Analyze performance (Phase 1)
analyzer = PerformanceAnalyzerNode()
analysis_result = await analyzer.run({
    'graph_id': 'production_workflow'
})

if not analysis_result['has_issues']:
    print("No issues found - no optimization needed")
    exit()

report = analysis_result['report']

# Step 2: Initialize experience database
experience_db = ExperienceDatabase()
await experience_db.initialize()

# Step 3: Generate hypotheses
model = OpenAIModel(model_id="gpt-4o")
generator = HypothesisGeneratorNode(
    model=model,
    max_hypotheses=5,
    hypothesis_types=["prompt_optimization", "parameter_tuning"],
    enable_pattern_learning=True,
    experience_db=experience_db
)

gen_result = await generator.run({
    'diagnostic_report': report,
    'graph': production_graph
})

print(f"\nGenerated {gen_result['count']} hypotheses")

# Step 4: Validate hypotheses
validator = ChangeValidatorNode(
    max_nodes_added=3,
    protected_nodes=["auth_node"],
    allowed_hypothesis_types=["prompt_optimization", "parameter_tuning"]
)

approved_hypotheses = []
for hypothesis in gen_result['hypotheses']:
    val_result = await validator.run({
        'hypothesis': hypothesis,
        'graph': production_graph
    })

    print(f"\nHypothesis {hypothesis.hypothesis_id}:")
    print(f"  Type: {hypothesis.hypothesis_type}")
    print(f"  Rationale: {hypothesis.rationale}")
    print(f"  Approved: {val_result['approved']}")
    print(f"  Risk: {val_result['risk_level']} ({val_result['risk_score']:.2f})")

    if val_result['approved']:
        approved_hypotheses.append(hypothesis)
        # Store in experience database
        await experience_db.store_hypothesis(
            hypothesis_id=hypothesis.hypothesis_id,
            graph_id=hypothesis.graph_id,
            graph_version_baseline=hypothesis.graph_version_baseline,
            hypothesis_type=hypothesis.hypothesis_type.value,
            proposal={
                'rationale': hypothesis.rationale,
                'changes': [vars(c) for c in hypothesis.changes]
            },
            target_node=hypothesis.target_node
        )

print(f"\n{len(approved_hypotheses)} hypotheses approved for testing")

# Proceed to Phase 3 (Testing)
```

## Best Practices

### Hypothesis Generation

1. **Use Appropriate Models**: GPT-4 or Claude for best results
2. **Provide Context**: Include graph specs and introspection data
3. **Enable Pattern Learning**: Learn from historical successes
4. **Limit Hypotheses**: Start with 3-5 hypotheses per iteration
5. **Focus Types**: Start with `prompt_optimization`, expand gradually

### Validation Configuration

1. **Set Conservative Limits**: Start strict, relax based on experience
2. **Protect Critical Nodes**: Always specify protected nodes
3. **Incremental Types**: Enable hypothesis types progressively
4. **Monitor Risk Scores**: Track risk scores of approved hypotheses
5. **Review Violations**: Analyze rejected hypotheses to tune rules

### Safety Guidelines

- Always validate before testing
- Never bypass validation for "urgent" changes
- Review HIGH and CRITICAL risk hypotheses manually
- Test in staging environment first for HIGH risk
- Keep audit trail of all validation decisions

## Troubleshooting

### No Hypotheses Generated

- Ensure model is properly configured with API key
- Check if diagnostic report has bottlenecks
- Verify hypothesis types are relevant to issues
- Review model logs for generation errors

### All Hypotheses Rejected

- Review validation violations
- Check if `allowed_hypothesis_types` is too restrictive
- Verify `protected_nodes` list is correct
- Consider relaxing `max_nodes_added/removed`
- Check if risk thresholds are too strict

### Poor Quality Hypotheses

- Use more capable models (GPT-4 vs GPT-3.5)
- Provide more context (graph specs, introspection)
- Enable pattern learning with experience database
- Review and improve diagnostic reports
- Fine-tune hypothesis prompts (advanced)

## Next Steps

After generating and validating hypotheses:

**Phase 3**: [Automated A/B Testing](phase3-testing.md) - Test approved hypotheses rigorously

## Related Documentation

- [Phase 1: Performance Analysis](phase1-analysis.md)
- [Phase 3: Automated A/B Testing](phase3-testing.md)
- [RSI Overview](overview.md)
- [API Reference: RSI](../api/rsi.md)
