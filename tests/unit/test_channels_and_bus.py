import pytest

from spark.nodes.channels import ChannelMessage, ForwardingChannel, InMemoryChannel
from spark.graphs.event_bus import GraphEventBus


@pytest.mark.asyncio
async def test_forwarding_channel_enriches_metadata():
    downstream = InMemoryChannel()
    channel = ForwardingChannel(downstream, metadata_defaults={'edge_id': 'edge-1'})

    await channel.send(ChannelMessage(payload={'value': 1}, metadata={'custom': 'yes'}))

    received = await downstream.receive()
    assert received.payload == {'value': 1}
    assert received.metadata['edge_id'] == 'edge-1'
    assert received.metadata['custom'] == 'yes'


@pytest.mark.asyncio
async def test_event_bus_publish_and_subscribe():
    bus = GraphEventBus()
    subscription = await bus.subscribe('updates')

    await bus.publish('updates', {'value': 42}, metadata={'source': 'test-suite'})

    message = await subscription.receive()
    assert message.payload == {'value': 42}
    assert message.metadata['topic'] == 'updates'
    assert message.metadata['source'] == 'test-suite'

    await subscription.close()
