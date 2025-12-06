# RSI CLI & Tools

## Overview

The RSI CLI provides command-line tools for reviewing hypotheses, managing deployments, and inspecting RSI system state.

## Installation

The CLI is available when Spark is installed:

```bash
pip install spark-adk
```

## Review CLI

The Review CLI enables human-in-the-loop review of hypotheses requiring approval.

### Commands

#### list

List pending review requests:

```bash
python -m spark.rsi.review_cli list
```

**Output**:
```
Pending Review Requests: 3

1. hyp_abc123
   Type: node_replacement
   Risk: HIGH
   Target: llm_node_1
   Created: 2025-12-05 10:30:00
   Status: pending

2. hyp_def456
   Type: parallelization
   Risk: MEDIUM
   Target: processing_pipeline
   Created: 2025-12-05 10:45:00
   Status: pending

3. hyp_ghi789
   Type: edge_modification
   Risk: HIGH
   Target: routing_logic
   Created: 2025-12-05 11:00:00
   Status: pending
```

**Options**:
- `--graph-id <id>`: Filter by graph ID
- `--risk <level>`: Filter by risk level (LOW, MEDIUM, HIGH, CRITICAL)
- `--status <status>`: Filter by status (pending, approved, rejected)
- `--limit <n>`: Limit results (default: 50)

#### review

Display detailed information for a specific hypothesis:

```bash
python -m spark.rsi.review_cli review hyp_abc123
```

**Output**:
```
Hypothesis Review: hyp_abc123

Graph: production_workflow (v1.0.0)
Type: node_replacement
Risk Level: HIGH
Risk Score: 0.75
Target Node: llm_node_1
Created: 2025-12-05 10:30:00
Status: pending

Rationale:
  Replace GPT-4 with GPT-4o-mini for cost reduction.
  Analysis shows 90% of requests don't require GPT-4 capabilities.
  Expected cost savings: 75% ($500/month → $125/month)

Expected Improvement:
  Latency: +0.05s (slightly slower)
  Cost: -75% (significant savings)
  Quality: -5% (minimal quality impact)

Changes:
  1. Update node config: model_id
     Old: gpt-4
     New: gpt-4o-mini

Diagnostic Evidence:
  - High cost node ($500/month)
  - Success rate: 98%
  - Avg complexity: LOW (85% of requests)
  - Quality requirement: Not critical

Validation Results:
  Approved: Pending review
  Risk Factors:
    - Node replacement changes behavior
    - Quality may decrease
    - Requires monitoring

Test Results:
  Status: PASSED
  Success Rate: +0.0% (no change)
  Latency: +0.05s (5% slower)
  Cost: -75% ($125 saved per month)
  Confidence: 95%

Recommendations:
  - Deploy with monitoring
  - Set quality alerts
  - Consider gradual rollout
```

#### approve

Approve a hypothesis:

```bash
python -m spark.rsi.review_cli approve hyp_abc123 \\
    --comments "Cost savings justify minor quality trade-off. Approved for canary deployment."
```

**Options**:
- `--comments <text>`: Review comments (recommended)
- `--conditions <text>`: Approval conditions (optional)

**Output**:
```
✓ Hypothesis hyp_abc123 approved

Next steps:
  - Hypothesis will be deployed automatically (auto_deploy=True)
  - Monitor post-deployment metrics
  - Review deployment outcome
```

#### reject

Reject a hypothesis:

```bash
python -m spark.rsi.review_cli reject hyp_abc123 \\
    --reason "Quality impact too high for critical user-facing feature" \\
    --recommendations "Consider testing on non-critical paths first"
```

**Options**:
- `--reason <text>`: Rejection reason (required)
- `--recommendations <text>`: Recommendations for improvement (optional)

**Output**:
```
✗ Hypothesis hyp_abc123 rejected

Reason: Quality impact too high for critical user-facing feature

Recommendations: Consider testing on non-critical paths first

The hypothesis has been marked as rejected and will not be deployed.
Feedback has been recorded in the experience database for future learning.
```

### Workflow Integration

Integrate review CLI into your workflow:

**1. Configure RSI for Human Review**:

