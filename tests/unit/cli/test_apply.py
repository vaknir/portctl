"""Tests for apply CLI command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.models.config import OrgConfig, PortctlConfig
from portctl.services.applier import ApplyResourceResult, ApplyResult
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
                diff={"values_changed": {}},
            ),
            ResourceChange(
                resource_type="scorecard",
                identifier="readiness",
                action="delete",
                breaking=True,
            ),
        ],
        validation_result=None,
    )


def _mock_apply_result() -> ApplyResult:
    """Return a successful ApplyResult."""
    return ApplyResult(
        results=[
            ApplyResourceResult("blueprint", "service", "created", True),
            ApplyResourceResult("blueprint", "deployment", "updated", True),
        ],
    )


def _mock_apply_result_with_failure() -> ApplyResult:
    """Return an ApplyResult with a failure."""
    return ApplyResult(
        results=[
            ApplyResourceResult("blueprint", "service", "created", True),
            ApplyResourceResult("blueprint", "deployment", "created", False, error="API error"),
        ],
    )


class TestApplyNoChanges:
    """test_apply_no_changes -- 'Nothing to apply' + exit 0."""

    def test_apply_no_changes(self) -> None:
        """Apply exits 0 and prints 'Nothing to apply' when plan has no changes."""
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
                return_value=_mock_plan_no_changes(),
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["apply", "prod", "--yes"])

        assert result.exit_code == 0
        assert "Nothing to apply" in result.output


class TestApplyWithYesFlag:
    """test_apply_with_yes_flag -- applies without prompt."""

    def test_apply_with_yes_flag(self) -> None:
        """Apply with --yes flag skips confirmation and runs apply_org."""
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
                return_value=_mock_plan_with_changes(),
            ),
            patch(
                "portctl.services.applier.apply_org",
                new_callable=AsyncMock,
                return_value=_mock_apply_result(),
            ) as mock_apply,
            patch(
                "portctl.services.state.record_apply",
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["apply", "prod", "--yes"])

        mock_apply.assert_called_once()
        assert result.exit_code == 0


class TestApplySummary:
    """test_apply_summary -- shows correct counts."""

    def test_apply_summary(self) -> None:
        """Apply prints a summary with correct counts."""
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
                return_value=_mock_plan_with_changes(),
            ),
            patch(
                "portctl.services.applier.apply_org",
                new_callable=AsyncMock,
                return_value=_mock_apply_result(),
            ),
            patch(
                "portctl.services.state.record_apply",
            ),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(app, ["apply", "prod", "--yes"])

        assert result.exit_code == 0
        assert "1 created" in result.output
        assert "1 updated" in result.output
