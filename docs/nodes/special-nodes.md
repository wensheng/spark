# Special Node Types

**Document Type**: Reference Documentation
**Audience**: Developers using specialized nodes for agents, RPC, and human interaction
**Related**: [Node Fundamentals](/docs/nodes/fundamentals.md), [Agent System](/docs/agents/fundamentals.md), [RPC System](/docs/rpc/overview.md)

---

## Overview

Spark provides specialized node types for common workflows beyond basic data processing. These nodes extend the base `Node` class with domain-specific capabilities for LLM agents, human interaction, distributed systems, and nested graphs.

**Special Node Types**:
1. **AgentNode**: LLM-powered autonomous agents
2. **HumanNode**: Human-in-the-loop patterns
3. **RpcNode**: JSON-RPC servers
4. **RemoteRpcProxyNode**: RPC clients
5. **SubgraphNode**: Nested graph composition
6. **Custom Base Classes**: When to create your own

---

## AgentNode

### Overview

`AgentNode` wraps the Spark `Agent` class to integrate LLM-powered agents into graphs as nodes.

**Location**: Typically created in application code by wrapping `spark.agents.Agent`

**Use Cases**:
- Natural language processing in workflows
- Tool-using agents as graph steps
- Multi-agent coordination via graphs
- Autonomous decision-making nodes

### Basic Pattern

```python
from spark.nodes import Node
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool
from spark.nodes.types import ExecutionContext

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return search_api(query)

class AgentNode(Node):
    """Node that wraps an LLM agent."""

    def __init__(self, model, tools, **kwargs):
        super().__init__(**kwargs)

        # Create agent configuration
        agent_config = AgentConfig(
            model=model,
            tools=tools,
            system_prompt="You are a helpful assistant."
        )

        # Initialize agent
        self.agent = Agent(config=agent_config)

    async def process(self, context: ExecutionContext) -> dict:
        # Extract query from inputs
        query = context.inputs.content.get('query', '')

        # Run agent
        result = await self.agent.run(query)

        # Return agent output
        return {
            'response': result.output,
            'tool_calls': len(result.tool_trace)
        }

# Usage in graph
model = OpenAIModel(model_id="gpt-4o")
agent_node = AgentNode(model=model, tools=[search_web])

graph = Graph(start=agent_node)
result = await graph.run(Task(inputs=NodeMessage(content={'query': 'What is the weather?'})))
```

### Multi-Agent Workflows

```python
class ResearcherAgentNode(Node):
    """Agent specialized in research."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = Agent(config=AgentConfig(
            model=OpenAIModel(model_id="gpt-4o"),
            system_prompt="You are a research specialist.",
            tools=[search_web, read_article]
        ))

    async def process(self, context: ExecutionContext) -> dict:
        topic = context.inputs.content['topic']
        research = await self.agent.run(f"Research: {topic}")
        return {'research': research.output}

class WriterAgentNode(Node):
    """Agent specialized in writing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = Agent(config=AgentConfig(
            model=OpenAIModel(model_id="gpt-4o"),
            system_prompt="You are a technical writer."
        ))

    async def process(self, context: ExecutionContext) -> dict:
        research = context.inputs.content['research']
        article = await self.agent.run(f"Write article based on: {research}")
        return {'article': article.output}

# Create pipeline
researcher = ResearcherAgentNode()
writer = WriterAgentNode()

researcher >> writer

graph = Graph(start=researcher)
```

### Agent State in Graphs

```python
class StatefulAgentNode(Node):
    """Agent that maintains conversation state."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = Agent(config=AgentConfig(
            model=OpenAIModel(model_id="gpt-4o"),
            system_prompt="You are a helpful assistant."
        ))

    async def process(self, context: ExecutionContext) -> dict:
        query = context.inputs.content['query']

        # Agent maintains conversation history internally
        result = await self.agent.run(query)

        # Can checkpoint agent state
        checkpoint = self.agent.checkpoint()
        context.state['agent_checkpoint'] = checkpoint

        return {'response': result.output}
```

### Coordination via Graph State

