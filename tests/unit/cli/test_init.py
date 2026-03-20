"""Tests for init CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.services.initializer import InitResult

runner = CliRunner()


@pytest.fixture()
def mock_init_result(tmp_path: Path) -> InitResult:
    """A successful InitResult for mocking."""
    return InitResult(
        config_path=Path("/tmp/test/.portctl/config.yaml"),
        state_path=Path("/tmp/test/.portctl-state.yaml"),
        ignore_path=Path("/tmp/test/.portctlignore"),
        ci_workflow_path=Path("/tmp/test/.github/workflows/portctl.yml"),
        exported_resources=0,
        scaffolded_templates=["blueprints/service.yaml", "blueprints/environment.yaml"],
        files_created=[
            Path("/tmp/test/.portctl/config.yaml"),
            Path("/tmp/test/.portctl-state.yaml"),
            Path("/tmp/test/.portctlignore"),
        ],
    )


class TestInitNonInteractive:
    """Tests for non-interactive init mode."""

    def test_init_non_interactive_requires_org(self) -> None:
        """Exits 1 without --org in non-interactive mode."""
        result = runner.invoke(app, ["init", "--non-interactive", "--mode", "fresh"])
        assert result.exit_code != 0

    def test_init_non_interactive_requires_mode(self) -> None:
        """Exits 1 without --mode in non-interactive mode."""
        result = runner.invoke(app, ["init", "--non-interactive", "--org", "my-org"])
        assert result.exit_code != 0

    def test_init_non_interactive_fresh(
        self, mock_init_result: InitResult, tmp_path: Path
    ) -> None:
        """Creates files without prompts in non-interactive fresh mode."""
        mock_init = AsyncMock(return_value=mock_init_result)
        with patch("portctl.cli.commands.init.init_project", mock_init):
            result = runner.invoke(
                app,
                [
                    "init",
                    "--non-interactive",
                    "--org",
                    "my-org",
                    "--mode",
                    "fresh",
                ],
            )

        assert result.exit_code == 0
        mock_init.assert_awaited_once()

    def test_init_no_ci_skips_workflow(
        self, mock_init_result: InitResult
    ) -> None:
        """--no-ci flag passes generate_ci=False to init_project."""
        mock_init_result.ci_workflow_path = None
        mock_init = AsyncMock(return_value=mock_init_result)
        with patch("portctl.cli.commands.init.init_project", mock_init):
            result = runner.invoke(
                app,
                [
                    "init",
                    "--non-interactive",
                    "--org",
                    "my-org",
                    "--mode",
                    "fresh",
                    "--no-ci",
                ],
            )

        assert result.exit_code == 0
        call_args = mock_init.call_args[0][0]
        assert call_args.generate_ci is False
