# Spark: ADK (AI Development Kit) Overview

## What is Spark?

Spark is a Python AI Development Kit (ADK) for building production-grade agentic workflows. It uses a **node-and-graph architecture** to orchestrate autonomous agents, combining the flexibility of the Actor Model with the power of Large Language Models (LLMs).

Spark goes beyond simple chains, offering a complete ecosystem for building, observing, and **self-improving** AI applications.

## Core Architecture

### 1. Nodes (The Actors)
Nodes are the fundamental processing units. Each node is an independent actor that processes inputs and produces outputs.
*   **BaseNode**: The abstract foundation.
*   **Node**: Standard implementation with built-in **Capabilities** (Retry, Timeout, Circuit Breaker, Rate Limit).
*   **Agent**: A specialized node for LLM interaction (see below).
*   **HumanNode**: Pauses execution for human-in-the-loop feedback.
*   **SubgraphNode**: Encapsulates an entire graph as a single node for modular composition.
*   **BatchProcessNodes**: For parallel processing (Threaded, Multiprocess, Async).

### 2. Graphs (The Orchestrators)
Graphs define the topology of your workflow.
*   **Control Flow**: Supports sequential chains (`>>`), conditional branching (routing based on logic), and loops (cyclic graphs).
*   **Execution Models**:
    *   **Finite Task**: Run a graph until completion (`graph.run()`).
    *   **Continuous Service**: Run as a long-lived service (`graph.go()`), ideal for message processing or reactive systems.
*   **State Management**: `GraphState` provides transactional, thread-safe shared state across the workflow with pluggable backends (In-Memory, SQLite, JSON).

### 3. Agents (The Intelligence)
Agents are specialized nodes designed for autonomous reasoning and tool use.
*   **Memory**: Configurable memory managers with policies (WindowBuffer, TokenBuffer, etc.).
*   **Strategies**: Pluggable reasoning engines:
    *   **ReAct**: Reason + Act loop (Think -> Tool -> Observe).
    *   **Chain-of-Thought**: Step-by-step reasoning before answering.
    *   **Plan-and-Solve**: Generates a multi-step plan before execution.
*   **Cost Tracking**: Built-in monitoring of token usage and costs across providers.
*   **Checkpointing**: Full serialization of agent state for pause/resume functionality.

## Key Subsystems

### 4. Recursive Self-Improvement (RSI)
A unique feature of Spark is the **RSI Meta-Graph**, a system that allows an application to optimize itself autonomously.
*   **Analyze**: `PerformanceAnalyzerNode` reviews telemetry to find bottlenecks.
*   **Hypothesize**: `HypothesisGeneratorNode` proposes improvements (e.g., prompt tweaks, model changes).
*   **Validate & Test**: Hypotheses are validated against safety rules and A/B tested.
*   **Deploy**: Successful changes can be automatically or semi-automatically rolled out.
*   **Experience DB**: A database that learns from past optimization attempts.

### 5. Governance & Policy
Spark includes a robust policy engine for safe AI deployment.
*   **Policy Sets**: Define rules for tool usage, sensitive data access, and budget limits.
*   **Approval Gates**: `HumanApprovalRequired` mechanisms for high-stakes actions.
*   **Audit Trails**: Detailed logging of policy decisions and violations.

### 6. The `spark-spec` Kit
A CLI toolkit (`spark.kit`) for managing the development lifecycle.
*   **Spec Generation**: Create JSON specifications of your graphs.
*   **Code Generation**: Compile JSON specs into Python code.
*   **Simulation**: Run mission specs against simulated tools for regression testing.
*   **Visualization**: Export graph structures for visualization.

### 7. Unified Model Interface
Write code once, run on any provider.
*   **Supported Providers**: OpenAI, AWS Bedrock, Google Gemini.
*   **Features**: Unified tool calling, JSON mode enforcement, and structured output parsing.
*   **EchoModel**: A mock model for testing and development without API costs.

## Ecosystem Features

*   **Resilience**: Declarative capabilities like `RetryCapability`, `CircuitBreakerCapability`, and `IdempotencyCapability` can be attached to any node.
*   **Telemetry**: Deep integration with telemetry systems for tracing execution paths, latencies, and errors.
*   **Distributed Execution**: `RpcNode` and `RemoteRpcProxyNode` allow graphs to span across network boundaries, enabling microservices architectures.

## Getting Started

### Installation
```bash
pip install spark
```

### Basic Agent
```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

# Configure
config = AgentConfig(
    model=OpenAIModel(model_id="gpt-5-mini"),
    system_prompt="You are a helpful assistant."
)

# Create and Run
agent = Agent(config=config)
result = await agent.run("Hello, Spark!")
print(result.content)
```

### The Spark CLI
```bash
# Generate a new pipeline spec
spark-spec generate "Research Assistant" -o research_pipeline.json

# Validate the spec
spark-spec validate research_pipeline.json
```

## Learn More

*   **Programming Guide**: `docs/spark_programming_guide.md`
*   **RSI Documentation**: `spark/rsi/README.md` (Check source)
*   **Examples**: `examples/` folder contains over 20 fully functional examples ranging from "Hello World" to complex "RSI" and "RPC" demos.