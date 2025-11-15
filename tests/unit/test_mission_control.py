"""Tests for mission control plan/guardrail layer."""

import pytest

from spark.graphs import (
    Graph,
    MissionControl,
    MissionPlan,
    PlanStep,
    PlanStepStatus,
    BudgetGuardrail,
    BudgetGuardrailConfig,
    GuardrailBreachError,
)
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext


class IncrementNode(Node):
    """Simple node that increments a counter."""

    async def process(self, context: ExecutionContext):
        payload = context.inputs.content or {}
        count = payload.get('count', 0)
        return {'count': count + 1}


@pytest.mark.asyncio
async def test_plan_manager_auto_progress():
    """Plan manager should update statuses via lifecycle hooks."""
    plan = MissionPlan(
        steps=[
            PlanStep(id="collect", description="Collect requirements"),
            PlanStep(id="build", description="Build solution", depends_on=["collect"]),
        ]
    )
    mission = MissionControl(plan=plan)
    graph = Graph(start=IncrementNode(), mission_control=mission)

    result = await graph.run({'count': 0})
    assert result.content['count'] == 1
    assert plan.steps[0].status == PlanStepStatus.COMPLETED
    assert plan.steps[1].status == PlanStepStatus.PENDING

    stored_plan = await graph.get_state('mission_plan', default=[])
    assert len(stored_plan) == 2
    assert stored_plan[0]['status'] == PlanStepStatus.COMPLETED.value
    assert stored_plan[1]['status'] == PlanStepStatus.PENDING.value


@pytest.mark.asyncio
async def test_budget_guardrail_enforces_iteration_limits():
    """Budget guardrail should stop graphs that exceed iteration budgets."""
    guardrail = BudgetGuardrail(BudgetGuardrailConfig(max_iterations=0))
    mission = MissionControl(guardrails=[guardrail])
    graph = Graph(start=IncrementNode(), mission_control=mission)

    with pytest.raises(GuardrailBreachError):
        await graph.run({'count': 0})
