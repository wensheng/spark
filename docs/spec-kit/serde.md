---
title: Serialization & Deserialization
parent: SpecKit
nav_order: 2
---
# Serialization & Deserialization
---

Spark provides bidirectional conversion between runtime Python objects (graphs, nodes, agents) and structured JSON specifications. This serialization system enables graph persistence, version control, portability, and programmatic manipulation.

## Overview

The serialization system (`spark/nodes/serde.py`) provides functions for:

- **Serialization**: Python objects → Pydantic models → JSON
- **Deserialization**: JSON → Pydantic models (→ Python objects via code generation)
- **Validation**: Type checking and semantic validation during conversion
- **Full Fidelity**: Complete preservation of configuration, state, and metadata

## Core Functions

### graph_to_spec()

Convert a Python graph to a GraphSpec model.

```python
from spark.nodes.serde import graph_to_spec
from spark.graphs import Graph
from spark.nodes import Node

class ProcessorNode(Node):
    async def process(self, context):
        return {"result": "processed"}

# Create graph
node = ProcessorNode()
graph = Graph(start=node)

# Convert to spec
spec = graph_to_spec(graph, spark_version="2.0")

# Access spec fields
print(spec.id)  # Graph identifier
print(spec.start)  # Starting node ID
print(len(spec.nodes))  # Number of nodes
print(len(spec.edges))  # Number of edges
```

**Signature**:
```python
def graph_to_spec(
    graph: BaseGraph,
    *,
    spark_version: str = '2.0'
) -> GraphSpec
```

**Parameters**:
- `graph`: Graph instance to serialize
- `spark_version`: Specification version (default: "2.0")

**Returns**: `GraphSpec` model

**What's Captured**:
- All nodes with complete configuration
- All edges with conditions
- Graph state (initial values, backend config, checkpoints)
- Event bus configuration
- Task and budget settings
- Graph-level tool definitions
- Agent configurations (model, tools, memory, reasoning)

### save_graph_json()

Serialize graph directly to JSON file.

```python
from spark.nodes.serde import save_graph_json
from spark.graphs import Graph

graph = Graph(start=my_node)

# Save to JSON file
save_graph_json("workflow.json", graph, indent=2)

# With version specified
save_graph_json("workflow.json", graph, spark_version="2.0", indent=2)
```

**Signature**:
```python
def save_graph_json(
    path: str,
    graph: BaseGraph,
    *,
    spark_version: str = '2.0',
    indent: int = 2
) -> None
```

**Parameters**:
- `path`: Output file path
- `graph`: Graph to serialize
- `spark_version`: Specification version
- `indent`: JSON indentation level (default: 2)

### graph_to_json()

Serialize graph to JSON string.

```python
from spark.nodes.serde import graph_to_json

json_str = graph_to_json(graph, spark_version="2.0", indent=2)
print(json_str)
```

**Signature**:
```python
def graph_to_json(
    graph: BaseGraph,
    *,
    spark_version: str = '2.0',
    indent: int = 2
) -> str
```

### load_graph_spec()

Load and validate GraphSpec from JSON file.

```python
from spark.nodes.serde import load_graph_spec

# Load from file
spec = load_graph_spec("workflow.json")

# Validate and access
print(f"Graph: {spec.id}")
print(f"Nodes: {len(spec.nodes)}")
print(f"Start: {spec.start}")

# Iterate nodes
for node in spec.nodes:
    print(f"Node {node.id} (type: {node.type})")

# Iterate edges
for edge in spec.edges:
    print(f"Edge {edge.from_node} -> {edge.to_node}")
```

**Signature**:
```python
def load_graph_spec(path: str) -> GraphSpec
```

**Validation**: Automatic validation via Pydantic:
- Schema validation (types, required fields)
- Unique node IDs
- Valid edge references
- Start node exists
- Cross-field consistency

## Mission Serialization

### save_mission_spec()

Save MissionSpec to JSON file.

```python
from spark.nodes.serde import save_mission_spec
from spark.nodes.spec import MissionSpec, GraphSpec

mission = MissionSpec(
    mission_id="com.example.my-mission",
    version="1.0",
    graph=GraphSpec(...),
    plan=...,
    deployment=...
)

save_mission_spec("mission.json", mission, indent=2)
```

**Signature**:
```python
def save_mission_spec(
    path: str,
    mission: MissionSpec,
    *,
    indent: int = 2
) -> None
```

### load_mission_spec()

Load MissionSpec from JSON file.

