---
title: Specification Models
nav_order: 13
---
# Specification Models

Spark's specification models provide complete, type-safe representations of all framework components using Pydantic. These models enable serialization, validation, and programmatic manipulation of graphs, nodes, agents, tools, and missions.

## Overview

All specification models are defined in `spark/nodes/spec.py` as Pydantic `BaseModel` subclasses with:

- **Full type safety** with comprehensive type hints
- **Validation** on construction and field assignment
- **Serialization** to/from JSON
- **Documentation** via docstrings and field descriptions
- **Extensibility** via `extra='ignore'` configuration

## Core Specifications

### GraphSpec

Complete specification for a Spark graph including nodes, edges, state, event bus, and execution configuration.

```python
from spark.nodes.spec import GraphSpec

spec = GraphSpec(
    spark_version="2.0",
    id="com.example.my-workflow",
    description="Multi-step data processing workflow",
    start="input_node",
    nodes=[...],  # List of NodeSpec
    edges=[...],  # List of EdgeSpec
    graph_state=GraphStateSpec(
        initial_state={"counter": 0, "results": []},
        concurrent_mode=False
    ),
    event_bus=GraphEventBusSpec(
        enabled=True,
        buffer_size=100
    ),
    task=TaskSpec(
        type="one_off",
        budget=BudgetSpec(max_seconds=60.0, max_tokens=100000)
    ),
    tools=[...]  # List of ToolDefinitionSpec
)
```

**Fields**:
- `spark_version`: Specification version (e.g., "2.0")
- `id`: Unique graph identifier (reverse DNS recommended)
- `description`: Human-readable description
- `start`: Starting node ID
- `nodes`: List of node specifications
- `edges`: List of edge specifications
- `graph_state`: Optional shared state configuration
- `event_bus`: Optional event bus configuration
- `task`: Optional default task configuration
- `tools`: Optional graph-level tool definitions

**Validation**:
- Node IDs must be unique within the graph
- Start node must exist in nodes list
- Edge references must point to valid nodes

### NodeSpec

Specification for a single node in a graph.

```python
from spark.nodes.spec import NodeSpec

node = NodeSpec(
    id="processor",
    type="Node",  # Or "Agent", "RpcNode", "SubgraphNode", etc.
    description="Process incoming data",
    inputs={"data": "str"},
    outputs={"result": "dict", "success": "bool"},
    config={
        "retry": {"max_attempts": 3, "backoff_seconds": 1.0},
        "timeout": {"seconds": 30.0},
        "rate_limit": {"requests_per_second": 10}
    }
)
```

**Fields**:
- `id`: Unique node identifier within graph
- `type`: Node class name (e.g., "Node", "Agent", "SubgraphNode")
- `description`: Human-readable description
- `inputs`: Expected input schema as dict mapping names to type strings
- `outputs`: Expected output schema as dict mapping names to type strings
- `config`: Node-specific configuration (capabilities, settings, etc.)

**Common Node Types**:
- `"Node"`: Standard processing node
- `"Agent"`: LLM-powered agent node (uses EnhancedAgentConfigSpec)
- `"RpcNode"`: JSON-RPC server node
- `"SubgraphNode"`: Nested graph node
- `"JoinNode"`: Synchronization node for parallel branches
- Custom node types can be specified

### EdgeSpec

Specification for connections between nodes.

```python
from spark.nodes.spec import EdgeSpec, ConditionSpec

edge = EdgeSpec(
    id="e1",
    from_node="router",
    to_node="processor",
    condition=ConditionSpec(
        kind="expr",
        expr="$.outputs.score > 0.7"
    ),
    priority=10,
    description="High quality route",
    metadata={"category": "quality_check"},
    delay_seconds=None,
    event_topic=None
)
```

**Fields**:
- `id`: Unique edge identifier
- `from_node`: Source node ID
- `to_node`: Target node ID
- `condition`: Optional activation condition
- `priority`: Evaluation priority (higher = evaluated first)
- `description`: Human-readable description
- `metadata`: Additional edge metadata
- `fanout_behavior`: Always `"evaluate_all"` in Spark
- `delay_seconds`: Optional delay before forwarding
- `event_topic`: Optional event bus topic for event-driven edges
- `event_filter`: Optional filter for event payloads

**Edge Conditions**: Edges can have conditions specified as:
- `None`: Always active
- String: Simple expression (e.g., `"$.outputs.success == true"`)
- `ConditionSpec`: Full condition specification

### ConditionSpec

Specification for edge activation conditions.

