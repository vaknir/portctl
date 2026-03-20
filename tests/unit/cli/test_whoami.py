"""Tests for whoami CLI command -- output formatting and exit codes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from portctl.cli.app import app

runner = CliRunner()

SERVICE_WHOAMI = "portctl.cli.commands.whoami"


def _make_whoami_info(
    *,
    org_name: str | None = "my-org",
    org_role: str | None = "production",
    api_url: str | None = "https://api.getport.io/v1",
    credential_source: str | None = "keyring",
    authenticated: bool = True,
    is_ci: bool = False,
    ci_provider: str | None = None,
) -> MagicMock:
    """Create a mock WhoamiInfo for testing."""
    from pathlib import Path

    info = MagicMock()
    info.version = "0.1.0"
    info.org_name = org_name
    info.org_role = org_role
    info.api_url = api_url
    info.user_email = None
    info.user_name = None
    info.credential_source = credential_source
    info.config_path = Path.home() / ".portctl" / "config.yaml"
    info.state_path = Path.home() / ".portctl" / "state.yaml"
    info.is_ci = is_ci
    info.ci_provider = ci_provider
    info.authenticated = authenticated
    return info


class TestWhoamiCommand:
    """Tests for the whoami command."""

    @patch(f"{SERVICE_WHOAMI}.gather_whoami_info", new_callable=AsyncMock)
    def test_whoami_default_output(
        self,
        mock_gather: AsyncMock,
    ) -> None:
        """Outputs rich panel with identity information."""
        mock_gather.return_value = _make_whoami_info()

        result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 0
        assert "my-org" in result.output
        assert "production" in result.output
        assert "keyring" in result.output

    @patch(f"{SERVICE_WHOAMI}.gather_whoami_info", new_callable=AsyncMock)
    def test_whoami_json_output(
        self,
        mock_gather: AsyncMock,
    ) -> None:
        """--json outputs valid JSON with all fields."""
        mock_gather.return_value = _make_whoami_info()

        result = runner.invoke(app, ["whoami", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["org"] == "my-org"
        assert data["role"] == "production"
        assert data["credential_source"] == "keyring"
        assert data["authenticated"] is True
        assert data["ci"] is False

    @patch(f"{SERVICE_WHOAMI}.gather_whoami_info", new_callable=AsyncMock)
    def test_whoami_exit_code_always_zero(
        self,
        mock_gather: AsyncMock,
    ) -> None:
        """Always exits 0 even with partial info (no org, no auth)."""
        mock_gather.return_value = _make_whoami_info(
            org_name=None,
            org_role=None,
            api_url=None,
            credential_source=None,
            authenticated=False,
        )

        result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 0

    @patch(f"{SERVICE_WHOAMI}.gather_whoami_info", new_callable=AsyncMock)
    def test_whoami_json_with_no_org(
        self,
        mock_gather: AsyncMock,
    ) -> None:
        """--json handles None values gracefully."""
        mock_gather.return_value = _make_whoami_info(
            org_name=None,
            org_role=None,
            api_url=None,
            credential_source=None,
            authenticated=False,
        )

        result = runner.invoke(app, ["whoami", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["org"] is None
        assert data["authenticated"] is False
