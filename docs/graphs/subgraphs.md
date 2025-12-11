---
title: Subgraphs and Composition
parent: Graph
nav_order: 6
---
# Subgraphs and Composition

---

**Subgraphs** enable hierarchical workflow composition by embedding complete graphs as nodes within parent graphs. This pattern provides:
- Modular workflow design
- Reusability across multiple graphs
- Clear separation of concerns
- Simplified testing
- Nested execution contexts

## SubgraphNode Pattern

The SubgraphNode pattern wraps a graph to make it usable as a node in another graph.

### Basic Implementation

```python
from spark.nodes import Node
from spark.graphs import Graph

class SubgraphNode(Node):
    def __init__(self, subgraph: Graph):
        super().__init__()
        self.subgraph = subgraph

    async def process(self, context):
        # Run subgraph with inputs from parent
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )
        # Return subgraph outputs to parent
        return result.content

# Create subgraph
inner_graph = Graph(start=InnerNode())

# Use as node in parent graph
subgraph_node = SubgraphNode(subgraph=inner_graph)
parent_graph = Graph(start=subgraph_node)

# Run parent (automatically runs subgraph)
result = await parent_graph.run()
```

### Complete Example

```python
from spark.nodes import Node
from spark.graphs import Graph

# Subgraph nodes
class ValidateNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data', '')
        valid = len(data) > 0
        return {'valid': valid, 'data': data}

class TransformNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data', '')
        return {'data': data.upper()}

# Build subgraph
validate = ValidateNode()
transform = TransformNode()
validate.on(valid=True) >> transform

subgraph = Graph(start=validate)

# Parent graph nodes
class InputNode(Node):
    async def process(self, context):
        return {'data': 'hello world'}

class OutputNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data')
        return {'result': f"Final: {data}"}

# Build parent graph with subgraph
input_node = InputNode()
subgraph_node = SubgraphNode(subgraph)
output_node = OutputNode()

input_node >> subgraph_node >> output_node

parent_graph = Graph(start=input_node)
result = await parent_graph.run()
print(result.content)  # {'result': 'Final: HELLO WORLD'}
```

## Nested Graph Execution

Subgraphs execute as nested contexts with their own execution lifecycle.

### Execution Flow

```
Parent Graph Start
      |
      v
  Parent Node 1
      |
      v
  SubgraphNode.process()
      |
      v
  +-- Subgraph Start --+
  |                     |
  |   Subgraph Node 1  |
  |         |          |
  |         v          |
  |   Subgraph Node 2  |
  |         |          |
  |         v          |
  |   Subgraph Result  |
  |                    |
  +--------------------+
      |
      v
  Parent Node 2
      |
      v
  Parent Graph End
```

### Lifecycle Events

Each graph (parent and subgraphs) emits its own lifecycle events:

```python
def log_event(event):
    graph_id = event.get('graph_id', 'unknown')
    event_type = event.get('event_type')
    print(f"[{graph_id}] {event_type}")

# Subscribe to parent graph events
parent_graph.event_bus.subscribe('*', log_event)

# Subscribe to subgraph events
subgraph.event_bus.subscribe('*', log_event)

result = await parent_graph.run()
# Output:
# [parent] graph_started
# [parent] node_started
# [subgraph] graph_started
# [subgraph] node_started
# [subgraph] node_finished
# [subgraph] graph_finished
# [parent] node_finished
# [parent] graph_finished
```

## State Isolation vs. Sharing

Subgraphs can have isolated state or share the parent graph's state.

### Isolated State (Default)

Each subgraph has its own independent state:

```python
# Parent graph with state
parent_graph = Graph(
    start=node1,
    initial_state={'parent_counter': 0}
)

# Subgraph with its own state
subgraph = Graph(
    start=inner_node,
    initial_state={'sub_counter': 0}
)

class SubgraphNode(Node):
    def __init__(self):
        super().__init__()
        self.subgraph = subgraph

    async def process(self, context):
        # Parent state not accessible to subgraph
        # Subgraph state not accessible to parent
        result = await self.subgraph.run()
        return result.content
```

**Characteristics:**
- Complete isolation between parent and subgraph
- Each graph manages its own state independently
- No state leakage or conflicts
- Easier to test and reason about

**Use when:**
- Subgraphs are self-contained
- No state sharing needed
- Maximum encapsulation desired
- Testing subgraphs independently

### Shared State

Share parent graph state with subgraph:

```python
class SharedStateSubgraphNode(Node):
    def __init__(self, parent_graph):
        super().__init__()
        # Create subgraph
        self.subgraph = Graph(start=InnerNode())
        # Share parent's state
        self.subgraph.graph_state = parent_graph.graph_state

    async def process(self, context):
        # Subgraph can access and modify parent state
        result = await self.subgraph.run()
        return result.content

# Build parent graph
parent_graph = Graph(start=start_node, initial_state={'shared_counter': 0})

# Add subgraph that shares state
shared_subgraph = SharedStateSubgraphNode(parent_graph)
```

