"""End-to-end: watch a subprocess's stdout pipe (async version)."""

import os
import subprocess
import sys

import pytest

from spark import Actor, Syndicate, WatchMessage
from spark.core.message import Message


class StdoutReaderActor(Actor):
    def __init__(self, fd: int) -> None:
        super().__init__()
        self.fd = fd
        self.output = bytearray()
        self.done = False

    async def pre_start(self) -> None:
        await self.watch(read=[self.fd])

    async def process(self, message: Message):
        if isinstance(message.content, WatchMessage):
            wm = message.content
            if self.fd in wm.ready_read:
                try:
                    chunk = os.read(self.fd, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    self.done = True
                    await self.watch()
                else:
                    self.output.extend(chunk)
            if self.fd in wm.failed:
                self.done = True


@pytest.mark.asyncio
async def test_actor_reads_subprocess_stdout() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.write('hello\\n'); sys.stdout.flush()"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        os.set_blocking(fd, False)

        async with Syndicate("async-subprocess-watch") as system:
            actor_addr = await system.create_actor(StdoutReaderActor, fd)
            actor = system.backend.registry.get(actor_addr.actor_id).actor

            import asyncio
            deadline = asyncio.get_event_loop().time() + 5.0
            while not actor.done and asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(0.05)
            assert actor.output == b"hello\n", actor.output
    finally:
        proc.wait(timeout=5.0)
