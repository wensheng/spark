---
title: Edge Conditions and Flow Control
parent: Graph
nav_order: 1
---
# Edge Conditions and Flow Control

This reference covers edge conditions, conditional routing, and flow control patterns in Spark graphs.

## Overview

**Edges** connect nodes in a graph and determine execution flow. Spark supports both unconditional edges (always follow) and conditional edges (follow based on node outputs). Edge conditions enable branching, looping, and complex workflow patterns.

## EdgeCondition Class

The `EdgeCondition` class wraps a lambda function that evaluates node outputs to determine if an edge should be followed.

### Structure

```python
from spark.nodes.base import EdgeCondition

condition = EdgeCondition(
    fn=lambda node: node.outputs.content.get('key') == 'value'
)
```

### Constructor

```python
EdgeCondition(fn: Callable[[BaseNode], bool])
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `fn` | `Callable[[BaseNode], bool]` | Function that takes a node and returns True if edge should be followed |

### Condition Function Signature

The lambda receives a `BaseNode` instance with:
- `node.outputs`: NodeMessage containing the node's output
- `node.outputs.content`: dict with output data
- `node.state`: NodeState with execution state

### Example

```python
from spark.nodes.base import EdgeCondition
from spark.nodes import Node

class CheckNode(Node):
    async def process(self, context):
        score = compute_score()
        return {'score': score, 'passed': score > 0.7}

# Create condition based on output
condition = EdgeCondition(lambda n: n.outputs.content.get('passed', False))

check_node = CheckNode()
success_node = SuccessNode()
check_node.goto(success_node, condition=condition)
```

## Shorthand Syntax

The `on()` method provides a concise syntax for simple key-value conditions.

### Basic Usage

```python
node_a.on(key=value) >> node_b
# Equivalent to:
# node_a.goto(node_b, condition=EdgeCondition(lambda n: n.outputs.content.get('key') == value))
```

### Multiple Conditions

```python
# AND logic (all conditions must match)
node_a.on(status='success', count=5) >> node_b
# Follows edge only if status='success' AND count=5
```

### Common Patterns

```python
# Boolean flag
node_a.on(success=True) >> success_handler
node_a.on(success=False) >> error_handler

# String matching
node_a.on(action='continue') >> next_step
node_a.on(action='abort') >> abort_handler

# Numeric values
node_a.on(retry_count=0) >> first_attempt
node_a.on(retry_count=1) >> second_attempt

# None checks
node_a.on(error=None) >> success_path
```

### Example: Simple Branching

```python
from spark.nodes import Node
from spark.graphs import Graph

class ValidationNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('data')
        is_valid = len(data) > 0
        return {'valid': is_valid, 'data': data}

class ProcessNode(Node):
    async def process(self, context):
        return {'result': 'processed'}

class ErrorNode(Node):
    async def process(self, context):
        return {'error': 'Invalid data'}

# Build branching workflow
validator = ValidationNode()
processor = ProcessNode()
error_handler = ErrorNode()

validator.on(valid=True) >> processor
validator.on(valid=False) >> error_handler

graph = Graph(start=validator)
```

## Full Syntax with goto()

The `goto()` method provides full control for complex conditions.

### Method Signature

```python
node.goto(
    target: BaseNode,
    condition: Optional[EdgeCondition] = None
) -> BaseNode
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target` | `BaseNode` | Required | Destination node for this edge |
| `condition` | `EdgeCondition` | `None` | Condition to evaluate (None = unconditional) |

**Returns:** The target node (for chaining).

### Complex Conditions

```python
from spark.nodes.base import EdgeCondition

# Numeric comparison
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: n.outputs.content.get('score', 0) > 0.8)
)

# Multiple fields
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: (
        n.outputs.content.get('status') == 'ready' and
        n.outputs.content.get('count', 0) > 10
    ))
)

# Complex logic
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: (
        n.outputs.content.get('type') in ['A', 'B'] and
        n.outputs.content.get('priority', 0) >= 5 and
        n.outputs.content.get('enabled', False)
    ))
)
```

### Accessing Node State in Conditions

```python
# Check execution count
node_a.goto(
    retry_node,
    condition=EdgeCondition(lambda n: n.state.process_count < 3)
)

