"""Tests for workspace abstraction."""

import asyncio
from pathlib import Path
import pytest

from spark.graphs.workspace import Workspace, WorkspaceMount, WorkspaceSecrets, WorkspaceManager
from spark.graphs import Graph
from spark.nodes import Node
from spark.nodes.types import ExecutionContext


def test_workspace_environment_and_mounts(tmp_path):
    root = tmp_path / 'workspace'
    mount = WorkspaceMount(name='cache', path=root / 'cache', read_only=False)
    secrets = WorkspaceSecrets(values={'API_KEY': '123'})
    workspace = Workspace(root=root, mounts=[mount], secrets=secrets, env={'MODE': 'test'})

    env = workspace.environment()
    assert env['API_KEY'] == '123'
    assert env['MODE'] == 'test'


def test_workspace_manager_creates_instances(tmp_path):
    manager = WorkspaceManager()
    workspace = manager.create(root=tmp_path / 'ws')
    assert isinstance(workspace, Workspace)
    assert workspace.root.exists() is False


@pytest.mark.asyncio
async def test_workspace_ensure_directories(tmp_path):
    root = tmp_path / 'ws'
    mount = WorkspaceMount(name='cache', path=root / 'cache')
    workspace = Workspace(root=root, mounts=[mount])
    await workspace.ensure_directories()
    assert root.exists()
    assert (root / 'cache').exists()


@pytest.mark.asyncio
async def test_graph_injects_workspace(tmp_path):
    class EchoNode(Node):
        async def process(self, context: ExecutionContext):
            return {'ok': True}

    node = EchoNode()
    workspace_root = tmp_path / 'mission'
    mount = WorkspaceMount(name='cache', path=workspace_root / 'cache')
    workspace = Workspace(root=workspace_root, mounts=[mount])
    graph = Graph(start=node, workspace=workspace)
    await graph.run()
    assert workspace_root.exists()
    state_workspace = await graph.get_state('workspace')
    assert state_workspace['root'] == str(workspace_root)
