import asyncio
import os
import sys
from datetime import timedelta

import pytest

from spark import Actor, Syndicate
from spark.core.message import Message
from spark.node.runcommand import (
    Command,
    CommandAbort,
    CommandError,
    CommandOutput,
    CommandResult,
    CommandStarted,
    RunCommand,
)


def _as_text(chunks: list[bytes | str]) -> str:
    return "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks)


class OutputCollector(Actor):
    def __init__(self) -> None:
        super().__init__()
        self.stdout: list[bytes | str] = []
        self.stderr: list[bytes | str] = []

    async def process(self, message: Message) -> None:
        if isinstance(message.content, CommandOutput):
            self.stdout.append(message.content.output)
        elif isinstance(message.content, CommandError):
            self.stderr.append(message.content.error_output)
        elif message.content == "get" and message.sender is not None:
            await self.tell((_as_text(self.stdout), _as_text(self.stderr)), message.sender)


@pytest.mark.asyncio
async def test_simple_command() -> None:
    async with Syndicate("runcommand-simple") as system:
        runner = await system.create_actor(RunCommand)
        result = await system.ask(
            runner,
            Command(sys.executable, ["-c", 'print("hello")']),
            timeout=5.0,
        )

        assert isinstance(result, CommandResult)
        assert result
        assert result.stdout == f"hello{os.linesep}"


@pytest.mark.asyncio
async def test_report_on_start_and_output_updates() -> None:
    program = "\n".join(
        [
            "import sys",
            "sys.stdout.write('hello\\n')",
            "sys.stdout.flush()",
            "name = sys.stdin.read().strip()",
            "sys.stdout.write(f'hello {name}\\n')",
            "sys.stderr.write('done\\n')",
            "sys.stderr.flush()",
        ]
    )

    async with Syndicate("runcommand-updates") as system:
        runner = await system.create_actor(RunCommand)
        collector = await system.create_actor(OutputCollector)

        await system.tell(
            runner,
            Command(
                sys.executable,
                ["-u", "-c", program],
                input_src="Harry\n",
                output_updates=collector,
                report_on_start=True,
            ),
        )

        started = await system.receive(timeout=5.0)
        assert isinstance(started, CommandStarted)
        assert started.pid >= 1

        result = await system.receive(timeout=5.0)
        assert isinstance(result, CommandResult)
        assert result
        assert result.stdout == f"hello{os.linesep}hello Harry{os.linesep}"
        assert result.stderr == f"done{os.linesep}"
        assert await system.ask(collector, "get", timeout=1.0) == (result.stdout, result.stderr)


@pytest.mark.asyncio
async def test_timeout_terminates_command() -> None:
    async with Syndicate("runcommand-timeout") as system:
        runner = await system.create_actor(RunCommand)
        result = await system.ask(
            runner,
            Command(sys.executable, ["-c", "import time; time.sleep(10)"], timeout=0.1),
            timeout=5.0,
        )

        assert isinstance(result, CommandResult)
        assert not result
        assert result.exitcode == -2
        assert result.duration is not None
        assert result.duration < timedelta(seconds=4)


@pytest.mark.asyncio
async def test_abort_running_command_replies_to_abort_requestor() -> None:
    async with Syndicate("runcommand-abort") as system:
        runner = await system.create_actor(RunCommand)
        await system.tell(
            runner,
            Command(sys.executable, ["-u", "-c", "import time; print('start'); time.sleep(10)"]),
        )

        await asyncio.sleep(0.1)
        result = await system.ask(runner, CommandAbort(), timeout=5.0)

        assert isinstance(result, CommandResult)
        assert not result
        assert result.exitcode != 0
        assert "start" in result.stdout


@pytest.mark.asyncio
async def test_commands_run_fifo() -> None:
    async with Syndicate("runcommand-fifo") as system:
        runner = await system.create_actor(RunCommand)
        await system.tell(
            runner,
            Command(sys.executable, ["-c", "import time; time.sleep(0.1); print('first')"]),
        )
        await system.tell(runner, Command(sys.executable, ["-c", "print('second')"]))

        first = await system.receive(timeout=5.0)
        second = await system.receive(timeout=5.0)

        assert isinstance(first, CommandResult)
        assert isinstance(second, CommandResult)
        assert first.stdout == f"first{os.linesep}"
        assert second.stdout == f"second{os.linesep}"


@pytest.mark.asyncio
async def test_missing_executable_returns_failure_result() -> None:
    async with Syndicate("runcommand-missing") as system:
        runner = await system.create_actor(RunCommand)
        result = await system.ask(
            runner,
            Command("definitely-not-a-spark-test-command", []),
            timeout=5.0,
        )

        assert isinstance(result, CommandResult)
        assert not result
        assert result.stderr
        assert "FAILED" in str(result)
