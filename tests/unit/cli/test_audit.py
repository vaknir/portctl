"""Tests for audit CLI command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.models.config import OrgConfig, PortctlConfig
from portctl.services.auditor import AuditResult, DriftItem

runner = CliRunner()


def _mock_config() -> PortctlConfig:
    """Return a mock config with one org."""
    return PortctlConfig(
        default_org="prod",
        orgs={
            "prod": OrgConfig(
                name="Production",
                client_id="test-id",
                client_secret="test-secret",
                role="production",
            ),
        },
    )


def _mock_audit_no_drift() -> AuditResult:
    """Return an AuditResult with no drift."""
    return AuditResult(drifts=[])


def _mock_audit_with_drift() -> AuditResult:
    """Return an AuditResult with some drift."""
    return AuditResult(
        drifts=[
            DriftItem(
                resource_type="blueprint",
                identifier="service",
                drift_type="modified",
                diff={
                    "values_changed": {
                        "root['title']": {
                            "old_value": "Service",
                            "new_value": "Changed Service",
                        },
                    },
                },
            ),
            DriftItem(
                resource_type="blueprint",
                identifier="new-remote-bp",
                drift_type="added_remotely",
            ),
            DriftItem(
                resource_type="scorecard",
                identifier="old-card",
                drift_type="removed_remotely",
            ),
        ],
    )


class TestAuditNoDriftExit0:
    """test_audit_no_drift_exit_0 -- exit code 0, 'No drift' message."""

    def test_audit_no_drift_exit_0(self) -> None:
        """Audit exits with code 0 when there is no drift."""
        audit_result = _mock_audit_no_drift()

        with (
            patch("portctl.services.config.load_config", return_value=_mock_config()),
            patch(
                "portctl.services.config.get_org",
                return_value=_mock_config().orgs["prod"],
            ),
            patch(
                "portctl.services.auth.resolve_credentials",
                return_value=("test-id", "test-secret"),
            ),
            patch(
                "portctl.services.auditor.audit_org",
                new_callable=AsyncMock,
                return_value=audit_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["audit", "prod"])

        assert result.exit_code == 0
        assert "No drift" in result.output


class TestAuditDriftExit1:
    """test_audit_drift_exit_1 -- exit code 1 when drift found."""

    def test_audit_drift_exit_1(self) -> None:
        """Audit exits with code 1 when drift is detected."""
        audit_result = _mock_audit_with_drift()

        with (
            patch("portctl.services.config.load_config", return_value=_mock_config()),
            patch(
                "portctl.services.config.get_org",
                return_value=_mock_config().orgs["prod"],
            ),
            patch(
                "portctl.services.auth.resolve_credentials",
                return_value=("test-id", "test-secret"),
            ),
            patch(
                "portctl.services.auditor.audit_org",
                new_callable=AsyncMock,
                return_value=audit_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["audit", "prod"])

        assert result.exit_code == 1
        # Table should contain drift info
        assert "service" in result.output
        assert "drifted" in result.output


class TestAuditJsonOutput:
    """test_audit_json_output -- valid JSON output with --output json."""

    def test_audit_json_output(self) -> None:
        """Audit with --output json outputs valid JSON."""
        audit_result = _mock_audit_with_drift()

        with (
            patch("portctl.services.config.load_config", return_value=_mock_config()),
            patch(
                "portctl.services.config.get_org",
                return_value=_mock_config().orgs["prod"],
            ),
            patch(
                "portctl.services.auth.resolve_credentials",
                return_value=("test-id", "test-secret"),
            ),
            patch(
                "portctl.services.auditor.audit_org",
                new_callable=AsyncMock,
                return_value=audit_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["audit", "prod", "--output", "json"])

        # Should exit 1 because there is drift
        assert result.exit_code == 1
        # Output should contain valid JSON
        parsed = json.loads(result.output)
        assert "drifts" in parsed
        assert len(parsed["drifts"]) == 3
        assert parsed["has_drift"] is True
        assert parsed["drift_count"] == 3
