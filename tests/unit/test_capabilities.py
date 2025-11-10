import pytest

from spark.nodes.config import NodeConfig
from spark.nodes.exceptions import NodeExecutionError
from spark.nodes.nodes import Node
from spark.nodes.policies import RetryPolicy
from spark.nodes.types import ExecutionContext


class FlakyNode(Node):
    """Test helper node that fails a configurable number of times before succeeding."""

    def __init__(self, *, fail_times: int, max_attempts: int):
        self._fail_times = fail_times
        self._invocations = 0
        config = NodeConfig(retry=RetryPolicy(max_attempts=max_attempts, delay=0))
        super().__init__(config=config)

    async def process(self, context: ExecutionContext):
        attempt = self._invocations
        self._invocations += 1
        if attempt < self._fail_times:
            raise RuntimeError(f'boom {attempt}')
        return {'attempt': attempt, 'echo': context.inputs.content}


@pytest.mark.asyncio
async def test_retry_capability_retries_until_success():
    node = FlakyNode(fail_times=2, max_attempts=5)

    result = await node.do({'value': 'ping'})

    assert result.content['attempt'] == 2
    assert result.content['echo'] == {'value': 'ping'}
    assert node._invocations == 3
    assert node._last_process_attempts == 3


@pytest.mark.asyncio
async def test_retry_capability_raises_after_exhaustion():
    node = FlakyNode(fail_times=5, max_attempts=3)

    with pytest.raises(NodeExecutionError) as excinfo:
        await node.do({'value': 'fail'})

    assert excinfo.value.kind == 'retry_exhausted'
    assert node._invocations == 3  # Only max_attempts executions should occur
    assert node._last_process_attempts == 3


def test_retry_policy_behavior():
    policy = RetryPolicy(
        max_attempts=3,
        delay=1,
        backoff_multiplier=2,
        max_delay=5,
        retry_on=(ValueError,),
    )

    assert policy.allows_retry(0) is True
    assert policy.allows_retry(1) is True
    assert policy.allows_retry(2) is False

    assert policy.is_retryable_exception(ValueError())
    assert not policy.is_retryable_exception(RuntimeError())

    assert policy.get_delay(0) == pytest.approx(1.0)
    assert policy.get_delay(1) == pytest.approx(2.0)
    assert policy.get_delay(3) == pytest.approx(5.0)  # capped by max_delay
