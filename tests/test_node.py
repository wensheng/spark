from dataclasses import dataclass, field
from typing import Any

import pytest

from spark.actor import Actor, ActorAddress
from spark.core.actor_spec import ActorSpec
from spark.core.exceptions import ActorNotStartedError
from spark.core.identity import ActorId, SyndicateId
from spark.core.message import Message
from spark.node.base import _FORWARDED_METADATA_KEY, Node, NodeConfig
from spark.system import Syndicate


@dataclass
class RecordingContext:
    actor_id: ActorId
    address: ActorAddress
    parent: ActorAddress | None = None
    sent: list[tuple[ActorAddress, Any]] = field(default_factory=list)

    async def tell(self, target: ActorAddress, message: Any) -> None:
        self.sent.append((target, message))

    async def ask(self, target: ActorAddress, message: Any, timeout: float | None = None) -> Any:
        return {"target": target, "message": message, "timeout": timeout}

    async def create_actor(
        self, actor_class: type[Actor], *args: Any, **kwargs: Any
    ) -> ActorAddress:
        return ActorAddress(ActorId(syndicate_id=self.actor_id.syndicate_id))

    async def create_actor_from_spec(self, spec: ActorSpec) -> ActorAddress:
        return ActorAddress(ActorId(syndicate_id=self.actor_id.syndicate_id))

    def schedule_after(self, delay: float, payload: Any = None) -> None:
        return None

    async def watch(self, *, read=(), write=()) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def syndicate_shutdown(self) -> None:
        return None


def make_context() -> RecordingContext:
    actor_id = ActorId(SyndicateId())
    return RecordingContext(actor_id=actor_id, address=ActorAddress(actor_id))


class UpperNode(Node):
    __spark_auto_start__ = False

    def process(self, message: Message) -> str:
        return str(message.content).upper()


class PrefixNode(Node):
    __spark_auto_start__ = False

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def process(self, message: Message) -> str:
        return f"{self.prefix}:{message.content}"


class IdentityNode(Node):
    __spark_auto_start__ = False

    def process(self, message: Message) -> Any:
        return message.content


@pytest.mark.asyncio
async def test_node_process_returns_result_without_forwarding() -> None:
    node = UpperNode()

    assert await node._process(Message("spark")) == "SPARK"


@pytest.mark.asyncio
async def test_node_process_applies_hooks_to_message_content_and_result() -> None:
    observed_nodes: list[Node] = []

    def pre_process(node: Node, content: Any) -> str:
        observed_nodes.append(node)
        return f"{content} plug"

    def post_process(node: Node, result: Any) -> str:
        observed_nodes.append(node)
        return f"{result}!"

    node = UpperNode(
        pre_process_hooks=[
            pre_process,
            lambda _node, content: f"hot {content}",
        ],
        post_process_hooks=[
            post_process,
            lambda _node, result: f"[{result}]",
        ],
    )

    message = Message("spark")
    result = await node._process(message)

    assert message.content == "hot spark plug"
    assert result == "[HOT SPARK PLUG!]"
    assert node.outputs == "[HOT SPARK PLUG!]"
    assert observed_nodes == [node, node]


@pytest.mark.asyncio
async def test_node_process_awaits_async_hooks() -> None:
    async def pre_process(node: Node, content: Any) -> str:
        assert isinstance(node, UpperNode)
        return f"{content} async"

    async def post_process(node: Node, result: Any) -> str:
        assert isinstance(node, UpperNode)
        return f"{result} done"

    node = UpperNode(config=NodeConfig(pre_process_hooks=[pre_process], post_process_hooks=[post_process]))

    assert await node._process(Message("spark")) == "SPARK ASYNC done"


@pytest.mark.asyncio
async def test_node_forward_to_node_resolves_target_address() -> None:
    source = UpperNode()
    target = UpperNode()
    source_context = make_context()
    target_context = make_context()
    source._bind_context(source_context)
    target._bind_context(target_context)

    source.forward_to(target)
    result = await source._process(Message("spark"))

    assert result is None
    assert len(source_context.sent) == 1
    sent_target, sent_message = source_context.sent[0]
    assert sent_target == target_context.address
    assert isinstance(sent_message, Message)
    assert sent_message.content == "SPARK"


