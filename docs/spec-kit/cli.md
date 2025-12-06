---
title: Spec CLI Tool
parent: SpecKit
nav_order: 3
---
# Spec CLI Tool

The `spark-spec` command-line tool provides comprehensive operations for working with graph specifications, missions, simulations, schemas, plans, approvals, and policies. It's the primary interface for spec operations in CI/CD pipelines, development workflows, and production deployments.

## Installation

The CLI is available when Spark is installed:

```bash
# If installed via pip
spark-spec --help

# Or run directly
python -m spark.kit.spec_cli --help
```

## Command Categories

The CLI is organized into logical command groups:

- **Graph Commands**: Export, validate, compile, analyze graph specifications
- **Mission Commands**: Generate, validate, package, deploy missions
- **Simulation Commands**: Run and compare simulation tests
- **Schema Commands**: Render, validate, migrate state schemas
- **Plan Commands**: Render mission plans
- **Approval Commands**: List and resolve governance approvals
- **Policy Commands**: Generate, validate, diff policy sets

## Graph Commands

### export

Export Python graph to JSON specification.

```bash
# Export graph from module
spark-spec export myapp.workflows:production_graph -o graph.json

# Specify Spark version
spark-spec export myapp.workflows:graph -o graph.json --version 2.0

# Export to stdout
spark-spec export myapp.workflows:graph
```

**Usage**:
```
spark-spec export TARGET [-o OUTPUT] [--version VERSION]
```

**Arguments**:
- `TARGET`: Module:attribute reference (e.g., `myapp.workflows:graph`)
- `-o, --output`: Output file path (default: stdout)
- `--version`: Spark version (default: "2.0")

**Target Format**: `module:attr` where:
- `module`: Python module path
- `attr`: Attribute name (can be Graph instance or factory function)

**Example**:
```python
# myapp/workflows.py
from spark.graphs import Graph
from spark.nodes import Node

def production_graph():
    """Factory function returning graph."""
    node = Node()
    return Graph(start=node)

# Export
# spark-spec export myapp.workflows:production_graph -o prod.json
```

### validate

Validate JSON specification against schema.

```bash
# Basic validation
spark-spec validate workflow.json

# Semantic validation (checks references, logic)
spark-spec validate workflow.json --semantic

# Strict mode (fail on warnings)
spark-spec validate workflow.json --strict

# Combined
spark-spec validate workflow.json --semantic --strict
```

**Usage**:
```
spark-spec validate FILE [--semantic] [--strict]
```

**Arguments**:
- `FILE`: Path to JSON spec file
- `--semantic`: Enable semantic validation beyond schema
- `--strict`: Treat warnings as errors

**Validation Levels**:
1. **Schema**: Pydantic model validation (always performed)
2. **Semantic**: Reference validation, logic checks (optional)
3. **Strict**: Warnings become errors (optional)

**Example Output**:
```
✓ Schema validation passed
✓ Semantic validation passed
Graph: com.example.workflow
Nodes: 5
Edges: 7
Start: input_node
```

### compile

Generate Python code from JSON specification.

```bash
# Generate simple code
spark-spec compile workflow.json -o ./generated

# Production-ready code with error handling
spark-spec compile workflow.json -o ./generated --style production

# Fully documented code
spark-spec compile workflow.json -o ./generated --style documented

# Include tests
spark-spec compile workflow.json -o ./generated --tests

# Single file output
spark-spec compile workflow.json --single-file -o workflow.py
```

**Usage**:
```
spark-spec compile FILE -o OUTPUT [--style STYLE] [--tests] [--single-file]
```

**Arguments**:
- `FILE`: Input JSON spec file
- `-o, --output`: Output directory or file path
- `--style`: Code generation style (simple, production, documented)
- `--tests`: Generate test files
- `--single-file`: Generate single Python file

**Generation Styles**:
- **simple**: Minimal readable code
- **production**: Production-ready with error handling, validation, logging
- **documented**: Fully documented with docstrings, type hints, comments

**Output Structure** (directory mode):
```
generated/
├── nodes.py          # Node class definitions
├── graph.py          # Graph assembly
├── __init__.py       # Package init
└── tests/            # Test suite (if --tests)
    ├── test_nodes.py
    └── test_graph.py
```

See [Code Generation](./codegen.md) for details.

### generate

Create JSON specification from natural language description.