```python
from spark.rsi import RSIMetaGraphConfig

config = RSIMetaGraphConfig(
    graph_id="production_workflow",
    auto_deploy=False,  # Require approval before deployment
    hypothesis_types=[
        "prompt_optimization",
        "node_replacement",  # HIGH risk - needs review
        "edge_modification"  # HIGH risk - needs review
    ]
)
```

**2. Run RSI**:

```bash
# RSI generates hypotheses and tests them
# HIGH risk hypotheses await review
python run_rsi.py
```

**3. Review Pending Hypotheses**:

```bash
# List pending reviews
python -m spark.rsi.review_cli list --risk HIGH

# Review each hypothesis
python -m spark.rsi.review_cli review hyp_abc123

# Approve or reject
python -m spark.rsi.review_cli approve hyp_abc123 --comments "Looks good"
```

**4. RSI Resumes**:

Once approved, RSI automatically deploys the hypothesis.

### Review Best Practices

1. **Review Promptly**: Set SLAs for review (e.g., < 4 hours)
2. **Document Decisions**: Always provide comments/reasons
3. **Consider Context**: Review in context of current priorities
4. **Check Test Results**: Verify test results are convincing
5. **Monitor Outcomes**: Follow up on approved hypotheses

## Hypothesis Management

### Query Hypotheses

Query hypotheses from experience database:

```bash
python -m spark.rsi.query_hypotheses \\
    --graph-id production_workflow \\
    --status approved \\
    --type prompt_optimization \\
    --limit 10
```

### Hypothesis History

View hypothesis history:

```bash
python -m spark.rsi.hypothesis_history hyp_abc123
```

**Output**:
```
Hypothesis History: hyp_abc123

Timeline:
  2025-12-05 10:30:00 - Created
  2025-12-05 10:35:00 - Validation: Approved (risk: HIGH)
  2025-12-05 10:40:00 - Testing Started
  2025-12-05 10:50:00 - Testing Completed: PASSED
  2025-12-05 10:55:00 - Human Review: Approved (reviewer: alice)
  2025-12-05 11:00:00 - Deployment Started
  2025-12-05 11:10:00 - Deployment Completed: SUCCESS
  2025-12-05 11:20:00 - Monitoring: No issues detected
  2025-12-05 11:30:00 - Marked as Successful

Final Outcome: SUCCESS
Impact: Cost reduced by 75%, quality maintained at 97%
Lessons Learned: 2 lessons recorded
Patterns Extracted: 1 pattern extracted
```

## Deployment Management

### List Deployments

List recent deployments:

```bash
python -m spark.rsi.list_deployments \\
    --graph-id production_workflow \\
    --status completed \\
    --limit 20
```

### Deployment Details

View deployment details:

```bash
python -m spark.rsi.deployment_details deploy_xyz789
```

### Rollback Deployment

Manually trigger rollback:

```bash
python -m spark.rsi.rollback_deployment deploy_xyz789 \\
    --reason "Performance degradation detected"
```

## Experience Database Tools

### Export Experience Data

Export experience data for analysis:

```bash
python -m spark.rsi.export_experience \\
    --graph-id production_workflow \\
    --format json \\
    --output experience_data.json
```

**Formats**: json, csv, sqlite

### Import Experience Data

Import experience data from another environment:

```bash
python -m spark.rsi.import_experience \\
    --input experience_data.json \\
    --merge  # Merge with existing data
```

### Clean Experience Data

Remove old or invalid experience data:

```bash
python -m spark.rsi.clean_experience \\
    --older-than 90d \\
    --status failed \\
    --dry-run  # Preview what would be deleted
```

## Pattern Analysis

### Extract Patterns

Manually trigger pattern extraction:

```bash
python -m spark.rsi.extract_patterns \\
    --graph-id production_workflow \\
    --min-occurrences 3 \\
    --min-success-rate 0.6 \\
    --output patterns.json
```

### List Patterns

List extracted patterns:

```bash
python -m spark.rsi.list_patterns \\
    --graph-id production_workflow \\
    --type success \\
    --sort-by success_rate
```

## Monitoring & Diagnostics

### RSI Health Check

Check RSI system health:

```bash
python -m spark.rsi.health_check
```

