from typing import Any

import pytest

from spark.core.message import Message
from spark.system.syndicate import Syndicate
from spark.workflow import Chain, Node, Workflow


class PrefixNode(Node):
    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def process(self, message: Message) -> str:
        return f"{self.prefix}:{message.content}"


class IdentityNode(Node):
    def process(self, message: Message) -> Any:
        return message.content


@pytest.mark.asyncio
async def test_workflow_run_requires_explicit_system_or_start() -> None:
    workflow = Workflow(start=IdentityNode())

    with pytest.raises(RuntimeError, match="explicit Syndicate"):
        await workflow.run("spark")


@pytest.mark.asyncio
async def test_workflow_run_starts_nodes_with_explicit_system() -> None:
    source = PrefixNode("source")
    target = PrefixNode("target")
    source >> target
    workflow = Workflow(start=source, initial_state={"seed": "value"})

    async with Syndicate("workflow-run") as system:
        result = await workflow.run("spark", system=system, timeout=1.0)
        assert await workflow.state.get("seed") == "value"
        await workflow.shutdown()

    assert result == "target:source:spark"
    assert not workflow.started


@pytest.mark.asyncio
async def test_workflow_start_then_run_reuses_system() -> None:
    source = PrefixNode("source")
    target = PrefixNode("target")
    source >> target
    workflow = Workflow(start=source)

    async with Syndicate("workflow-start-run") as system:
        await workflow.start(system)
        result = await workflow.run("spark", timeout=1.0)
        await workflow.shutdown()

    assert result == "target:source:spark"


def test_workflow_from_chain_keeps_chain_type() -> None:
    source = IdentityNode()
    target = IdentityNode()
    chain = source >> target

    workflow = Workflow.from_chain(chain)

    assert isinstance(chain, Chain)
    assert workflow.start_node is source
    assert workflow.end_node is target
    assert workflow.nodes == {source, target}


@pytest.mark.asyncio
async def test_workflow_rejects_dangling_edge_on_start() -> None:
    source = IdentityNode()
    source.on(expr="$.ready")
    workflow = Workflow(start=source)

    async with Syndicate("workflow-dangling-edge") as system:
        with pytest.raises(ValueError, match="dangling edges"):
            await workflow.start(system)


@pytest.mark.asyncio
async def test_workflow_structure_is_immutable_after_start() -> None:
    workflow = Workflow(start=IdentityNode())

    async with Syndicate("workflow-immutable") as system:
        await workflow.start(system)
        with pytest.raises(RuntimeError, match="cannot be changed"):
            workflow.add_node(IdentityNode())
        await workflow.shutdown()


@pytest.mark.asyncio
async def test_workflow_shutdown_allows_restart_in_new_system() -> None:
    source = PrefixNode("source")
    target = PrefixNode("target")
    source >> target
    workflow = Workflow(start=source)

    async with Syndicate("workflow-restart-one") as system:
        assert await workflow.run("one", system=system, timeout=1.0) == "target:source:one"
        await workflow.shutdown()

    async with Syndicate("workflow-restart-two") as system:
        assert await workflow.run("two", system=system, timeout=1.0) == "target:source:two"
        await workflow.shutdown()


@pytest.mark.asyncio
async def test_workflow_rejects_node_started_in_different_system() -> None:
    node = IdentityNode()
    workflow = Workflow(start=node)

    async with Syndicate("workflow-owner-one") as first:
        await first.start_actor(node)
        async with Syndicate("workflow-owner-two") as second:
            with pytest.raises(RuntimeError, match="different Syndicate"):
                await workflow.start(second)
