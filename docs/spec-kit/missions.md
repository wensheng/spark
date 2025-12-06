# Mission System

The Spark Mission System provides high-level orchestration and deployment packaging for complete agentic workflows. A **Mission** is more than just a graph - it's a complete deployable package including the graph specification, execution plan, state schema, deployment metadata, and simulation configuration.

## Overview

A **MissionSpec** extends **GraphSpec** with:

- **Mission Metadata**: ID, version, description
- **Execution Plan**: Declarative steps with dependencies
- **State Schema**: Typed state models with validation
- **Strategy Bindings**: Agent strategy configurations
- **Telemetry Configuration**: Observability settings
- **Deployment Metadata**: Target environment, resources, replicas
- **Simulation Configuration**: Tool overrides for testing

**Use Cases**:
- Production deployments with complete configuration
- Multi-step workflows with complex orchestration
- Environments requiring formal approval and governance
- Systems needing comprehensive monitoring and control
- Workflows requiring rigorous testing before deployment

## Mission Specification

### MissionSpec Structure

```python
from spark.nodes.spec import MissionSpec, MissionPlanSpec, MissionStateSchemaSpec

mission = MissionSpec(
    spark_version="2.0",
    mission_id="com.example.data-pipeline",
    version="1.0.0",
    description="Production data processing pipeline",

    # Core workflow
    graph=GraphSpec(...),

    # Execution plan
    plan=MissionPlanSpec(
        steps=[
            MissionPlanStepSpec(
                id="validate",
                description="Validate input data",
                depends_on=[]
            ),
            MissionPlanStepSpec(
                id="transform",
                description="Transform validated data",
                depends_on=["validate"]
            ),
            MissionPlanStepSpec(
                id="load",
                description="Load transformed data",
                depends_on=["transform"]
            )
        ]
    ),

    # State schema
    state_schema=MissionStateSchemaSpec(
        schema_class="myapp.schemas:PipelineState",
        fields={
            "processed_count": {"type": "int", "required": True, "default": 0},
            "error_count": {"type": "int", "required": True, "default": 0},
            "last_run": {"type": "datetime", "required": False}
        }
    ),

    # Telemetry
    telemetry=MissionTelemetrySpec(
        enabled=True,
        backend="sqlite",
        sampling_rate=1.0
    ),

    # Deployment
    deployment=MissionDeploymentSpec(
        target="production",
        replicas=3,
        resources={"cpu": "2", "memory": "4Gi"},
        health_check_interval=30
    ),

    # Simulation
    simulation=MissionSimulationSpec(
        enabled=True,
        tools=[
            SimulationToolOverrideSpec(
                name="external_api",
                static_response={"status": "success"}
            )
        ]
    )
)
```

### Mission Metadata

**Required Fields**:
- `mission_id`: Unique identifier (reverse DNS recommended)
- `version`: Semantic version (e.g., "1.0.0")
- `graph`: Core GraphSpec

**Optional Fields**:
- `description`: Human-readable description
- `plan`: Mission execution plan
- `state_schema`: State model definition
- `strategies`: Agent strategy bindings
- `telemetry`: Telemetry configuration
- `deployment`: Deployment metadata
- `simulation`: Simulation configuration

## Mission Plans

### MissionPlanSpec

Declarative execution plan with steps and dependencies.

```python
from spark.nodes.spec import MissionPlanSpec, MissionPlanStepSpec

plan = MissionPlanSpec(
    steps=[
        MissionPlanStepSpec(
            id="step1",
            description="Initialize system",
            depends_on=[]
        ),
        MissionPlanStepSpec(
            id="step2",
            description="Process data",
            depends_on=["step1"]
        ),
        MissionPlanStepSpec(
            id="step3",
            description="Generate report",
            depends_on=["step2"]
        ),
        MissionPlanStepSpec(
            id="step4",
            description="Send notifications",
            depends_on=["step2"]  # Parallel with step3
        )
    ]
)
```

