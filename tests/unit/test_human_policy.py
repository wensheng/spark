import pytest

from spark.nodes.config import NodeConfig
from spark.nodes.human import HumanPrompt, InteractiveHumanPolicy
from spark.nodes.nodes import Node
from spark.nodes.types import ExecutionContext, NodeMessage


class EchoNode(Node):
    async def process(self, context: ExecutionContext):
        return {'echo': context.inputs.content}


class MessageNode(Node):
    async def process(self, context: ExecutionContext):
        return NodeMessage(content={'status': 'ok'}, extras={'existing': True})


@pytest.mark.asyncio
async def test_interactive_policy_option_selection():
    responses = iter(['1'])

    async def provider(prompt: str) -> str:
        return next(responses)

    policy = InteractiveHumanPolicy(
        prompt=lambda node, ctx, result: HumanPrompt(
            message='Choose what to do',
            kind='options',
            options=('approve', 'reject'),
            allow_freeform=False,
        ),
        input_provider=provider,
    )

    node = EchoNode(config=NodeConfig(human_policy=policy))
    output = await node.do({'message': 'hello'})

    assert output.content['echo'] == {'message': 'hello'}
    feedback = output.content['human_feedback']
    assert feedback['kind'] == 'options'
    assert feedback['selected_option'] == 'approve'
    assert feedback['selected_index'] == 1
    assert node._state['human_feedback']['selected_option'] == 'approve'


@pytest.mark.asyncio
async def test_interactive_policy_respects_trigger():
    async def provider(prompt: str) -> str:  # pragma: no cover - should not be called
        pytest.fail('input provider should not be invoked when trigger is false')

    policy = InteractiveHumanPolicy(
        trigger=lambda node, ctx, result: False,
        prompt=HumanPrompt(
            message='Should never show',
            kind='text',
        ),
        input_provider=provider,
    )

    node = EchoNode(config=NodeConfig(human_policy=policy))
    output = await node.do({'message': 'skip'})

    assert 'human_feedback' not in output.content
    assert 'human_feedback' not in node._state


@pytest.mark.asyncio
async def test_interactive_policy_clipboard_mode():
    responses = iter(['line one', 'line two', ''])

    async def provider(prompt: str) -> str:
        return next(responses)

    policy = InteractiveHumanPolicy(
        prompt=HumanPrompt(
            message='Paste the generated plan:',
            kind='clipboard',
        ),
        input_provider=provider,
    )

    node = MessageNode(config=NodeConfig(human_policy=policy))
    output = await node.do({'payload': 'ignored'})

    assert output.content == {'status': 'ok'}
    extras = output.extras
    assert extras['existing'] is True
    feedback = extras['human_feedback']
    assert feedback['kind'] == 'clipboard'
    assert feedback['raw_value'] == 'line one\nline two'
    assert node._state['human_feedback']['raw_value'] == 'line one\nline two'