**Example: Counter Shared Across Graphs**

```python
from spark.nodes import Node
from spark.graphs import Graph

class ParentIncrementNode(Node):
    async def process(self, context):
        counter = await context.graph_state.get('counter', 0)
        await context.graph_state.set('counter', counter + 1)
        return {'counter': counter + 1}

class SubgraphIncrementNode(Node):
    async def process(self, context):
        # Access same counter as parent
        counter = await context.graph_state.get('counter', 0)
        await context.graph_state.set('counter', counter + 1)
        return {'counter': counter + 1}

# Build graphs
parent_increment = ParentIncrementNode()
subgraph = Graph(start=SubgraphIncrementNode())

class SharedSubgraphNode(Node):
    def __init__(self, parent_graph):
        super().__init__()
        self.subgraph = subgraph
        # Share state
        self.subgraph.graph_state = parent_graph.graph_state

    async def process(self, context):
        result = await self.subgraph.run()
        return result.content

parent_graph = Graph(
    start=parent_increment,
    initial_state={'counter': 0}
)

parent_increment >> SharedSubgraphNode(parent_graph)

result = await parent_graph.run()
counter = await parent_graph.get_state('counter')
print(counter)  # 2 (incremented by both parent and subgraph)
```

**Use when:**
- Need to coordinate state across graphs
- Aggregating results from subgraphs
- Implementing counter or accumulator patterns
- Building complex workflows with shared context

## Input/Output Mapping

Map data between parent and subgraph contexts.

### Direct Pass-Through

```python
class SubgraphNode(Node):
    async def process(self, context):
        # Pass parent inputs directly to subgraph
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )
        # Return subgraph outputs directly to parent
        return result.content
```

### Input Transformation

```python
class TransformingSubgraphNode(Node):
    async def process(self, context):
        # Transform parent inputs before passing to subgraph
        parent_data = context.inputs.content.get('data', [])

        subgraph_inputs = {
            'items': parent_data,
            'config': {'mode': 'batch'}
        }

        result = await self.subgraph.run(initial_inputs=subgraph_inputs)
        return result.content
```

### Output Transformation

```python
class OutputMappingSubgraphNode(Node):
    async def process(self, context):
        # Run subgraph
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )

        # Transform subgraph outputs for parent
        subgraph_output = result.content
        parent_output = {
            'processed_data': subgraph_output.get('data'),
            'metadata': {
                'subgraph_status': subgraph_output.get('status'),
                'timestamp': datetime.now().isoformat()
            }
        }

        return parent_output
```

### Selective Mapping

```python
class SelectiveMappingSubgraphNode(Node):
    async def process(self, context):
        # Extract specific fields from parent
        subgraph_inputs = {
            'id': context.inputs.content.get('user_id'),
            'query': context.inputs.content.get('search_query')
        }

        result = await self.subgraph.run(initial_inputs=subgraph_inputs)

        # Return only specific fields to parent
        return {
            'results': result.content.get('matches', []),
            'count': result.content.get('total_matches', 0)
        }
```

## Subgraph Reusability

Design subgraphs for reuse across multiple parent graphs.

### Parameterized Subgraphs

```python
class ConfigurableSubgraphNode(Node):
    def __init__(self, mode: str = 'standard'):
        super().__init__()
        self.mode = mode
        # Build subgraph based on mode
        if mode == 'standard':
            self.subgraph = Graph(start=StandardProcessor())
        elif mode == 'advanced':
            self.subgraph = Graph(start=AdvancedProcessor())

    async def process(self, context):
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )
        return result.content

# Use in multiple graphs with different configurations
graph1 = Graph(start=ConfigurableSubgraphNode(mode='standard'))
graph2 = Graph(start=ConfigurableSubgraphNode(mode='advanced'))
```

### Factory Pattern

```python
def create_validation_subgraph(rules: List[str]) -> Graph:
    """Factory function to create validation subgraphs."""
    validators = []
    for rule in rules:
        if rule == 'length':
            validators.append(LengthValidator())
        elif rule == 'format':
            validators.append(FormatValidator())

    # Chain validators
    start = validators[0]
    for i in range(len(validators) - 1):
        validators[i] >> validators[i + 1]

    return Graph(start=start)

# Create different validation subgraphs
basic_validation = create_validation_subgraph(['length'])
full_validation = create_validation_subgraph(['length', 'format'])

# Use in parent graphs
graph1 = Graph(start=SubgraphNode(basic_validation))
graph2 = Graph(start=SubgraphNode(full_validation))
```

### Subgraph Library

