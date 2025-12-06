# Quick Start

This guide will get you building with Spark in minutes. We'll create a simple node, compose a workflow, and build an AI agent with tools.

## Prerequisites

Make sure Spark is installed:

```bash
pip install spark-adk openai
export OPENAI_API_KEY="sk-..."
```

See [Installation](installation.md) for details.

## Hello World Node

The most basic Spark component is a **Node** - an independent processing unit that implements a `process()` method.

Create `hello.py`:

```python
from spark.nodes import Node
from spark.utils import arun

class HelloNode(Node):
    async def process(self, context):
        """Process method is called when the node executes."""
        name = context.inputs.content.get('name', 'World')
        print(f"Hello, {name}!")
        return {'done': True}

if __name__ == "__main__":
    node = HelloNode()
    arun(node.run({'name': 'Spark'}))
```

Run it:

```bash
python hello.py
# Output: Hello, Spark!
```

**What happened?**
1. Created a `HelloNode` class inheriting from `Node`
2. Implemented `process()` method with business logic
3. Accessed inputs via `context.inputs.content`
4. Returned a dictionary that becomes the node's outputs
5. Used `arun()` utility to run async code from sync context

## Your First Graph

Nodes are powerful when composed into **Graphs** - complete workflows with multiple connected nodes.

Create `first_graph.py`:

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.utils import arun

class InputNode(Node):
    async def process(self, context):
        """Accept user input and pass to next node."""
        message = context.inputs.content.get('message', '')
        print(f"Input: {message}")
        return {'message': message.upper()}

class ProcessNode(Node):
    async def process(self, context):
        """Process the message from previous node."""
        message = context.inputs.content.get('message', '')
        processed = f"Processed: {message}"
        print(processed)
        return {'result': processed}

class OutputNode(Node):
    async def process(self, context):
        """Output final result."""
        result = context.inputs.content.get('result', '')
        print(f"Final: {result}")
        return {'done': True}

# Create nodes
input_node = InputNode()
process_node = ProcessNode()
output_node = OutputNode()

# Connect nodes with >> operator
input_node >> process_node >> output_node

# Create graph starting from first node
graph = Graph(start=input_node)

if __name__ == "__main__":
    result = arun(graph.run({'message': 'hello spark'}))
    print(f"Graph completed: {result.content}")
```

Run it:

```bash
python first_graph.py
# Output:
# Input: hello spark
# Processed: HELLO SPARK
# Final: Processed: HELLO SPARK
# Graph completed: {'done': True}
```

**What happened?**
1. Created three nodes: `InputNode`, `ProcessNode`, `OutputNode`
2. Connected them with `>>` operator (syntactic sugar for edges)
3. Created a `Graph` with the first node
4. Graph automatically discovered all connected nodes via BFS traversal
5. Executed nodes sequentially, passing outputs to next node's inputs

## Conditional Flow

Add branching logic with conditional edges:

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.utils import arun

class CheckNode(Node):
    async def process(self, context):
        """Check if number is even or odd."""
        number = context.inputs.content.get('number', 0)
        is_even = number % 2 == 0
        print(f"Checking {number}: {'even' if is_even else 'odd'}")
        return {'number': number, 'is_even': is_even}

class EvenNode(Node):
    async def process(self, context):
        """Handle even numbers."""
        number = context.inputs.content.get('number')
        print(f"{number} is even!")
        return {'done': True}

class OddNode(Node):
    async def process(self, context):
        """Handle odd numbers."""
        number = context.inputs.content.get('number')
        print(f"{number} is odd!")
        return {'done': True}

# Create nodes
check = CheckNode()
even = EvenNode()
odd = OddNode()

# Conditional edges using .on() shorthand
check.on(is_even=True) >> even
check.on(is_even=False) >> odd

# Create and run graph
graph = Graph(start=check)

if __name__ == "__main__":
    print("Testing with 4:")
    arun(graph.run({'number': 4}))
    # Output: Checking 4: even
    #         4 is even!

    print("\nTesting with 7:")
    arun(graph.run({'number': 7}))
    # Output: Checking 7: odd
    #         7 is odd!
```