@pytest.mark.asyncio
async def test_node_forward_to_sends_post_processed_result() -> None:
    source = UpperNode(post_process_hooks=[lambda node, result: f"{node.__class__.__name__}:{result}!"])
    target = UpperNode()
    source_context = make_context()
    target_context = make_context()
    source._bind_context(source_context)
    target._bind_context(target_context)

    source.forward_to(target)
    result = await source._process(Message("spark"))

    assert result is None
    assert len(source_context.sent) == 1
    _, sent_message = source_context.sent[0]
    assert isinstance(sent_message, Message)
    assert sent_message.content == "UpperNode:SPARK!"


@pytest.mark.asyncio
async def test_node_forward_to_preserves_original_requester_for_final_reply() -> None:
    source = PrefixNode("source")
    target = PrefixNode("target")
    source.forward_to(target)

    async with Syndicate("node-forward-chain") as system:
        source_address = await system.start_actor(source)
        await system.start_actor(target)

        result = await system.ask(source_address, "spark", timeout=1.0)

    assert result == "target:source:spark"


@pytest.mark.asyncio
async def test_forwarded_terminal_node_without_reply_target_suppresses_reply_to_previous_node() -> None:
    node = UpperNode()
    context = make_context()
    node._bind_context(context)

    result = await node._process(Message("spark", metadata={_FORWARDED_METADATA_KEY: True}))

    assert result is None
    assert context.sent == []