```bash
# Generate from description
spark-spec generate "Multi-agent workflow with data processing" -o workflow.json

# With additional context
spark-spec generate "API gateway with rate limiting and caching" \
    -o gateway.json \
    --context "Use 3 nodes: input, processor, output"
```

**Usage**:
```
spark-spec generate DESCRIPTION -o OUTPUT [--context CONTEXT]
```

**Arguments**:
- `DESCRIPTION`: Natural language workflow description
- `-o, --output`: Output file path
- `--context`: Additional context for generation

**Note**: Requires LLM access. Uses AI to generate initial spec structure.

### analyze

Analyze graph structure and complexity.

```bash
# Basic analysis
spark-spec analyze workflow.json

# Generate HTML report
spark-spec analyze workflow.json --report analysis.html

# Fail if complexity exceeds threshold
spark-spec analyze workflow.json --fail-on "complexity>10"

# JSON output
spark-spec analyze workflow.json --format json
```

**Usage**:
```
spark-spec analyze FILE [--report REPORT] [--fail-on CONDITION] [--format FORMAT]
```

**Arguments**:
- `FILE`: JSON spec file
- `--report`: Generate HTML/Markdown report file
- `--fail-on`: Condition to fail on (e.g., "complexity>10", "cyclic")
- `--format`: Output format (text, json, markdown)

**Metrics Provided**:
- Node count, edge count
- Max depth, average depth
- Branching factor
- Cycle detection
- Unreachable nodes
- Connected components
- Critical path analysis

See [Graph Analysis](./analysis.md) for details.

### diff

Compare two specifications and show differences.

```bash
# Basic diff
spark-spec diff old.json new.json

# Unified format
spark-spec diff old.json new.json --format unified

# JSON output
spark-spec diff old.json new.json --format json

# HTML report
spark-spec diff old.json new.json --format html -o diff.html

# Ignore specific fields
spark-spec diff old.json new.json --ignore metadata
```

**Usage**:
```
spark-spec diff OLD_FILE NEW_FILE [--format FORMAT] [-o OUTPUT] [--ignore FIELDS]
```

**Arguments**:
- `OLD_FILE`: Original spec file
- `NEW_FILE`: Updated spec file
- `--format`: Output format (text, unified, json, html)
- `-o, --output`: Output file for report
- `--ignore`: Comma-separated fields to ignore

**Output Formats**:
- **text**: Human-readable summary
- **unified**: Git-style unified diff
- **json**: Structured diff data
- **html**: Visual side-by-side comparison

### optimize

Suggest and apply optimizations to graph.

```bash
# Show optimization suggestions
spark-spec optimize workflow.json

# Apply optimizations automatically
spark-spec optimize workflow.json --auto-fix -o optimized.json

# Specific optimization types
spark-spec optimize workflow.json --optimize "parallelization,caching"

# Dry run (show what would change)
spark-spec optimize workflow.json --dry-run
```

**Usage**:
```
spark-spec optimize FILE [--auto-fix] [-o OUTPUT] [--optimize TYPES] [--dry-run]
```

**Arguments**:
- `FILE`: Input spec file
- `--auto-fix`: Automatically apply optimizations
- `-o, --output`: Output file for optimized spec
- `--optimize`: Comma-separated optimization types
- `--dry-run`: Show changes without applying

**Optimization Types**:
- **parallelization**: Convert sequential to parallel where safe
- **caching**: Add caching to expensive operations
- **batching**: Batch similar operations
- **edge-simplification**: Simplify complex edge conditions
- **node-merging**: Merge similar nodes

### test

Test specification validity and round-trip conversion.

```bash
# Validate spec
spark-spec test workflow.json

# Test round-trip (spec → code → spec)
spark-spec test workflow.json --round-trip

# Validate and test execution
spark-spec test workflow.json --validate --execute

# Verbose output
spark-spec test workflow.json -v
```

**Usage**:
```
spark-spec test FILE [--round-trip] [--validate] [--execute] [-v]
```

**Arguments**:
- `FILE`: Spec file to test
- `--round-trip`: Test serialization fidelity
- `--validate`: Perform validation
- `--execute`: Test execution (requires valid inputs)
- `-v, --verbose`: Verbose output

**Tests Performed**:
- Schema validation
- Semantic validation
- Round-trip conversion (optional)
- Execution test (optional)

### introspect

Inspect Python graph and show detailed information.

```bash
# Introspect graph
spark-spec introspect myapp.workflows:graph

# JSON output
spark-spec introspect myapp.workflows:graph --format json

# Markdown output
spark-spec introspect myapp.workflows:graph --format markdown -o graph.md

# Include private attributes
spark-spec introspect myapp.workflows:graph --include-private
```

