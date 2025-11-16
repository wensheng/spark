"""Tests for blob streaming support in state backends."""

import asyncio
import pytest

from spark.graphs import GraphState
from spark.graphs.state_backend import InMemoryStateBackend, JSONFileStateBackend


@pytest.mark.asyncio
async def test_inmemory_blob_streaming():
    state = GraphState(initial_state={}, backend=InMemoryStateBackend())
    await state.initialize()

    async with state.open_blob_writer(blob_id='blob1') as writer:
        await writer.write(b'hello')
        await writer.write(b' world')

    blobs = await state.list_blobs()
    assert 'blob1' in blobs

    async with state.open_blob_reader('blob1') as reader:
        data = await reader.read()
    assert data == b'hello world'

    await state.delete_blob('blob1')
    assert 'blob1' not in await state.list_blobs()


@pytest.mark.asyncio
async def test_json_backend_blob_streaming(tmp_path):
    backend = JSONFileStateBackend(path=tmp_path / 'state.json')
    state = GraphState(initial_state={}, backend=backend)
    await state.initialize()

    async with state.open_blob_writer(metadata={'kind': 'example'}) as writer:
        await writer.write(b'data')

    blobs = await state.list_blobs()
    assert len(blobs) == 1
    blob_id = blobs[0]

    async with state.open_blob_reader(blob_id) as reader:
        assert await reader.read() == b'data'

    await state.delete_blob(blob_id)
    assert await state.list_blobs() == []
