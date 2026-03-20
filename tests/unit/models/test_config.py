"""Tests for config pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from portctl.models.config import OrgConfig, PortctlConfig


class TestOrgConfig:
    """Tests for OrgConfig model validation."""

    def test_valid_org_config(self) -> None:
        """All required fields provided produces a valid model."""
        org = OrgConfig(
            name="My Org",
            client_id="abc123",
            client_secret="secret456",
        )
        assert org.name == "My Org"
        assert org.client_id == "abc123"
        assert org.client_secret == "secret456"

    def test_default_role_is_development(self) -> None:
        """Role defaults to 'development' when not specified."""
        org = OrgConfig(
            name="Dev Org",
            client_id="id",
            client_secret="secret",
        )
        assert org.role == "development"

    def test_default_api_url(self) -> None:
        """API URL defaults to the Port API base URL."""
        org = OrgConfig(
            name="Org",
            client_id="id",
            client_secret="secret",
        )
        assert org.api_url == "https://api.getport.io/v1"

    def test_custom_role(self) -> None:
        """Accepts valid role values: production, mirror, development."""
        for role in ("production", "mirror", "development"):
            org = OrgConfig(
                name="Org",
                client_id="id",
                client_secret="secret",
                role=role,
            )
            assert org.role == role

    def test_invalid_role_rejected(self) -> None:
        """Rejects role values outside the allowed literal set."""
        with pytest.raises(ValidationError):
            OrgConfig(
                name="Org",
                client_id="id",
                client_secret="secret",
                role="staging",  # type: ignore[arg-type]
            )

    def test_missing_name_rejected(self) -> None:
        """Name is required."""
        with pytest.raises(ValidationError):
            OrgConfig(
                client_id="id",
                client_secret="secret",
            )  # type: ignore[call-arg]

    def test_missing_client_id_defaults_empty(self) -> None:
        """Client ID defaults to empty string (credentials stored in keyring)."""
        org = OrgConfig(name="Org", client_secret="secret")
        assert org.client_id == ""

    def test_missing_client_secret_defaults_empty(self) -> None:
        """Client secret defaults to empty string (credentials stored in keyring)."""
        org = OrgConfig(name="Org", client_id="id")
        assert org.client_secret == ""

    def test_custom_api_url(self) -> None:
        """Accepts a custom API URL."""
        org = OrgConfig(
            name="Org",
            client_id="id",
            client_secret="secret",
            api_url="https://custom.api.io/v2",
        )
        assert org.api_url == "https://custom.api.io/v2"


class TestPortctlConfig:
    """Tests for PortctlConfig root model."""

    def test_valid_config(self) -> None:
        """Accepts a valid config with orgs and default_org."""
        config = PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id="id1",
                    client_secret="secret1",
                    role="production",
                ),
            },
        )
        assert config.default_org == "prod"
        assert "prod" in config.orgs

    def test_default_org_is_optional(self) -> None:
        """default_org can be None."""
        config = PortctlConfig(
            orgs={
                "dev": OrgConfig(
                    name="Dev",
                    client_id="id",
                    client_secret="secret",
                ),
            },
        )
        assert config.default_org is None

    def test_missing_orgs_rejected(self) -> None:
        """orgs is required."""
        with pytest.raises(ValidationError):
            PortctlConfig()  # type: ignore[call-arg]

    def test_empty_orgs_accepted(self) -> None:
        """An empty orgs dict is structurally valid."""
        config = PortctlConfig(orgs={})
        assert config.orgs == {}

    def test_multiple_orgs(self) -> None:
        """Supports multiple org entries."""
        config = PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id="id1",
                    client_secret="s1",
                    role="production",
                ),
                "dev": OrgConfig(
                    name="Development",
                    client_id="id2",
                    client_secret="s2",
                    role="development",
                ),
            },
        )
        assert len(config.orgs) == 2
