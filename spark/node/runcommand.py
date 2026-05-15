"""Async external command runner actor for Spark.

Create a :class:`RunCommand` actor and send it a :class:`Command`.  The actor
starts the subprocess asynchronously, streams output while it runs, and sends a
:class:`CommandResult` when the command completes.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from importlib import import_module
from typing import Any, cast

from ..core.message import Message
from .base import Actor, ActorAddress

HALF_NUM_LINES_LOGGED = 5
_READ_SIZE = 64 * 1024

type CommandText = str | tuple[str, str]


@dataclass(slots=True)
class Command:
    """Defines a command to be run by :class:`RunCommand`.

    ``exe`` is the executable to run, and ``args`` are command-line arguments.
    ``input_src`` may be ``str`` or ``bytes`` and is written to stdin before
    stdin is closed.  ``output_updates`` receives streaming
    :class:`CommandOutput` and :class:`CommandError` messages when it is an
    :class:`ActorAddress`.
    """

    exe: str
    args: Sequence[str]
    use_shell: bool = False
    omit_string: str | None = None
    error_ok: bool = False
    logger: ActorAddress | bool | None = None
    logtag: str | None = None
    input_src: str | bytes | None = None
    output_updates: ActorAddress | None = None
    max_bufsize: int | None = 1024 * 1024
    env: Mapping[str, str] | None = None
    timeout: timedelta | float | int | None = None
    report_on_start: bool = False
    sender: ActorAddress | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.omit_string = self.omit_string or ""
        self.logtag = self.logtag or str(self.exe)
        if self.timeout is not None and not isinstance(self.timeout, timedelta):
            self.timeout = timedelta(seconds=float(self.timeout))


@dataclass(frozen=True, slots=True)
class CommandStarted:
    """Sent to the command requestor when ``Command.report_on_start`` is true."""

    command: Command
    pid: int


@dataclass(frozen=True, slots=True)
class CommandAbort:
    """Request that the currently running command be terminated."""


class CommandLog:
    """Log message sent to a command-specific logger actor."""

    def __init__(self, level: str, msg: str, *args: Any) -> None:
        self.level = level
        self.message = msg % args if args else msg


@dataclass(frozen=True, slots=True)
class CommandOutput:
    """Streaming stdout chunk produced by a running command."""

    command: Command
    output: bytes | str


@dataclass(frozen=True, slots=True)
class CommandError:
    """Streaming stderr chunk produced by a running command."""

    command: Command
    error_output: bytes | str


@dataclass(slots=True)
class CommandResult:
    """Result of executing a :class:`Command`.

    ``stdout`` and ``stderr`` are strings unless the corresponding output
    exceeded ``Command.max_bufsize``; in that case the value is
    ``(beginning, end)`` with the middle omitted.  Timeout results use exit
    code ``-2``.
    """

    command: Command
    exitcode: int
    stdout: CommandText = ""
    stderr: CommandText = ""
    duration: timedelta | None = None

    def __bool__(self) -> bool:
        return self.exitcode == 0

    @property
    def errorstr(self) -> CommandText:
        return self.stderr or ("" if self else "FAILED")

    def __str__(self) -> str:
        parts = [self.__class__.__name__, "success" if self else "FAILED"]
        if not self:
            stderr = " [...] ".join(self.stderr) if isinstance(self.stderr, tuple) else self.stderr
            parts.extend([f"Error #{self.exitcode}", stderr])
        return " ".join(parts)


def str_form(value: bytes | str) -> str:
    """Decode subprocess output to text."""

    if isinstance(value, str):
        return value
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        with suppress(ImportError, UnicodeDecodeError, TypeError):
            chardet = cast(Any, import_module("chardet"))
            encoding = chardet.detect(value).get("encoding")
            if encoding:
                return value.decode(encoding)
    return str(value)


@dataclass(slots=True)
class _QueuedCommand:
    command: Command
    sender: ActorAddress | None


@dataclass(slots=True)
class _CapturedOutput:
    max_bufsize: int | None
    head: str = ""
    tail: str = ""

    def add(self, text: str) -> None:
        self.tail += text
        if not self.max_bufsize:
            return
        if len(self.head) + len(self.tail) <= self.max_bufsize:
            return
        if not self.head:
            head_len = int(self.max_bufsize / 2)
            self.head = self.tail[:head_len]
            self.tail = self.tail[head_len:]
        tail_len = self.max_bufsize - len(self.head)
        self.tail = self.tail[-tail_len:] if tail_len > 0 else ""

    def value(self) -> CommandText:
        return (self.head, self.tail) if self.head else self.tail


@dataclass(slots=True)
class _LineLogState:
    buffered: str = ""
    nlines: int = 0
    suppressed: bool = False


@dataclass(slots=True)
class _RunState:
    command: Command
    sender: ActorAddress | None
    start_time: datetime
    abort_event: asyncio.Event
    stdout: _CapturedOutput
    stderr: _CapturedOutput
    process: asyncio.subprocess.Process | None = None
    abort_reply_to: ActorAddress | None = None
    stdout_log: _LineLogState = field(default_factory=_LineLogState)
    stderr_log: _LineLogState = field(default_factory=_LineLogState)


class RunCommand(Actor):
    """Actor that runs external commands without blocking Spark's event loop."""

    def __init__(self) -> None:
        super().__init__()
        self.pending_commands: deque[_QueuedCommand] = deque()
        self.command_num = 0
        self._current: _RunState | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._stopping = False

    async def process(self, message: Message) -> None:
        payload = message.content
        if isinstance(payload, Command):
            payload.sender = message.sender
            self.pending_commands.append(_QueuedCommand(payload, message.sender))
            self._ensure_worker()
        elif isinstance(payload, CommandAbort):
            if self._current is not None:
                self._current.abort_reply_to = message.sender
                self._current.abort_event.set()

    async def post_stop(self) -> None:
        self._stopping = True
        current = self._current
        if current is not None:
            await self._stop_process(current.process)
        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker_task
        while self.pending_commands:
            queued = self.pending_commands.popleft()
            await self._send_result(
                queued.sender,
                CommandResult(queued.command, -3, "", "", None),
            )

    def _ensure_worker(self) -> None:
        if self._stopping:
            return
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._command_worker())

    async def _command_worker(self) -> None:
        try:
            while self.pending_commands and not self._stopping:
                queued = self.pending_commands.popleft()
                state = _RunState(
                    command=queued.command,
                    sender=queued.sender,
                    start_time=datetime.now(),
                    abort_event=asyncio.Event(),
                    stdout=_CapturedOutput(queued.command.max_bufsize),
                    stderr=_CapturedOutput(queued.command.max_bufsize),
                )
                self._current = state
                self.command_num += 1
                try:
                    await self._run_command(state)
                finally:
                    self._current = None
        finally:
            self._worker_task = None
            if self.pending_commands and not self._stopping:
                self._ensure_worker()

    async def _run_command(self, state: _RunState) -> None:
        command = state.command
        self._log(command, "info", "%s CMD: %s", command.logtag, self._log_command(command))
        try:
            process = await self._create_process(command)
        except OSError as exc:
            await self._add_output(state, "error", f"{exc}\n")
            await self._finish_command(state, exc.errno or -1)
            return

        state.process = process
        if command.report_on_start:
            await self._send_to_requestors(state, CommandStarted(command, process.pid))

        await self._write_stdin(process, command.input_src)
        stdout_task = asyncio.create_task(self._read_stream(state, "normal", process.stdout))
        stderr_task = asyncio.create_task(self._read_stream(state, "error", process.stderr))

        wait_task = asyncio.create_task(process.wait())
        abort_task = asyncio.create_task(state.abort_event.wait())
        timed_out = False
        try:
            timeout = command.timeout.total_seconds() if isinstance(command.timeout, timedelta) else None
            done, pending = await asyncio.wait(
                {wait_task, abort_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if wait_task not in done:
                timed_out = abort_task not in done
                await self._stop_process(process)
                with suppress(asyncio.CancelledError):
                    await wait_task
            for task in pending:
                task.cancel()
            with suppress(asyncio.CancelledError):
                await abort_task
        finally:
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        exitcode = -2 if timed_out else (process.returncode if process.returncode is not None else -4)
        await self._finish_command(state, exitcode)

    async def _create_process(self, command: Command) -> asyncio.subprocess.Process:
        env = dict(command.env) if command.env is not None else None
        if command.use_shell:
            return await asyncio.create_subprocess_shell(
                self._shell_command(command),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        return await asyncio.create_subprocess_exec(
            str(command.exe),
            *(str(arg) for arg in command.args),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

    @staticmethod
    def _shell_command(command: Command) -> str:
        return " ".join(shlex.quote(str(part)) for part in (command.exe, *command.args))

    @staticmethod
    def _log_command(command: Command) -> str:
        logcmd = " ".join(str(part) for part in (command.exe, *command.args))
        return logcmd.replace(command.omit_string, "...") if command.omit_string else logcmd

    async def _write_stdin(
        self,
        process: asyncio.subprocess.Process,
        input_src: str | bytes | None,
    ) -> None:
        stdin = process.stdin
        if stdin is None:
            return
        try:
            if input_src is not None:
                stdin.write(input_src if isinstance(input_src, bytes) else input_src.encode("utf-8"))
                await stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await stdin.wait_closed()

    async def _read_stream(
        self,
        state: _RunState,
        outmark: str,
        stream: asyncio.StreamReader | None,
    ) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(_READ_SIZE)
            if not chunk:
                return
            await self._add_output(state, outmark, chunk)

    async def _add_output(self, state: _RunState, outmark: str, new_output: bytes | str) -> None:
        if not new_output:
            return
        command = state.command
        text = str_form(new_output)
        capture = state.stdout if outmark == "normal" else state.stderr
        capture.add(text)

        updates_to = command.output_updates
        if isinstance(updates_to, ActorAddress):
            update = CommandOutput(command, new_output) if outmark == "normal" else CommandError(command, new_output)
            await self.tell(update, updates_to)

        if outmark == "normal":
            self._log_output_lines(state, outmark, text, " OUT| ", "info")
        else:
            self._log_output_lines(state, outmark, text, " ERR> ", "info" if command.error_ok else "error")

    def _log_output_lines(self, state: _RunState, outmark: str, text: str, prefix: str, level: str) -> None:
        log_state = state.stdout_log if outmark == "normal" else state.stderr_log
        if log_state.nlines >= HALF_NUM_LINES_LOGGED:
            log_state.suppressed = True
            return
        log_state.buffered += text
        while "\n" in log_state.buffered and log_state.nlines < HALF_NUM_LINES_LOGGED:
            line, log_state.buffered = log_state.buffered.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            command = state.command
            if command.omit_string:
                line = line.replace(command.omit_string, "...")
            self._log(command, level, "%s%s%s", command.logtag, prefix, line)
            log_state.nlines += 1
        if log_state.nlines >= HALF_NUM_LINES_LOGGED and log_state.buffered:
            log_state.suppressed = True

    async def _finish_command(self, state: _RunState, exitcode: int) -> None:
        result = CommandResult(
            state.command,
            exitcode,
            state.stdout.value(),
            state.stderr.value(),
            datetime.now() - state.start_time,
        )
        self._log_finished_command(result)
        await self._send_result(state.sender, result)
        if state.abort_reply_to is not None and state.abort_reply_to != state.sender:
            await self._send_result(state.abort_reply_to, result)

    def _log_finished_command(self, result: CommandResult) -> None:
        if result.exitcode:
            self._log(
                result.command,
                "info" if result.command.error_ok else "error",
                "%s ERROR exit code: %d",
                result.command.logtag,
                result.exitcode,
            )
        else:
            self._log(result.command, "info", "%s completed successfully", result.command.logtag)

    async def _send_to_requestors(self, state: _RunState, payload: object) -> None:
        await self._send_result(state.sender, payload)
        if state.abort_reply_to is not None and state.abort_reply_to != state.sender:
            await self._send_result(state.abort_reply_to, payload)

    async def _send_result(self, target: ActorAddress | None, payload: object) -> None:
        if target is not None:
            await self.tell(payload, target)

    async def _stop_process(self, process: asyncio.subprocess.Process | None) -> None:
        if process is None or process.returncode is not None:
            return
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            async with asyncio.timeout(2.0):
                await process.wait()
                return
        except TimeoutError:
            pass
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            with suppress(TimeoutError):
                async with asyncio.timeout(2.0):
                    await process.wait()

    def _log(self, command: Command, level: str, msg: str, *args: Any) -> None:
        if command.logger is False:
            return
        if isinstance(command.logger, ActorAddress):
            asyncio.create_task(self.tell(CommandLog(level, msg, *args), command.logger))
            return
        if command.logger is None:
            log = logging.info if level == "info" else logging.error
            log(msg, *args)