# Check if node is processing
node_a.goto(
    wait_node,
    condition=EdgeCondition(lambda n: not n.state.processing)
)
```

### List and Dict Operations

```python
# Check list membership
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: 'item' in n.outputs.content.get('list', []))
)

# Check dict keys
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: 'required_key' in n.outputs.content)
)

# List length
node_a.goto(
    node_b,
    condition=EdgeCondition(lambda n: len(n.outputs.content.get('items', [])) > 0)
)
```

## Branching Workflows

Branching creates multiple possible execution paths.

### Binary Branch

```python
class DecisionNode(Node):
    async def process(self, context):
        value = context.inputs.content.get('value', 0)
        return {'high': value > 50}

decision = DecisionNode()
high_path = HighPathNode()
low_path = LowPathNode()

decision.on(high=True) >> high_path
decision.on(high=False) >> low_path
```

### Multi-Way Branch

```python
class RouterNode(Node):
    async def process(self, context):
        request_type = context.inputs.content.get('type')
        return {'type': request_type}

router = RouterNode()
handler_a = HandlerA()
handler_b = HandlerB()
handler_c = HandlerC()
default_handler = DefaultHandler()

router.on(type='A') >> handler_a
router.on(type='B') >> handler_b
router.on(type='C') >> handler_c
router.on(type='unknown') >> default_handler
```

### Branch with Merge

```python
class BranchNode(Node):
    async def process(self, context):
        return {'path': 'left'}

class LeftNode(Node):
    async def process(self, context):
        return {'result': 'from left'}

class RightNode(Node):
    async def process(self, context):
        return {'result': 'from right'}

class MergeNode(Node):
    async def process(self, context):
        result = context.inputs.content.get('result')
        return {'merged': f"Merged: {result}"}

branch = BranchNode()
left = LeftNode()
right = RightNode()
merge = MergeNode()

# Branch
branch.on(path='left') >> left
branch.on(path='right') >> right

# Merge - both paths lead to same node
left >> merge
right >> merge

graph = Graph(start=branch)
```

## Looping Workflows

Loops enable iterative processing by creating cycles in the graph.

### Simple Loop

```python
class LoopNode(Node):
    def __init__(self):
        super().__init__()
        self.iteration = 0

    async def process(self, context):
        self.iteration += 1
        done = self.iteration >= 5
        return {'done': done, 'iteration': self.iteration}

class ExitNode(Node):
    async def process(self, context):
        return {'result': 'loop completed'}

loop = LoopNode()
exit_node = ExitNode()

# Loop back to self
loop.on(done=False) >> loop

# Exit when done
loop.on(done=True) >> exit_node

graph = Graph(start=loop)
```

### Loop with Graph State

```python
from spark.nodes import Node
from spark.graphs import Graph

class IterationNode(Node):
    async def process(self, context):
        # Read counter from graph state
        counter = await context.graph_state.get('counter', 0)
        counter += 1
        await context.graph_state.set('counter', counter)

        # Continue until counter reaches 10
        done = counter >= 10
        return {'done': done, 'counter': counter}

class ResultNode(Node):
    async def process(self, context):
        final_count = await context.graph_state.get('counter', 0)
        return {'result': f"Completed {final_count} iterations"}

iterator = IterationNode()
result = ResultNode()

iterator.on(done=False) >> iterator  # Loop
iterator.on(done=True) >> result     # Exit

graph = Graph(start=iterator, initial_state={'counter': 0})
```

### While Loop Pattern

```python
class ConditionCheckNode(Node):
    async def process(self, context):
        data = await context.graph_state.get('data', [])
        has_more = len(data) > 0

        if has_more:
            item = data.pop(0)
            await context.graph_state.set('data', data)
            return {'continue': True, 'item': item}
        else:
            return {'continue': False}

class ProcessItemNode(Node):
    async def process(self, context):
        item = context.inputs.content.get('item')
        # Process item
        return {'processed': True}

class DoneNode(Node):
    async def process(self, context):
        return {'result': 'all items processed'}

check = ConditionCheckNode()
process = ProcessItemNode()
done = DoneNode()

# While loop: check -> process -> check
check.on(continue=True) >> process
process >> check

# Exit condition
check.on(continue=False) >> done

graph = Graph(start=check, initial_state={'data': [1, 2, 3, 4, 5]})
```

## Conditional Routing Patterns

### Priority-Based Routing

```python
class PriorityNode(Node):
    async def process(self, context):
        priority = context.inputs.content.get('priority', 0)
        return {'priority': priority}

