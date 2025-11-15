import pytest

from spark.graphs import GraphState, spae_template, MissionControl, MissionPlan, PlanStep
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext, NodeMessage


class SenseNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        await context.graph_state.set('observations', ['data'])
        return NodeMessage(content={'stage': 'sense'}, metadata={})


class PlanNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        plan = ['step1', 'step2']
        await context.graph_state.set('plan', plan)
        return NodeMessage(content={'plan': plan}, metadata={})


class ActNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        actions = ['run-tool']
        await context.graph_state.set('actions', actions)
        return NodeMessage(content={'actions': actions}, metadata={})


class EvaluateNode(Node):
    async def process(self, context: ExecutionContext) -> NodeMessage:
        return NodeMessage(content={'status': 'done'}, metadata={})


@pytest.mark.asyncio
async def test_spae_template_attach_plan_and_runs():
    graph = spae_template(
        SenseNode(id='sense'),
        PlanNode(id='plan'),
        ActNode(id='act'),
        EvaluateNode(id='evaluate'),
        initial_state={'counter': 0},
        plan_steps=("Sense signals", "Plan response", "Execute", "Evaluate"),
    )

    result = await graph.run()
    assert result.content['status'] == 'done'
    plan_snapshot = await graph.state.get('mission_plan')
    assert len(plan_snapshot) == 4
    assert plan_snapshot[-1]['status'] in {'completed', 'in_progress'}