**Usage**:
```
spark-spec introspect TARGET [--format FORMAT] [-o OUTPUT] [--include-private]
```

**Arguments**:
- `TARGET`: Module:attribute reference
- `--format`: Output format (text, json, markdown)
- `-o, --output`: Output file
- `--include-private`: Include private attributes

**Information Provided**:
- Graph structure
- Node details
- Edge connections
- Configuration
- State and features

### merge

Merge multiple specifications into one.

```bash
# Merge specs
spark-spec merge spec1.json spec2.json spec3.json -o merged.json

# Specify merge strategy
spark-spec merge spec1.json spec2.json --strategy append -o merged.json

# Resolve conflicts
spark-spec merge spec1.json spec2.json --on-conflict ask -o merged.json
```

**Usage**:
```
spark-spec merge FILE1 FILE2 [FILE3 ...] -o OUTPUT [--strategy STRATEGY] [--on-conflict MODE]
```

**Arguments**:
- `FILE1, FILE2, ...`: Input spec files
- `-o, --output`: Output merged spec file
- `--strategy`: Merge strategy (append, replace, combine)
- `--on-conflict`: Conflict resolution (ask, first, last, error)

**Merge Strategies**:
- **append**: Append all nodes and edges
- **replace**: Later specs replace earlier
- **combine**: Intelligent merging

### extract

Extract subgraph from specification.

```bash
# Extract from start node
spark-spec extract workflow.json --node start_node -o subgraph.json

# Extract specific nodes
spark-spec extract workflow.json --nodes "node1,node2,node3" -o sub.json

# Extract by depth
spark-spec extract workflow.json --node start --depth 3 -o sub.json

# Include dependencies
spark-spec extract workflow.json --node end --include-deps -o sub.json
```

**Usage**:
```
spark-spec extract FILE --node NODE [-o OUTPUT] [--depth DEPTH] [--include-deps]
```

**Arguments**:
- `FILE`: Input spec file
- `--node`: Starting node ID
- `--nodes`: Comma-separated node IDs
- `-o, --output`: Output subgraph file
- `--depth`: Maximum traversal depth
- `--include-deps`: Include all dependencies

## Mission Commands

### mission-generate

Generate mission specification from description.

```bash
# Generate mission
spark-spec mission-generate "Data processing pipeline" \
    --graph workflow.json \
    -o mission.json

# With plan
spark-spec mission-generate "ETL workflow" \
    --graph etl.json \
    --plan "validate,transform,load" \
    -o mission.json

# With deployment metadata
spark-spec mission-generate "Production API" \
    --graph api.json \
    --deployment production \
    -o mission.json
```

**Usage**:
```
spark-spec mission-generate DESCRIPTION --graph GRAPH -o OUTPUT [OPTIONS]
```

**Arguments**:
- `DESCRIPTION`: Mission description
- `--graph`: Path to graph JSON
- `-o, --output`: Output mission file
- `--plan`: Comma-separated plan steps
- `--deployment`: Deployment target

See [Mission System](./missions.md) for details.

### mission-validate

Validate mission specification.

```bash
# Validate mission
spark-spec mission-validate mission.json

# Strict validation
spark-spec mission-validate mission.json --strict

# Check deployment readiness
spark-spec mission-validate mission.json --check-deployment
```

**Usage**:
```
spark-spec mission-validate FILE [--strict] [--check-deployment]
```

**Arguments**:
- `FILE`: Mission spec file
- `--strict`: Strict mode
- `--check-deployment`: Verify deployment readiness

**Validation Checks**:
- Mission structure
- Graph validity
- Plan consistency
- State schema
- Deployment metadata
- Simulation configuration

### mission-diff

Compare two mission specifications.

```bash
# Diff missions
spark-spec mission-diff old_mission.json new_mission.json

# HTML report
spark-spec mission-diff old.json new.json --format html -o diff.html

# Focus on specific sections
spark-spec mission-diff old.json new.json --sections "graph,plan"
```

**Usage**:
```
spark-spec mission-diff OLD NEW [--format FORMAT] [-o OUTPUT] [--sections SECTIONS]
```

**Arguments**:
- `OLD`: Original mission file
- `NEW`: Updated mission file
- `--format`: Output format (text, html, json)
- `-o, --output`: Output file
- `--sections`: Sections to compare (comma-separated)