```python
# subgraph_library.py
from spark.graphs import Graph

class SubgraphLibrary:
    @staticmethod
    def data_cleaning() -> Graph:
        """Standard data cleaning subgraph."""
        return Graph(start=CleaningNode())

    @staticmethod
    def validation(strict: bool = False) -> Graph:
        """Validation subgraph with configurable strictness."""
        if strict:
            return Graph(start=StrictValidationNode())
        return Graph(start=LenientValidationNode())

    @staticmethod
    def transformation(transform_type: str) -> Graph:
        """Transformation subgraph."""
        if transform_type == 'normalize':
            return Graph(start=NormalizeNode())
        elif transform_type == 'aggregate':
            return Graph(start=AggregateNode())

# Use library
from subgraph_library import SubgraphLibrary

cleaning = SubgraphLibrary.data_cleaning()
validation = SubgraphLibrary.validation(strict=True)
transform = SubgraphLibrary.transformation('normalize')

# Compose into pipeline
pipeline = Graph(start=SubgraphNode(cleaning))
# Add more subgraphs...
```

## Recursive Composition

Subgraphs can contain other subgraphs, enabling deep hierarchies.

### Multi-Level Nesting

```python
# Level 3: Innermost processing
inner_graph = Graph(start=InnerProcessor())

# Level 2: Middle layer that uses inner graph
class MiddleSubgraphNode(Node):
    def __init__(self):
        super().__init__()
        self.subgraph = inner_graph

    async def process(self, context):
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )
        return result.content

middle_graph = Graph(start=MiddleSubgraphNode())

# Level 1: Outer layer that uses middle graph
class OuterSubgraphNode(Node):
    def __init__(self):
        super().__init__()
        self.subgraph = middle_graph

    async def process(self, context):
        result = await self.subgraph.run(
            initial_inputs=context.inputs.content
        )
        return result.content

# Top level: Parent graph
parent_graph = Graph(start=OuterSubgraphNode())

# Execution: Parent -> Outer -> Middle -> Inner
result = await parent_graph.run()
```

### Hierarchical Workflow

```python
# Data processing hierarchy
class ETLPipeline:
    @staticmethod
    def extract_layer() -> Graph:
        """Extract data from sources."""
        return Graph(start=ExtractNode())

    @staticmethod
    def transform_layer() -> Graph:
        """Transform data with multiple steps."""
        # Transform layer uses validation and cleaning subgraphs
        validate = SubgraphNode(SubgraphLibrary.validation())
        clean = SubgraphNode(SubgraphLibrary.data_cleaning())
        normalize = NormalizeNode()

        validate >> clean >> normalize
        return Graph(start=validate)

    @staticmethod
    def load_layer() -> Graph:
        """Load data to destinations."""
        return Graph(start=LoadNode())

    @staticmethod
    def create_pipeline() -> Graph:
        """Create complete ETL pipeline."""
        extract = SubgraphNode(ETLPipeline.extract_layer())
        transform = SubgraphNode(ETLPipeline.transform_layer())
        load = SubgraphNode(ETLPipeline.load_layer())

        extract >> transform >> load
        return Graph(start=extract)

# Use hierarchical pipeline
pipeline = ETLPipeline.create_pipeline()
result = await pipeline.run(initial_inputs={'source': 'database'})
```

## Testing Subgraphs

Test subgraphs independently and as part of larger workflows.

### Unit Testing Subgraphs

```python
import pytest
from spark.graphs import Graph

@pytest.mark.asyncio
async def test_validation_subgraph():
    """Test validation subgraph independently."""
    # Create subgraph
    subgraph = create_validation_subgraph(['length', 'format'])

    # Test with valid input
    result = await subgraph.run(initial_inputs={
        'data': 'valid_data_123'
    })
    assert result.content['valid'] == True

    # Test with invalid input
    result = await subgraph.run(initial_inputs={
        'data': 'x'
    })
    assert result.content['valid'] == False
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_parent_with_subgraph():
    """Test parent graph with subgraph integration."""
    # Create mock subgraph for testing
    class MockSubgraph(Node):
        async def process(self, context):
            # Mock subgraph behavior
            return {'processed': True, 'data': 'mocked'}

    # Build parent graph with mock
    parent_graph = Graph(start=MockSubgraph())

    # Test parent
    result = await parent_graph.run()
    assert result.content['processed'] == True
```

### Mocking Subgraphs

```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_with_mocked_subgraph():
    """Test parent graph with mocked subgraph."""

    class TestableSubgraphNode(Node):
        def __init__(self, subgraph=None):
            super().__init__()
            self.subgraph = subgraph or Graph(start=RealNode())

        async def process(self, context):
            result = await self.subgraph.run(
                initial_inputs=context.inputs.content
            )
            return result.content

    # Create mock subgraph
    mock_subgraph = AsyncMock()
    mock_subgraph.run = AsyncMock(return_value=NodeMessage(
        content={'mocked': True}
    ))

    # Test with mock
    node = TestableSubgraphNode(subgraph=mock_subgraph)
    graph = Graph(start=node)

    result = await graph.run(initial_inputs={'test': 'data'})

    # Verify mock was called
    mock_subgraph.run.assert_called_once()
    assert result.content['mocked'] == True
```