priority = PriorityNode()
urgent = UrgentHandler()
high = HighPriorityHandler()
normal = NormalHandler()

# Check in priority order
priority.goto(urgent, condition=EdgeCondition(lambda n: n.outputs.content.get('priority', 0) > 90))
priority.goto(high, condition=EdgeCondition(lambda n: n.outputs.content.get('priority', 0) > 50))
priority.goto(normal, condition=EdgeCondition(lambda n: n.outputs.content.get('priority', 0) <= 50))
```

### Fallback Chain

```python
class RetryNode(Node):
    async def process(self, context):
        attempt = context.inputs.content.get('attempt', 0)
        success = try_operation()
        return {'success': success, 'attempt': attempt + 1}

retry = RetryNode()
success_handler = SuccessHandler()
retry_again = RetryNode()
failure_handler = FailureHandler()

# Success path
retry.on(success=True) >> success_handler

# Retry path (attempt < 3)
retry.goto(
    retry_again,
    condition=EdgeCondition(lambda n: (
        not n.outputs.content.get('success', False) and
        n.outputs.content.get('attempt', 0) < 3
    ))
)

# Failure path (attempt >= 3)
retry.goto(
    failure_handler,
    condition=EdgeCondition(lambda n: (
        not n.outputs.content.get('success', False) and
        n.outputs.content.get('attempt', 0) >= 3
    ))
)
```

### State Machine Pattern

```python
class StateMachine(Node):
    async def process(self, context):
        state = await context.graph_state.get('state', 'INIT')

        # State transitions
        if state == 'INIT':
            await context.graph_state.set('state', 'PROCESSING')
            return {'state': 'PROCESSING'}
        elif state == 'PROCESSING':
            await context.graph_state.set('state', 'COMPLETE')
            return {'state': 'COMPLETE'}
        else:
            return {'state': state}

sm = StateMachine()
processing_node = ProcessingNode()
complete_node = CompleteNode()

sm.on(state='PROCESSING') >> processing_node
processing_node >> sm  # Loop back

sm.on(state='COMPLETE') >> complete_node

graph = Graph(start=sm, initial_state={'state': 'INIT'})
```

## Multiple Outgoing Edges

Nodes can have multiple outgoing edges with different conditions.

### Edge Evaluation Order

Edges are evaluated in the order they were added. The **first matching edge** is followed.

```python
node_a.on(priority='high') >> handler_a     # Evaluated first
node_a.on(priority='medium') >> handler_b   # Evaluated second
node_a.on(priority='low') >> handler_c      # Evaluated third
node_a >> default_handler                   # Fallback (unconditional)
```

### Example: Multiple Paths

```python
class ProcessorNode(Node):
    async def process(self, context):
        value = context.inputs.content.get('value', 0)
        return {
            'value': value,
            'positive': value > 0,
            'large': value > 100,
            'even': value % 2 == 0
        }

processor = ProcessorNode()
large_handler = LargeHandler()
positive_handler = PositiveHandler()
even_handler = EvenHandler()
default_handler = DefaultHandler()

# Multiple conditions
processor.on(large=True) >> large_handler           # Checked first
processor.on(positive=True, even=True) >> even_handler  # Checked second
processor.on(positive=True) >> positive_handler     # Checked third
processor >> default_handler                        # Fallback

graph = Graph(start=processor)

# Examples:
# value=150: goes to large_handler
# value=50:  goes to even_handler (positive and even)
# value=25:  goes to positive_handler (positive but not even)
# value=-10: goes to default_handler (not positive)
```

## Edge Priority and Evaluation

### Priority Rules

1. Edges are evaluated in the order they are defined
2. First matching condition wins
3. Unconditional edges (no condition) always match
4. If no edge matches, execution stops at that node

### Explicit Priority Example

```python
# Order matters!

# This works as expected:
node.on(critical=True) >> critical_handler  # High priority
node.on(normal=True) >> normal_handler      # Lower priority
node >> fallback                            # Lowest priority