```python
class CollaborativeAgentNode(Node):
    """Agent that coordinates via graph state."""

    def __init__(self, role, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.agent = Agent(config=AgentConfig(
            model=OpenAIModel(model_id="gpt-4o"),
            system_prompt=f"You are a {role} agent."
        ))

    async def process(self, context: ExecutionContext) -> dict:
        # Read shared context from graph state
        topic = await context.graph_state.get('topic')
        other_findings = await context.graph_state.get('findings', [])

        # Agent processes with awareness of other agents
        result = await self.agent.run(
            f"Topic: {topic}. Other findings: {other_findings}. Your analysis:"
        )

        # Update shared graph state
        async with context.graph_state.transaction() as state:
            findings = state.get('findings', [])
            findings.append({
                'role': self.role,
                'result': result.output
            })
            state['findings'] = findings

        return {'done': True}

# Create multi-agent system
analyst = CollaborativeAgentNode(role='analyst')
critic = CollaborativeAgentNode(role='critic')
synthesizer = CollaborativeAgentNode(role='synthesizer')

graph = Graph(start=analyst, initial_state={'topic': 'AI safety'})
analyst >> critic >> synthesizer
```

---

## HumanNode

### Overview

`HumanNode` enables human-in-the-loop patterns through configurable policies for approval and input.

**Location**: `spark/nodes/human.py`

**Use Cases**:
- Manual approval gates
- Human input collection
- Quality control checkpoints
- Compliance reviews

### Human Approval Policy

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig
from spark.nodes.human import InteractiveHumanPolicy
from spark.nodes.types import ExecutionContext

class ApprovalNode(Node):
    """Node requiring human approval."""

    def __init__(self, **kwargs):
        # Configure human approval policy
        human_policy = InteractiveHumanPolicy(
            prompt="Approve this operation? (yes/no): "
        )

        config = NodeConfig(
            human_policy=human_policy
        )

        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Perform operation
        result = await risky_operation()

        # Human policy applied automatically after process returns
        # Framework prompts human for approval

        return {'result': result, 'approved': True}

# Usage
approval_node = ApprovalNode()
```

### Human Input Policy

```python
from spark.nodes.human import HumanPrompt

class InputNode(Node):
    """Node that requests human input."""

    def __init__(self, **kwargs):
        human_policy = InteractiveHumanPolicy(
            prompt=lambda node, ctx, result: HumanPrompt(
                message="Enter additional context:",
                kind='text'
            )
        )

        config = NodeConfig(human_policy=human_policy)
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        base_data = context.inputs.content

        # Human input collected after processing
        return {'base_data': base_data}
```

### Conditional Human Approval

```python
class ConditionalApprovalNode(Node):
    """Request approval only for high-risk operations."""

    def __init__(self, **kwargs):
        def should_approve(node, context, result):
            """Approve only if cost exceeds threshold."""
            return result.get('cost', 0) > 100

        human_policy = InteractiveHumanPolicy(
            trigger=should_approve,
            prompt="High cost operation. Approve? (yes/no): "
        )

        config = NodeConfig(human_policy=human_policy)
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        operation = context.inputs.content['operation']
        cost = estimate_cost(operation)

        # Human prompted only if cost > 100
        return {'operation': operation, 'cost': cost}
```

### Option Selection

```python
from spark.nodes.human import HumanPrompt

class OptionSelectorNode(Node):
    """Present options to human for selection."""

    def __init__(self, **kwargs):
        def create_prompt(node, context, result):
            options = result['options']
            return HumanPrompt(
                message="Select an option:",
                kind='options',
                options=options
            )

        human_policy = InteractiveHumanPolicy(
            prompt=create_prompt
        )

        config = NodeConfig(human_policy=human_policy)
        super().__init__(config=config, **kwargs)

    async def process(self, context: ExecutionContext) -> dict:
        # Generate options
        options = ["Option A", "Option B", "Option C"]

        # Human selects from options
        return {'options': options}
```

---

## RpcNode

### Overview

`RpcNode` exposes nodes as JSON-RPC 2.0 servers supporting HTTP and WebSocket transports.

**Location**: `spark/nodes/rpc.py`

**Use Cases**:
- Microservices architecture
- Distributed workflows
- External service integration
- Load distribution

### Basic RPC Server

```python
from spark.nodes.rpc import RpcNode