### Testing State Isolation

```python
@pytest.mark.asyncio
async def test_subgraph_state_isolation():
    """Test that subgraph state is isolated from parent."""

    class ParentNode(Node):
        async def process(self, context):
            await context.graph_state.set('parent_key', 'parent_value')
            return {'done': True}

    class SubgraphNode(Node):
        async def process(self, context):
            # Should not see parent state
            parent_value = await context.graph_state.get('parent_key')
            assert parent_value is None

            # Set own state
            await context.graph_state.set('sub_key', 'sub_value')
            return {'done': True}

    # Create graphs
    subgraph = Graph(start=SubgraphNode(), initial_state={})
    parent = ParentNode()

    class WrapperNode(Node):
        def __init__(self):
            super().__init__()
            self.subgraph = subgraph

        async def process(self, context):
            result = await self.subgraph.run()
            return result.content

    parent_graph = Graph(start=parent, initial_state={})
    parent >> WrapperNode()

    # Run and verify isolation
    result = await parent_graph.run()
    assert result.content['done'] == True
```

## Performance Considerations

### Subgraph Overhead

| Metric | Overhead per Subgraph |
|--------|----------------------|
| Initialization | ~1-5ms |
| Execution context | ~0.5ms |
| State isolation | ~0.1ms |
| Event publishing | ~0.2ms per event |

### Optimization Tips

1. **Minimize Nesting Depth**
   ```python
   # Bad: Excessive nesting (4+ levels)
   deep_nested_graph  # Hard to debug, high overhead

   # Good: Flatten when possible (2-3 levels)
   flatter_graph  # Easier to understand, lower overhead
   ```

2. **Reuse Subgraph Instances**
   ```python
   # Bad: Create new subgraph for each use
   class BadNode(Node):
       async def process(self, context):
           subgraph = Graph(start=HeavyNode())  # Created each time!
           return await subgraph.run()

   # Good: Create subgraph once
   class GoodNode(Node):
       def __init__(self):
           super().__init__()
           self.subgraph = Graph(start=HeavyNode())  # Created once

       async def process(self, context):
           return await self.subgraph.run()
   ```

3. **Share State When Appropriate**
   ```python
   # If subgraphs need to coordinate, share state
   # Otherwise, use isolated state for better encapsulation
   ```

## Best Practices

1. **Single Responsibility**: Each subgraph should have one clear purpose
2. **Clear Interfaces**: Define clear input/output contracts
3. **Document Dependencies**: Document what state/inputs subgraph needs
4. **Test Independently**: Unit test subgraphs before integration
5. **Limit Nesting**: Keep hierarchy depth reasonable (2-3 levels)
6. **Reuse Patterns**: Create library of common subgraphs
7. **Parameterize**: Make subgraphs configurable for reuse
8. **Isolate by Default**: Use state isolation unless sharing is needed

## Common Patterns

### Pipeline Pattern

```python
# Sequential processing stages as subgraphs
extract = SubgraphNode(extract_graph)
transform = SubgraphNode(transform_graph)
load = SubgraphNode(load_graph)

extract >> transform >> load
pipeline = Graph(start=extract)
```

### Branch-Merge Pattern

```python
# Parallel subgraphs that merge results
class BranchMergeGraph:
    def __init__(self):
        self.branch_a = SubgraphNode(Graph(start=ProcessorA()))
        self.branch_b = SubgraphNode(Graph(start=ProcessorB()))
        self.merge = MergeNode()

        # Build graph with branches
        router >> self.branch_a >> self.merge
        router >> self.branch_b >> self.merge
```

### Decorator Pattern

```python
# Wrap subgraph with pre/post processing
class DecoratedSubgraphNode(Node):
    def __init__(self, subgraph: Graph):
        super().__init__()
        self.subgraph = subgraph

    async def process(self, context):
        # Pre-processing
        inputs = self.prepare_inputs(context.inputs.content)

        # Run subgraph
        result = await self.subgraph.run(initial_inputs=inputs)

        # Post-processing
        outputs = self.process_outputs(result.content)

        return outputs
```

## Next Steps

- **[Graph State](graph-state.md)**: Learn about state sharing between graphs
- **[Testing Nodes](../nodes/testing.md)**: Test subgraph nodes
- **[Fundamentals](fundamentals.md)**: Review graph basics
- **[Execution Modes](execution-modes.md)**: Understand subgraph execution modes