### mission-package

Create deployable mission package.

```bash
# Create package
spark-spec mission-package mission.json -o mission.zip

# Include dependencies
spark-spec mission-package mission.json --include-deps -o package.zip

# Specify manifest
spark-spec mission-package mission.json --manifest manifest.json -o pkg.zip
```

**Usage**:
```
spark-spec mission-package FILE -o OUTPUT [--include-deps] [--manifest MANIFEST]
```

**Arguments**:
- `FILE`: Mission spec file
- `-o, --output`: Output package file (zip)
- `--include-deps`: Include Python dependencies
- `--manifest`: Custom manifest file

**Package Contents**:
- Mission specification
- Graph specification
- State schemas
- Tool definitions
- Deployment metadata
- Optional: Dependencies, manifests

### mission-deploy

Run deployment readiness checks.

```bash
# Check deployment readiness
spark-spec mission-deploy mission.json

# Specify target
spark-spec mission-deploy mission.json --target production

# Dry run
spark-spec mission-deploy mission.json --dry-run

# With validation
spark-spec mission-deploy mission.json --validate-all
```

**Usage**:
```
spark-spec mission-deploy FILE [--target TARGET] [--dry-run] [--validate-all]
```

**Arguments**:
- `FILE`: Mission spec file
- `--target`: Deployment target (development, staging, production)
- `--dry-run`: Simulate deployment
- `--validate-all`: Comprehensive validation

**Checks Performed**:
- Mission validity
- Resource availability
- Configuration completeness
- Security requirements
- Dependencies

## Simulation Commands

### simulation-run

Run mission with simulated tool overrides.

```bash
# Run simulation
spark-spec simulation-run mission.json

# With inputs
spark-spec simulation-run mission.json --inputs inputs.json

# Override simulation config
spark-spec simulation-run mission.json --simulation-config sim.json

# Save outputs
spark-spec simulation-run mission.json -o outputs.json

# Verbose mode
spark-spec simulation-run mission.json -v
```

**Usage**:
```
spark-spec simulation-run FILE [--inputs INPUTS] [--simulation-config CONFIG] [-o OUTPUT] [-v]
```

**Arguments**:
- `FILE`: Mission spec file
- `--inputs`: JSON file with input data
- `--simulation-config`: Override simulation configuration
- `-o, --output`: Save outputs to file
- `-v, --verbose`: Verbose logging

**Output Includes**:
- Execution results
- Tool call records
- Policy events
- Timing information

See [Simulation System](./simulation.md) for details.

### simulation-diff

Compare outputs from multiple simulation runs.

```bash
# Compare two runs
spark-spec simulation-diff run1.json run2.json

# HTML report
spark-spec simulation-diff run1.json run2.json --format html -o diff.html

# Focus on specific fields
spark-spec simulation-diff run1.json run2.json --fields "outputs,timing"

# Ignore tool calls
spark-spec simulation-diff run1.json run2.json --ignore tool_records
```

**Usage**:
```
spark-spec simulation-diff RUN1 RUN2 [--format FORMAT] [-o OUTPUT] [--fields FIELDS] [--ignore IGNORE]
```

**Arguments**:
- `RUN1, RUN2`: Simulation output files
- `--format`: Output format (text, html, json)
- `-o, --output`: Output file
- `--fields`: Fields to compare (comma-separated)
- `--ignore`: Fields to ignore (comma-separated)

## Schema Commands

### schema-render

Render MissionStateModel metadata and JSON schema.

```bash
# Render schema
spark-spec schema-render myapp.schemas:DataPipelineState

# Output to file
spark-spec schema-render myapp.schemas:State -o schema.json

# Format as markdown
spark-spec schema-render myapp.schemas:State --format markdown -o schema.md

# Include examples
spark-spec schema-render myapp.schemas:State --include-examples
```

**Usage**:
```
spark-spec schema-render TARGET [-o OUTPUT] [--format FORMAT] [--include-examples]
```

**Arguments**:
- `TARGET`: Module:class reference to MissionStateModel
- `-o, --output`: Output file
- `--format`: Output format (json, markdown, yaml)
- `--include-examples`: Include example data

**Output Includes**:
- Field definitions
- Types and constraints
- Default values
- JSON schema
- Documentation

### schema-validate

Validate fixture data against MissionStateModel.