def test_node_forward_to_rejects_invalid_target() -> None:
    node = UpperNode()

    with pytest.raises(TypeError, match="next_node must be a BaseNode"):
        node.forward_to(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_node_forward_to_unstarted_node_raises_clear_error() -> None:
    source = UpperNode()
    target = UpperNode()
    source._bind_context(make_context())
    source.forward_to(target)

    with pytest.raises(ActorNotStartedError, match="UpperNode"):
        await source._process(Message("spark"))


@pytest.mark.asyncio
async def test_node_goto_forwards_to_node() -> None:
    source = UpperNode()
    target = UpperNode()
    source_context = make_context()
    target_context = make_context()
    source._bind_context(source_context)
    target._bind_context(target_context)

    source.goto(target)
    result = await source._process(Message("spark"))

    assert result is None
    assert len(source_context.sent) == 1
    sent_target, sent_message = source_context.sent[0]
    assert sent_target == target_context.address
    assert isinstance(sent_message, Message)
    assert sent_message.content == "SPARK"


@pytest.mark.asyncio
async def test_node_goto_forwards_to_multiple_active_nodes_in_priority_order() -> None:
    source = UpperNode()
    high_priority_target = UpperNode()
    low_priority_target = UpperNode()
    source_context = make_context()
    high_priority_context = make_context()
    low_priority_context = make_context()
    source._bind_context(source_context)
    high_priority_target._bind_context(high_priority_context)
    low_priority_target._bind_context(low_priority_context)

    source.goto(low_priority_target, priority=0)
    source.goto(high_priority_target, priority=10)
    result = await source._process(Message("spark"))

    assert result is None
    assert [target for target, _ in source_context.sent] == [
        high_priority_context.address,
        low_priority_context.address,
    ]
    assert [message.content for _, message in source_context.sent] == ["SPARK", "SPARK"]


@pytest.mark.asyncio
async def test_node_forward_to_appends_multiple_edges() -> None:
    source = UpperNode()
    first_target = UpperNode()
    second_target = UpperNode()
    source_context = make_context()
    first_context = make_context()
    second_context = make_context()
    source._bind_context(source_context)
    first_target._bind_context(first_context)
    second_target._bind_context(second_context)

    source.forward_to(first_target).forward_to(second_target)
    result = await source._process(Message("spark"))

    assert result is None
    assert [target for target, _ in source_context.sent] == [first_context.address, second_context.address]


@pytest.mark.asyncio
async def test_node_fanin_joins_outputs_from_prior_fanout() -> None:
    source = IdentityNode()
    left = PrefixNode("left")
    right = PrefixNode("right")
    join = IdentityNode()

    source >> left >> join
    source >> right >> join

    async with Syndicate("node-fanout-fanin") as system:
        source_address = await system.start_actor(source)
        await system.start_actor(left)
        await system.start_actor(right)
        await system.start_actor(join)

        result = await system.ask(source_address, "spark", timeout=1.0)

    assert sorted(result) == ["left:spark", "right:spark"]


@pytest.mark.asyncio
async def test_node_goto_uses_expr_condition() -> None:
    source = IdentityNode()
    high_target = UpperNode()
    low_target = UpperNode()
    source_context = make_context()
    high_context = make_context()
    low_context = make_context()
    source._bind_context(source_context)
    high_target._bind_context(high_context)
    low_target._bind_context(low_context)

    source.goto(high_target, expr="$.outputs.score > 0.5")
    source.goto(low_target, expr="$.outputs.score <= 0.5")
    result = await source._process(Message({"score": 0.75}))

    assert result is None
    assert [target for target, _ in source_context.sent] == [high_context.address]


@pytest.mark.asyncio
async def test_node_goto_uses_equals_condition() -> None:
    source = IdentityNode()
    search_target = UpperNode()
    other_target = UpperNode()
    source_context = make_context()
    search_context = make_context()
    other_context = make_context()
    source._bind_context(source_context)
    search_target._bind_context(search_context)
    other_target._bind_context(other_context)

    source.goto(search_target, action="search")
    source.goto(other_target, action="other")
    result = await source._process(Message({"action": "search"}))

    assert result is None
    assert [target for target, _ in source_context.sent] == [search_context.address]


@pytest.mark.asyncio
async def test_node_on_edge_uses_condition() -> None:
    source = IdentityNode()
    target = UpperNode()
    source_context = make_context()
    target_context = make_context()
    source._bind_context(source_context)
    target._bind_context(target_context)

    source.on(expr="$.outputs.ready") >> target
    result = await source._process(Message({"ready": True}))

    assert result is None
    assert [sent_target for sent_target, _ in source_context.sent] == [target_context.address]


def test_node_rshift_connects_to_next_node() -> None:
    source = IdentityNode()
    target = UpperNode()

    chain = source >> target

    assert chain.nodes == [source, target]
    assert len(source.edges) == 1
    assert source.edges[0].from_node is source
    assert source.edges[0].to_node is target


def test_node_rshift_can_chain_multiple_nodes() -> None:
    source = IdentityNode()
    middle = PrefixNode("middle")
    target = UpperNode()

    chain = source >> middle >> target

    assert chain.nodes == [source, middle, target]
    assert [edge.to_node for edge in source.edges] == [middle]
    assert [edge.to_node for edge in middle.edges] == [target]


@pytest.mark.asyncio
async def test_node_process_returns_result_when_no_edge_matches() -> None:
    source = IdentityNode()
    target = UpperNode()
    target._bind_context(make_context())

    source.goto(target, expr="$.outputs.score > 0.5")
    result = await source._process(Message({"score": 0.25}))

    assert result == {"score": 0.25}


@pytest.mark.asyncio
async def test_node_forwarding_resolves_all_targets_before_sending() -> None:
    source = UpperNode()
    started_target = UpperNode()
    unstarted_target = UpperNode()
    source_context = make_context()
    started_target._bind_context(make_context())
    source._bind_context(source_context)

    source.goto(started_target, priority=10)
    source.goto(unstarted_target, priority=0)

    with pytest.raises(ActorNotStartedError, match="UpperNode"):
        await source._process(Message("spark"))

    assert source_context.sent == []


def test_node_goto_rejects_conflicting_condition_styles() -> None:
    source = UpperNode()
    target = UpperNode()

    with pytest.raises(TypeError, match="Only one edge condition style"):
        source.goto(target, condition="$.outputs.ready", expr="$.outputs.score > 0.5")


def test_node_on_rejects_conflicting_condition_styles() -> None:
    source = UpperNode()

    with pytest.raises(TypeError, match="Only one edge condition style"):
        source.on(expr="$.outputs.ready", action="search")
