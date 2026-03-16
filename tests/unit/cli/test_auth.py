"""Tests for auth CLI commands -- login and status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from portctl.cli.app import app

runner = CliRunner()

SERVICE_AUTH = "portctl.cli.commands.auth"


def _write_config(tmp_path: object, config_data: dict[str, object]) -> str:
    """Write a config YAML file and return its path as a string."""
    from pathlib import Path

    path = Path(str(tmp_path)) / "config.yaml"
    path.write_text(yaml.dump(config_data))
    return str(path)


@pytest.fixture()
def valid_config() -> dict[str, object]:
    """Return a valid config dict."""
    return {
        "default_org": "prod",
        "orgs": {
            "prod": {
                "name": "Production",
                "client_id": "cfg-id",
                "client_secret": "cfg-secret",
                "role": "production",
                "api_url": "https://api.getport.io/v1",
            },
        },
    }


class TestLoginCommand:
    """Tests for the auth login command."""

    @patch(f"{SERVICE_AUTH}.verify_token", new_callable=AsyncMock)
    @patch(f"{SERVICE_AUTH}.store_credentials")
    @patch(f"{SERVICE_AUTH}.load_config")
    def test_login_with_flags(
        self,
        mock_load_config: MagicMock,
        mock_store: MagicMock,
        mock_verify: AsyncMock,
    ) -> None:
        """Non-interactive login with --client-id and --client-secret flags works."""
        from portctl.models.config import OrgConfig, PortctlConfig

        mock_load_config.return_value = PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id="old-id",
                    client_secret="old-secret",
                    role="production",
                ),
            },
        )
        mock_verify.return_value = {"id": "user-1", "email": "test@example.com"}

        result = runner.invoke(
            app,
            [
                "auth",
                "login",
                "--client-id",
                "my-id",
                "--client-secret",
                "my-secret",
            ],
        )

        assert result.exit_code == 0
        assert "Authenticated" in result.output or "authenticated" in result.output.lower()
        mock_verify.assert_called_once()

    @patch(f"{SERVICE_AUTH}.verify_token", new_callable=AsyncMock)
    @patch(f"{SERVICE_AUTH}.store_credentials")
    @patch(f"{SERVICE_AUTH}.load_config")
    def test_login_stores_credentials(
        self,
        mock_load_config: MagicMock,
        mock_store: MagicMock,
        mock_verify: AsyncMock,
    ) -> None:
        """Credentials are stored in keyring after successful login."""
        from portctl.models.config import OrgConfig, PortctlConfig

        mock_load_config.return_value = PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id="old-id",
                    client_secret="old-secret",
                    role="production",
                ),
            },
        )
        mock_verify.return_value = {"id": "user-1", "email": "test@example.com"}

        runner.invoke(
            app,
            [
                "auth",
                "login",
                "--client-id",
                "store-id",
                "--client-secret",
                "store-secret",
            ],
        )

        mock_store.assert_called_once_with("prod", "store-id", "store-secret")


class TestStatusCommand:
    """Tests for the auth status command."""

    @patch(f"{SERVICE_AUTH}.verify_token", new_callable=AsyncMock)
    @patch(f"{SERVICE_AUTH}.resolve_credentials")
    @patch(f"{SERVICE_AUTH}.load_config")
    def test_status_authenticated(
        self,
        mock_load_config: MagicMock,
        mock_resolve: MagicMock,
        mock_verify: AsyncMock,
    ) -> None:
        """Shows authenticated status when credentials are valid."""
        from portctl.models.config import OrgConfig, PortctlConfig

        mock_load_config.return_value = PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id="cfg-id",
                    client_secret="cfg-secret",
                    role="production",
                ),
            },
        )
        mock_resolve.return_value = ("cid", "csecret")
        mock_verify.return_value = {"id": "user-1", "email": "test@example.com"}

        result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "authenticated" in result.output.lower()

    @patch(f"{SERVICE_AUTH}.resolve_credentials")
    @patch(f"{SERVICE_AUTH}.load_config")
    def test_status_not_configured(
        self,
        mock_load_config: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """Exits non-zero when no credentials are configured."""
        from portctl.exceptions import AuthError
        from portctl.models.config import PortctlConfig

        mock_load_config.return_value = PortctlConfig(
            default_org=None,
            orgs={},
        )
        mock_resolve.side_effect = AuthError("No credentials found for org 'prod'")

        result = runner.invoke(app, ["auth", "status", "--org", "prod"])

        assert result.exit_code != 0