class MyRpcNode(RpcNode):
    """Simple RPC server node."""

    async def rpc_add(self, params, context):
        """Handle 'add' RPC method."""
        a = params.get('a', 0)
        b = params.get('b', 0)
        return {'sum': a + b}

    async def rpc_getData(self, params, context):
        """Handle 'getData' RPC method."""
        data_id = params.get('id')
        data = await self.fetch_data(data_id)
        return {'data': data}

    async def fetch_data(self, data_id):
        """Helper method for fetching data."""
        # Implementation
        return {'id': data_id, 'value': 'example'}

# Start server
node = MyRpcNode(host="0.0.0.0", port=8000)
await node.start_server()
```

**RPC Method Naming**: Methods named `rpc_<method>` handle RPC calls. The framework converts dots/dashes in method names (e.g., `rpc_user_create` handles `user.create`).

### HTTPS/WSS Support

```python
# Start with SSL
node = MyRpcNode(
    host="0.0.0.0",
    port=8443,
    ssl_certfile="/path/to/cert.pem",
    ssl_keyfile="/path/to/key.pem"
)
await node.start_server()

# Clients connect via:
# https://hostname:8443/  (HTTP)
# wss://hostname:8443/ws  (WebSocket)
```

### Lifecycle Hooks

```python
class HookedRpcNode(RpcNode):
    """RPC node with lifecycle hooks."""

    async def before_request(self, method, params, request_id):
        """Called before each request - use for auth, logging."""
        print(f"Request {request_id}: {method}")

        # Authentication example
        if 'auth_token' not in params:
            raise Exception("Missing auth token")

        # Rate limiting example
        await self.check_rate_limit(params['auth_token'])

    async def after_request(self, method, params, request_id, result):
        """Called after each request."""
        print(f"Request {request_id} completed: {result}")

    async def on_websocket_connect(self, client_id, websocket):
        """Called when WebSocket client connects."""
        print(f"Client {client_id} connected")

        # Send welcome notification
        await self.send_notification_to_client(
            client_id,
            "welcome",
            {"message": "Connected to RPC server"}
        )

    async def on_websocket_disconnect(self, client_id):
        """Called when WebSocket client disconnects."""
        print(f"Client {client_id} disconnected")
```

### Server Notifications

```python
class NotifyingRpcNode(RpcNode):
    """RPC node that sends notifications to clients."""

    async def rpc_subscribe(self, params, context):
        """Subscribe client to updates."""
        client_id = params['client_id']
        topic = params['topic']

        # Store subscription
        self.subscriptions[topic] = self.subscriptions.get(topic, [])
        self.subscriptions[topic].append(client_id)

        return {'subscribed': True}

    async def broadcast_update(self, topic, data):
        """Broadcast update to subscribed clients."""
        clients = self.subscriptions.get(topic, [])

        for client_id in clients:
            await self.send_notification_to_client(
                client_id,
                "update",
                {"topic": topic, "data": data}
            )

# From elsewhere in code
await node.broadcast_notification("alert", {"level": "warning", "msg": "..."})
```

### Exposing Graph as RPC Service

```python
class GraphRpcNode(RpcNode):
    """Expose graph execution via RPC."""

    def __init__(self, graph, **kwargs):
        super().__init__(**kwargs)
        self.graph = graph

    async def rpc_execute(self, params, context):
        """Execute graph with provided inputs."""
        from spark.graphs.tasks import Task
        from spark.nodes.types import NodeMessage

        task = Task(inputs=NodeMessage(content=params))
        result = await self.graph.run(task)

        return {
            'success': True,
            'result': result.content
        }

# Usage
processing_graph = Graph(start=ProcessingNode())
rpc_node = GraphRpcNode(graph=processing_graph, host="0.0.0.0", port=8000)
await rpc_node.start_server()
```

---

## RemoteRpcProxyNode

### Overview

`RemoteRpcProxyNode` allows local graphs to call remote RPC services as if they were local nodes.

**Location**: `spark/nodes/rpc_client.py`

**Use Cases**:
- Distributed workflows
- Microservices integration
- Load balancing
- Remote execution

### Basic HTTP Proxy

```python
from spark.nodes.rpc_client import RemoteRpcProxyNode, RemoteRpcProxyConfig
from spark.nodes import Node
from spark.graphs import Graph

