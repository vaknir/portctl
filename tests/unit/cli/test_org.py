"""Tests for org CLI commands."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.exceptions import ConfigError
from portctl.models.config import OrgConfig, PortctlConfig

runner = CliRunner()


@pytest.fixture()
def two_org_config() -> PortctlConfig:
    """A PortctlConfig with two orgs, prod as default."""
    return PortctlConfig(
        default_org="prod",
        orgs={
            "prod": OrgConfig(
                name="Production",
                client_id="prod-id",
                client_secret="prod-secret",
                role="production",
                api_url="https://api.getport.io/v1",
            ),
            "dev": OrgConfig(
                name="Development",
                client_id="dev-id",
                client_secret="dev-secret",
                role="development",
                api_url="https://api.getport.io/v1",
            ),
        },
    )


@pytest.fixture()
def single_org_config() -> PortctlConfig:
    """A PortctlConfig with a single org and no default set."""
    return PortctlConfig(
        default_org=None,
        orgs={
            "staging": OrgConfig(
                name="Staging",
                client_id="staging-id",
                client_secret="staging-secret",
                role="mirror",
                api_url="https://api.getport.io/v1",
            ),
        },
    )


class TestOrgList:
    """Tests for 'portctl org list' command."""

    def test_org_list_shows_all_orgs(self, two_org_config: PortctlConfig) -> None:
        """All configured orgs appear in the table output."""
        with patch("portctl.cli.commands.org.load_config", return_value=two_org_config):
            result = runner.invoke(app, ["org", "list"])

        assert result.exit_code == 0
        assert "Production" in result.output
        assert "Development" in result.output
        assert "prod" in result.output
        assert "dev" in result.output

    def test_org_list_marks_default(self, two_org_config: PortctlConfig) -> None:
        """The default org row is marked with a '*' indicator."""
        with patch("portctl.cli.commands.org.load_config", return_value=two_org_config):
            result = runner.invoke(app, ["org", "list"])

        assert result.exit_code == 0
        assert "*" in result.output

        # The '*' should appear on the prod line, not dev
        lines = result.output.splitlines()
        prod_lines = [line for line in lines if "Production" in line or "prod" in line]
        dev_lines = [line for line in lines if "Development" in line]
        assert any("*" in line for line in prod_lines), "Default org should have '*' marker"
        assert not any("*" in line for line in dev_lines), "Non-default org should not have '*'"

    def test_org_list_shows_role_and_api_url(self, two_org_config: PortctlConfig) -> None:
        """Each org row includes its role and API URL."""
        with patch("portctl.cli.commands.org.load_config", return_value=two_org_config):
            result = runner.invoke(app, ["org", "list"])

        assert result.exit_code == 0
        assert "production" in result.output
        assert "development" in result.output
        assert "api.getport.io" in result.output

    def test_org_list_no_config(self) -> None:
        """Exits non-zero and prints an error when config cannot be loaded."""
        with patch(
            "portctl.cli.commands.org.load_config",
            side_effect=ConfigError("Config file not found"),
        ):
            result = runner.invoke(app, ["org", "list"])

        assert result.exit_code == 1
        assert "Config file not found" in result.output

    def test_org_list_empty_orgs(self) -> None:
        """Shows a 'no orgs configured' message when the org map is empty."""
        empty_config = PortctlConfig(default_org=None, orgs={})
        with patch("portctl.cli.commands.org.load_config", return_value=empty_config):
            result = runner.invoke(app, ["org", "list"])

        assert result.exit_code == 0
        assert "no orgs configured" in result.output.lower()
