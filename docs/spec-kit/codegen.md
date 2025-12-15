---
title: Code Generation
parent: SpecKit
nav_order: 4
---
# Code Generation
---

The Spark code generator (`spark/kit/codegen.py`) provides reverse-compilation from GraphSpec specifications to executable Python code. This enables specification-driven development, where workflows are defined declaratively and code is generated automatically.

## Overview

The code generator transforms JSON specifications into production-ready Python code with:

- **Complete Implementations**: Full node class definitions with process methods
- **Agent Configuration**: Complete agent setup with models, tools, memory, reasoning
- **Graph Assembly**: Connection of nodes with edge conditions
- **Import Optimization**: Minimal, organized import statements
- **Multiple Styles**: Simple, production, or fully documented code
- **Test Generation**: Optional test suite generation
- **Multi-File Support**: Project structure or single-file output

## Generation Styles

The generator supports three code generation styles:

### Simple Style

Minimal, readable code for quick prototyping.

```python
from spark.kit.codegen import CodeGenerator

generator = CodeGenerator(spec, style="simple")
code = generator.generate()
```

**Characteristics**:
- Minimal boilerplate
- Basic error handling
- Inline comments
- Single file output
- Quick to understand

**Use Cases**:
- Prototyping
- Learning
- Simple workflows
- Internal tools

### Production Style

Production-ready code with comprehensive error handling and logging.

```python
generator = CodeGenerator(spec, style="production")
code = generator.generate()
```

**Characteristics**:
- Full error handling
- Structured logging
- Input validation
- Configuration management
- Retry logic
- Health checks
- Graceful shutdown

**Use Cases**:
- Production deployments
- Critical workflows
- Enterprise systems
- Long-running services

### Documented Style

Fully documented code with docstrings, type hints, and inline documentation.

```python
generator = CodeGenerator(spec, style="documented")
code = generator.generate()
```

**Characteristics**:
- Comprehensive docstrings
- Type annotations
- Parameter documentation
- Return value documentation
- Usage examples
- Cross-references

**Use Cases**:
- Public APIs
- Team collaboration
- Documentation generation
- Code review
- Maintenance

## Basic Usage

### Command Line

```bash
# Simple style
spark-spec compile workflow.json -o generated.py --style simple

# Production style
spark-spec compile workflow.json -o ./src --style production

# Documented style with tests
spark-spec compile workflow.json -o ./project --style documented --tests
```

### Python API

```python
from spark.nodes.serde import load_graph_spec
from spark.kit.codegen import CodeGenerator

# Load specification
spec = load_graph_spec("workflow.json")

# Create generator
generator = CodeGenerator(spec, style="production")

# Generate code
code = generator.generate()

# Save to file
with open("generated.py", "w") as f:
    f.write(code)
```

## Generated Code Structure

### Single File Output

Generated code in single-file mode includes:

```python
# ===== Generated Code Structure =====

# 1. Module docstring
"""Generated workflow implementation.

This code was automatically generated from workflow.json
Do not edit manually - regenerate from specification.
"""

# 2. Import statements (optimized)
from typing import Any, Dict, List, Optional
from spark.graphs.graph import Graph
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext

# 3. Tool definitions
@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    # Implementation or stub

# 4. Node class definitions
class ProcessorNode(Node):
    """Process incoming data."""

    async def process(self, context: ExecutionContext):
        """Process method implementation."""
        # Generated logic
        return {"result": "processed"}

# 5. Graph assembly
def create_graph() -> Graph:
    """Create and configure the workflow graph."""
    # Node instantiation
    # Edge connections
    # Graph configuration
    return graph

# 6. Entry point
if __name__ == "__main__":
    graph = create_graph()
    result = asyncio.run(graph.run())
    print(result)
```

### Multi-File Output

Generated project structure:

```
project/
├── __init__.py           # Package initialization
├── nodes.py              # Node class definitions
├── tools.py              # Tool definitions
├── graph.py              # Graph assembly
├── config.py             # Configuration
├── main.py               # Entry point
└── tests/                # Test suite (optional)
    ├── __init__.py
    ├── test_nodes.py
    ├── test_tools.py
    └── test_graph.py
```

## Component Generation

### Node Generation

Nodes are generated as classes with type-safe process methods.

**Specification**:
```json
{
  "id": "processor",
  "type": "Node",
  "description": "Process incoming data",
  "inputs": {"data": "str"},
  "outputs": {"result": "dict"},
  "config": {
    "retry": {"max_attempts": 3},
    "timeout": {"seconds": 30}
  }
}
```