# Configure proxy
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://remote-server:8000",
    transport="http",
    default_method="process",
    request_timeout=30.0
)

proxy_node = RemoteRpcProxyNode(config=proxy_config)

# Use in graph like any other node
local_node = LocalProcessingNode()
local_node >> proxy_node  # Calls remote service

graph = Graph(start=local_node)
result = await graph.run()
```

### Input Formats

```python
class ProxyCallerNode(Node):
    """Node that calls remote RPC service."""

    async def process(self, context: ExecutionContext) -> dict:
        user_id = context.inputs.content['user_id']

        # Return RPC call specification
        # RemoteRpcProxyNode interprets this

        # Simple method name
        return "getData"

        # Method with parameters
        return {
            'method': 'getData',
            'id': user_id
        }

        # Full JSON-RPC payload
        return {
            'jsonrpc': '2.0',
            'method': 'getData',
            'params': {'id': user_id},
            'id': 1
        }

        # Notification (no response expected)
        return {
            'method': 'log',
            'params': {'message': 'Processing started'},
            'notify': True
        }
```

### WebSocket Mode

```python
# Configure for WebSocket with notifications
proxy_config = RemoteRpcProxyConfig(
    endpoint="http://remote-server:8000",
    transport="websocket",
    auto_connect_websocket=True,
    forward_notifications_to_event_bus=True
)

proxy_node = RemoteRpcProxyNode(config=proxy_config)

# Subscribe to server notifications via event bus
def handle_notification(event):
    print(f"Server notification: {event}")

graph.event_bus.subscribe("remote.rpc.*", handle_notification)

# Add proxy to graph
graph = Graph(start=proxy_node)
```

### Distributed Workflow Pattern

```python
# Local preprocessing
class PreprocessNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        data = context.inputs.content['raw_data']
        cleaned = self.clean_data(data)
        return {'method': 'analyze', 'data': cleaned}

# Remote processing via RPC
remote_analyzer = RemoteRpcProxyNode(config=RemoteRpcProxyConfig(
    endpoint="http://ml-server:8000",
    transport="http"
))

# Local postprocessing
class PostprocessNode(Node):
    async def process(self, context: ExecutionContext) -> dict:
        results = context.inputs.content['result']
        formatted = self.format_results(results)
        return {'final_results': formatted}

# Connect into pipeline
preprocess = PreprocessNode()
postprocess = PostprocessNode()

preprocess >> remote_analyzer >> postprocess

graph = Graph(start=preprocess)
```

---

## SubgraphNode

### Overview

`SubgraphNode` enables nesting graphs within graphs for composition and reusability.

**Pattern**: Wrapper node that runs a complete graph as its processing logic.

**Use Cases**:
- Reusable workflow components
- Modular graph design
- Complex workflows with sub-stages
- Isolated state management

### Basic Subgraph

```python
from spark.nodes import Node
from spark.graphs import Graph
from spark.nodes.types import ExecutionContext

class SubgraphNode(Node):
    """Node that runs a nested graph."""

    def __init__(self, subgraph: Graph, **kwargs):
        super().__init__(**kwargs)
        self.subgraph = subgraph

    async def process(self, context: ExecutionContext) -> dict:
        # Create task from current inputs
        from spark.graphs.tasks import Task
        from spark.nodes.types import NodeMessage

        task = Task(inputs=NodeMessage(content=context.inputs.content))

        # Run subgraph
        result = await self.subgraph.run(task)

        # Return subgraph outputs
        return result.content

# Create subgraph
step1 = ProcessingNode()
step2 = TransformNode()
step1 >> step2

subgraph = Graph(start=step1)

# Use as node in parent graph
subgraph_node = SubgraphNode(subgraph=subgraph)

parent_graph = Graph(start=subgraph_node)
```

### State Isolation

```python
class IsolatedSubgraphNode(Node):
    """Subgraph with isolated state."""

    def __init__(self, subgraph: Graph, **kwargs):
        super().__init__(**kwargs)
        self.subgraph = subgraph

    async def process(self, context: ExecutionContext) -> dict:
        # Subgraph has its own isolated graph state
        # Parent graph state not accessible to subgraph
        task = Task(inputs=NodeMessage(content=context.inputs.content))

        result = await self.subgraph.run(task)

        return result.content
