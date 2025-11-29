# Spark Programming Guide

## Table of Contents
1. [Quick Start](#quick-start)
2. [Spark Kit & CLI](#spark-kit--cli)
3. [Core Concepts](#core-concepts)
4. [Building Nodes](#building-nodes)
5. [Creating Graphs](#creating-graphs)
6. [Working with Agents](#working-with-agents)
7. [Governance & Compliance](#governance--compliance)
8. [Telemetry & Observability](#telemetry--observability)
9. [Recursive Self-Improvement (RSI)](#recursive-self-improvement-rsi)
10. [State Management](#state-management)
11. [Distributed Execution](#distributed-execution)
12. [Best Practices](#best-practices)

## Quick Start

### Installation

```bash
# Install Spark
pip install -e .

# Install optional dependencies
pip install openai boto3 starlette uvicorn httpx websockets
```

### Your First Node

```python
from spark.nodes import Node
from spark.utils import arun

class HelloNode(Node):
    async def process(self, context):
        """Process method is where your logic goes."""
        name = context.inputs.content.get('name', 'World')
        return {'message': f'Hello, {name}!'} 

# Run the node
node = HelloNode()
result = arun(node.run({'name': 'Developer'}))
print(result.content['message'])  # Output: Hello, Developer!
```

## Spark Kit & CLI

Spark includes a powerful CLI tool, `spark-spec`, for managing the lifecycle of your AI applications.

### Generating Specs
Generate a JSON specification for a new mission or graph:

```bash
# Generate a basic mission scaffold
spark-spec mission-generate "A research agent that searches web and summarizes" \
  --mission-id "research_v1" \
  --strategy "plan_and_solve" \
  -o mission.json
```

### Validating Specs
Ensure your spec is valid before running it:

```bash
spark-spec mission-validate mission.json --semantic
```

### Compiling to Code
Turn a JSON spec into Python code:

```bash
spark-spec compile mission.json -o ./src/generated --style production
```

### Managing Approvals
List and resolve pending human approvals from the command line:

```bash
# List pending approvals
spark-spec approval-list --state state/mission.sqlite --backend sqlite

# Approve a request
spark-spec approval-resolve "req-123" --state state/mission.sqlite --backend sqlite --status approved
```

## Core Concepts

### The Execution Context

Every `process()` method receives an `ExecutionContext` object with:

```python
class MyNode(Node):
    async def process(self, context):
        # Access inputs from previous node
        data = context.inputs.content

        # Access node state
        previous_run = context.state.context_snapshot

        # Access graph state (if enabled)
        if context.graph_state:
            counter = await context.graph_state.get('counter', 0)

        # Access metadata
        node_id = context.metadata.get('node_id')

        # Return outputs for next node
        return {'result': processed_data}
```

## Building Nodes

### Basic Node Structure

```python
from spark.nodes import Node

class ProcessingNode(Node):
    def __init__(self, multiplier: int = 2):
        super().__init__()
        self.multiplier = multiplier

    async def process(self, context):
        value = context.inputs.content.get('value', 0)
        result = value * self.multiplier
        return {'result': result, 'success': True}
```

### Nodes with Configuration

Use `NodeConfig` for advanced features like capabilities:

```python
from spark.nodes import Node, NodeConfig
from spark.nodes.capabilities import (
    RetryCapability,
    TimeoutCapability,
    RateLimitCapability,
    CircuitBreakerCapability
)

node = Node(
    name="resilient_node",
    config=NodeConfig(
        # Retry 3 times with backoff
        retry=RetryCapability(max_retries=3, backoff_factor=2.0),
        # Timeout after 30s
        timeout=TimeoutCapability(timeout_seconds=30.0),
        # Circuit breaker to prevent cascading failures
        circuit_breaker=CircuitBreakerCapability(failure_threshold=5)
    )
)
```

## Creating Graphs

### Simple Linear Flow

```python
from spark.graphs import Graph

node1 = ProcessNode()
node2 = TransformNode()
node1 >> node2

graph = Graph(start=node1)
result = await graph.run()
```

### Mission Control & Guardrails

For production missions, wrap your graph in `MissionControl` to enforce budgets and track progress against a plan.

```python
from spark.graphs import MissionControl, MissionPlan, PlanStep, BudgetGuardrail, BudgetGuardrailConfig

# Define the plan
plan = MissionPlan([
    PlanStep(id='research', description='Gather data'),
    PlanStep(id='draft', description='Write content', depends_on=['research']),
    PlanStep(id='review', description='Review and refine', depends_on=['draft'])
])

# Define guardrails
budget = BudgetGuardrail(BudgetGuardrailConfig(
    max_iterations=20,
    max_cost_usd=5.0
))

# Attach to graph
mission = MissionControl(plan=plan, guardrails=[budget])
mission.attach(graph)

await graph.run()
```

## Working with Agents

### Basic Agent

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

config = AgentConfig(
    model=OpenAIModel(model_id="gpt-4o"),
    system_prompt="You are a helpful assistant."
)
agent = Agent(config=config)
result = await agent.run("Hello, Spark!")
```

### Reasoning Strategies

Agents support pluggable reasoning patterns.

**ReAct (Reason + Act):**
Ideal for tool-heavy tasks where the agent needs to observe results before proceeding.
```python
from spark.agents.strategies import ReActStrategy

config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy=ReActStrategy(verbose=True)
)
```

**Chain-of-Thought (CoT):**
Best for complex logic or math problems.
```python
from spark.agents.strategies import ChainOfThoughtStrategy

config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy=ChainOfThoughtStrategy()
)
```

**Plan-and-Solve:**
Generates a structured plan before executing.
```python
from spark.agents.strategies import PlanAndSolveStrategy

config = AgentConfig(
    model=model,
    output_mode='json',
    reasoning_strategy=PlanAndSolveStrategy()
)
```

## Governance & Compliance

Spark includes a built-in policy engine to control agent behavior, enforce safety, and manage costs.

### Defining Policies

Policies are defined as sets of rules that allow or deny actions.

```python
from spark.governance.policy import PolicySet, PolicyRule, PolicyEffect

# Create a policy that prevents file deletion
fs_policy = PolicySet(
    name="fs_safety",
    rules=[
        PolicyRule(
            name="block_delete",
            effect=PolicyEffect.DENY,
            actions=["tool:execute"],
            resources=["tool://delete_file"],
            description="Prevent agents from deleting files"
        ),
        PolicyRule(
            name="require_approval_write",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            actions=["tool:execute"],
            resources=["tool://write_file"],
            description="Require human approval to write files"
        )
    ]
)
```

### Attaching Policies to Agents

```python
config = AgentConfig(
    model=model,
    tools=[read_file, write_file, delete_file],
    policy_set=fs_policy  # Attach the policy set
)
agent = Agent(config=config)
```

### Human Approval Flow

When a policy triggers `REQUIRE_APPROVAL`, the agent pauses execution.

1.  **Pause**: The agent raises `ApprovalPendingError`.
2.  **Persist**: The approval request is saved to `GraphState`.
3.  **Review**: An operator reviews the request (via CLI or API).
4.  **Resume**: Once approved, the graph resumes execution.

```python
# CLI command to approve a pending request
spark-spec approval-resolve "req-123" --status approved
```

## Telemetry & Observability

The `TelemetryManager` provides centralized tracing and metrics.

### Configuration

```python
from spark.telemetry import TelemetryManager, TelemetryConfig

config = TelemetryConfig(
    enabled=True,
    backend='sqlite',
    backend_config={'path': 'telemetry.db'}
)
manager = TelemetryManager.get_instance(config)
```

### Instrumenting Code

```python
async def my_task():
    # Start a trace
    trace = manager.start_trace("my_workflow")
    
    # Create a span
    async with manager.start_span("step_1", trace.trace_id) as span:
        # Add attributes
        span.set_attribute("user_id", "123")
        
        # Record events
        manager.record_event("process_started", trace_id=trace.trace_id)
        
        # Do work...
        
    manager.end_trace(trace.trace_id)
```

## Recursive Self-Improvement (RSI)

Spark can autonomously improve your graphs using the RSI Meta-Graph.

### Concept
RSI involves a feedback loop:
1.  **Analyze**: Review telemetry for bottlenecks or errors.
2.  **Hypothesize**: Generate ideas for improvement (e.g., better prompts, different tools).
3.  **Validate**: Check if changes are safe.
4.  **Test**: Run A/B tests.
5.  **Deploy**: Roll out successful changes.

### Setup

```python
from spark.rsi import RSIMetaGraph, RSIMetaGraphConfig, ExperienceDatabase

# 1. Initialize Experience DB
experience_db = ExperienceDatabase("experience.db")
await experience_db.initialize()

# 2. Configure RSI
rsi_config = RSIMetaGraphConfig(
    graph_id="customer_service_agent",
    graph_version="1.0",
    analysis_window_hours=24,
    max_hypotheses=3
)

# 3. Create Meta-Graph
rsi = RSIMetaGraph(
    config=rsi_config,
    experience_db=experience_db,
    model=OpenAIModel(model_id="gpt-4o")
)

# 4. Run Improvement Loop
summary = await rsi.run(target_graph=my_graph)
print(f"RSI Result: {summary}")
```

## State Management

### Persistent Backends
Swap the in-memory store for durable backends to survive restarts.

```python
from spark.graphs import Graph, SQLiteStateBackend, MissionStateModel

# Define schema
class MissionState(MissionStateModel):
    counter: int = 0
    notes: list[str] = []

# Initialize backend
backend = SQLiteStateBackend("mission_state.db")

# Create graph with persistence
graph = Graph(
    start=node,
    state_backend=backend,
    state_schema=MissionState
)
```

### Checkpointing
Save the full execution state of a graph to resume later.

```python
# Create checkpoint
checkpoint = await graph.checkpoint_state()

# ... Application restarts ...

# Resume
await graph.resume_from(checkpoint)
```

## Distributed Execution

### RPC Nodes
Expose graphs as services or call remote graphs.

```python
# Server
service = DataProcessingService(host="0.0.0.0", port=8000)
await service.start_server()

# Client (Proxy Node)
proxy_config = RemoteRpcProxyConfig(endpoint="http://localhost:8000")
proxy = RemoteRpcProxyNode(config=proxy_config)

local_node >> proxy >> output_node
```

## Best Practices

1.  **Use Schemas**: Always define a Pydantic model for your `GraphState`. It documents your data and prevents runtime type errors.
2.  **Design for Resumability**: Use checkpoints and persistent backends for long-running missions.
3.  **Least Privilege**: Use `PolicySet` to restrict agent tools to only what is necessary.
4.  **Think Async**: Design nodes to be non-blocking. Use `asyncio.gather` within nodes if you need to parallelize internal tasks.
5.  **Simulate First**: Use `spark-spec simulation-run` to test your mission logic with mock tools before hitting real APIs.

```python
# Good - production configuration
import os

model = OpenAIModel(
    model_id=os.getenv('MODEL_ID', 'gpt-4o'),
    api_key=os.getenv('OPENAI_API_KEY')
)

config = AgentConfig(
    model=model,
    tools=tools,
    max_steps=int(os.getenv('MAX_STEPS', '20')),
    parallel_tool_execution=True
)

agent = Agent(config=config)

# Checkpoint every N interactions
if interaction_count % 10 == 0:
    agent.save_checkpoint(f'checkpoint_{interaction_count}.json')
```