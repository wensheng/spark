"""Tests for mission templates wiring workspaces."""

import pytest

from spark.graphs import spae_template, WorkspacePolicy
from spark.nodes import Node
from spark.nodes.types import ExecutionContext


class NullNode(Node):
    async def process(self, context: ExecutionContext):
        return {'ok': True}


def build_chain():
    sense = NullNode()
    plan = NullNode()
    act = NullNode()
    evaluate = NullNode()
    return sense, plan, act, evaluate


@pytest.mark.asyncio
async def test_spae_template_accepts_workspace(tmp_path):
    sense, plan, act, evaluate = build_chain()
    workspace_root = tmp_path / 'mission'
    graph = spae_template(
        sense=sense,
        plan=plan,
        act=act,
        evaluate=evaluate,
        workspace_config={'root': workspace_root, 'policy': {'cleanup_on_success': False}},
    )
    await graph.run()
    state_workspace = await graph.get_state('workspace')
    assert state_workspace['root'] == str(workspace_root)


@pytest.mark.asyncio
async def test_spae_template_workspace_cleanup(tmp_path):
    sense, plan, act, evaluate = build_chain()
    workspace_root = tmp_path / 'mission'
    graph = spae_template(
        sense=sense,
        plan=plan,
        act=act,
        evaluate=evaluate,
        workspace_config={'root': workspace_root, 'policy': {'cleanup_on_success': True}},
    )
    await graph.run()
    assert not workspace_root.exists()