```

### State Sharing

```python
class SharedStateSubgraphNode(Node):
    """Subgraph that shares parent graph state."""

    def __init__(self, subgraph: Graph, **kwargs):
        super().__init__(**kwargs)
        self.subgraph = subgraph

    async def process(self, context: ExecutionContext) -> dict:
        # Pass parent graph state to subgraph
        # (Requires custom implementation or framework support)

        # For now, pass data via inputs/outputs
        shared_data = await context.graph_state.get('shared_data') \
            if context.graph_state else None

        task_inputs = {**context.inputs.content, 'shared_data': shared_data}
        task = Task(inputs=NodeMessage(content=task_inputs))

        result = await self.subgraph.run(task)

        # Update parent state with subgraph results
        if context.graph_state:
            await context.graph_state.set('subgraph_result', result.content)

        return result.content
```

### Recursive Composition

```python
# Subgraph with nested subgraphs
inner_graph = Graph(start=InnerNode())
inner_subgraph = SubgraphNode(subgraph=inner_graph)

middle_graph = Graph(start=inner_subgraph)
middle_subgraph = SubgraphNode(subgraph=middle_graph)

outer_graph = Graph(start=middle_subgraph)

# outer_graph -> middle_graph -> inner_graph
```

---

## Custom Node Base Classes

### When to Create Custom Base Classes

Create custom base classes when:
1. Multiple nodes share common initialization logic
2. Need domain-specific capabilities not in standard capabilities
3. Building a node library for a specific domain
4. Want to enforce patterns across many nodes

### Custom Base Class Pattern

```python
from spark.nodes import Node
from spark.nodes.config import NodeConfig

class DatabaseNode(Node):
    """Base class for database-accessing nodes."""

    def __init__(self, connection_string, **kwargs):
        # Common initialization
        self.connection_string = connection_string
        self.db = None

        # Configure common capabilities
        config = NodeConfig(
            retry=RetryPolicy(max_attempts=3),
            timeout=TimeoutPolicy(seconds=30.0)
        )

        super().__init__(config=config, **kwargs)

    async def connect(self):
        """Connect to database."""
        if self.db is None:
            self.db = await create_connection(self.connection_string)

    async def disconnect(self):
        """Disconnect from database."""
        if self.db:
            await self.db.close()
            self.db = None

class UserQueryNode(DatabaseNode):
    """Query users from database."""

    async def process(self, context: ExecutionContext) -> dict:
        await self.connect()

        user_id = context.inputs.content['user_id']
        user = await self.db.fetch_user(user_id)

        return {'user': user}
```

### Domain-Specific Base Classes

```python
class MLModelNode(Node):
    """Base class for ML model nodes."""

    def __init__(self, model_path, **kwargs):
        super().__init__(**kwargs)
        self.model_path = model_path
        self.model = None

    async def load_model(self):
        """Load ML model."""
        if self.model is None:
            self.model = await load_model_async(self.model_path)

    async def predict(self, features):
        """Make prediction."""
        await self.load_model()
        return await self.model.predict_async(features)

class SentimentAnalysisNode(MLModelNode):
    """Sentiment analysis using ML model."""

    async def process(self, context: ExecutionContext) -> dict:
        text = context.inputs.content['text']

        # Use base class predict method
        sentiment = await self.predict(self.extract_features(text))

        return {'sentiment': sentiment}
```

### Capability Extensions

```python
from spark.nodes.policies import SupportsProcessWrapper, ProcessWrapper

class CachingCapability(SupportsProcessWrapper):
    """Custom caching capability."""

    def __init__(self, ttl=300):
        self.ttl = ttl
        self.cache = {}

    def build_wrapper(self, node) -> ProcessWrapper:
        async def wrapper(context, process_fn):
            # Check cache
            cache_key = self._make_key(context.inputs.content)

            if cache_key in self.cache:
                cached_value, cached_time = self.cache[cache_key]
                if time.time() - cached_time < self.ttl:
                    return cached_value

            # Execute and cache
            result = await process_fn(context)
            self.cache[cache_key] = (result, time.time())

            return result

        return wrapper

    def _make_key(self, content):
        import hashlib
        import json
        return hashlib.md5(json.dumps(content, sort_keys=True).encode()).hexdigest()

