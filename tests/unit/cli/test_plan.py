"""Tests for diff (plan) CLI command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.models.config import OrgConfig, PortctlConfig
from portctl.services.planner import PlanResult, ResourceChange

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


def _mock_plan_no_changes() -> PlanResult:
    """Return a PlanResult with no changes."""
    return PlanResult(changes=[], validation_result=None)


def _mock_plan_with_changes() -> PlanResult:
    """Return a PlanResult with some changes."""
    return PlanResult(
        changes=[
            ResourceChange(
                resource_type="blueprint",
                identifier="service",
                action="create",
            ),
            ResourceChange(
                resource_type="blueprint",
                identifier="deployment",
                action="update",
                diff={
                    "values_changed": {
                        "root['title']": {
                            "old_value": "Deploy",
                            "new_value": "Deployment",
                        },
                    },
                },
            ),
            ResourceChange(
                resource_type="scorecard",
                identifier="old-card",
                action="delete",
                breaking=True,
            ),
        ],
        validation_result=None,
    )


def _setup_patches(plan_result: PlanResult) -> dict[str, MagicMock | AsyncMock]:
    """Create common patches for plan CLI tests.

    Returns:
        Dict of patch context managers.
    """
    return {
        "config": patch(
            "portctl.services.config.load_config",
            return_value=_mock_config(),
        ),
        "get_org": patch(
            "portctl.services.config.get_org",
            return_value=_mock_config().orgs["prod"],
        ),
        "creds": patch(
            "portctl.services.auth.resolve_credentials",
            return_value=("test-id", "test-secret"),
        ),
        "plan": patch(
            "portctl.services.planner.plan_org",
            new_callable=AsyncMock,
            return_value=plan_result,
        ),
    }


class TestPlanNoChangesExit0:
    """test_plan_no_changes_exit_0 -- exit code 0."""

    def test_plan_no_changes_exit_0(self) -> None:
        """Plan exits with code 0 when there are no changes."""
        plan_result = _mock_plan_no_changes()

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
                "portctl.services.planner.plan_org",
                new_callable=AsyncMock,
                return_value=plan_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["diff", "prod"])

        assert result.exit_code == 0


class TestPlanWithChangesExit2:
    """test_plan_with_changes_exit_2 -- exit code 2."""

    def test_plan_with_changes_exit_2(self) -> None:
        """Plan exits with code 2 when there are changes."""
        plan_result = _mock_plan_with_changes()

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
                "portctl.services.planner.plan_org",
                new_callable=AsyncMock,
                return_value=plan_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["diff", "prod"])

        assert result.exit_code == 2


class TestPlanJsonOutput:
    """test_plan_json_output -- valid JSON output."""

    def test_plan_json_output(self) -> None:
        """Plan with --json flag outputs valid JSON."""
        plan_result = _mock_plan_with_changes()

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
                "portctl.services.planner.plan_org",
                new_callable=AsyncMock,
                return_value=plan_result,
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["diff", "prod", "--json"])

        # Should still exit 2 because there are changes
        assert result.exit_code == 2
        # Output should be valid JSON
        parsed = json.loads(result.output)
        assert "changes" in parsed
        assert len(parsed["changes"]) == 3
        assert parsed["has_changes"] is True
        assert parsed["change_count"] == 3
        assert parsed["breaking_count"] == 1