```bash
# Validate data
spark-spec schema-validate myapp.schemas:State --fixture data.json

# Validate multiple files
spark-spec schema-validate myapp.schemas:State --fixture "data/*.json"

# Strict mode
spark-spec schema-validate myapp.schemas:State --fixture data.json --strict
```

**Usage**:
```
spark-spec schema-validate TARGET --fixture FIXTURE [--strict]
```

**Arguments**:
- `TARGET`: Module:class reference to MissionStateModel
- `--fixture`: Data file or glob pattern
- `--strict`: Strict validation mode

### schema-migrate

Run schema migrations.

```bash
# Migrate data
spark-spec schema-migrate data.json --from v1 --to v2 -o migrated.json

# Auto-detect version
spark-spec schema-migrate data.json --schema myapp.schemas:State -o out.json

# Dry run
spark-spec schema-migrate data.json --from v1 --to v2 --dry-run
```

**Usage**:
```
spark-spec schema-migrate FILE --from VERSION --to VERSION [-o OUTPUT] [--dry-run]
```

**Arguments**:
- `FILE`: Data file to migrate
- `--from`: Source schema version
- `--to`: Target schema version
- `--schema`: Schema class reference
- `-o, --output`: Output file
- `--dry-run`: Show changes without applying

### schema-diff

Compare two MissionStateModel definitions.

```bash
# Diff schemas
spark-spec schema-diff myapp.schemas:StateV1 myapp.schemas:StateV2

# HTML report
spark-spec schema-diff old:State new:State --format html -o diff.html
```

**Usage**:
```
spark-spec schema-diff OLD NEW [--format FORMAT] [-o OUTPUT]
```

**Arguments**:
- `OLD, NEW`: Module:class references
- `--format`: Output format (text, html, markdown)
- `-o, --output`: Output file

## Plan Commands

### plan-render

Render mission plan snapshot to text.

```bash
# Render plan from mission
spark-spec plan-render mission.json

# From state backend
spark-spec plan-render --state state.db --backend sqlite

# Format options
spark-spec plan-render mission.json --format markdown -o plan.md
```

**Usage**:
```
spark-spec plan-render FILE [--state STATE] [--backend BACKEND] [--format FORMAT] [-o OUTPUT]
```

**Arguments**:
- `FILE`: Mission spec file
- `--state`: State backend path
- `--backend`: Backend type (file, sqlite)
- `--format`: Output format (text, markdown, json)
- `-o, --output`: Output file

**Output Shows**:
- Plan steps with status
- Dependencies
- Progress indicators
- Timing information

## Approval Commands

### approval-list

List governance approval requests from GraphState.

```bash
# List approvals from file backend
spark-spec approval-list --state approvals.json

# From SQLite backend
spark-spec approval-list --state db.sqlite --backend sqlite --table state

# Filter by status
spark-spec approval-list --state approvals.json --status pending

# JSON output
spark-spec approval-list --state approvals.json --format json
```

**Usage**:
```
spark-spec approval-list --state STATE [--backend BACKEND] [--table TABLE] [--status STATUS] [--format FORMAT]
```

**Arguments**:
- `--state`: State backend path
- `--backend`: Backend type (file, sqlite)
- `--table`: Table name (for SQLite)
- `--status`: Filter by status (pending, approved, rejected)
- `--format`: Output format (text, json)
- `--storage-key`: Storage key (default: "approval_requests")

### approval-resolve

Approve or reject pending approval request.

```bash
# Approve request
spark-spec approval-resolve REQUEST_ID \
    --state approvals.json \
    --action approve \
    --approver alice

# Reject with reason
spark-spec approval-resolve REQUEST_ID \
    --state approvals.json \
    --action reject \
    --approver bob \
    --reason "Security concerns"

# With SQLite backend
spark-spec approval-resolve REQUEST_ID \
    --state db.sqlite \
    --backend sqlite \
    --action approve \
    --approver admin
```

**Usage**:
```
spark-spec approval-resolve REQUEST_ID --state STATE --action ACTION --approver APPROVER [OPTIONS]
```

**Arguments**:
- `REQUEST_ID`: Approval request ID
- `--state`: State backend path
- `--backend`: Backend type (file, sqlite)
- `--action`: Action (approve, reject)
- `--approver`: Approver identifier
- `--reason`: Reason for decision (optional)
- `--table`: Table name (for SQLite)

## Policy Commands

### policy-generate

Generate policy set scaffold.