**Output**:
```
RSI System Health Check

Telemetry:
  ✓ Telemetry backend: Connected (SQLite)
  ✓ Recent data: 1,234 traces in last 24h
  ✓ Data quality: Good (98% complete traces)

Experience Database:
  ✓ Database: Connected (in-memory)
  ✓ Total hypotheses: 47
  ✓ Successful: 32 (68%)
  ✓ Patterns extracted: 5

LLM:
  ✓ Model: Connected (gpt-4o)
  ✓ Cache hit rate: 45%
  ✓ Avg latency: 1.2s

Current Status:
  ✓ No pending reviews
  ✓ Last cycle: 2025-12-05 11:00:00 (30 minutes ago)
  ✓ Last deployment: 2025-12-05 10:30:00 (60 minutes ago)
  ✓ Active deployments: 1 (monitoring)

Overall Health: GOOD
```

### RSI Statistics

View RSI statistics:

```bash
python -m spark.rsi.stats \\
    --graph-id production_workflow \\
    --period 7d
```

**Output**:
```
RSI Statistics (Last 7 Days)

Cycles:
  Total: 28
  Successful: 25 (89%)
  Failed: 3 (11%)

Hypotheses:
  Generated: 84
  Approved: 62 (74%)
  Tested: 62
  Passed: 45 (73%)
  Deployed: 40 (89% of passed)

Deployments:
  Successful: 38 (95%)
  Rolled back: 2 (5%)

Performance Impact:
  Avg latency improvement: -0.15s (-8%)
  Avg cost reduction: -$45/day
  Avg quality improvement: +3%
  Success rate improvement: +5%

Cost:
  Total LLM cost: $12.50
  ROI: 25x (cost savings / LLM cost)
```

## Configuration

### RSI CLI Configuration

Configure CLI defaults:

```bash
# Create config file
cat > ~/.spark/rsi_cli_config.yaml <<EOF
default_graph_id: production_workflow
review_timeout: 3600  # 1 hour
auto_refresh: true
output_format: json
EOF

# Use config
python -m spark.rsi.review_cli list  # Uses default_graph_id
```

## Scripting & Automation

### Automated Review Workflow

Example approval script:

```python
#!/usr/bin/env python3
"""Automated low-risk hypothesis approval."""
import asyncio
from spark.rsi.human_review import ReviewRequestStore

async def auto_approve_low_risk():
    store = ReviewRequestStore()

    pending = await store.list_pending_reviews()

    for request in pending:
        if request.risk_level == "LOW" and request.risk_score < 0.3:
            await store.approve_request(
                request_id=request.request_id,
                reviewer="auto_approver",
                comments="Auto-approved: LOW risk, score < 0.3"
            )
            print(f"Auto-approved: {request.hypothesis_id}")

if __name__ == "__main__":
    asyncio.run(auto_approve_low_risk())
```

### Integration with CI/CD

Example GitHub Actions workflow:

```yaml
name: RSI Continuous Improvement

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  rsi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Run RSI
        run: python scripts/run_rsi.py

      - name: Auto-approve LOW risk
        run: python scripts/auto_approve_low_risk.py

      - name: Notify pending reviews
        if: failure()
        run: python scripts/notify_pending_reviews.py
```

## Troubleshooting

### Review CLI Not Working

```bash
# Check review store connection
python -c "from spark.rsi.human_review import ReviewRequestStore; \
           store = ReviewRequestStore(); \
           print('Store OK')"

# Check for pending reviews directly
python -c "from spark.rsi.human_review import ReviewRequestStore; \
           import asyncio; \
           store = ReviewRequestStore(); \
           reviews = asyncio.run(store.list_pending_reviews()); \
           print(f'Pending: {len(reviews)}')"
```

### No Pending Reviews

- Verify RSI is generating HIGH/CRITICAL risk hypotheses
- Check `enable_human_review` configuration
- Review `require_review_threshold` setting
- Verify review store is accessible

## Next Steps

- Set up [RSI Meta-Graph](meta-graph.md) for continuous improvement
- Configure [telemetry](../telemetry/overview.md) for RSI data
- Review [API reference](../api/rsi.md) for programmatic access
- Explore [Phase 6: Advanced Optimization](phase6-advanced.md) for human review integration

## Related Documentation

- [RSI Overview](overview.md)
- [Phase 6: Advanced Optimization](phase6-advanced.md) - Human Review Node
- [RSI Meta-Graph](meta-graph.md)
- [API Reference: RSI](../api/rsi.md)
