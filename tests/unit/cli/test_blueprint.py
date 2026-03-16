"""Tests for blueprint CLI commands -- show."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.exceptions import PortAPIError
from portctl.models.config import OrgConfig, PortctlConfig

runner = CliRunner()

CMD_MODULE = "portctl.cli.commands.blueprint"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BLUEPRINT_DATA: dict = {
    "identifier": "service",
    "title": "Microservice",
    "icon": "Microservice",
    "description": "A microservice component",
    "schema": {
        "properties": {
            "language": {"type": "string", "title": "Language"},
        },
        "required": ["language"],
    },
    "relations": {
        "team": {"target": "team", "title": "Team", "many": False},
    },
}


@pytest.fixture()
def prod_config() -> PortctlConfig:
    """A PortctlConfig with a single production org."""
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
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBlueprintShowSuccess:
    """blueprint show renders the blueprint when it is found."""

    @patch(f"{CMD_MODULE}.PortClient")
    @patch(f"{CMD_MODULE}.resolve_credentials")
    @patch(f"{CMD_MODULE}.load_config")
    def test_blueprint_show_success(
        self,
        mock_load_config: MagicMock,
        mock_resolve_credentials: MagicMock,
        mock_port_client_cls: MagicMock,
        prod_config: PortctlConfig,
    ) -> None:
        """Renders the blueprint detail view on success."""
        mock_load_config.return_value = prod_config
        mock_resolve_credentials.return_value = ("prod-id", "prod-secret")

        mock_client = AsyncMock()
        mock_client.get_blueprint = AsyncMock(return_value=BLUEPRINT_DATA)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_port_client_cls.return_value = mock_client

        result = runner.invoke(app, ["blueprint", "show", "service"])

        assert result.exit_code == 0
        assert "Microservice" in result.output or "service" in result.output

    @patch(f"{CMD_MODULE}.PortClient")
    @patch(f"{CMD_MODULE}.resolve_credentials")
    @patch(f"{CMD_MODULE}.load_config")
    def test_blueprint_show_with_org_flag(
        self,
        mock_load_config: MagicMock,
        mock_resolve_credentials: MagicMock,
        mock_port_client_cls: MagicMock,
        prod_config: PortctlConfig,
    ) -> None:
        """--org flag selects the correct organization."""
        mock_load_config.return_value = prod_config
        mock_resolve_credentials.return_value = ("prod-id", "prod-secret")

        mock_client = AsyncMock()
        mock_client.get_blueprint = AsyncMock(return_value=BLUEPRINT_DATA)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_port_client_cls.return_value = mock_client

        result = runner.invoke(app, ["blueprint", "show", "service", "--org", "prod"])

        assert result.exit_code == 0
        mock_resolve_credentials.assert_called_once_with("prod", prod_config)


class TestBlueprintShowNotFound:
    """blueprint show exits 1 with an error message when blueprint not found."""

    @patch(f"{CMD_MODULE}.PortClient")
    @patch(f"{CMD_MODULE}.resolve_credentials")
    @patch(f"{CMD_MODULE}.load_config")
    def test_blueprint_show_not_found(
        self,
        mock_load_config: MagicMock,
        mock_resolve_credentials: MagicMock,
        mock_port_client_cls: MagicMock,
        prod_config: PortctlConfig,
    ) -> None:
        """Prints 'Blueprint X not found' message and exits with code 1."""
        mock_load_config.return_value = prod_config
        mock_resolve_credentials.return_value = ("prod-id", "prod-secret")

        mock_client = AsyncMock()
        mock_client.get_blueprint = AsyncMock(
            side_effect=PortAPIError(status_code=404, detail="Blueprint not found")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_port_client_cls.return_value = mock_client

        result = runner.invoke(app, ["blueprint", "show", "no-such-blueprint"])

        assert result.exit_code == 1
        assert "no-such-blueprint" in result.output
        assert "not found" in result.output.lower()


class TestBlueprintShowJson:
    """blueprint show --json emits raw JSON."""

    @patch(f"{CMD_MODULE}.PortClient")
    @patch(f"{CMD_MODULE}.resolve_credentials")
    @patch(f"{CMD_MODULE}.load_config")
    def test_blueprint_show_json(
        self,
        mock_load_config: MagicMock,
        mock_resolve_credentials: MagicMock,
        mock_port_client_cls: MagicMock,
        prod_config: PortctlConfig,
    ) -> None:
        """--json flag outputs valid JSON instead of the rich view."""
        mock_load_config.return_value = prod_config
        mock_resolve_credentials.return_value = ("prod-id", "prod-secret")

        mock_client = AsyncMock()
        mock_client.get_blueprint = AsyncMock(return_value=BLUEPRINT_DATA)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_port_client_cls.return_value = mock_client

        result = runner.invoke(app, ["blueprint", "show", "service", "--json"])

        assert result.exit_code == 0
        # Output should be valid JSON containing the blueprint identifier
        parsed = json.loads(result.output)
        assert parsed["identifier"] == "service"
