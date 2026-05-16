"""Tests for Spark command line helpers."""

from spark.cli import main


def test_status_command_prints_guidance(capsys) -> None:
    assert main(["status"]) == 0

    output = capsys.readouterr().out
    assert "Spark status" in output
    assert "diagnostics" in output


def test_version_command_prints_version(capsys) -> None:
    assert main(["--version"]) == 0

    assert "Spark" in capsys.readouterr().out
