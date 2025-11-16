"""Unit tests for the governance policy framework."""

from __future__ import annotations

import json

import pytest

from spark.agents.agent import Agent
from spark.agents.config import AgentConfig
from spark.governance.approval import ApprovalPendingError, ApprovalStatus
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
from spark.graphs.graph_state import GraphState
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


@pytest.mark.asyncio
async def test_graph_policy_requires_approval_records_request():
    """Graphs should surface approval requests and persist them."""
    rule = PolicyRule(
        name='pause_sensitive',
        effect=PolicyEffect.REQUIRE_APPROVAL,
        actions=['node:execute'],
        resources=['graph://*/nodes/*'],
        constraints=[PolicyConstraint(key='node.type', equals='SensitiveNode')],
    )
    policy = PolicySet(default_effect=PolicyEffect.ALLOW, rules=[rule])
    graph = Graph(start=SensitiveNode(), policy_set=policy)

    with pytest.raises(ApprovalPendingError) as excinfo:
        await graph.run({'value': 1})

    approval = excinfo.value.approval
    assert approval.status is ApprovalStatus.PENDING
    stored = await graph.state.get('approval_requests', [])
    assert len(stored) == 1
    assert stored[0]['approval_id'] == approval.approval_id
    assert stored[0]['status'] == ApprovalStatus.PENDING.value


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


@pytest.mark.asyncio
async def test_agent_tool_policy_requires_approval():
    """Agents should log approval requests when policy asks for review."""
    rule = PolicyRule(
        name='require_review',
        effect=PolicyEffect.REQUIRE_APPROVAL,
        actions=['agent:tool_execute'],
        resources=['tool://sample_region_tool'],
    )
    config = AgentConfig(
        model=EchoModel(),
        tools=[sample_region_tool],
        policy_set=PolicySet(default_effect=PolicyEffect.ALLOW, rules=[rule]),
    )
    agent = Agent(config=config)
    context = agent._prepare_context(NodeMessage(content={}))
    context.graph_state = GraphState()
    await context.graph_state.initialize()

    tool_call = {
        'id': 'call-approval',
        'function': {
            'name': 'sample_region_tool',
            'arguments': json.dumps({'region': 'us-east-1'}),
        },
    }

    with pytest.raises(ApprovalPendingError):
        await agent._execute_tool_calls([tool_call], context)

    requests = await context.graph_state.get('approval_requests', [])
    assert len(requests) == 1
    assert requests[0]['status'] == ApprovalStatus.PENDING.value