```python
from spark.nodes.spec import ConditionSpec

# Expression-based condition
condition = ConditionSpec(
    kind="expr",
    expr="$.outputs.score > 0.7 && $.outputs.valid == true"
)

# Lambda-based condition (for code generation)
condition = ConditionSpec(
    kind="lambda",
    expr="lambda n: n.outputs.score > 0.7"
)

# Field equality condition
condition = ConditionSpec(
    kind="field_eq",
    field="outputs.status",
    value="success"
)
```

**Condition Kinds**:
- `"expr"`: JSONPath-style expression
- `"lambda"`: Python lambda expression
- `"field_eq"`: Simple field equality check
- `"always"`: Always true
- `"never"`: Always false

## Agent Specifications

### EnhancedAgentConfigSpec

Complete agent configuration including model, tools, memory, reasoning strategy, and hooks.

```python
from spark.nodes.spec import (
    EnhancedAgentConfigSpec,
    ModelSpec,
    ToolConfigSpec,
    MemoryConfigSpec,
    ReasoningStrategySpec,
    CostTrackingSpec
)

agent_config = EnhancedAgentConfigSpec(
    model=ModelSpec(
        provider="openai",
        model_id="gpt-4o",
        temperature=0.7,
        max_tokens=2000
    ),
    system_prompt="You are a helpful data processing assistant.",
    tools=[
        ToolConfigSpec(
            name="search",
            source="tools:search_web",
            enabled=True,
            config={"max_results": 5}
        )
    ],
    tool_choice="auto",
    max_steps=10,
    parallel_tool_execution=True,
    memory_config=MemoryConfigSpec(
        policy="rolling_window",
        window=20,
        summary_max_chars=2000
    ),
    reasoning_strategy=ReasoningStrategySpec(
        type="react",
        config={"verbose": True}
    ),
    cost_tracking=CostTrackingSpec(
        enabled=True,
        track_tokens=True,
        track_cost=True
    )
)
```

**Key Fields**:
- `model`: Model configuration (ModelSpec or model_id string)
- `system_prompt`: System-level instructions
- `prompt_template`: Jinja2 template for user messages
- `tools`: List of tool configurations
- `tool_choice`: Tool selection strategy ("auto", "any", "none", or tool name)
- `max_steps`: Maximum reasoning/tool execution steps
- `parallel_tool_execution`: Enable parallel tool calls
- `output_config`: Structured output configuration
- `memory_config`: Conversation history management
- `reasoning_strategy`: How agent thinks and plans
- `cost_tracking`: Token and cost tracking configuration
- `hooks`: Lifecycle hooks for customization
- `preload_messages`: Initial conversation history

### ModelSpec

LLM model configuration.

```python
from spark.nodes.spec import ModelSpec

model = ModelSpec(
    provider="openai",  # or "bedrock", "gemini"
    model_id="gpt-4o",
    temperature=0.7,
    max_tokens=2000,
    top_p=0.9,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    enable_cache=True,
    cache_ttl_seconds=3600
)
```

**Providers**: `"openai"`, `"bedrock"`, `"gemini"`

### ReasoningStrategySpec

Agent reasoning strategy configuration.

```python
from spark.nodes.spec import ReasoningStrategySpec

# ReAct strategy
react = ReasoningStrategySpec(
    type="react",
    config={"verbose": True, "max_iterations": 5}
)

# Chain of Thought
cot = ReasoningStrategySpec(
    type="chain_of_thought",
    config={}
)

# Plan and Solve
plan_solve = ReasoningStrategySpec(
    type="plan_and_solve",
    config={"planning_steps": 3}
)

# Custom strategy
custom = ReasoningStrategySpec(
    type="custom",
    custom_class="myapp.strategies:MyStrategy",
    config={"param": "value"}
)
```

**Strategy Types**:
- `"noop"`: No structured reasoning (simple Q&A)
- `"react"`: Reasoning + Acting iteratively
- `"chain_of_thought"`: Step-by-step reasoning
- `"plan_and_solve"`: Plan-first execution
- `"custom"`: User-defined strategy

### MemoryConfigSpec

Conversation history management configuration.

```python
from spark.nodes.spec import MemoryConfigSpec

# Rolling window memory
memory = MemoryConfigSpec(
    policy="rolling_window",
    window=10  # Keep last 10 messages
)

# Summarization memory
memory = MemoryConfigSpec(
    policy="summarize",
    window=5,  # Keep last 5 messages + summary
    summary_max_chars=1000
)
```

**Memory Policies**:
- `"null"`: No memory retention
- `"rolling_window"`: Keep last N messages
- `"summarize"`: Summarize old messages
- `"custom"`: Custom policy

## Tool Specifications

### ToolDefinitionSpec

Complete tool definition from @tool decorator.