# Custom node with custom capability
class CachedNode(Node):
    def __init__(self, **kwargs):
        # Would need custom config to support
        # or manually apply wrapper
        super().__init__(**kwargs)
```

---

## Testing Special Nodes

### Testing AgentNode

```python
@pytest.mark.asyncio
async def test_agent_node():
    from spark.models.openai import OpenAIModel
    from unittest.mock import AsyncMock

    # Mock model
    model = OpenAIModel(model_id="gpt-4o")
    model.get_text = AsyncMock(return_value="Test response")

    agent_node = AgentNode(model=model, tools=[])

    inputs = NodeMessage(content={'query': 'test query'})
    result = await agent_node.run(inputs)

    assert 'response' in result.content
```

### Testing HumanNode

```python
@pytest.mark.asyncio
async def test_human_approval():
    from unittest.mock import AsyncMock

    # Mock human input
    async def mock_input(prompt):
        return "yes"

    human_policy = InteractiveHumanPolicy(
        input_provider=mock_input
    )

    config = NodeConfig(human_policy=human_policy)
    node = ApprovalNode(config=config)

    result = await node.run(NodeMessage(content={}))
    assert result.content['approved'] is True
```

### Testing RPC Nodes

```python
@pytest.mark.asyncio
async def test_rpc_node():
    import httpx

    # Start server in background
    node = MyRpcNode(host="127.0.0.1", port=8888)
    server_task = asyncio.create_task(node.start_server())

    await asyncio.sleep(0.5)  # Let server start

    try:
        # Call RPC method
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:8888/",
                json={
                    "jsonrpc": "2.0",
                    "method": "add",
                    "params": {"a": 2, "b": 3},
                    "id": 1
                }
            )

        result = response.json()
        assert result['result']['sum'] == 5

    finally:
        # Cleanup
        node._stop_flag = True
        server_task.cancel()
```

---

## Best Practices

### 1. Agent Nodes: Keep Prompts Focused

```python
# Good: Focused role
agent_config = AgentConfig(
    system_prompt="You are a sentiment analysis specialist."
)

# Less ideal: Too broad
agent_config = AgentConfig(
    system_prompt="You can do anything."
)
```

### 2. Human Nodes: Clear Prompts

```python
# Good: Clear instructions
prompt="Review the API call. Approve? (yes/no): "

# Less ideal: Ambiguous
prompt="Ok? "
```

### 3. RPC Nodes: Version Your API

```python
class VersionedRpcNode(RpcNode):
    async def rpc_v1_getData(self, params, context):
        """Version 1 API."""
        return {"data": "v1"}

    async def rpc_v2_getData(self, params, context):
        """Version 2 API with breaking changes."""
        return {"data": "v2", "metadata": {}}
```

### 4. Subgraphs: Clear Contracts

```python
class SubgraphNode(Node):
    """
    Process data using specialized subgraph.

    Input Contract:
        raw_data (dict): Unprocessed data

    Output Contract:
        processed_data (dict): Processed results
        status (str): Processing status
    """
    async def process(self, context: ExecutionContext) -> dict:
        # Implementation
        pass
```

---

## Related Documentation

- [Node Fundamentals](/docs/nodes/fundamentals.md) - Basic node concepts
- [Agent System](/docs/agents/fundamentals.md) - Complete agent reference
- [RPC System](/docs/rpc/overview.md) - Distributed workflows
- [Graph Composition](/docs/graphs/subgraphs.md) - Nested graphs

---

## Summary

Special node types provide domain-specific capabilities:
- **AgentNode**: Integrates LLM agents into workflows
- **HumanNode**: Enables human-in-the-loop patterns
- **RpcNode**: Exposes nodes as JSON-RPC services
- **RemoteRpcProxyNode**: Calls remote services from graphs
- **SubgraphNode**: Nests graphs for composition
- **Custom Base Classes**: Domain-specific abstractions

These nodes extend Spark's capabilities beyond basic data processing into autonomous agents, human interaction, and distributed systems.