```python
from spark.nodes.serde import load_mission_spec

mission = load_mission_spec("mission.json")

print(mission.mission_id)
print(mission.version)
print(mission.graph.start)
```

**Signature**:
```python
def load_mission_spec(path: str) -> MissionSpec
```

## Component Serialization

### node_to_spec()

Serialize individual node to NodeSpec.

```python
from spark.nodes.serde import node_to_spec
from spark.nodes import Node

node = Node(id="processor")
spec = node_to_spec(node)

print(spec.id)  # "processor"
print(spec.type)  # "Node"
print(spec.config)  # Node configuration
```

**Type Inference**: Automatically detects node type:
- `"Agent"` for agent nodes
- `"RpcNode"` for RPC server nodes
- `"SubgraphNode"` for nested graphs
- `"JoinNode"` for synchronization nodes
- Class name for custom nodes

### edge_to_spec()

Serialize edge to EdgeSpec.

```python
from spark.nodes.serde import edge_to_spec

edge = node1.goto(node2, condition=lambda n: n.outputs.success)
spec = edge_to_spec(edge)

print(spec.from_node)  # Source node ID
print(spec.to_node)  # Target node ID
print(spec.condition)  # Condition spec
```

### tool_to_spec()

Serialize tool to ToolDefinitionSpec.

```python
from spark.nodes.serde import tool_to_spec
from spark.tools.decorator import tool

@tool
def search_web(query: str) -> str:
    """Search the web."""
    return search(query)

spec = tool_to_spec(search_web)

print(spec.name)  # "search_web"
print(spec.description)  # "Search the web."
print(spec.parameters)  # [ToolParameterSpec(...)]
```

### agent_config_to_spec()

Serialize agent configuration to EnhancedAgentConfigSpec.

```python
from spark.nodes.serde import agent_config_to_spec
from spark.agents import Agent

agent = Agent(...)
config_spec = agent_config_to_spec(agent)

print(config_spec.model)  # ModelSpec
print(config_spec.tools)  # List[ToolConfigSpec]
print(config_spec.reasoning_strategy)  # ReasoningStrategySpec
```

**Captures**:
- Model configuration
- Tool registry
- Memory settings
- Reasoning strategy
- Cost tracking
- Hooks
- Initial conversation history

### model_to_spec()

Serialize model to ModelSpec.

```python
from spark.nodes.serde import model_to_spec
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-5-mini", temperature=0.7)
spec = model_to_spec(model)

print(spec.provider)  # "openai"
print(spec.model_id)  # "gpt-5-mini"
print(spec.temperature)  # 0.7
```

## Serialization Patterns

### Full Graph Serialization

Complete workflow: create graph, serialize, save.

```python
from spark.nodes.serde import save_graph_json
from spark.graphs import Graph
from spark.nodes import Node

# 1. Create graph
class InputNode(Node):
    async def process(self, context):
        return {"data": "input"}

class ProcessorNode(Node):
    async def process(self, context):
        data = context.inputs.content["data"]
        return {"result": f"processed: {data}"}

input_node = InputNode()
processor = ProcessorNode()

input_node >> processor

graph = Graph(
    start=input_node,
    initial_state={"counter": 0}
)

# 2. Serialize to JSON
save_graph_json("workflow.json", graph, indent=2)

# 3. Verify
from spark.nodes.serde import load_graph_spec
spec = load_graph_spec("workflow.json")
assert len(spec.nodes) == 2
assert len(spec.edges) == 1
```

### Agent Workflow Serialization

Serialize graph with agent nodes.

```python
from spark.nodes.serde import save_graph_json
from spark.graphs import Graph
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

@tool
def calculate(expression: str) -> str:
    """Evaluate math expression."""
    return str(eval(expression))

model = OpenAIModel(model_id="gpt-5-mini")
config = AgentConfig(
    model=model,
    tools=[calculate],
    system_prompt="You are a math assistant"
)

agent = Agent(config=config)
graph = Graph(start=agent)

# Serialize - captures complete agent config
save_graph_json("agent_workflow.json", graph)

# Load and verify
from spark.nodes.serde import load_graph_spec
spec = load_graph_spec("agent_workflow.json")
agent_node = spec.nodes[0]
assert agent_node.type == "Agent"
assert "model" in agent_node.config
assert "tools" in agent_node.config
```

### Conditional Workflow Serialization

Serialize graph with edge conditions.

