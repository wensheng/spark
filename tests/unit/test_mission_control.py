"""Tests for MissionControl plan telemetry and guardrails."""

from __future__ import annotations

import asyncio

import pytest

from spark.graphs import Graph, MissionControl, MissionPlan, PlanStep, BudgetGuardrail, BudgetGuardrailConfig
from spark.graphs.mission_control import PlanAdaptiveContext
from spark.nodes.nodes import Node


class EchoNode(Node):
    async def process(self, context):  # type: ignore[override]
        count = context.inputs.content.get('count', 0)
        return {'count': count + 1}


@pytest.mark.asyncio
async def test_plan_manager_telemetry_and_adaptive():
    start = EchoNode()
    graph = Graph(start=start, initial_state={'count': 0})
    plan = MissionPlan([PlanStep(id='step-1', description='Increment')])
    events: list[tuple[str, str]] = []

    async def adaptive_hook(ctx: PlanAdaptiveContext):
        events.append((ctx.event, ctx.step.id))

    mission_control = MissionControl(
        plan=plan,
        plan_telemetry_topic='mission.plan',
        plan_adaptive_hook=adaptive_hook,
    )
    mission_control.attach(graph)
    subscription = await graph.event_bus.subscribe('mission.plan')

    await graph.run({'count': 0})

    final_status = None
    for _ in range(3):
        message = await asyncio.wait_for(subscription.receive(), timeout=1)
        final_status = message.payload['plan'][0]['status']
        if final_status == 'completed':
            break
    assert final_status in {'pending', 'in_progress', 'completed'}
    assert ('step_started', 'step-1') in events
    assert ('step_completed', 'step-1') in events
    snapshot = await graph.state.get('mission_plan')
    assert snapshot[-1]['status'] == 'completed'


@pytest.mark.asyncio
async def test_budget_guardrail_persists_state():
    start = EchoNode()
    graph = Graph(start=start, initial_state={'count': 0})
    guardrail = BudgetGuardrail(BudgetGuardrailConfig(max_iterations=5, max_runtime_seconds=10))
    MissionControl(plan=None, guardrails=[guardrail]).attach(graph)
    await graph.run({'count': 0})
    budget_state = await graph.state.get('guardrail_budget')
    assert budget_state['iteration_count'] >= 0
    assert budget_state['max_iterations'] == 5