**Key concept**: Use `.on(key=value)` to create conditional edges based on node outputs.

## Building an AI Agent

Now let's create an AI agent that can use tools to answer questions.

Create `simple_agent.py`:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

# Define a tool using @tool decorator
@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The name of the city

    Returns:
        Weather information as a string
    """
    # In production, call a real weather API
    return f"The weather in {city} is sunny and 72°F"

@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: Mathematical expression to evaluate (e.g., "2 + 2")

    Returns:
        Result of the calculation
    """
    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

# Create model and agent
model = OpenAIModel(model_id="gpt-4o-mini")

config = AgentConfig(
    model=model,
    tools=[get_weather, calculate],
    system_prompt="You are a helpful assistant with access to weather and calculator tools."
)

agent = Agent(config=config)

if __name__ == "__main__":
    # Ask questions that require tool use
    questions = [
        "What's the weather in San Francisco?",
        "What is 15 * 23?",
        "Calculate 100 / 4 and tell me the weather in Tokyo"
    ]

    for question in questions:
        print(f"\nQuestion: {question}")
        result = agent.run(question)
        print(f"Answer: {result.final_output}")
```

Run it:

```bash
python simple_agent.py
```

**What happened?**
1. Defined tools with `@tool` decorator - automatically generates schemas
2. Created `OpenAIModel` with a specific model ID
3. Configured agent with model, tools, and system prompt
4. Agent automatically decides when to call tools based on user questions
5. Tools are executed and results fed back to the LLM
6. Agent returns final answer incorporating tool results

## Agent with Memory

Add conversation memory to maintain context across multiple interactions:

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

model = OpenAIModel(model_id="gpt-4o-mini")

config = AgentConfig(
    model=model,
    system_prompt="You are a helpful assistant. Remember conversation context.",
    max_conversation_history=10  # Keep last 10 messages
)

agent = Agent(config=config)

# Multi-turn conversation
print("=== Multi-turn Conversation ===")

response1 = agent.run("My name is Alice and I like Python")
print(f"Agent: {response1.final_output}")

response2 = agent.run("What's my name?")
print(f"Agent: {response2.final_output}")  # Should remember "Alice"

response3 = agent.run("What programming language do I like?")
print(f"Agent: {response3.final_output}")  # Should remember "Python"

# Check conversation history
print(f"\nConversation has {len(agent.get_conversation_history())} messages")
```

**Key concept**: Agent maintains conversation history automatically, enabling contextual multi-turn interactions.

## Running Repository Examples

Spark includes 17+ working examples covering all features. Run them to learn more:

### Basic Examples

```bash
# Hello world
python -m examples.e001_hello

# Simple flow with multiple nodes
python -m examples.e002_simple_flow

# Conditional flow with branching
python -m examples.e003_conditional_flow

# Long-running nodes
python -m examples.e004_long_running
```

### Agent Examples

```bash
# LLM tool usage
python -m examples.e006_llm_tool

# Reasoning strategies (ReAct, Chain-of-Thought)
python -m examples.e010_reasoning_strategies

# Agent enhancements (parallel tools, cost tracking)
python -m examples.e011_agent_enhancements
```

### Advanced Examples

```bash
# Telemetry system
python -m examples.e011_telemetry

# RPC nodes (distributed workflows)
python -m examples.e008_rpc_node_basic
python -m examples.e009_rpc_node_advanced

# RSI (Recursive Self-Improvement) - 6 phases
python -m examples.e012_rsi_phase1  # Performance analysis
python -m examples.e013_rsi_phase2  # Hypothesis generation
python -m examples.e014_rsi_phase3  # A/B testing
python -m examples.e015_rsi_phase4  # Deployment
python -m examples.e016_rsi_phase5  # Pattern learning
python -m examples.e017_rsi_phase6  # Structural optimization
```

## Project Structure

Organize your Spark project like this:

```
my-spark-project/
├── nodes/              # Custom nodes
│   ├── __init__.py
│   ├── data_nodes.py
│   └── logic_nodes.py
├── graphs/             # Graph definitions
│   ├── __init__.py
│   └── main_workflow.py
├── tools/              # Custom tools
│   ├── __init__.py
│   └── my_tools.py
├── config/             # Configuration
│   ├── .env
│   └── model_pricing.json
├── specs/              # Graph specifications
│   └── workflow.json
├── tests/              # Tests
│   └── test_workflow.py
├── main.py             # Entry point
└── requirements.txt    # Dependencies
```

## Common Patterns

### Pattern 1: Error Handling with Retry

```python
from spark.nodes import Node, NodeConfig
from spark.nodes.capabilities import RetryCapability

class UnreliableNode(Node):
    def __init__(self):
        config = NodeConfig(
            retry_capability=RetryCapability(
                max_attempts=3,
                backoff_factor=2.0
            )
        )
        super().__init__(config=config)

    async def process(self, context):
        # This will retry up to 3 times if it fails
        result = call_external_api()
        return {'result': result}
```

### Pattern 2: Timeout Protection

```python
from spark.nodes import Node, NodeConfig
from spark.nodes.capabilities import TimeoutCapability

class SlowNode(Node):
    def __init__(self):
        config = NodeConfig(
            timeout_capability=TimeoutCapability(timeout_seconds=5.0)
        )
        super().__init__(config=config)

    async def process(self, context):
        # Will timeout after 5 seconds
        result = long_running_operation()
        return {'result': result}
```

### Pattern 3: Graph with Shared State

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.utils import arun

class CounterNode(Node):
    async def process(self, context):
        # Access shared graph state
        count = await context.graph_state.get('counter', 0)
        count += 1
        await context.graph_state.set('counter', count)

        print(f"Count: {count}")

        # Loop if count < 5
        return {'continue': count < 5}

# Create graph with initial state
node = CounterNode()
node.on(continue=True) >> node  # Loop back to self

graph = Graph(start=node, initial_state={'counter': 0})

# Run graph - will loop 5 times
arun(graph.run())
```

### Pattern 4: Agent with Custom Strategy

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

@tool
def search(query: str) -> str:
    """Search for information."""
    return search_web(query)

model = OpenAIModel(model_id="gpt-4o")

config = AgentConfig(
    model=model,
    tools=[search],
    output_mode='json',  # Required for ReAct
    reasoning_strategy=ReActStrategy(verbose=True)  # Show reasoning steps
)

agent = Agent(config=config)

result = agent.run("What is the population of Tokyo?")
print(result.final_output)

# View reasoning history
for step in agent.get_reasoning_history():
    print(f"Thought: {step.get('thought')}")
    print(f"Action: {step.get('action')}")
```

## Next Steps

Now that you've built your first Spark applications, explore these topics:

### Deep Dive into Concepts
- **[Core Concepts](concepts.md)**: Understand the architecture and abstractions
- **[Node Guide](../guides/nodes.md)**: Master node development
- **[Graph Guide](../guides/graphs.md)**: Build complex workflows
- **[Agent Guide](../guides/agents.md)**: Create sophisticated AI agents

### Tutorials
- **[Tutorial 1: Building a Research Assistant](../tutorials/01-research-assistant.md)**
- **[Tutorial 2: Data Processing Pipeline](../tutorials/02-data-pipeline.md)**
- **[Tutorial 3: Multi-Agent System](../tutorials/03-multi-agent.md)**

### Advanced Features
- **[Telemetry](../guides/telemetry.md)**: Monitor and analyze execution
- **[RSI System](../guides/rsi.md)**: Enable autonomous improvement
- **[RPC Nodes](../guides/rpc-nodes.md)**: Build distributed workflows
- **[Governance](../guides/governance.md)**: Add policy controls

### Reference
- **[API Reference](../api/README.md)**: Complete API documentation
- **[Examples](../../examples/)**: 17+ working examples
- **[Troubleshooting](../guides/troubleshooting.md)**: Common issues and solutions

## Getting Help

- Review the [Core Concepts](concepts.md) for deeper understanding
- Check [Examples](../../examples/) for more patterns
- Read the [Guides](../guides/README.md) for specific features
- Open an issue on [GitHub](https://github.com/yourusername/spark/issues)

Happy building with Spark!