```bash
# Generate policy template
spark-spec policy-generate --name "API Rate Limiting" -o policies.json

# With specific rules
spark-spec policy-generate \
    --name "Cost Control" \
    --rules "max_cost,budget_limit" \
    -o cost_policies.json
```

**Usage**:
```
spark-spec policy-generate --name NAME -o OUTPUT [--rules RULES]
```

**Arguments**:
- `--name`: Policy set name
- `-o, --output`: Output policy file
- `--rules`: Comma-separated rule types

### policy-validate

Validate policy JSON.

```bash
# Validate policy
spark-spec policy-validate policies.json

# Strict mode
spark-spec policy-validate policies.json --strict

# Check for conflicts
spark-spec policy-validate policies.json --check-conflicts
```

**Usage**:
```
spark-spec policy-validate FILE [--strict] [--check-conflicts]
```

**Arguments**:
- `FILE`: Policy JSON file
- `--strict`: Strict validation
- `--check-conflicts`: Check for conflicting rules

### policy-diff

Compare two policy JSON files.

```bash
# Diff policies
spark-spec policy-diff old_policies.json new_policies.json

# HTML report
spark-spec policy-diff old.json new.json --format html -o diff.html
```

**Usage**:
```
spark-spec policy-diff OLD NEW [--format FORMAT] [-o OUTPUT]
```

**Arguments**:
- `OLD, NEW`: Policy files
- `--format`: Output format (text, html, json)
- `-o, --output`: Output file

## Common Options

### Global Options

Available for all commands:

```bash
--help          # Show help message
--version       # Show version information
-v, --verbose   # Verbose output
-q, --quiet     # Suppress output
--color         # Force colored output
--no-color      # Disable colored output
```

### Output Formats

Many commands support multiple output formats:

- `text`: Human-readable text (default)
- `json`: Structured JSON
- `yaml`: YAML format
- `markdown`: Markdown documentation
- `html`: HTML reports with styling

## CI/CD Integration

### Validation Pipeline

```bash
#!/bin/bash
# validate_specs.sh

# Validate all specs
for spec in specs/*.json; do
    echo "Validating $spec..."
    spark-spec validate "$spec" --semantic --strict || exit 1
done

# Test round-trips
for spec in specs/*.json; do
    echo "Testing $spec..."
    spark-spec test "$spec" --round-trip || exit 1
done

echo "All specs validated successfully"
```

### Deployment Pipeline

```bash
#!/bin/bash
# deploy_mission.sh

MISSION=$1
TARGET=$2

# Validate mission
spark-spec mission-validate "$MISSION" --check-deployment || exit 1

# Run simulation tests
spark-spec simulation-run "$MISSION" --inputs test_inputs.json || exit 1

# Package mission
spark-spec mission-package "$MISSION" --include-deps -o mission.zip || exit 1

# Deploy
spark-spec mission-deploy "$MISSION" --target "$TARGET" || exit 1

echo "Mission deployed to $TARGET"
```

## Best Practices

**Always Validate**: Run `validate` before committing specs to version control.

**Use Semantic Validation**: Enable `--semantic` flag for deeper checks.

**Test Round-Trips**: Verify serialization fidelity with `--round-trip`.

**Generate Reports**: Use HTML reports for human review (`--format html`).

**Version Control**: Commit JSON specs, track changes with `diff`.

**Automate**: Integrate CLI commands in CI/CD pipelines.

**Use Missions**: Package complete deployments with `mission-package`.

**Simulate First**: Test with `simulation-run` before production deployment.

## Troubleshooting

### Command Not Found

```bash
# If spark-spec not found
python -m spark.kit.spec_cli --help

# Or add to PATH
export PATH="$PATH:$(python -m site --user-base)/bin"
```

### Import Errors

```bash
# If target module not found
PYTHONPATH=/path/to/project spark-spec export myapp:graph
```

### Validation Failures

```bash
# Get detailed error information
spark-spec validate workflow.json -v
```

## Next Steps

- **[Specification Models](./models.md)**: Understanding spec structures
- **[Code Generation](./codegen.md)**: Generating Python from specs
- **[Graph Analysis](./analysis.md)**: Analyzing complexity and structure
- **[Mission System](./missions.md)**: High-level orchestration
- **[Simulation System](./simulation.md)**: Testing workflows

## Related Documentation

- [Best Practices: CI/CD Integration](../best-practices/cicd.md)
- [Integration: Specification-Driven Development](../integration/spec-driven-dev.md)
- [Troubleshooting: CLI Issues](../troubleshooting/cli.md)
