---
title: Spec Kit Classes
parent: API
nav_order: 7
---
# Spec Kit Classes
---

This document provides comprehensive API reference for Spark's Spec Kit system. These classes enable graph serialization, code generation, analysis, and manipulation through comprehensive specification models.

## Table of Contents

- [Overview](#overview)
- [Specification Models](#specification-models)
  - [GraphSpec](#graphspec)
  - [NodeSpec](#nodespec)
  - [EdgeSpec](#edgespec)
  - [AgentConfigSpec](#agentconfigspec)
  - [ToolDefinitionSpec](#tooldefinitionspec)
  - [ModelSpec](#modelspec)
  - [GraphStateSpec](#graphstatespec)
- [Mission System](#mission-system)
  - [MissionSpec](#missionspec)
  - [MissionPlanSpec](#missionplanspec)
  - [MissionSimulationSpec](#missionsimulationspec)
  - [SimulationRunner](#simulationrunner)
- [Serialization](#serialization)
  - [graph_to_spec](#graph_to_spec)
  - [save_graph_json](#save_graph_json)
  - [load_graph_spec](#load_graph_spec)
  - [tool_to_spec](#tool_to_spec)
- [Code Generation](#code-generation)
  - [CodeGenerator](#codegenerator)
  - [ImportOptimizer](#importoptimizer)
  - [Generation Styles](#generation-styles)
- [Graph Analysis](#graph-analysis)
  - [GraphAnalyzer](#graphanalyzer)
  - [Complexity Metrics](#complexity-metrics)
  - [Optimization Suggestions](#optimization-suggestions)
- [Diff and Comparison](#diff-and-comparison)
  - [GraphDiffer](#graphdiffer)
  - [DiffResult](#diffresult)
  - [Diff Formats](#diff-formats)
- [CLI Tool](#cli-tool)

---

## Overview

The Spec Kit provides a complete system for:

- **Serialization**: Export graphs to JSON specifications
- **Deserialization**: Load graphs from JSON specifications
- **Code Generation**: Generate Python code from specifications
- **Analysis**: Analyze graph complexity and identify issues
- **Diffing**: Compare specifications and visualize changes
- **Validation**: Validate specifications for correctness
- **Optimization**: Suggest improvements based on analysis
- **Mission Management**: High-level goal orchestration with metadata
- **Simulation**: Test workflows without external dependencies

**Use Cases**:
- Version control for graph definitions
- Graph portability across environments
- Specification-driven development
- CI/CD validation of graph structures
- Documentation generation
- Graph optimization and refactoring
- Testing with simulated tools

---

## Specification Models

### GraphSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

`GraphSpec` is the top-level specification model representing a complete Spark graph with all nodes, edges, tools, and configuration.

### Class Signature

```python
class GraphSpec(BaseModel):
    """Complete graph specification."""
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Graph identifier |
| `name` | `Optional[str]` | Human-readable graph name |
| `description` | `Optional[str]` | Graph description |
| `version` | `str` | Spec version (e.g., "2.0") |
| `spark_version` | `str` | Spark ADK version |
| `start` | `Optional[str]` | Start node ID |
| `nodes` | `list[NodeSpec]` | List of node specifications |
| `edges` | `list[EdgeSpec]` | List of edge specifications |
| `tools` | `list[ToolDefinitionSpec]` | Tool definitions |
| `graph_state` | `Optional[GraphStateSpec]` | Graph state configuration |
| `event_bus` | `Optional[GraphEventBusSpec]` | Event bus configuration |
| `metadata` | `dict[str, Any]` | Additional metadata |

### Example

```python
from spark.nodes.spec import GraphSpec, NodeSpec, EdgeSpec

spec = GraphSpec(
    id="my_workflow",
    name="My Workflow",
    version="2.0",
    spark_version="2.0.0",
    start="input_node",
    nodes=[
        NodeSpec(id="input_node", type="Basic", ...),
        NodeSpec(id="process_node", type="Agent", ...)
    ],
    edges=[
        EdgeSpec(from_node="input_node", to_node="process_node")
    ],
    metadata={"author": "Alice", "created": "2025-12-05"}
)
```

---

### NodeSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

`NodeSpec` represents a single node in the graph with its type, configuration, and metadata.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Node identifier (required) |
| `type` | `str` | Node type (Basic, Agent, RpcNode, etc.) |
| `name` | `Optional[str]` | Human-readable node name |
| `description` | `Optional[str]` | Node description |
| `config` | `dict[str, Any]` | Node-specific configuration |
| `agent_config` | `Optional[EnhancedAgentConfigSpec]` | Agent configuration (if type=Agent) |
| `rpc_config` | `Optional[RpcNodeSpec]` | RPC configuration (if type=RpcNode) |
| `join_config` | `Optional[JoinNodeSpec]` | Join configuration (if type=JoinNode) |
| `batch_config` | `Optional[BatchProcessingSpec]` | Batch configuration |
| `subgraph` | `Optional[GraphSpec]` | Nested graph (if type=SubgraphNode) |
| `custom_class` | `Optional[str]` | Module:class reference for custom nodes |
| `metadata` | `dict[str, Any]` | Additional metadata |

### Example

```python
from spark.nodes.spec import NodeSpec, EnhancedAgentConfigSpec, ModelSpec

# Basic node
node = NodeSpec(
    id="process_node",
    type="Basic",
    name="Data Processor",
    config={"timeout": 30}
)

# Agent node
agent_node = NodeSpec(
    id="agent_node",
    type="Agent",
    agent_config=EnhancedAgentConfigSpec(
        model=ModelSpec(provider="openai", model_id="gpt-5-mini"),
        system_prompt="You are a helpful assistant",
        max_steps=10
    )
)
```

---

### EdgeSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

`EdgeSpec` represents a connection between two nodes with optional conditional routing.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `Optional[str]` | Edge identifier |
| `from_node` | `str` | Source node ID (required) |
| `to_node` | `str` | Destination node ID (required) |
| `condition` | `Optional[ConditionSpec]` | Routing condition |
| `label` | `Optional[str]` | Edge label for visualization |
| `metadata` | `dict[str, Any]` | Additional metadata |

### Example

```python
from spark.nodes.spec import EdgeSpec, ConditionSpec

# Unconditional edge
edge = EdgeSpec(from_node="node_a", to_node="node_b")

# Conditional edge
edge = EdgeSpec(
    from_node="decision_node",
    to_node="success_node",
    condition=ConditionSpec(
        type="equals",
        key="status",
        value="success"
    )
)
```

---

### AgentConfigSpec

**Module**: `spark.nodes.spec`

**Type Alias**: `EnhancedAgentConfigSpec`

### Overview

Complete agent configuration specification including model, tools, memory, reasoning strategy, and hooks.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `model` | `Union[str, ModelSpec]` | Model configuration (required) |
| `name` | `Optional[str]` | Agent name |
| `description` | `Optional[str]` | Agent description |
| `system_prompt` | `Optional[str]` | System prompt for agent behavior |
| `prompt_template` | `Optional[str]` | Jinja2 template for user prompts |
| `tools` | `list[ToolConfigSpec]` | Tools available to agent |
| `tool_choice` | `str` | Tool selection strategy (auto, any, none) |
| `max_steps` | `int` | Maximum reasoning steps (default: 100) |
| `parallel_tool_execution` | `bool` | Enable parallel tool execution |
| `output_config` | `Optional[StructuredOutputSpec]` | Structured output configuration |
| `memory_config` | `Optional[MemoryConfigSpec]` | Memory management configuration |
| `reasoning_strategy` | `Optional[ReasoningStrategySpec]` | Reasoning strategy |
| `cost_tracking` | `Optional[CostTrackingSpec]` | Cost tracking configuration |
| `hooks` | `Optional[AgentHooksSpec]` | Agent hook callbacks |

### Example

```python
from spark.nodes.spec import (
    EnhancedAgentConfigSpec,
    ModelSpec,
    ToolConfigSpec,
    ReasoningStrategySpec,
    MemoryConfigSpec
)

config = EnhancedAgentConfigSpec(
    model=ModelSpec(provider="openai", model_id="gpt-5-mini"),
    system_prompt="You are a data analysis assistant",
    tools=[
        ToolConfigSpec(
            name="search_web",
            source="tools:search_web",
            enabled=True
        )
    ],
    tool_choice="auto",
    max_steps=10,
    memory_config=MemoryConfigSpec(
        policy="rolling_window",
        window=10
    ),
    reasoning_strategy=ReasoningStrategySpec(
        type="react",
        config={"verbose": True}
    )
)
```

---

### ToolDefinitionSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

Complete tool definition specification extracted from @tool decorated functions.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Tool identifier (required) |
| `description` | `Optional[str]` | Tool description |
| `function_ref` | `str` | Module:function reference |
| `parameters` | `list[ToolParameterSpec]` | Tool parameters |
| `return_type` | `Optional[str]` | Return type annotation |
| `is_async` | `bool` | Whether tool is async |
| `requires_context` | `bool` | Whether tool requires context injection |

### Example

```python
from spark.nodes.spec import ToolDefinitionSpec, ToolParameterSpec

tool = ToolDefinitionSpec(
    name="web_search",
    description="Search the web for information",
    function_ref="myapp.tools:web_search",
    parameters=[
        ToolParameterSpec(
            name="query",
            type="str",
            required=True,
            description="Search query"
        ),
        ToolParameterSpec(
            name="max_results",
            type="int",
            required=False,
            default=10
        )
    ],
    return_type="str",
    is_async=True,
    requires_context=False
)
```

---

### ModelSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

Model configuration specification for any LLM provider.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `provider` | `str` | Provider name (openai, bedrock, gemini) |
| `model_id` | `str` | Model identifier (required) |
| `api_key` | `Optional[str]` | API key (use env vars in production) |
| `base_url` | `Optional[str]` | Custom API endpoint |
| `region` | `Optional[str]` | AWS region (for Bedrock) |
| `config` | `dict[str, Any]` | Provider-specific configuration |

### Example

```python
from spark.nodes.spec import ModelSpec

# OpenAI model
model = ModelSpec(
    provider="openai",
    model_id="gpt-5-mini",
    config={"temperature": 0.7, "max_tokens": 1000}
)

# Bedrock model
model = ModelSpec(
    provider="bedrock",
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region="us-west-2"
)
```

---

### GraphStateSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

Graph state configuration specification with backend and schema settings.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | `bool` | Whether graph state is enabled |
| `initial_state` | `dict[str, Any]` | Initial state values |
| `backend` | `Optional[StateBackendConfigSpec]` | State backend configuration |
| `enable_transactions` | `bool` | Enable transactional updates |
| `enable_locking` | `bool` | Enable thread-safe locking |
| `schema` | `Optional[MissionStateSchemaSpec]` | State schema definition |

---

## Mission System

### MissionSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

High-level goal orchestration with graph + metadata + configuration. Missions provide a deployment-ready package with versioning, state schemas, plans, and deployment settings.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `mission_id` | `str` | Mission identifier (required) |
| `name` | `str` | Human-readable mission name (required) |
| `description` | `Optional[str]` | Mission description |
| `version` | `str` | Mission version |
| `graph` | `GraphSpec` | The workflow graph (required) |
| `state_schema` | `Optional[MissionStateSchemaSpec]` | State schema definition |
| `plan` | `Optional[MissionPlanSpec]` | Mission plan with steps |
| `strategy_bindings` | `list[MissionStrategyBindingSpec]` | Strategy bindings |
| `deployment` | `Optional[MissionDeploymentSpec]` | Deployment configuration |
| `metadata` | `dict[str, Any]` | Additional metadata |

### Example

```python
from spark.nodes.spec import MissionSpec, GraphSpec, MissionStateSchemaSpec

mission = MissionSpec(
    mission_id="data_pipeline_v1",
    name="Data Processing Pipeline",
    description="ETL pipeline for customer data",
    version="1.0.0",
    graph=my_graph_spec,
    state_schema=MissionStateSchemaSpec(
        schema_class="myapp.models:PipelineState",
        initial_state={"processed_count": 0}
    ),
    metadata={
        "owner": "data-team",
        "environment": "production"
    }
)
```

---

### MissionPlanSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

Declarative plan with steps and dependencies for mission execution tracking.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `steps` | `list[MissionPlanStepSpec]` | Ordered list of steps |
| `dependencies` | `dict[str, list[str]]` | Step dependencies map |
| `metadata` | `dict[str, Any]` | Additional metadata |

---

### MissionSimulationSpec

**Module**: `spark.nodes.spec`

**Inheritance**: `BaseModel`

### Overview

Configuration for running missions with simulated tools (no external dependencies).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool_overrides` | `dict[str, Any]` | Tool name to mock response map |
| `custom_handlers` | `dict[str, str]` | Tool name to handler function map |
| `enable_logging` | `bool` | Enable simulation logging |

### Example

```python
from spark.nodes.spec import MissionSimulationSpec

simulation = MissionSimulationSpec(
    tool_overrides={
        "web_search": {"results": ["Mock result 1", "Mock result 2"]},
        "database_query": {"rows": [{"id": 1, "name": "Test"}]}
    },
    custom_handlers={
        "complex_tool": "myapp.handlers:mock_complex_tool"
    },
    enable_logging=True
)
```

---

### SimulationRunner

**Module**: `spark.kit.simulation`

### Overview

Execute missions with simulated tools for testing without external dependencies.

### Key Methods

#### `run_mission_simulation()`

Run a mission with tool overrides.

```python
async def run_mission_simulation(
    mission_spec: MissionSpec,
    simulation_spec: MissionSimulationSpec,
    inputs: Optional[dict] = None
) -> dict
```

**Parameters**:
- `mission_spec`: Mission to run
- `simulation_spec`: Simulation configuration
- `inputs`: Optional mission inputs

**Returns**: Dictionary with simulation results

---

## Serialization

### graph_to_spec

**Module**: `spark.nodes.serde`

### Overview

Convert a runtime Graph instance to a GraphSpec for serialization.

### Signature

```python
def graph_to_spec(
    graph: BaseGraph,
    spark_version: str = "2.0",
    include_metadata: bool = True
) -> GraphSpec
```

**Parameters**:
- `graph`: Graph instance to convert
- `spark_version`: Spec version to use
- `include_metadata`: Include runtime metadata

**Returns**: GraphSpec representation

### Example

```python
from spark.nodes.serde import graph_to_spec
from spark.graphs import Graph

# Create graph
graph = Graph(start=my_node)

# Convert to spec
spec = graph_to_spec(graph, spark_version="2.0")

# Access spec fields
print(f"Graph has {len(spec.nodes)} nodes and {len(spec.edges)} edges")
```

---

### save_graph_json

**Module**: `spark.nodes.serde`

### Overview

Serialize a graph to JSON file.

### Signature

```python
def save_graph_json(
    file_path: str,
    graph: BaseGraph,
    spark_version: str = "2.0",
    indent: int = 2
) -> None
```

**Parameters**:
- `file_path`: Path to JSON file
- `graph`: Graph instance to save
- `spark_version`: Spec version
- `indent`: JSON indentation (None for compact)

### Example

```python
from spark.nodes.serde import save_graph_json

save_graph_json("workflow.json", graph, indent=2)
```

---

### load_graph_spec

**Module**: `spark.nodes.serde`

### Overview

Load and validate a GraphSpec from JSON file.

### Signature

```python
def load_graph_spec(file_path: str) -> GraphSpec
```

**Parameters**:
- `file_path`: Path to JSON file

**Returns**: GraphSpec instance

**Raises**: `ValidationError` if JSON is invalid

### Example

```python
from spark.nodes.serde import load_graph_spec

spec = load_graph_spec("workflow.json")
print(f"Loaded {spec.name} v{spec.version}")
```

---

### tool_to_spec

**Module**: `spark.nodes.serde`

### Overview

Extract tool specification from @tool decorated function.

### Signature

```python
def tool_to_spec(tool: Any) -> Optional[ToolDefinitionSpec]
```

**Parameters**:
- `tool`: Tool function or BaseTool instance

**Returns**: ToolDefinitionSpec or None if extraction fails

---

## Code Generation

### CodeGenerator

**Module**: `spark.kit.codegen`

### Overview

Generate Python code from GraphSpec with multiple output styles.

### Key Methods

#### `generate_code()`

Generate Python code from specification.

```python
def generate_code(
    spec: GraphSpec,
    style: str = "simple",
    include_tests: bool = False,
    include_docs: bool = False
) -> str
```

**Parameters**:
- `spec`: GraphSpec to generate from
- `style`: Generation style (simple, production, documented)
- `include_tests`: Generate test file
- `include_docs`: Generate documentation

**Returns**: Generated Python code as string

### Example

```python
from spark.kit.codegen import CodeGenerator
from spark.nodes.serde import load_graph_spec

# Load spec
spec = load_graph_spec("workflow.json")

# Generate code
generator = CodeGenerator()
code = generator.generate_code(
    spec,
    style="production",
    include_tests=True,
    include_docs=True
)

# Write to file
with open("generated_workflow.py", "w") as f:
    f.write(code)
```

---

### ImportOptimizer

**Module**: `spark.kit.codegen`

### Overview

Optimize and organize imports for generated code.

### Key Methods

#### `add_import()`

Add an import to the optimizer.

```python
def add_import(
    self,
    module: str,
    items: Optional[List[str]] = None
) -> None
```

#### `generate_imports()`

Generate optimized import statements.

```python
def generate_imports(self) -> str
```

**Returns**: Formatted import block

---

### Generation Styles

#### Simple Style
- Minimal readable code
- Basic imports and structure
- No error handling
- Good for prototypes

#### Production Style
- Complete error handling
- Input validation
- Type hints throughout
- Logging integration
- Retry logic
- Good for deployment

#### Documented Style
- Full docstrings
- Inline comments
- Usage examples
- Type annotations
- Good for libraries and documentation

---

## Graph Analysis

### GraphAnalyzer

**Module**: `spark.kit.analysis`

### Overview

Analyze graph structure, detect issues, and provide optimization suggestions.

### Constructor

```python
def __init__(self, spec: GraphSpec) -> None
```

### Key Methods

#### `analyze_complexity()`

Compute complexity metrics for the graph.

```python
def analyze_complexity(self) -> Dict[str, Any]
```

**Returns**: Dictionary with complexity metrics

#### `find_bottlenecks()`

Identify potential performance bottlenecks.

```python
def find_bottlenecks(self) -> List[Dict[str, Any]]
```

**Returns**: List of bottleneck descriptions

#### `suggest_optimizations()`

Generate optimization suggestions.

```python
def suggest_optimizations(self) -> List[str]
```

**Returns**: List of optimization suggestions

#### `validate_semantic()`

Perform semantic validation beyond schema.

```python
def validate_semantic(self) -> List[str]
```

**Returns**: List of validation errors

### Example

```python
from spark.kit.analysis import GraphAnalyzer
from spark.nodes.serde import load_graph_spec

# Load spec
spec = load_graph_spec("workflow.json")

# Analyze
analyzer = GraphAnalyzer(spec)

# Get complexity metrics
metrics = analyzer.analyze_complexity()
print(f"Nodes: {metrics['node_count']}")
print(f"Max depth: {metrics['max_depth']}")
print(f"Cyclic: {metrics['cyclic']}")

# Find bottlenecks
bottlenecks = analyzer.find_bottlenecks()
for b in bottlenecks:
    print(f"Bottleneck at {b['node_id']}: {b['reason']}")

# Get suggestions
suggestions = analyzer.suggest_optimizations()
for s in suggestions:
    print(f"Suggestion: {s}")

# Validate
errors = analyzer.validate_semantic()
if errors:
    print(f"Found {len(errors)} validation errors")
```

---

### Complexity Metrics

Metrics returned by `analyze_complexity()`:

| Metric | Type | Description |
|--------|------|-------------|
| `node_count` | `int` | Total number of nodes |
| `edge_count` | `int` | Total number of edges |
| `max_depth` | `int` | Maximum path length from start |
| `avg_depth` | `float` | Average path length from start |
| `branching_factor` | `float` | Average outgoing edges per node |
| `cyclic` | `bool` | Whether graph contains cycles |
| `cycle_count` | `int` | Number of cycles detected |
| `connected_components` | `int` | Number of disconnected components |
| `unreachable_nodes` | `list[str]` | Nodes not reachable from start |

---

### Optimization Suggestions

Suggestions may include:

- **Parallel Execution**: Identify independent nodes that can run concurrently
- **Redundant Paths**: Detect and simplify redundant routing
- **Bottlenecks**: Suggest splitting heavy nodes
- **Dead Code**: Identify unreachable nodes
- **Cycle Optimization**: Suggest loop unrolling or caching
- **Edge Simplification**: Simplify complex conditions

---

## Diff and Comparison

### GraphDiffer

**Module**: `spark.kit.diff`

### Overview

Compare two GraphSpec instances and generate detailed diff reports in multiple formats.

### Key Methods

#### `diff()`

Generate diff between two specs.

```python
def diff(
    spec1: GraphSpec,
    spec2: GraphSpec
) -> DiffResult
```

**Parameters**:
- `spec1`: Baseline specification
- `spec2`: Comparison specification

**Returns**: DiffResult with detailed changes

#### `render_text()`

Render diff as text.

```python
def render_text(diff_result: DiffResult) -> str
```

#### `render_html()`

Render diff as HTML with styling.

```python
def render_html(diff_result: DiffResult) -> str
```

#### `render_json()`

Render diff as JSON.

```python
def render_json(diff_result: DiffResult) -> str
```

### Example

```python
from spark.kit.diff import GraphDiffer
from spark.nodes.serde import load_graph_spec

# Load specs
spec1 = load_graph_spec("workflow_v1.json")
spec2 = load_graph_spec("workflow_v2.json")

# Create differ
differ = GraphDiffer()

# Generate diff
diff_result = differ.diff(spec1, spec2)

# Check for changes
if diff_result.has_changes:
    summary = diff_result.summary
    print(f"Nodes added: {summary['nodes_added']}")
    print(f"Nodes removed: {summary['nodes_removed']}")
    print(f"Nodes modified: {summary['nodes_modified']}")

# Render as text
text_diff = differ.render_text(diff_result)
print(text_diff)

# Render as HTML
html_diff = differ.render_html(diff_result)
with open("diff.html", "w") as f:
    f.write(html_diff)
```

---

### DiffResult

**Module**: `spark.kit.diff`

### Overview

Complete diff result with all changes categorized.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `spec1_id` | `str` | Baseline spec identifier |
| `spec2_id` | `str` | Comparison spec identifier |
| `node_diffs` | `list[NodeDiff]` | Node changes |
| `edge_diffs` | `list[EdgeDiff]` | Edge changes |
| `tool_diffs` | `list[ToolDiff]` | Tool changes |
| `start_changed` | `bool` | Whether start node changed |
| `graph_state_changed` | `bool` | Whether graph state changed |
| `metadata_changes` | `dict` | Metadata changes |

### Properties

#### `has_changes: bool`

Returns True if there are any changes.

#### `summary: dict`

Returns summary statistics of changes.

---

### Diff Formats

#### Text Format
```
=== Graph Diff: workflow_v1 → workflow_v2 ===

Nodes:
+ Node 'new_node' added (type: Agent)
- Node 'old_node' removed (type: Basic)
~ Node 'modified_node' modified (description: old → new)

Edges:
+ Edge 'edge_1' added (node_a → node_b)

Summary:
  Nodes: +1 -1 ~1
  Edges: +1 -0 ~0
```

#### HTML Format
Styled HTML with color-coded additions (green), removals (red), and modifications (yellow).

#### JSON Format
Structured JSON with all diff details for programmatic processing.

---

## CLI Tool

### spark-spec

**Module**: `spark.kit.spec_cli`

Command-line interface for spec operations.

### Graph Commands

#### export
Export Python graph to JSON spec.
```bash
python -m spark.kit.spec_cli export module:graph_factory -o graph.json --version 2.0
```

#### validate
Validate JSON spec.
```bash
python -m spark.kit.spec_cli validate graph.json --semantic --strict
```

#### compile
Generate Python code from JSON spec.
```bash
python -m spark.kit.spec_cli compile graph.json -o ./generated --style production --tests
```

#### generate
Create minimal JSON spec from description.
```bash
python -m spark.kit.spec_cli generate "My graph description" -o graph.json
```

#### analyze
Analyze graph structure and complexity.
```bash
python -m spark.kit.spec_cli analyze graph.json --report report.html
```

#### diff
Compare two specs.
```bash
python -m spark.kit.spec_cli diff old.json new.json --format unified
```

#### optimize
Suggest and apply optimizations.
```bash
python -m spark.kit.spec_cli optimize graph.json --auto-fix -o optimized.json
```

#### test
Test spec validity and round-trip conversion.
```bash
python -m spark.kit.spec_cli test graph.json --validate --round-trip
```

#### introspect
Inspect Python graph and show detailed info.
```bash
python -m spark.kit.spec_cli introspect module:graph --format json
```

#### merge
Merge multiple specs into one.
```bash
python -m spark.kit.spec_cli merge spec1.json spec2.json spec3.json -o merged.json
```

#### extract
Extract subgraph from a spec.
```bash
python -m spark.kit.spec_cli extract graph.json --node start_node -o subgraph.json
```

### Mission Commands

#### mission-generate
Generate mission spec from description.
```bash
python -m spark.kit.spec_cli mission-generate "Data pipeline" graph.json -o mission.json
```

#### mission-validate
Validate mission spec JSON.
```bash
python -m spark.kit.spec_cli mission-validate mission.json
```

#### mission-package
Create deployable mission package.
```bash
python -m spark.kit.spec_cli mission-package mission.json -o package.zip
```

#### mission-deploy
Deployment readiness checks.
```bash
python -m spark.kit.spec_cli mission-deploy mission.json --check-all
```

### Simulation Commands

#### simulation-run
Run mission with simulated tools.
```bash
python -m spark.kit.spec_cli simulation-run mission.json simulation.json
```

#### simulation-diff
Diff simulation outputs.
```bash
python -m spark.kit.spec_cli simulation-diff run1.json run2.json
```

---

## Complete Example

```python
from spark.nodes.serde import graph_to_spec, save_graph_json, load_graph_spec
from spark.kit.codegen import CodeGenerator
from spark.kit.analysis import GraphAnalyzer
from spark.kit.diff import GraphDiffer
from spark.graphs import Graph

# Step 1: Create and save graph
graph = Graph(start=my_node)
save_graph_json("workflow_v1.json", graph, indent=2)

# Step 2: Load and analyze
spec = load_graph_spec("workflow_v1.json")
analyzer = GraphAnalyzer(spec)

metrics = analyzer.analyze_complexity()
print(f"Graph complexity: {metrics['node_count']} nodes, depth {metrics['max_depth']}")

suggestions = analyzer.suggest_optimizations()
for suggestion in suggestions:
    print(f"Optimization: {suggestion}")

# Step 3: Generate code
generator = CodeGenerator()
code = generator.generate_code(spec, style="production", include_tests=True)

with open("generated_workflow.py", "w") as f:
    f.write(code)

# Step 4: Make changes and compare
# ... modify graph ...
save_graph_json("workflow_v2.json", modified_graph)

spec1 = load_graph_spec("workflow_v1.json")
spec2 = load_graph_spec("workflow_v2.json")

differ = GraphDiffer()
diff_result = differ.diff(spec1, spec2)

if diff_result.has_changes:
    print("Changes detected:")
    print(differ.render_text(diff_result))

    # Save HTML diff report
    html_diff = differ.render_html(diff_result)
    with open("diff_report.html", "w") as f:
        f.write(html_diff)
```

---

## Best Practices

1. **Version Everything**: Include version in specs for compatibility tracking
2. **Validate Early**: Use `validate --semantic` in CI/CD pipelines
3. **Generate Tests**: Always generate tests with `--tests` flag
4. **Analyze Before Deploy**: Run analysis on specs before deployment
5. **Use Missions**: Package graphs as missions for deployment
6. **Simulate First**: Test with simulation before using real tools
7. **Diff Reviews**: Use HTML diffs for change reviews
8. **Document Specs**: Add rich metadata to specs
9. **Optimize Regularly**: Run optimization suggestions periodically
10. **Round-Trip Test**: Verify graph → spec → code → graph fidelity