**Step Fields**:
- `id`: Step identifier
- `description`: Human-readable description
- `depends_on`: List of prerequisite step IDs

**Step Status** (runtime):
- `pending`: Not yet started
- `in_progress`: Currently executing
- `completed`: Successfully finished
- `blocked`: Waiting on dependencies

### Mission Control Components

**PlanManager**: Synchronizes plan state with graph execution.

```python
from spark.graphs.mission_control import MissionPlan, PlanManager

# Create plan
plan = MissionPlan(steps=[
    PlanStep(id="validate", description="Validate input"),
    PlanStep(id="process", description="Process data", depends_on=["validate"])
])

# Attach to graph
manager = PlanManager(plan, state_key="mission_plan", auto_advance=True)
manager.attach(graph)

# Run graph - plan advances automatically
await graph.run()

# Check plan status
print(plan.render_text())
```

**Guardrails**: Budget constraints and runtime limits.

```python
from spark.graphs.mission_control import Guardrails

guardrails = Guardrails(
    max_iterations=100,
    max_runtime_seconds=300,
    max_cost=10.0
)

guardrails.attach(graph)

# Run with guardrails enforcement
try:
    await graph.run()
except GuardrailBreachError as e:
    print(f"Guardrail breached: {e}")
```

## State Schemas

### MissionStateModel

Define typed state models for missions.

```python
from spark.graphs.state_schema import MissionStateModel
from pydantic import Field

class PipelineState(MissionStateModel):
    """State model for data pipeline."""

    processed_count: int = Field(default=0, description="Number of processed items")
    error_count: int = Field(default=0, description="Number of errors")
    last_batch_id: str | None = Field(default=None, description="Last processed batch ID")
    metrics: dict[str, float] = Field(default_factory=dict, description="Performance metrics")
```

**Benefits**:
- Type safety for state access
- Validation on state updates
- Schema documentation
- Migration support
- IDE autocomplete

**Usage in Graph**:
```python
from spark.graphs import Graph

# Attach schema to graph
graph = Graph(start=node, state_schema=PipelineState)

# Access typed state
state = await graph.state.get_typed()
state.processed_count += 1
await graph.state.set_from_model(state)
```

### MissionStateSchemaSpec

Specify state schema in MissionSpec.

```python
state_schema = MissionStateSchemaSpec(
    schema_class="myapp.schemas:PipelineState",
    fields={
        "processed_count": {
            "type": "int",
            "required": True,
            "default": 0,
            "description": "Items processed"
        },
        "error_count": {
            "type": "int",
            "required": True,
            "default": 0
        }
    }
)
```

## Strategy Bindings

### MissionStrategyBindingSpec

Bind reasoning strategies to specific agents.

```python
from spark.nodes.spec import MissionStrategyBindingSpec

strategies = [
    MissionStrategyBindingSpec(
        target="agent1",
        reference="agents.agent1",
        strategy=ReasoningStrategySpec(
            type="react",
            config={"verbose": True}
        )
    ),
    MissionStrategyBindingSpec(
        target="agent2",
        reference="agents.agent2",
        strategy=ReasoningStrategySpec(
            type="plan_and_solve",
            config={"planning_steps": 3}
        )
    )
]
```

**Use Cases**:
- Configure different strategies per environment
- A/B testing of reasoning approaches
- Agent-specific optimization

## Telemetry Configuration

### MissionTelemetrySpec

Configure observability for mission.

```python
telemetry = MissionTelemetrySpec(
    enabled=True,
    backend="sqlite",
    db_path="telemetry.db",
    sampling_rate=1.0,
    buffer_size=100,
    export_interval=10.0
)
```

**Backend Options**:
- `memory`: In-memory (dev/test)
- `sqlite`: SQLite database (local production)
- `postgresql`: PostgreSQL (distributed production)
- `otlp`: OpenTelemetry Protocol (observability platforms)

## Deployment Metadata

### MissionDeploymentSpec

Specify deployment configuration.