```python
from spark.nodes.serde import save_graph_json
from spark.graphs import Graph
from spark.nodes import Node

router = Node(id="router")
success_handler = Node(id="success")
error_handler = Node(id="error")

# Conditional edges
router.on(success=True) >> success_handler
router.on(success=False) >> error_handler

graph = Graph(start=router)
save_graph_json("conditional.json", graph)

# Verify conditions preserved
from spark.nodes.serde import load_graph_spec
spec = load_graph_spec("conditional.json")
for edge in spec.edges:
    print(f"{edge.from_node} -> {edge.to_node}: {edge.condition}")
```

## Deserialization Patterns

### Load and Validate

Load spec and perform validation.

```python
from spark.nodes.serde import load_graph_spec
from pydantic import ValidationError

try:
    spec = load_graph_spec("workflow.json")

    # Validation successful
    print(f"Loaded graph: {spec.id}")
    print(f"Nodes: {len(spec.nodes)}")
    print(f"Edges: {len(spec.edges)}")

    # Semantic validation
    node_ids = {n.id for n in spec.nodes}
    for edge in spec.edges:
        assert edge.from_node in node_ids, f"Invalid from_node: {edge.from_node}"
        assert edge.to_node in node_ids, f"Invalid to_node: {edge.to_node}"

except ValidationError as e:
    print("Validation failed:")
    for error in e.errors():
        print(f"  {error['loc']}: {error['msg']}")
except FileNotFoundError:
    print("File not found")
```

### Load and Inspect

Load spec and inspect structure.

```python
from spark.nodes.serde import load_graph_spec

spec = load_graph_spec("workflow.json")

# Inspect nodes
print("\nNodes:")
for node in spec.nodes:
    print(f"  {node.id} ({node.type})")
    if node.description:
        print(f"    Description: {node.description}")
    if node.config:
        print(f"    Config keys: {list(node.config.keys())}")

# Inspect edges
print("\nEdges:")
for edge in spec.edges:
    condition_str = f" if {edge.condition}" if edge.condition else ""
    print(f"  {edge.from_node} -> {edge.to_node}{condition_str}")

# Inspect graph features
if spec.graph_state:
    print(f"\nGraph State:")
    print(f"  Initial state: {spec.graph_state.initial_state}")
    print(f"  Backend: {spec.graph_state.backend.name if spec.graph_state.backend else 'default'}")

if spec.event_bus:
    print(f"\nEvent Bus:")
    print(f"  Enabled: {spec.event_bus.enabled}")
    print(f"  Buffer size: {spec.event_bus.buffer_size}")

if spec.tools:
    print(f"\nTools: {len(spec.tools)}")
    for tool in spec.tools:
        print(f"  {tool.name}: {tool.description}")
```

### Load and Generate Code

Load spec and generate Python code.

```python
from spark.nodes.serde import load_graph_spec
from spark.kit.codegen import CodeGenerator

spec = load_graph_spec("workflow.json")

# Generate code
generator = CodeGenerator(spec, style="production")
code = generator.generate()

print(code)
# Output contains:
# - Import statements
# - Node class definitions
# - Graph assembly
# - Entry point
```

See [Code Generation](./codegen.md) for details.

## Error Handling

### Validation Errors

Handle schema validation errors.

```python
from spark.nodes.serde import load_graph_spec
from pydantic import ValidationError

try:
    spec = load_graph_spec("invalid.json")
except ValidationError as e:
    print("Validation errors:")
    for error in e.errors():
        loc = " -> ".join(str(x) for x in error['loc'])
        print(f"  {loc}: {error['msg']}")
        print(f"    Input: {error.get('input', 'N/A')}")
```

**Common Validation Errors**:
- Missing required fields
- Invalid types
- Duplicate node IDs
- Invalid edge references
- Start node not found
- Tool choice requires tools

### File Errors

Handle file-related errors.

```python
from spark.nodes.serde import load_graph_spec

try:
    spec = load_graph_spec("workflow.json")
except FileNotFoundError:
    print("File not found")
except PermissionError:
    print("Permission denied")
except json.JSONDecodeError as e:
    print(f"Invalid JSON at line {e.lineno}, col {e.colno}: {e.msg}")
```

### Partial Serialization

Handle nodes that can't be fully serialized.

```python
from spark.nodes.serde import graph_to_spec
import logging

logging.basicConfig(level=logging.DEBUG)

# Serialization logs warnings for incomplete data
spec = graph_to_spec(graph)

# Check for missing data
for node in spec.nodes:
    if not node.config:
        print(f"Warning: Node {node.id} has no config")
```

## Version Compatibility

### Specifying Versions

Always include version in serialization.

