---
title: Integration
nav_order: 14
---
# Integration
---

This guide covers how to integrate Spark agents into graph workflows, enabling you to build multi-step workflows that leverage LLM-powered autonomous agents alongside traditional processing nodes.

## Table of Contents

- [Overview](#overview)
- [AgentNode Wrapper Pattern](#agentnode-wrapper-pattern)
- [Passing Inputs to Agents](#passing-inputs-to-agents)
- [Capturing Agent Outputs](#capturing-agent-outputs)
- [Multi-Agent Workflows](#multi-agent-workflows)
- [Agent Coordination via GraphState](#agent-coordination-via-graphstate)
- [Error Handling](#error-handling)
- [Testing Agent-Based Graphs](#testing-agent-based-graphs)

## Overview

Spark agents can be seamlessly integrated into graph workflows by wrapping them in Node classes. This allows agents to participate in complex workflows alongside traditional processing nodes, with full access to graph state, edge conditions, and workflow orchestration.

**Benefits of Agents in Graphs**:
- Combine deterministic processing with autonomous decision-making
- Chain multiple agents with different specializations
- Share state and coordinate between agents and traditional nodes
- Apply graph-level capabilities (retry, timeout, etc.) to agent execution
- Leverage telemetry and observability for agent operations

## AgentNode Wrapper Pattern

The recommended pattern for integrating agents into graphs is to create a Node subclass that wraps an Agent instance.

### Basic AgentNode Pattern

```python
from spark.nodes import Node
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel

class AgentNode(Node):
    """Wrapper node for integrating agents into graphs."""

    def __init__(self, agent_config: AgentConfig, **kwargs):
        super().__init__(**kwargs)
        self.agent = Agent(config=agent_config)

    async def process(self, context):
        """Execute the agent with input from the graph."""
        # Extract input query from context
        user_query = context.inputs.content.get('query', '')

        # Run agent
        result = await self.agent.run(user_query)

        # Return result as node output
        return {
            'agent_response': result.output,
            'steps_taken': result.steps,
            'success': True
        }
```

### Example Usage

```python
from spark.graphs import Graph
from spark.tools.decorator import tool

# Define tools for the agent
@tool
def search_docs(query: str) -> str:
    """Search documentation."""
    return f"Found docs for: {query}"

# Create agent configuration
model = OpenAIModel(model_id="gpt-4o")
agent_config = AgentConfig(
    model=model,
    tools=[search_docs],
    system_prompt="You are a helpful documentation assistant."
)

# Create agent node
doc_agent = AgentNode(agent_config=agent_config, name="DocAgent")

# Build graph
input_node = InputNode()
input_node >> doc_agent

graph = Graph(start=input_node)

# Run
result = await graph.run({'query': 'How do I create a node?'})
print(result.content['agent_response'])
```

## Passing Inputs to Agents

Agents can receive inputs from previous nodes in multiple ways:

### 1. Direct Query String

Pass the query directly from node outputs:

```python
class SimpleAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        query = context.inputs.content.get('query')
        result = await self.agent.run(query)
        return {'response': result.output}
```

### 2. Structured Context

Build a structured prompt from multiple input fields:

```python
class ContextAwareAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Extract context from previous nodes
        user_data = context.inputs.content.get('user_data', {})
        request = context.inputs.content.get('request', '')

        # Build contextual prompt
        prompt = f"""
        User: {user_data.get('name')}
        Role: {user_data.get('role')}
        Request: {request}
        """

        result = await self.agent.run(prompt)
        return {'response': result.output}
```

### 3. Conversation History

Maintain conversation state across multiple agent invocations:

```python
class ConversationalAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Get new message
        user_message = context.inputs.content.get('message')

        # Add to agent's history
        self.agent.add_message_to_history({
            'role': 'user',
            'content': user_message
        })

        # Run agent (continues conversation)
        result = await self.agent.run(user_message)

        return {
            'response': result.output,
            'conversation_length': len(self.agent.messages)
        }
```

### 4. Graph State Integration

Use GraphState to share data between agents and nodes:

```python
class StateAwareAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Read shared context from graph state
        shared_context = await context.graph_state.get('shared_context', {})
        user_message = context.inputs.content.get('message')

        # Build prompt with shared context
        prompt = f"Context: {shared_context}\n\nUser: {user_message}"

        result = await self.agent.run(prompt)

        # Update graph state with agent insights
        await context.graph_state.set('last_agent_response', result.output)

        return {'response': result.output}
```

## Capturing Agent Outputs

Agent outputs can be captured and routed to subsequent nodes in various ways:

### 1. Basic Output Routing

```python
class ProcessingNode(Node):
    async def process(self, context):
        # Get agent response from previous node
        agent_response = context.inputs.content.get('agent_response')

        # Process the agent's output
        processed = agent_response.upper()

        return {'processed_response': processed}

# Connect nodes
agent_node >> ProcessingNode()
```

### 2. Conditional Routing Based on Agent Output

```python
# Agent decides which path to take
success_node = SuccessNode()
retry_node = RetryNode()

agent_node.on(success=True) >> success_node
agent_node.on(success=False) >> retry_node
```

### 3. Extracting Structured Data

Agents with `output_mode='json'` can return structured data:

```python
class DataExtractorAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        text = context.inputs.content.get('text')

        # Agent extracts structured data
        result = await self.agent.run(
            f"Extract key information from: {text}"
        )

        # Result is already structured JSON
        return {
            'extracted_data': result.output,
            'success': True
        }

# Use extracted data in next node
class ValidatorNode(Node):
    async def process(self, context):
        data = context.inputs.content.get('extracted_data')

        # Validate extracted fields
        required_fields = ['name', 'email', 'phone']
        is_valid = all(field in data for field in required_fields)

        return {'valid': is_valid, 'data': data}

agent_node >> ValidatorNode()
```

## Multi-Agent Workflows

Combine multiple specialized agents in a single workflow:

### Sequential Agent Chain

```python
from spark.agents import Agent, AgentConfig, ReActStrategy
from spark.models.openai import OpenAIModel
from spark.tools.decorator import tool

# Define specialized tools
@tool
def research_topic(topic: str) -> str:
    """Research a topic."""
    return f"Research findings on {topic}"

@tool
def analyze_data(data: str) -> str:
    """Analyze data."""
    return f"Analysis of: {data}"

@tool
def generate_report(analysis: str) -> str:
    """Generate report."""
    return f"Report based on: {analysis}"

# Create specialized agents
model = OpenAIModel(model_id="gpt-4o")

research_agent = Agent(config=AgentConfig(
    model=model,
    tools=[research_topic],
    system_prompt="You are a research specialist.",
    name="Researcher"
))

analysis_agent = Agent(config=AgentConfig(
    model=model,
    tools=[analyze_data],
    system_prompt="You are a data analyst.",
    name="Analyst"
))

report_agent = Agent(config=AgentConfig(
    model=model,
    tools=[generate_report],
    system_prompt="You are a report writer.",
    name="Reporter"
))

# Create agent nodes
class ResearchNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = research_agent

    async def process(self, context):
        topic = context.inputs.content.get('topic')
        result = await self.agent.run(f"Research: {topic}")
        return {'research': result.output}

class AnalysisNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = analysis_agent

    async def process(self, context):
        research = context.inputs.content.get('research')
        result = await self.agent.run(f"Analyze: {research}")
        return {'analysis': result.output}

class ReportNode(Node):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = report_agent

    async def process(self, context):
        analysis = context.inputs.content.get('analysis')
        result = await self.agent.run(f"Generate report: {analysis}")
        return {'report': result.output}

# Build sequential agent workflow
research_node = ResearchNode(name="Research")
analysis_node = AnalysisNode(name="Analysis")
report_node = ReportNode(name="Report")

research_node >> analysis_node >> report_node

graph = Graph(start=research_node)
result = await graph.run({'topic': 'AI safety'})
```

### Parallel Agent Execution

Run multiple agents in parallel using graph state to aggregate results:

```python
class ParallelAgentNode(Node):
    """Agent node that stores results in graph state."""

    def __init__(self, agent: Agent, result_key: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.result_key = result_key

    async def process(self, context):
        query = context.inputs.content.get('query')
        result = await self.agent.run(query)

        # Store in graph state
        results = await context.graph_state.get('agent_results', {})
        results[self.result_key] = result.output
        await context.graph_state.set('agent_results', results)

        return {'completed': True}

class AggregatorNode(Node):
    """Aggregates results from parallel agents."""

    async def process(self, context):
        # Wait for all agents to complete
        results = await context.graph_state.get('agent_results', {})

        # Combine results
        combined = "\n\n".join(
            f"{key}: {value}"
            for key, value in results.items()
        )

        return {'aggregated_results': combined}

# Create parallel agents
agent1 = ParallelAgentNode(
    agent=research_agent,
    result_key='research',
    name="Agent1"
)
agent2 = ParallelAgentNode(
    agent=analysis_agent,
    result_key='analysis',
    name="Agent2"
)
agent3 = ParallelAgentNode(
    agent=report_agent,
    result_key='report',
    name="Agent3"
)

aggregator = AggregatorNode(name="Aggregator")

# All agents feed into aggregator
agent1 >> aggregator
agent2 >> aggregator
agent3 >> aggregator

graph = Graph(
    start=agent1,
    initial_state={'agent_results': {}}
)
```

## Agent Coordination via GraphState

Use GraphState for sophisticated agent coordination patterns:

### 1. Shared Knowledge Base

```python
class KnowledgeAgentNode(Node):
    """Agent that contributes to shared knowledge base."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Read existing knowledge
        knowledge_base = await context.graph_state.get('knowledge', [])

        # Provide context to agent
        context_str = "\n".join(knowledge_base)
        prompt = f"Existing knowledge:\n{context_str}\n\nNew query: {query}"

        result = await self.agent.run(prompt)

        # Add new knowledge
        knowledge_base.append(result.output)
        await context.graph_state.set('knowledge', knowledge_base)

        return {'response': result.output}
```

### 2. Agent Voting/Consensus

```python
class VotingAgentNode(Node):
    """Agent that votes on decisions."""

    def __init__(self, agent: Agent, agent_id: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.agent_id = agent_id

    async def process(self, context):
        proposal = context.inputs.content.get('proposal')

        # Agent evaluates proposal
        result = await self.agent.run(
            f"Vote YES or NO on: {proposal}\nProvide reasoning."
        )

        # Record vote
        votes = await context.graph_state.get('votes', {})
        votes[self.agent_id] = {
            'vote': 'YES' if 'yes' in result.output.lower() else 'NO',
            'reasoning': result.output
        }
        await context.graph_state.set('votes', votes)

        return {'voted': True}

class ConsensusNode(Node):
    """Determines consensus from agent votes."""

    async def process(self, context):
        votes = await context.graph_state.get('votes', {})

        yes_votes = sum(1 for v in votes.values() if v['vote'] == 'YES')
        no_votes = len(votes) - yes_votes

        consensus = yes_votes > no_votes

        return {
            'consensus': consensus,
            'yes_votes': yes_votes,
            'no_votes': no_votes,
            'details': votes
        }
```

### 3. Task Queue Pattern

```python
class TaskQueueAgentNode(Node):
    """Agent that processes tasks from a shared queue."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Get next task from queue
        async with context.graph_state.transaction() as state:
            task_queue = state.get('task_queue', [])
            if not task_queue:
                return {'status': 'no_tasks'}

            task = task_queue.pop(0)
            state['task_queue'] = task_queue

        # Process task with agent
        result = await self.agent.run(f"Process task: {task}")

        # Record completion
        completed = await context.graph_state.get('completed_tasks', [])
        completed.append({'task': task, 'result': result.output})
        await context.graph_state.set('completed_tasks', completed)

        return {'status': 'completed', 'task': task}
```

## Error Handling

Proper error handling ensures robust agent-based workflows:

### 1. Agent Error Recovery

```python
from spark.agents.types import AgentError, ToolExecutionError

class RobustAgentNode(Node):
    def __init__(self, agent: Agent, max_retries: int = 3, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.max_retries = max_retries

    async def process(self, context):
        query = context.inputs.content.get('query')

        for attempt in range(self.max_retries):
            try:
                result = await self.agent.run(query)
                return {
                    'response': result.output,
                    'success': True,
                    'attempts': attempt + 1
                }
            except ToolExecutionError as e:
                # Tool failed - log and retry
                print(f"Tool error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    return {
                        'error': str(e),
                        'success': False,
                        'attempts': attempt + 1
                    }
            except AgentError as e:
                # Agent-level error - may not be retryable
                return {
                    'error': str(e),
                    'success': False,
                    'attempts': attempt + 1
                }
```

### 2. Fallback Agent Pattern

```python
class PrimaryAgentNode(Node):
    async def process(self, context):
        try:
            result = await self.primary_agent.run(context.inputs.content['query'])
            return {'response': result.output, 'success': True}
        except Exception as e:
            return {'error': str(e), 'success': False}

class FallbackAgentNode(Node):
    async def process(self, context):
        # Simpler, more reliable agent
        result = await self.fallback_agent.run(context.inputs.content['query'])
        return {'response': result.output, 'fallback_used': True}

# Route based on success
primary = PrimaryAgentNode()
fallback = FallbackAgentNode()

primary.on(success=True) >> output_node
primary.on(success=False) >> fallback
fallback >> output_node
```

### 3. Telemetry for Debugging

```python
from spark.telemetry import TelemetryConfig

class InstrumentedAgentNode(Node):
    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        from spark.telemetry import TelemetryManager

        manager = TelemetryManager.get_instance()
        trace_id = context.metadata.get('trace_id')

        # Create custom span for agent execution
        async with manager.start_span(
            f"agent_{self.name}",
            trace_id,
            attributes={
                'agent_name': self.agent.config.name,
                'tools_count': len(self.agent.config.tools)
            }
        ) as span:
            try:
                result = await self.agent.run(context.inputs.content['query'])
                span.set_attribute('success', True)
                span.set_attribute('steps', result.steps)
                return {'response': result.output}
            except Exception as e:
                span.set_attribute('success', False)
                span.set_attribute('error', str(e))
                raise

# Enable telemetry on graph
telemetry_config = TelemetryConfig.create_sqlite(
    db_path="agent_telemetry.db",
    sampling_rate=1.0
)

graph = Graph(start=agent_node, telemetry_config=telemetry_config)
```

## Testing Agent-Based Graphs

Strategies for testing graphs that include agents:

### 1. Mock Agents for Unit Tests

```python
from spark.models.echo import EchoModel

class TestAgentNode:
    async def test_agent_node_processing(self):
        # Use EchoModel for deterministic testing
        config = AgentConfig(
            model=EchoModel(),
            name="TestAgent"
        )

        node = AgentNode(agent_config=config)
        context = ExecutionContext(
            inputs=NodeMessage(content={'query': 'test query'}),
            state={}
        )

        result = await node.process(context)

        assert result['success'] is True
        assert 'agent_response' in result
```

### 2. Integration Tests with Real Agents

```python
import pytest

@pytest.mark.asyncio
async def test_multi_agent_workflow():
    """Test complete multi-agent workflow."""

    # Use real models but with caching
    model = OpenAIModel(
        model_id="gpt-4o-mini",  # Cheaper model for testing
        enable_cache=True  # Cache responses
    )

    # Build workflow
    research_node = ResearchNode(model=model)
    analysis_node = AnalysisNode(model=model)

    research_node >> analysis_node

    graph = Graph(start=research_node)

    # Run workflow
    result = await graph.run({'topic': 'test topic'})

    # Verify
    assert 'analysis' in result.content
    assert result.content['analysis']  # Non-empty
```

### 3. Graph State Verification

```python
async def test_agent_coordination():
    """Test agents coordinate via graph state."""

    graph = Graph(
        start=agent1_node,
        initial_state={'shared_data': {}}
    )

    result = await graph.run({'query': 'test'})

    # Verify graph state was updated
    shared_data = graph.get_state_snapshot()['shared_data']
    assert 'agent1_result' in shared_data
    assert 'agent2_result' in shared_data
```

## Best Practices

1. **Clear Separation of Concerns**: Keep agent logic separate from workflow orchestration
2. **Use GraphState for Coordination**: Leverage graph state for agent-to-agent communication
3. **Error Recovery**: Implement retry logic and fallback patterns
4. **Telemetry**: Enable comprehensive observability for debugging
5. **Test with Mock Models**: Use EchoModel for fast, deterministic tests
6. **Cache Responses**: Enable caching during development to reduce costs
7. **Agent Specialization**: Create focused agents with specific tools and prompts
8. **Structured Outputs**: Use `output_mode='json'` for agents that produce data for other nodes

## Related Documentation

- [Multi-Agent Coordination](./multi-agent.md) - Advanced multi-agent patterns
- [Tools and Agents](./tools-agents.md) - Tool integration with agents
- [Agent System Reference](/docs/agents/fundamentals.md) - Core agent concepts
- [Graph State](/docs/graphs/graph-state.md) - Shared state management
- [Testing Strategies](/docs/best-practices/testing.md) - Testing approaches