```python
deployment = MissionDeploymentSpec(
    target="production",
    replicas=3,
    resources={
        "cpu": "2",
        "memory": "4Gi",
        "gpu": "0"
    },
    health_check_interval=30,
    restart_policy="on-failure",
    environment={
        "LOG_LEVEL": "INFO",
        "API_TIMEOUT": "30"
    }
)
```

**Targets**: `development`, `staging`, `production`

## Mission Lifecycle

### Creation

```python
from spark.nodes.spec import MissionSpec
from spark.nodes.serde import save_mission_spec

# Create mission
mission = MissionSpec(
    mission_id="com.example.workflow",
    version="1.0.0",
    graph=graph_spec,
    plan=plan_spec
)

# Save
save_mission_spec("mission.json", mission)
```

### Validation

```bash
# Validate mission
spark-spec mission-validate mission.json --strict --check-deployment
```

### Packaging

```bash
# Create deployable package
spark-spec mission-package mission.json --include-deps -o mission.zip
```

**Package Contents**:
- mission.json (specification)
- requirements.txt (dependencies)
- manifest.json (metadata)
- schemas/ (state schemas)
- tools/ (tool definitions)

### Deployment

```bash
# Check deployment readiness
spark-spec mission-deploy mission.json --target production --dry-run

# Deploy
spark-spec mission-deploy mission.json --target production
```

## Mission Execution

### Loading and Running

```python
from spark.nodes.serde import load_mission_spec
from spark.kit.loader import SpecLoader

# Load mission
mission = load_mission_spec("mission.json")

# Load graph from mission
loader = SpecLoader()
graph = loader.load_graph(mission.graph)

# Attach mission control
if mission.plan:
    from spark.graphs.mission_control import MissionPlan, PlanManager
    plan = MissionPlan.from_snapshot(mission.plan.model_dump()["steps"])
    manager = PlanManager(plan)
    manager.attach(graph)

# Run
result = await graph.run()
```

### Monitoring

```python
# Access plan status
plan_snapshot = await graph.state.get("mission_plan")
print(MissionPlan.from_snapshot(plan_snapshot).render_text())

# Access metrics
metrics = await graph.state.get("metrics")
```

## CLI Commands

### mission-generate

```bash
spark-spec mission-generate "ETL Pipeline" \
    --graph etl.json \
    --plan "extract,transform,load" \
    -o mission.json
```

### mission-validate

```bash
spark-spec mission-validate mission.json --check-deployment
```

### mission-diff

```bash
spark-spec mission-diff mission_v1.json mission_v2.json --format html -o diff.html
```

### mission-package

```bash
spark-spec mission-package mission.json --include-deps -o package.zip
```

### mission-deploy

```bash
spark-spec mission-deploy mission.json --target production
```

## Best Practices

**Use Semantic Versioning**: Version missions with semver (MAJOR.MINOR.PATCH).

**Document Plans**: Provide clear descriptions for each plan step.

**Define State Schemas**: Use typed state models for validation and safety.

**Configure Telemetry**: Enable comprehensive observability.

**Test with Simulation**: Use simulation before production deployment.

**Package Dependencies**: Include all dependencies in mission packages.

**Version Control**: Commit mission specs to git.

**Separate Environments**: Maintain separate missions for dev/staging/prod.

**Monitor Plans**: Track plan progress during execution.

**Use Guardrails**: Set runtime limits and budgets.

## Examples

See [Simulation System](./simulation.md) for testing missions with simulated tools.

## Next Steps

- **[Simulation System](./simulation.md)**: Testing missions
- **[Spec CLI Tool](./cli.md)**: Mission CLI commands
- **[Graph Analysis](./analysis.md)**: Analyzing mission graphs
- **[Best Practices: Production Deployment](../best-practices/production.md)

## Related Documentation

- [Graph System: Graph State](../graphs/graph-state.md)
- [Integration: Mission Deployment](../integration/mission-deployment.md)
- [API Reference: Mission Control](../api/mission-control.md)