```python
from spark.nodes.serde import save_graph_json

# Specify version explicitly
save_graph_json("workflow.json", graph, spark_version="2.0")

# Load and check version
from spark.nodes.serde import load_graph_spec
spec = load_graph_spec("workflow.json")
print(f"Spec version: {spec.spark_version}")

if spec.spark_version != "2.0":
    print("Warning: Version mismatch")
```

### Migration Between Versions

Handling version differences.

```python
from spark.nodes.serde import load_graph_spec
from spark.nodes.spec import GraphSpec

spec = load_graph_spec("old_workflow.json")

# Check version
if spec.spark_version == "1.0":
    # Migrate to 2.0
    print("Migrating from 1.0 to 2.0...")

    # Apply migrations
    # ... (future: use spark-spec schema-migrate)

    # Update version
    spec.spark_version = "2.0"

    # Save migrated version
    from spark.nodes.serde import save_graph_json
    # (requires reconstruction of graph or direct spec manipulation)
```

## Performance Considerations

**Serialization Speed**: Fast for typical graphs (< 1 second for 100+ nodes)

**File Size**: Compact JSON (1-100KB for typical graphs)

**Memory Usage**: Specs are lightweight Pydantic models

**Incremental Serialization**: Not supported - always serialize complete graph

**Caching**: Repeated serialization is not cached

## Best Practices

**Always Specify Version**: Include `spark_version` for compatibility tracking.

**Validate After Loading**: Check loaded specs meet your requirements.

**Use save_graph_json**: Prefer high-level functions over manual serialization.

**Handle Validation Errors**: Use try/except for ValidationError.

**Document Custom Nodes**: Add descriptions to help with code generation.

**Test Round-Trips**: Verify serialization → deserialization → code generation works.

**Use Indentation**: Indent JSON (indent=2) for readability and version control.

**Version Control**: Commit JSON specs to git for workflow versioning.

## Advanced Usage

### Custom Serialization

Extend serialization for custom node types.

```python
from spark.nodes.serde import node_to_spec, _infer_node_type
from spark.nodes.spec import NodeSpec

# Custom node
class MyCustomNode(Node):
    def __init__(self, custom_param=None):
        super().__init__()
        self.custom_param = custom_param

# Serialize
node = MyCustomNode(custom_param="value")
spec = node_to_spec(node)

# Custom config is preserved
assert spec.config.get("custom_param") == "value"
```

### Programmatic Spec Manipulation

Modify specs programmatically.

```python
from spark.nodes.serde import load_graph_spec, save_graph_json

# Load spec
spec = load_graph_spec("workflow.json")

# Modify
spec.description = "Updated workflow"
for node in spec.nodes:
    if node.type == "Agent":
        # Update agent config
        if "max_steps" in node.config:
            node.config["max_steps"] = 20

# Save modified spec
# (requires exporting back to graph or direct JSON dump)
import json
with open("workflow_updated.json", "w") as f:
    json.dump(spec.model_dump(), f, indent=2)
```

### Spec Merging

Combine multiple specs.

```python
from spark.nodes.serde import load_graph_spec
from spark.nodes.spec import GraphSpec

spec1 = load_graph_spec("graph1.json")
spec2 = load_graph_spec("graph2.json")

# Merge nodes and edges
merged_nodes = spec1.nodes + spec2.nodes
merged_edges = spec1.edges + spec2.edges

merged = GraphSpec(
    spark_version="2.0",
    id="merged-graph",
    start=spec1.start,
    nodes=merged_nodes,
    edges=merged_edges
)

# Validate
merged.model_validate(merged.model_dump())
```

## CLI Integration

The Spec CLI provides high-level commands for serialization:

```bash
# Export graph to JSON
spark-spec export myapp.workflows:production_graph -o workflow.json

# Validate JSON spec
spark-spec validate workflow.json

# Test round-trip conversion
spark-spec test workflow.json --round-trip
```

See [Spec CLI Tool](./cli.md) for complete command reference.

## Next Steps

- **[Specification Models](./models.md)**: Complete model reference
- **[Spec CLI Tool](./cli.md)**: Command-line operations
- **[Code Generation](./codegen.md)**: Generating Python from specs
- **[Mission System](./missions.md)**: High-level orchestration
- **[Simulation System](./simulation.md)**: Testing with mocked tools

## Related Documentation

- [API Reference: Spec Kit Classes](../api/spec-kit.md)
- [Best Practices: Production Deployment](../best-practices/production.md)
- [Integration: Specification-Driven Development](../integration/spec-driven-dev.md)
