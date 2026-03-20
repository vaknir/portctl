"""Tests for the init wizard UX."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from portctl.cli.commands.init import _render_step_header, _render_summary, _render_welcome_banner
from portctl.services.initializer import InitResult


class TestWizardRendering:
    """Tests for wizard rendering helpers."""

    def test_welcome_banner_renders(self) -> None:
        """Welcome banner renders without error."""
        console = MagicMock()
        _render_welcome_banner(console)
        assert console.print.called

    def test_step_header_renders(self) -> None:
        """Step header renders with step number and total."""
        console = MagicMock()
        _render_step_header(console, 1, 4, "Organization Setup")
        call_args = str(console.print.call_args)
        assert "1" in call_args
        assert "4" in call_args

    def test_step_header_renders_different_steps(self) -> None:
        """Step header renders correctly for different step numbers."""
        console = MagicMock()
        _render_step_header(console, 3, 4, "Project Setup")
        call_args = str(console.print.call_args)
        assert "3" in call_args
        assert "Project Setup" in call_args

    def test_summary_renders(self) -> None:
        """Summary panel renders with result data."""
        console = MagicMock()
        result = InitResult(
            config_path=Path("~/.portctl/config.yaml"),
            state_path=Path(".portctl-state.yaml"),
            ignore_path=Path(".portctlignore"),
            ci_workflow_path=None,
            exported_resources=12,
            scaffolded_templates=[],
            files_created=[],
        )
        _render_summary(console, result, "my-org", 12, 3)
        assert console.print.called

    def test_summary_renders_with_zero_resources(self) -> None:
        """Summary panel renders correctly with zero exported resources."""
        console = MagicMock()
        result = InitResult(
            config_path=Path("~/.portctl/config.yaml"),
            state_path=Path(".portctl-state.yaml"),
            ignore_path=None,
            ci_workflow_path=None,
            exported_resources=0,
            scaffolded_templates=["blueprints/service.yaml"],
            files_created=[],
        )
        _render_summary(console, result, "dev-org")
        assert console.print.called

    def test_summary_renders_with_ci_workflow(self) -> None:
        """Summary panel includes CI workflow path when present."""
        console = MagicMock()
        result = InitResult(
            config_path=Path("~/.portctl/config.yaml"),
            state_path=Path(".portctl-state.yaml"),
            ignore_path=Path(".portctlignore"),
            ci_workflow_path=Path(".github/workflows/portctl.yml"),
            exported_resources=5,
            scaffolded_templates=[],
            files_created=[],
        )
        _render_summary(console, result, "prod-org", 5, 2)
        assert console.print.called