```python
from spark.nodes.spec import ToolDefinitionSpec, ToolParameterSpec

tool = ToolDefinitionSpec(
    name="search_web",
    function="tools:search_web",
    description="Search the web for information",
    parameters=[
        ToolParameterSpec(
            name="query",
            type="str",
            description="Search query",
            required=True
        ),
        ToolParameterSpec(
            name="max_results",
            type="int",
            description="Maximum results",
            required=False,
            default=10
        )
    ],
    return_type="str",
    return_description="Search results as formatted string",
    is_async=False,
    category="search",
    tags=["web", "search", "information"]
)
```

**Fields**:
- `name`: Tool identifier
- `function`: Module:function reference
- `description`: Human-readable description
- `parameters`: List of parameter specifications
- `return_type`: Return type as string
- `return_description`: Description of return value
- `is_async`: Whether tool is async
- `category`: Tool category
- `tags`: Tool tags for organization

### ToolConfigSpec

Tool configuration within an agent.

```python
from spark.nodes.spec import ToolConfigSpec

tool_config = ToolConfigSpec(
    name="search_web",
    source="tools:search_web",
    enabled=True,
    config={
        "max_results": 5,
        "timeout": 10.0
    }
)
```

## State and Event Specifications

### GraphStateSpec

Shared state configuration for graphs.

```python
from spark.nodes.spec import GraphStateSpec, StateBackendConfigSpec

state = GraphStateSpec(
    initial_state={"counter": 0, "results": []},
    concurrent_mode=False,
    backend=StateBackendConfigSpec(
        type="memory"  # or "sqlite", "json"
    ),
    checkpoint=StateCheckpointSpec(
        enabled=True,
        interval_seconds=60.0,
        retention_count=10
    )
)
```

**Backend Types**:
- `"memory"`: In-memory (default)
- `"sqlite"`: SQLite persistent storage
- `"json"`: JSON file storage

### GraphEventBusSpec

Event bus configuration.

```python
from spark.nodes.spec import GraphEventBusSpec

event_bus = GraphEventBusSpec(
    enabled=True,
    buffer_size=100,
    replay_buffer_size=50
)
```

### BudgetSpec

Execution budget constraints.

```python
from spark.nodes.spec import BudgetSpec

budget = BudgetSpec(
    max_seconds=60.0,
    max_tokens=100000,
    max_cost=1.0
)
```

## Mission Specifications

### MissionSpec

Complete mission package with graph, plan, strategies, and deployment metadata.

```python
from spark.nodes.spec import MissionSpec, MissionPlanSpec, MissionStateSchemaSpec

mission = MissionSpec(
    spark_version="2.0",
    mission_id="com.example.data-pipeline",
    version="1.0",
    description="Production data processing pipeline",
    graph=GraphSpec(...),
    plan=MissionPlanSpec(
        steps=[
            MissionPlanStepSpec(
                id="validate",
                description="Validate input data",
                depends_on=[]
            ),
            MissionPlanStepSpec(
                id="process",
                description="Process validated data",
                depends_on=["validate"]
            )
        ]
    ),
    state_schema=MissionStateSchemaSpec(
        schema_class="myapp.schemas:DataPipelineState",
        fields={
            "processed_count": {"type": "int", "required": True},
            "error_count": {"type": "int", "required": True}
        }
    ),
    deployment=MissionDeploymentSpec(
        target="production",
        replicas=3,
        resources={"cpu": "2", "memory": "4Gi"}
    ),
    simulation=MissionSimulationSpec(
        enabled=True,
        tools=[
            SimulationToolOverrideSpec(
                name="external_api",
                static_response={"status": "success", "data": [...]}
            )
        ]
    )
)
```

**Mission Components**:
- `graph`: Core workflow specification
- `plan`: Declarative execution plan with steps
- `strategies`: Strategy bindings for agents
- `state_schema`: State model definition
- `telemetry`: Telemetry configuration
- `deployment`: Deployment metadata
- `simulation`: Tool overrides for testing

See [Mission System](./missions.md) for complete details.

### MissionSimulationSpec

Simulation configuration for testing.

```python
from spark.nodes.spec import MissionSimulationSpec, SimulationToolOverrideSpec

simulation = MissionSimulationSpec(
    enabled=True,
    latency_seconds=0.1,
    tools=[
        # Static response override
        SimulationToolOverrideSpec(
            name="external_api",
            description="Simulated API",
            static_response={"status": "ok"},
            parameters={"endpoint": {"type": "str"}},
            response_schema={"type": "object"}
        ),
        # Custom handler override
        SimulationToolOverrideSpec(
            name="database_query",
            description="Simulated DB",
            handler="myapp.mocks:mock_db_query",
            parameters={"query": {"type": "str"}}
        )
    ]
)
```