**Generated Code** (production style):
```python
class ProcessorNode(Node):
    """Process incoming data.

    Inputs:
        data: str - Input data

    Outputs:
        result: dict - Processed result
    """

    def __init__(self):
        config = NodeConfig(
            retry=RetryCapability(max_attempts=3),
            timeout=TimeoutCapability(seconds=30.0)
        )
        super().__init__(id="processor", config=config)
        self.logger = logging.getLogger(__name__)

    async def process(self, context: ExecutionContext) -> Dict[str, Any]:
        """Process incoming data.

        Args:
            context: Execution context with inputs and state

        Returns:
            Dictionary with processed results

        Raises:
            ValueError: If input data is invalid
        """
        try:
            # Extract inputs
            data = context.inputs.content.get("data")
            if not data:
                raise ValueError("Missing required input: data")

            self.logger.info(f"Processing data: {data}")

            # Process data
            result = {"status": "success", "data": data}

            return {"result": result}

        except Exception as e:
            self.logger.error(f"Error processing data: {e}")
            raise
```

### Agent Generation

Agents are generated with complete configuration.

**Specification**:
```json
{
  "id": "assistant",
  "type": "Agent",
  "config": {
    "model": {
      "provider": "openai",
      "model_id": "gpt-5-mini",
      "temperature": 0.7
    },
    "system_prompt": "You are a helpful assistant",
    "tools": [
      {"name": "search", "source": "tools:search_web"}
    ],
    "max_steps": 10
  }
}
```

**Generated Code**:
```python
class AssistantAgent(Node):
    """Agent node for assistant tasks."""

    def __init__(self):
        # Create model
        model = OpenAIModel(
            model_id="gpt-5-mini",
            temperature=0.7
        )

        # Register tools
        tool_registry = ToolRegistry()
        tool_registry.register(search_web)

        # Create agent config
        config = AgentConfig(
            model=model,
            system_prompt="You are a helpful assistant",
            tools=[search_web],
            max_steps=10
        )

        # Create agent
        self.agent = Agent(config=config)
        super().__init__(id="assistant")

    async def process(self, context: ExecutionContext):
        """Run agent on input."""
        user_message = context.inputs.content.get("message", "")
        response = await self.agent.run(user_message)
        return {"response": response}
```

### Edge Generation

Edges with conditions are generated as connections.

**Specification**:
```json
{
  "id": "e1",
  "from_node": "router",
  "to_node": "processor",
  "condition": {
    "kind": "expr",
    "expr": "$.outputs.score > 0.7"
  },
  "priority": 10
}
```

**Generated Code**:
```python
# Connect nodes with condition
router.goto(
    processor,
    condition=EdgeCondition(lambda n: n.outputs.get('score', 0) > 0.7),
    priority=10
)
```

### Tool Generation

Tools are generated as decorated functions.

**Specification**:
```json
{
  "name": "search_web",
  "description": "Search the web for information",
  "parameters": [
    {
      "name": "query",
      "type": "str",
      "required": true
    }
  ],
  "return_type": "str"
}
```

**Generated Code**:
```python
@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: Search query string

    Returns:
        Search results as formatted string
    """
    # TODO: Implement search_web logic
    raise NotImplementedError("search_web implementation required")
```

### Graph Assembly

Graph creation with complete configuration.

```python
def create_graph() -> Graph:
    """Create and configure the workflow graph.

    Returns:
        Configured Graph instance ready for execution
    """
    # Create nodes
    input_node = InputNode()
    processor = ProcessorNode()
    output_node = OutputNode()

    # Connect nodes
    input_node >> processor
    processor.on(success=True) >> output_node

    # Configure graph state
    initial_state = {"counter": 0, "results": []}

    # Create graph
    graph = Graph(
        start=input_node,
        initial_state=initial_state
    )

    return graph
```

## Import Optimization

The generator automatically optimizes imports:

**Features**:
- Minimal import set
- Organized by category (stdlib, Spark, third-party)
- Alphabetically sorted
- Avoids duplicates
- Only imports what's used

**Example**:
```python
# Standard library
import asyncio
import logging
from typing import Any, Dict, List, Optional

# Spark framework
from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.graphs.graph import Graph
from spark.models.openai import OpenAIModel
from spark.nodes.config import NodeConfig
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext
from spark.tools.decorator import tool
```

## Test Generation

Generate test suite alongside code.

```bash
# Generate with tests
spark-spec compile workflow.json -o ./project --tests
```

**Generated Tests**:

```python
# tests/test_nodes.py
import pytest
from project.nodes import ProcessorNode

@pytest.mark.asyncio
async def test_processor_node():
    """Test ProcessorNode processing."""
    node = ProcessorNode()

    # Create mock context
    context = ExecutionContext(
        inputs=NodeMessage(content={"data": "test"}),
        state=NodeState()
    )

    # Run node
    result = await node.process(context)

    # Verify
    assert "result" in result
    assert result["result"]["status"] == "success"


# tests/test_graph.py
import pytest
from project.graph import create_graph

@pytest.mark.asyncio
async def test_graph_execution():
    """Test complete graph execution."""
    graph = create_graph()

    # Run graph
    result = await graph.run({"input": "test data"})

    # Verify
    assert result is not None
```

## Advanced Features

### Template System

