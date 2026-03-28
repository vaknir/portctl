"""Tests for portctl CLI app and command group registration."""

from __future__ import annotations

import subprocess
import sys

import pytest
from typer.testing import CliRunner

from portctl.cli.app import app

runner = CliRunner()

EXPECTED_COMMAND_GROUPS = [
    "auth",
    "org",
    "pull",
    "diff",
    "push",
    "validate",
    "blueprint",
]


class TestCLIHelp:
    """Tests that the CLI app starts and shows help."""

    def test_help_exits_zero(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_help_shows_app_name(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "portctl" in result.output.lower()

    @pytest.mark.parametrize("group", EXPECTED_COMMAND_GROUPS)
    def test_command_group_registered(self, group: str) -> None:
        result = runner.invoke(app, ["--help"])
        assert group in result.output, f"Command group '{group}' not found in --help output"

    @pytest.mark.parametrize("group", EXPECTED_COMMAND_GROUPS)
    def test_command_group_help(self, group: str) -> None:
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0


class TestCLIEntryPoint:
    """Tests that the CLI entry point works via python -m."""

    def test_python_m_portctl_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "portctl", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "portctl" in result.stdout.lower()


class TestCLIVersion:
    """Tests for version display."""

    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
