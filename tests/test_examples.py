"""Smoke tests for runnable examples."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

PHASE9_EXAMPLES = [
    "basic_actor_echo.py",
    "parent_child_supervision.py",
    "mailbox_backpressure_timeout.py",
    "timers_and_watch.py",
    "persistent_counter.py",
    "durable_timer.py",
    "diagnostics_and_dead_letters.py",
    "run_command_pipeline.py",
    "troupe_parallel_map.py",
    "workflow_router.py",
    "workflow_fanout_fanin.py",
    "tcp_two_hosts.py",
    "websocket_direct_two_hosts.py",
    "nat_relay_service.py",
    "nat_relay_worker_pool.py",
    "federation_placement.py",
]


def _run_example(name: str, *args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(EXAMPLES / name), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def test_phase9_examples_have_help() -> None:
    for example in PHASE9_EXAMPLES:
        result = _run_example(example, "--help")
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout


def test_examples_doc_references_existing_files() -> None:
    docs = (ROOT / "docs" / "examples.md").read_text()
    for example in PHASE9_EXAMPLES:
        assert f"examples/{example}" in docs
        assert (EXAMPLES / example).exists()


def test_documented_example_commands_run() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "docs" / "examples.md",
    ]
    commands: list[list[str]] = []
    for document in documents:
        for line in document.read_text().splitlines():
            if not re.match(r"^python examples/[a-z0-9_]+\.py\b", line):
                continue
            parts = shlex.split(line)
            commands.append([sys.executable, str(ROOT / parts[1]), *parts[2:]])

    assert commands
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            text=True,
            capture_output=True,
            timeout=20.0,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_basic_actor_echo_example_runs() -> None:
    result = _run_example("basic_actor_echo.py", "--message", "hi")
    assert result.returncode == 0, result.stderr
    assert "ask=echo:hi" in result.stdout
    assert "tell=echo:hi" in result.stdout


def test_fault_tolerance_examples_run(tmp_path: Path) -> None:
    counter = _run_example("persistent_counter.py", "--db", str(tmp_path / "counter.sqlite"), "--delta", "4")
    assert counter.returncode == 0, counter.stderr
    assert "recovered=4" in counter.stdout

    timer = _run_example("durable_timer.py", "--db", str(tmp_path / "timer.sqlite"))
    assert timer.returncode == 0, timer.stderr
    assert "fired=True" in timer.stdout


def test_local_workflow_and_network_examples_run() -> None:
    cases = [
        ("workflow_router.py", "--score", "95"),
        ("workflow_fanout_fanin.py", "--topic", "phase9"),
        ("tcp_two_hosts.py", "local", "--codec", "trusted-pickle", "--message", "hi"),
        ("websocket_direct_two_hosts.py", "local", "--codec", "trusted-pickle", "--message", "hi"),
        ("nat_relay_service.py", "local", "--codec", "trusted-pickle", "--secret", "shared", "--message", "hi"),
        (
            "nat_relay_worker_pool.py",
            "local",
            "--codec",
            "trusted-pickle",
            "--secret",
            "shared",
            "--values",
            "2,3",
        ),
        ("federation_placement.py", "local", "--codec", "trusted-pickle", "--message", "hi"),
    ]
    for case in cases:
        result = _run_example(case[0], *case[1:])
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip()