See [Simulation System](./simulation.md) for complete details.

## Special Node Specifications

### RpcNodeSpec

JSON-RPC server node configuration.

```python
from spark.nodes.spec import RpcNodeSpec

rpc = RpcNodeSpec(
    host="0.0.0.0",
    port=8000,
    ssl_certfile="/path/to/cert.pem",
    ssl_keyfile="/path/to/key.pem",
    methods=["process", "getData", "healthCheck"]
)
```

### SubgraphNodeSpec

Nested graph node configuration.

```python
from spark.nodes.spec import SubgraphNodeSpec

subgraph = SubgraphNodeSpec(
    graph_ref="workflows:data_processing_subgraph",
    input_mapping={"data": "$.inputs.raw_data"},
    output_mapping={"result": "processed_data"},
    isolated_state=True
)
```

### JoinNodeSpec

Synchronization node for parallel branches.

```python
from spark.nodes.spec import JoinNodeSpec

join = JoinNodeSpec(
    strategy="wait_all",  # or "wait_any", "wait_n"
    required_inputs=["branch1", "branch2", "branch3"],
    timeout_seconds=30.0,
    merge_strategy="dict"  # or "list", "first"
)
```

## Validation

All specification models include comprehensive validation:

**Field Validation**: Type checking, required fields, default values

**Cross-Field Validation**: Consistency checks across related fields

**Semantic Validation**: Business logic validation (e.g., tool_choice requires tools)

**Reference Validation**: IDs and references point to valid targets

### Example Validation Errors

```python
from spark.nodes.spec import EnhancedAgentConfigSpec
from pydantic import ValidationError

try:
    config = EnhancedAgentConfigSpec(
        model="gpt-4o",
        tool_choice="any",  # Requires tools!
        tools=[]  # Empty tools list
    )
except ValidationError as e:
    print(e)
    # ValidationError: tool_choice='any' requires at least one tool
```

## Best Practices

**Use Type Hints**: Always include complete type annotations in NodeSpec inputs/outputs.

**Document Thoroughly**: Provide descriptions for nodes, edges, and tools.

**Version Specifications**: Include `spark_version` for compatibility tracking.

**Validate Early**: Use Pydantic's validation to catch errors during construction.

**Leverage Defaults**: Most fields have sensible defaults; only override when needed.

**Structure Configs**: Use nested specifications (like `MemoryConfigSpec`) rather than raw dicts.

**Reference External Code**: Use `"module:attr"` strings for functions, classes, and factories.

## Model Hierarchy

```
GraphSpec
├── nodes: List[NodeSpec]
│   ├── config: EnhancedAgentConfigSpec (for Agent nodes)
│   │   ├── model: ModelSpec
│   │   ├── tools: List[ToolConfigSpec]
│   │   ├── memory_config: MemoryConfigSpec
│   │   ├── reasoning_strategy: ReasoningStrategySpec
│   │   └── cost_tracking: CostTrackingSpec
│   └── config: RpcNodeSpec | SubgraphNodeSpec | ... (for special nodes)
├── edges: List[EdgeSpec]
│   └── condition: ConditionSpec
├── graph_state: GraphStateSpec
│   ├── backend: StateBackendConfigSpec
│   └── checkpoint: StateCheckpointSpec
├── event_bus: GraphEventBusSpec
├── task: TaskSpec
│   └── budget: BudgetSpec
└── tools: List[ToolDefinitionSpec]
    └── parameters: List[ToolParameterSpec]

MissionSpec
├── graph: GraphSpec
├── plan: MissionPlanSpec
│   └── steps: List[MissionPlanStepSpec]
├── state_schema: MissionStateSchemaSpec
├── telemetry: MissionTelemetrySpec
├── deployment: MissionDeploymentSpec
└── simulation: MissionSimulationSpec
    └── tools: List[SimulationToolOverrideSpec]
```

## Next Steps

- **[Serialization & Deserialization](./serde.md)**: Converting between Python and JSON
- **[Spec CLI Tool](./cli.md)**: Command-line operations
- **[Code Generation](./codegen.md)**: Generating Python from specifications
- **[Mission System](./missions.md)**: High-level orchestration packages
- **[Simulation System](./simulation.md)**: Testing with mocked tools

## Related Documentation

- [API Reference: Spec Kit Classes](../api/spec-kit.md)
- [Architecture: System Architecture](../architecture/system-architecture.md)
- [Node System: Fundamentals](../nodes/fundamentals.md)
- [Agent System: Configuration](../agents/configuration.md)