# This may not work as expected:
node >> fallback                            # Always matches!
node.on(critical=True) >> critical_handler  # Never reached!
```

### Best Practice: Unconditional Last

Always add unconditional edges last:

```python
# Good: conditional edges first, unconditional last
node.on(status='A') >> handler_a
node.on(status='B') >> handler_b
node.on(status='C') >> handler_c
node >> default_handler  # Fallback

# Bad: unconditional first means others never execute
node >> default_handler  # Always matches!
node.on(status='A') >> handler_a  # Never reached
```

## Debugging Edge Conditions

### Logging Condition Evaluation

```python
def debug_condition(expected_value):
    def condition_fn(node):
        actual_value = node.outputs.content.get('key')
        matches = actual_value == expected_value
        print(f"Condition check: {actual_value} == {expected_value} -> {matches}")
        return matches
    return EdgeCondition(condition_fn)

node_a.goto(node_b, condition=debug_condition('target_value'))
```

### Inspecting Node Outputs

```python
class DebugNode(Node):
    async def process(self, context):
        result = {'status': 'success', 'value': 42}
        print(f"Node outputs: {result}")  # Debug output
        return result

node = DebugNode()
node.on(status='success') >> next_node

# Run and observe output
result = await graph.run()
```

### Using Event Bus

```python
def log_node_finished(event):
    node_name = event.get('node')
    outputs = event.get('outputs', {})
    print(f"Node {node_name} finished with outputs: {outputs}")

graph.event_bus.subscribe('node_finished', log_node_finished)
result = await graph.run()
```

## Common Pitfalls

### 1. Forgetting to Return Values

```python
# Bad: condition will fail
class BadNode(Node):
    async def process(self, context):
        # Missing return statement!
        pass

bad_node.on(key='value') >> next_node  # Never matches

# Good: always return dict
class GoodNode(Node):
    async def process(self, context):
        return {'key': 'value'}

good_node.on(key='value') >> next_node  # Works!
```

### 2. Typos in Key Names

```python
class MyNode(Node):
    async def process(self, context):
        return {'status': 'done'}  # Note: 'status'

# Bad: typo in key name
my_node.on(statuss='done') >> next_node  # Never matches!

# Good: correct key name
my_node.on(status='done') >> next_node  # Works!
```

### 3. Type Mismatches

```python
class MyNode(Node):
    async def process(self, context):
        return {'count': 5}  # Returns int

# Bad: comparing int to string
my_node.on(count='5') >> next_node  # Never matches!

# Good: compare with correct type
my_node.on(count=5) >> next_node  # Works!
```

### 4. Missing Fallback Edge

```python
# Bad: no fallback, execution stops if no condition matches
node.on(status='A') >> handler_a
node.on(status='B') >> handler_b
# If status='C', execution stops here!

# Good: always provide fallback
node.on(status='A') >> handler_a
node.on(status='B') >> handler_b
node >> default_handler  # Handles all other cases
```

## Performance Considerations

### Condition Complexity

- Simple conditions (equality checks) are very fast
- Complex conditions (multiple operations) add minimal overhead
- Avoid expensive operations in condition functions

```python
# Fast: simple equality
node.on(status='done') >> next_node

# Fast: simple logic
node.goto(next_node, condition=EdgeCondition(
    lambda n: n.outputs.content.get('count', 0) > 10
))

# Slower: expensive operation (avoid)
node.goto(next_node, condition=EdgeCondition(
    lambda n: expensive_computation(n.outputs.content)  # Don't do this!
))
```

### Edge Count

- Multiple edges per node have minimal overhead
- Evaluation is sequential and stops at first match
- No practical limit on edge count

## Best Practices

1. **Use `on()` for Simple Conditions**: Cleaner and more readable
2. **Use `goto()` for Complex Logic**: Full control when needed
3. **Always Provide Fallback**: Add unconditional edge to handle unexpected cases
4. **Order Matters**: Put specific conditions before general ones
5. **Keep Conditions Pure**: Don't modify state in condition functions
6. **Test Edge Cases**: Verify all edge conditions with different inputs
7. **Document Complex Conditions**: Add comments explaining non-obvious logic

## Next Steps

- **[Graph State](graph-state.md)**: Learn about shared state in conditions
- **[Execution Modes](execution-modes.md)**: Understand how edges work in different modes
- **[Event Bus](event-bus.md)**: Monitor edge traversal and flow
- **[Subgraphs](subgraphs.md)**: Compose complex flows with subgraphs
