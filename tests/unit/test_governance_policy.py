"""Unit tests for the governance policy framework."""

from __future__ import annotations

import json

import pytest

from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.governance.policy import (
    PolicyConstraint,
    PolicyEffect,
    PolicyEngine,
    PolicyRequest,
    PolicyRule,
    PolicySet,
    PolicySubject,
    PolicyViolationError,
)
from spark.graphs.graph import Graph
from spark.models.echo import EchoModel
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext, NodeMessage
from spark.tools.decorator import tool


def test_policy_engine_constraint_matching():
    """Policies should evaluate constraint maps before defaulting to deny."""
    rule = PolicyRule(
        name='allow_us_only',
        effect=PolicyEffect.ALLOW,
        actions=['agent:tool_execute'],
        resources=['tool://s3.copy'],
        constraints=[PolicyConstraint(key='tool.arguments.region', equals='us-east-1')],
    )
    policy_set = PolicySet(name='copy', default_effect=PolicyEffect.DENY, rules=[rule])
    engine = PolicyEngine(policy_set)
    request = PolicyRequest(
        subject=PolicySubject(identifier='agent-123'),
        action='agent:tool_execute',
        resource='tool://s3.copy',
        context={'tool': {'arguments': {'region': 'us-east-1'}}},
    )
    decision = engine.evaluate(request)
    assert decision.effect == PolicyEffect.ALLOW

    request.context['tool']['arguments']['region'] = 'eu-west-1'
    decision = engine.evaluate(request)
    assert decision.effect == PolicyEffect.DENY


class SensitiveNode(Node):
    """Minimal node used to assert graph-level enforcement."""

    async def process(self, context: ExecutionContext) -> NodeMessage:
        return NodeMessage(content=context.inputs.content)


@pytest.mark.asyncio
async def test_graph_blocks_nodes_via_policy():
    """Graphs should enforce governance before running nodes."""
    rule = PolicyRule(
        name='block_sensitive',
        effect=PolicyEffect.DENY,
        actions=['node:execute'],
        resources=['graph://*/nodes/*'],
        constraints=[PolicyConstraint(key='node.type', equals='SensitiveNode')],
    )
    policy = PolicySet(default_effect=PolicyEffect.ALLOW, rules=[rule])
    graph = Graph(start=SensitiveNode(), policy_set=policy)

    with pytest.raises(PolicyViolationError):
        await graph.run({'value': 1})

    events = await graph.state.get('policy_events', [])
    assert any(event['decision'] == 'deny' and event['action'] == 'node:execute' for event in events)


@tool
def sample_region_tool(region: str) -> str:
    """Echo the selected region."""

    return region


@pytest.mark.asyncio
async def test_agent_tool_policy_blocks_execution():
    """Agents should consult policy engine before tool execution."""
    rule = PolicyRule(
        name='deny_eu_region',
        effect=PolicyEffect.DENY,
        actions=['agent:tool_execute'],
        resources=['tool://sample_region_tool'],
        constraints=[PolicyConstraint(key='tool.arguments.region', equals='eu-west-1')],
    )
    config = AgentConfig(
        model=EchoModel(),
        tools=[sample_region_tool],
        policy_set=PolicySet(default_effect=PolicyEffect.ALLOW, rules=[rule]),
    )
    agent = Agent(config=config)
    context = agent._prepare_context(NodeMessage(content={}))

    tool_call = {
        'id': 'call-1',
        'function': {
            'name': 'sample_region_tool',
            'arguments': json.dumps({'region': 'eu-west-1'}),
        },
    }

    with pytest.raises(PolicyViolationError):
        await agent._execute_tool_calls([tool_call], context)
