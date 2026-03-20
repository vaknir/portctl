"""Tests for the config guard module."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from portctl.exceptions import ConfigError
from portctl.models.config import OrgConfig, PortctlConfig


class TestRequireConfig:
    """Tests for require_config()."""

    def test_returns_config_when_exists(self) -> None:
        """Returns the loaded PortctlConfig when config file exists."""
        expected = PortctlConfig(
            default_org="my-org",
            orgs={
                "my-org": OrgConfig(
                    name="my-org",
                    client_id="test-id",
                    client_secret="test-secret",
                )
            },
        )

        with patch("portctl.cli.guard.load_config", return_value=expected):
            from portctl.cli.guard import require_config

            result = require_config()

        assert result is expected

    def test_exits_when_no_config_non_interactive(self) -> None:
        """Raises typer.Exit(code=1) when config is missing and interactive=False."""
        with (
            patch(
                "portctl.cli.guard.load_config",
                side_effect=ConfigError("Config file not found"),
            ),
            patch("portctl.cli.guard.console") as mock_console,
            pytest.raises(typer.Exit) as exc_info,
        ):
            from portctl.cli.guard import require_config

            require_config(interactive=False)

        assert exc_info.value.exit_code == 1
        mock_console.print.assert_called()
