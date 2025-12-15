---
title: Multi-Agent Coordination
parent: Integration
nav_order: 1
---
# Multi-Agent Coordination
---

This guide covers advanced patterns for coordinating multiple AI agents within Spark workflows, enabling sophisticated multi-agent systems with specialization, collaboration, and consensus mechanisms.

## Table of Contents

- [Overview](#overview)
- [Specialization Patterns](#specialization-patterns)
- [Sequential Agent Workflows](#sequential-agent-workflows)
- [Parallel Agent Execution](#parallel-agent-execution)
- [Hierarchical Agents](#hierarchical-agents)
- [Consensus Mechanisms](#consensus-mechanisms)
- [Shared Memory via GraphState](#shared-memory-via-graphstate)
- [Agent Communication Patterns](#agent-communication-patterns)

## Overview

Multi-agent systems decompose complex problems into specialized sub-tasks, with each agent responsible for specific capabilities. Spark's graph architecture provides natural support for multi-agent coordination through:

- **GraphState**: Shared memory for agent coordination
- **Edge Conditions**: Dynamic routing between agents
- **Event Bus**: Agent-to-agent messaging
- **Telemetry**: Observability into multi-agent execution

## Specialization Patterns

Create specialized agents for different aspects of problem-solving:

### Domain Specialization

```python
from spark.agents import Agent, AgentConfig
from spark.models.openai import OpenAIModel
from spark.nodes import Node
from spark.tools.decorator import tool

# Domain-specific tools
@tool
def query_customer_db(customer_id: str) -> dict:
    """Query customer database."""
    return {'id': customer_id, 'status': 'active', 'tier': 'premium'}

@tool
def query_order_db(order_id: str) -> dict:
    """Query order database."""
    return {'id': order_id, 'status': 'shipped', 'items': 3}

@tool
def query_inventory_db(sku: str) -> dict:
    """Query inventory database."""
    return {'sku': sku, 'available': 42, 'warehouse': 'US-WEST'}

# Create specialized agents
model = OpenAIModel(model_id="gpt-5-mini")

customer_agent = Agent(config=AgentConfig(
    model=model,
    tools=[query_customer_db],
    system_prompt="""You are a customer service specialist.
    You can look up customer information and history.
    Be helpful and professional.""",
    name="CustomerAgent"
))

order_agent = Agent(config=AgentConfig(
    model=model,
    tools=[query_order_db],
    system_prompt="""You are an order management specialist.
    You can look up order status and details.
    Provide accurate order information.""",
    name="OrderAgent"
))

inventory_agent = Agent(config=AgentConfig(
    model=model,
    tools=[query_inventory_db],
    system_prompt="""You are an inventory specialist.
    You can check product availability and locations.
    Provide real-time inventory data.""",
    name="InventoryAgent"
))
```

### Capability Specialization

```python
from spark.agents import ReActStrategy, ChainOfThoughtStrategy

# Research specialist with ReAct strategy
researcher = Agent(config=AgentConfig(
    model=model,
    tools=[search_tool, summarize_tool],
    reasoning_strategy=ReActStrategy(),
    system_prompt="You research topics thoroughly using available tools.",
    name="Researcher"
))

# Analyst with chain-of-thought reasoning
analyst = Agent(config=AgentConfig(
    model=model,
    tools=[calculate_tool, visualize_tool],
    reasoning_strategy=ChainOfThoughtStrategy(),
    system_prompt="You analyze data methodically, step by step.",
    name="Analyst"
))

# Writer with no reasoning overhead
writer = Agent(config=AgentConfig(
    model=model,
    system_prompt="You write clear, concise reports.",
    name="Writer"
))
```

## Sequential Agent Workflows

Chain agents together for multi-stage processing:

### Linear Agent Pipeline

```python
from spark.graphs import Graph

class SpecializedAgentNode(Node):
    """Wrapper for specialized agents."""

    def __init__(self, agent: Agent, input_key: str, output_key: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.input_key = input_key
        self.output_key = output_key

    async def process(self, context):
        # Get input
        input_data = context.inputs.content.get(self.input_key, '')

        # Run agent
        result = await self.agent.run(input_data)

        # Return with specific output key
        return {
            self.output_key: result.output,
            'agent_name': self.agent.config.name,
            'steps': result.steps
        }

# Build pipeline
research_node = SpecializedAgentNode(
    agent=researcher,
    input_key='topic',
    output_key='research_findings',
    name="ResearchStage"
)

analysis_node = SpecializedAgentNode(
    agent=analyst,
    input_key='research_findings',
    output_key='analysis_report',
    name="AnalysisStage"
)

writing_node = SpecializedAgentNode(
    agent=writer,
    input_key='analysis_report',
    output_key='final_document',
    name="WritingStage"
)

# Connect pipeline
research_node >> analysis_node >> writing_node

graph = Graph(start=research_node)

# Execute
result = await graph.run({'topic': 'AI safety in autonomous vehicles'})
final_doc = result.content['final_document']
```

### Context-Enriching Pipeline

Each agent adds to the context for the next agent:

```python
class ContextEnrichingAgentNode(Node):
    """Agent that enriches shared context."""

    def __init__(self, agent: Agent, contribution_key: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.contribution_key = contribution_key

    async def process(self, context):
        # Read accumulated context
        accumulated = await context.graph_state.get('accumulated_context', {})

        # Build prompt with all previous context
        context_summary = "\n\n".join(
            f"{key}: {value}"
            for key, value in accumulated.items()
        )

        query = context.inputs.content.get('query', '')
        prompt = f"Previous context:\n{context_summary}\n\nTask: {query}"

        # Run agent
        result = await self.agent.run(prompt)

        # Add contribution to context
        accumulated[self.contribution_key] = result.output
        await context.graph_state.set('accumulated_context', accumulated)

        return {
            'contribution': result.output,
            'continue': True
        }

# Build enriching pipeline
node1 = ContextEnrichingAgentNode(
    agent=researcher,
    contribution_key='research',
    name="Research"
)
node2 = ContextEnrichingAgentNode(
    agent=analyst,
    contribution_key='analysis',
    name="Analysis"
)
node3 = ContextEnrichingAgentNode(
    agent=writer,
    contribution_key='document',
    name="Writing"
)

node1 >> node2 >> node3

graph = Graph(
    start=node1,
    initial_state={'accumulated_context': {}}
)
```

## Parallel Agent Execution

Execute multiple agents concurrently for improved performance:

### Fan-Out Pattern

```python
class ParallelAgentNode(Node):
    """Agent that executes in parallel with others."""

    def __init__(self, agent: Agent, result_key: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.result_key = result_key

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Each agent processes independently
        result = await self.agent.run(query)

        # Store result in graph state
        async with context.graph_state.transaction() as state:
            results = state.get('parallel_results', {})
            results[self.result_key] = {
                'output': result.output,
                'steps': result.steps,
                'agent': self.agent.config.name
            }
            state['parallel_results'] = results

        return {'completed': True}

# Create parallel agents
agent1 = ParallelAgentNode(
    agent=customer_agent,
    result_key='customer_info',
    name="CustomerLookup"
)
agent2 = ParallelAgentNode(
    agent=order_agent,
    result_key='order_info',
    name="OrderLookup"
)
agent3 = ParallelAgentNode(
    agent=inventory_agent,
    result_key='inventory_info',
    name="InventoryLookup"
)

# All agents can run in parallel (no dependencies)
# They all write to graph state
```

### Fan-In Aggregation

```python
class AggregatorNode(Node):
    """Aggregates results from multiple parallel agents."""

    def __init__(self, synthesizer_agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.synthesizer = synthesizer_agent

    async def process(self, context):
        # Wait for all parallel agents to complete
        parallel_results = await context.graph_state.get('parallel_results', {})

        # Build comprehensive context
        context_parts = []
        for key, result in parallel_results.items():
            context_parts.append(f"{key}:\n{result['output']}")

        combined_context = "\n\n".join(context_parts)

        # Synthesizer agent creates unified response
        synthesis = await self.synthesizer.run(
            f"Synthesize the following information into a coherent response:\n\n{combined_context}"
        )

        return {
            'synthesized_response': synthesis.output,
            'sources': list(parallel_results.keys())
        }

# Create synthesizer
synthesizer_agent = Agent(config=AgentConfig(
    model=model,
    system_prompt="You synthesize information from multiple sources into clear, coherent responses.",
    name="Synthesizer"
))

aggregator = AggregatorNode(
    synthesizer_agent=synthesizer_agent,
    name="Aggregator"
)

# Connect parallel agents to aggregator
agent1 >> aggregator
agent2 >> aggregator
agent3 >> aggregator

graph = Graph(
    start=agent1,
    initial_state={'parallel_results': {}}
)
```

## Hierarchical Agents

Implement supervisor-worker patterns for task delegation:

### Supervisor-Worker Pattern

{% raw %}
```python
class SupervisorNode(Node):
    """Supervisor agent that delegates tasks."""

    def __init__(self, supervisor_agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.supervisor = supervisor_agent

    async def process(self, context):
        request = context.inputs.content.get('request')

        # Supervisor analyzes request and creates task breakdown
        plan = await self.supervisor.run(
            f"""Analyze this request and break it into sub-tasks:
            {request}

            Respond with JSON:
            {{
                "tasks": [
                    {{"type": "research", "description": "..."}},
                    {{"type": "analysis", "description": "..."}},
                    {{"type": "writing", "description": "..."}}
                ]
            }}
            """
        )

        # Store task queue in graph state
        await context.graph_state.set('task_queue', plan.output['tasks'])
        await context.graph_state.set('completed_tasks', [])

        return {'plan_created': True, 'task_count': len(plan.output['tasks'])}

class WorkerNode(Node):
    """Worker agent that processes tasks from queue."""

    def __init__(self, worker_agent: Agent, task_type: str, **kwargs):
        super().__init__(**kwargs)
        self.worker = worker_agent
        self.task_type = task_type

    async def process(self, context):
        # Get tasks for this worker type
        async with context.graph_state.transaction() as state:
            task_queue = state.get('task_queue', [])
            my_tasks = [t for t in task_queue if t['type'] == self.task_type]

            if not my_tasks:
                return {'status': 'no_tasks'}

            # Take first matching task
            task = my_tasks[0]
            task_queue.remove(task)
            state['task_queue'] = task_queue

        # Process task
        result = await self.worker.run(task['description'])

        # Record completion
        async with context.graph_state.transaction() as state:
            completed = state.get('completed_tasks', [])
            completed.append({
                'type': task['type'],
                'description': task['description'],
                'result': result.output
            })
            state['completed_tasks'] = completed

        return {'status': 'completed', 'task_type': self.task_type}

class ReviewNode(Node):
    """Supervisor reviews completed work."""

    def __init__(self, supervisor_agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.supervisor = supervisor_agent

    async def process(self, context):
        completed = await context.graph_state.get('completed_tasks', [])

        # Supervisor reviews and synthesizes
        review_context = "\n\n".join(
            f"{task['type']}: {task['result']}"
            for task in completed
        )

        final_result = await self.supervisor.run(
            f"Review and synthesize these completed tasks:\n\n{review_context}"
        )

        return {
            'final_result': final_result.output,
            'tasks_completed': len(completed)
        }

# Build hierarchical workflow
supervisor_config = AgentConfig(
    model=model,
    system_prompt="You are a project supervisor. Break down complex requests and review final results.",
    output_mode='json',
    name="Supervisor"
)

supervisor = SupervisorNode(
    supervisor_agent=Agent(config=supervisor_config),
    name="Supervisor"
)

research_worker = WorkerNode(
    worker_agent=researcher,
    task_type='research',
    name="ResearchWorker"
)

analysis_worker = WorkerNode(
    worker_agent=analyst,
    task_type='analysis',
    name="AnalysisWorker"
)

review = ReviewNode(
    supervisor_agent=Agent(config=supervisor_config),
    name="Review"
)

# Flow: Supervisor -> Workers (parallel) -> Review
supervisor >> research_worker >> review
supervisor >> analysis_worker >> review
```
{% endraw %}

## Consensus Mechanisms

Implement voting and consensus for critical decisions:

### Simple Majority Voting

{% raw %}
```python
class VotingAgentNode(Node):
    """Agent that casts a vote."""

    def __init__(self, agent: Agent, voter_id: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.voter_id = voter_id

    async def process(self, context):
        proposal = context.inputs.content.get('proposal')

        # Agent evaluates and votes
        result = await self.agent.run(
            f"""Evaluate this proposal and vote YES or NO:
            {proposal}

            Provide your vote and detailed reasoning in JSON format:
            {{
                "vote": "YES" or "NO",
                "confidence": 0.0 to 1.0,
                "reasoning": "detailed explanation"
            }}
            """
        )

        # Record vote
        async with context.graph_state.transaction() as state:
            votes = state.get('votes', {})
            votes[self.voter_id] = result.output
            state['votes'] = votes

        return {'voted': True}

class ConsensusNode(Node):
    """Determines consensus from votes."""

    def __init__(self, threshold: float = 0.5, **kwargs):
        super().__init__(**kwargs)
        self.threshold = threshold

    async def process(self, context):
        votes = await context.graph_state.get('votes', {})

        if not votes:
            return {'consensus_reached': False, 'reason': 'no_votes'}

        # Count votes
        yes_votes = sum(1 for v in votes.values() if v['vote'] == 'YES')
        total_votes = len(votes)
        yes_ratio = yes_votes / total_votes

        # Calculate weighted consensus (considering confidence)
        weighted_yes = sum(
            v['confidence'] if v['vote'] == 'YES' else 0
            for v in votes.values()
        )
        weighted_total = sum(v['confidence'] for v in votes.values())
        weighted_ratio = weighted_yes / weighted_total if weighted_total > 0 else 0

        consensus = weighted_ratio >= self.threshold

        return {
            'consensus_reached': consensus,
            'yes_votes': yes_votes,
            'total_votes': total_votes,
            'yes_ratio': yes_ratio,
            'weighted_ratio': weighted_ratio,
            'vote_details': votes
        }

# Build voting workflow
voter1 = VotingAgentNode(agent=agent1, voter_id='agent1')
voter2 = VotingAgentNode(agent=agent2, voter_id='agent2')
voter3 = VotingAgentNode(agent=agent3, voter_id='agent3')
consensus = ConsensusNode(threshold=0.6)

# All voters feed into consensus
voter1 >> consensus
voter2 >> consensus
voter3 >> consensus

graph = Graph(start=voter1, initial_state={'votes': {}})
```
{% endraw %}

### Iterative Consensus

```python
class DebateRoundNode(Node):
    """One round of debate between agents."""

    def __init__(self, agents: list[Agent], round_num: int, **kwargs):
        super().__init__(**kwargs)
        self.agents = agents
        self.round_num = round_num

    async def process(self, context):
        proposal = context.inputs.content.get('proposal')

        # Get previous debate history
        debate_history = await context.graph_state.get('debate_history', [])

        # Build context from previous rounds
        history_str = "\n\n".join(
            f"Round {i+1}: {round_info}"
            for i, round_info in enumerate(debate_history)
        )

        # Each agent contributes
        round_responses = {}
        for agent in self.agents:
            prompt = f"""Debate proposal: {proposal}

Previous discussion:
{history_str}

Provide your current position and reasoning."""

            result = await agent.run(prompt)
            round_responses[agent.config.name] = result.output

        # Update debate history
        debate_history.append({
            'round': self.round_num,
            'responses': round_responses
        })
        await context.graph_state.set('debate_history', debate_history)

        # Check for convergence
        positions = [r.lower() for r in round_responses.values()]
        agreement = all('agree' in p or 'yes' in p for p in positions)

        return {
            'round_complete': True,
            'agreement_reached': agreement,
            'continue_debate': not agreement
        }

# Build iterative debate
round1 = DebateRoundNode(agents=[agent1, agent2, agent3], round_num=1, name="Round1")
round2 = DebateRoundNode(agents=[agent1, agent2, agent3], round_num=2, name="Round2")
round3 = DebateRoundNode(agents=[agent1, agent2, agent3], round_num=3, name="Round3")
final_decision = FinalDecisionNode()

# Loop until agreement or max rounds
round1.on(agreement_reached=True) >> final_decision
round1.on(agreement_reached=False) >> round2

round2.on(agreement_reached=True) >> final_decision
round2.on(agreement_reached=False) >> round3

round3 >> final_decision  # Max 3 rounds
```

## Shared Memory via GraphState

Advanced GraphState patterns for agent coordination:

### Shared Knowledge Graph

{% raw %}
```python
class KnowledgeContributorNode(Node):
    """Agent contributes facts to shared knowledge graph."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Read knowledge graph
        knowledge_graph = await context.graph_state.get('knowledge_graph', {
            'entities': {},
            'relationships': []
        })

        # Agent extracts knowledge
        result = await self.agent.run(
            f"""Extract structured knowledge from this query: {query}

            Return JSON with:
            {{
                "entities": [{{"name": "...", "type": "...", "properties": {{}}}}],
                "relationships": [{{"source": "...", "target": "...", "type": "..."}}]
            }}
            """
        )

        # Merge into knowledge graph
        for entity in result.output['entities']:
            knowledge_graph['entities'][entity['name']] = entity

        knowledge_graph['relationships'].extend(result.output['relationships'])

        await context.graph_state.set('knowledge_graph', knowledge_graph)

        return {'knowledge_added': True}

class KnowledgeQueryNode(Node):
    """Agent queries shared knowledge graph."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Read knowledge graph
        knowledge_graph = await context.graph_state.get('knowledge_graph', {})

        # Provide knowledge to agent
        kg_summary = f"""
        Entities: {len(knowledge_graph.get('entities', {}))}
        Relationships: {len(knowledge_graph.get('relationships', []))}

        Knowledge graph:
        {json.dumps(knowledge_graph, indent=2)}
        """

        result = await self.agent.run(
            f"Using this knowledge graph:\n{kg_summary}\n\nAnswer: {query}"
        )

        return {'answer': result.output}
```
{% endraw %}

### Blackboard Pattern

{% raw %}
```python
class BlackboardWriterNode(Node):
    """Agent writes hypotheses to blackboard."""

    def __init__(self, agent: Agent, hypothesis_type: str, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self.hypothesis_type = hypothesis_type

    async def process(self, context):
        problem = context.inputs.content.get('problem')

        # Read current blackboard state
        blackboard = await context.graph_state.get('blackboard', {
            'problem': problem,
            'hypotheses': [],
            'evidence': []
        })

        # Agent generates hypothesis
        result = await self.agent.run(
            f"Analyze this problem and generate a {self.hypothesis_type} hypothesis:\n{problem}"
        )

        # Write to blackboard
        blackboard['hypotheses'].append({
            'type': self.hypothesis_type,
            'content': result.output,
            'agent': self.agent.config.name,
            'timestamp': datetime.now().isoformat()
        })

        await context.graph_state.set('blackboard', blackboard)

        return {'hypothesis_added': True}

class BlackboardEvaluatorNode(Node):
    """Agent evaluates hypotheses on blackboard."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Read all hypotheses
        blackboard = await context.graph_state.get('blackboard', {})
        hypotheses = blackboard.get('hypotheses', [])

        # Agent evaluates and ranks
        hypotheses_str = "\n\n".join(
            f"{i+1}. {h['type']}: {h['content']}"
            for i, h in enumerate(hypotheses)
        )

        result = await self.agent.run(
            f"""Evaluate these hypotheses and select the most promising:
            {hypotheses_str}

            Return JSON with:
            {{
                "selected_index": 0,
                "reasoning": "why this hypothesis is most promising"
            }}
            """
        )

        return {
            'selected_hypothesis': hypotheses[result.output['selected_index']],
            'reasoning': result.output['reasoning']
        }
```
{% endraw %}

## Agent Communication Patterns

Direct agent-to-agent messaging via event bus:

### Message Passing

```python
class MessageSendingAgentNode(Node):
    """Agent that sends messages to other agents."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        query = context.inputs.content.get('query')

        # Process query
        result = await self.agent.run(query)

        # Send message to other agents via graph state
        messages = await context.graph_state.get('agent_messages', [])
        messages.append({
            'from': self.agent.config.name,
            'content': result.output,
            'timestamp': datetime.now().isoformat()
        })
        await context.graph_state.set('agent_messages', messages)

        return {'message_sent': True}

class MessageReceivingAgentNode(Node):
    """Agent that receives and responds to messages."""

    def __init__(self, agent: Agent, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent

    async def process(self, context):
        # Get messages
        messages = await context.graph_state.get('agent_messages', [])

        # Build conversation context
        conversation = "\n".join(
            f"{msg['from']}: {msg['content']}"
            for msg in messages
        )

        # Agent responds
        result = await self.agent.run(
            f"Conversation history:\n{conversation}\n\nYour response:"
        )

        # Add response to messages
        messages.append({
            'from': self.agent.config.name,
            'content': result.output,
            'timestamp': datetime.now().isoformat()
        })
        await context.graph_state.set('agent_messages', messages)

        return {'response_sent': True}
```

## Best Practices

1. **Clear Specialization**: Give each agent a well-defined role and responsibilities
2. **Explicit Communication**: Use GraphState for structured agent coordination
3. **Timeout Handling**: Set timeouts for agent operations to prevent deadlocks
4. **Cost Tracking**: Monitor total costs across all agents
5. **Telemetry**: Track each agent's performance and decision-making
6. **Graceful Degradation**: Handle agent failures without breaking the workflow
7. **Testing Strategies**: Test each agent individually before integration
8. **State Transactions**: Use transactions for atomic multi-agent state updates

## Related Documentation

- [Agents in Graphs](./agents-in-graphs.md) - Basic agent integration
- [Graph State](/docs/graphs/graph-state.md) - Shared state management
- [Agent System Reference](/docs/agents/fundamentals.md) - Core agent concepts
- [Telemetry and RSI](./telemetry-rsi.md) - Monitoring multi-agent systems