Customize code generation with templates.

```python
from spark.kit.codegen import CodeGenerator

# Custom node template
node_template = '''
class {class_name}(Node):
    """Custom node: {description}"""

    def __init__(self):
        super().__init__(id="{node_id}")
        # Custom initialization

    async def process(self, context):
        {process_body}
'''

generator = CodeGenerator(spec, style="production")
generator.node_template = node_template
code = generator.generate()
```

### AST Manipulation

Generate and manipulate Python AST.

```python
import ast
from spark.kit.codegen import CodeGenerator

generator = CodeGenerator(spec)

# Generate AST
module = generator.generate_ast()

# Manipulate AST
# ... modify nodes ...

# Convert to code
code = ast.unparse(module)
```

### Incremental Generation

Generate specific components.

```python
generator = CodeGenerator(spec, style="production")

# Generate only nodes
nodes_code = generator.generate_nodes()

# Generate only tools
tools_code = generator.generate_tools()

# Generate only graph assembly
graph_code = generator.generate_graph()

# Generate only imports
imports_code = generator.generate_imports()
```

## Customization

### Custom Node Types

Support custom node types in generation.

```python
from spark.kit.codegen import CodeGenerator

class CustomCodeGenerator(CodeGenerator):
    def generate_node_class(self, node_spec):
        """Override to support custom node types."""
        if node_spec.type == "MyCustomNode":
            return self._generate_custom_node(node_spec)
        return super().generate_node_class(node_spec)

    def _generate_custom_node(self, node_spec):
        # Custom generation logic
        return f"class {node_spec.id}(MyCustomNode): ..."
```

### Custom Templates

Provide custom templates for generation.

```python
templates = {
    "node_class": "{class_name}Node",
    "module_docstring": "Auto-generated by MyTool",
    "test_prefix": "test_",
}

generator = CodeGenerator(spec, templates=templates)
```

## Best Practices

**Regenerate from Spec**: Always regenerate code from specification rather than editing generated code.

**Version Control Specs**: Commit JSON specs to git, not generated code.

**Add Implementation**: Generated code contains stubs - implement business logic.

**Test Generated Code**: Run tests on generated code to verify correctness.

**Review Before Deploy**: Review generated code before production deployment.

**Use Production Style**: Prefer production style for deployed code.

**Document Custom Logic**: Add documentation to implemented business logic.

**Separate Concerns**: Keep generated code separate from custom business logic.

## Limitations

**Incomplete Implementations**: Generated code contains stubs requiring implementation.

**Complex Logic**: Cannot generate complex business logic from specifications.

**External Dependencies**: May not handle all external dependencies correctly.

**Custom Node Types**: Limited support for highly custom node types.

**Dynamic Behavior**: Cannot capture runtime dynamic behavior.

## Error Handling

**Generation Failures**:
```python
try:
    generator = CodeGenerator(spec, style="production")
    code = generator.generate()
except ValueError as e:
    print(f"Generation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

**Validation Before Generation**:
```python
from spark.nodes.serde import load_graph_spec
from pydantic import ValidationError

try:
    spec = load_graph_spec("workflow.json")
    generator = CodeGenerator(spec)
    code = generator.generate()
except ValidationError as e:
    print("Invalid spec:", e)
```

## Examples

### Generate Simple Workflow

```python
from spark.nodes.serde import load_graph_spec
from spark.kit.codegen import CodeGenerator

# Load spec
spec = load_graph_spec("simple_workflow.json")

# Generate simple code
generator = CodeGenerator(spec, style="simple")
code = generator.generate()

# Save
with open("workflow.py", "w") as f:
    f.write(code)
```

### Generate Production Project

```bash
# Generate complete project with tests
spark-spec compile workflow.json \
    -o ./production_workflow \
    --style production \
    --tests

# Structure created:
# production_workflow/
# ├── nodes.py
# ├── graph.py
# ├── main.py
# └── tests/
```

### Generate and Execute

```python
from spark.nodes.serde import load_graph_spec
from spark.kit.codegen import generate  # Convenience function

# Load and generate
spec = load_graph_spec("workflow.json")
code = generate(spec, style="production")

# Execute generated code
exec_namespace = {}
exec(code, exec_namespace)

# Get graph factory
create_graph = exec_namespace["create_graph"]
graph = create_graph()

# Run
result = await graph.run()
```

## Next Steps

- **[Specification Models](./models.md)**: Understanding specs for generation
- **[Spec CLI Tool](./cli.md)**: Command-line code generation
- **[Graph Analysis](./analysis.md)**: Analyzing specs before generation
- **[Mission System](./missions.md)**: Generating from mission packages
- **[Simulation System](./simulation.md)**: Testing generated code

## Related Documentation

- [Best Practices: Code Generation](../best-practices/codegen.md)
- [Integration: Specification-Driven Development](../integration/spec-driven-dev.md)
- [Examples: Generated Workflows](../examples/generated.md)
