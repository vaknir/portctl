"""Tests for rollback CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import yaml
from typer.testing import CliRunner

from portctl.cli.app import app
from portctl.models.config import OrgConfig, PortctlConfig
from portctl.services.applier import ApplyResourceResult, ApplyResult
from portctl.services.planner import PlanResult, ResourceChange
from portctl.services.rollback import RollbackResult, RollbackTarget

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


def _write_state(tmp_path: Path, data: dict) -> None:
    """Write a .portctl-state.yaml file to tmp_path."""
    state_file = tmp_path / ".portctl-state.yaml"
    with state_file.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _mock_target(
    event_id: str = "initial-export",
    git_commit: str | None = None,
) -> RollbackTarget:
    """Return a mock RollbackTarget."""
    return RollbackTarget(
        event_id=event_id,
        timestamp="2026-03-25T10:00:00+00:00",
        git_commit=git_commit,
        via="export",
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
                action="update",
                diff={"values_changed": {}},
            ),
        ],
        validation_result=None,
    )


def _mock_rollback_result_success(target: RollbackTarget) -> RollbackResult:
    """Return a successful RollbackResult."""
    return RollbackResult(
        target=target,
        apply_result=ApplyResult(
            results=[
                ApplyResourceResult("blueprint", "service", "updated", True),
            ]
        ),
    )


def _mock_rollback_result_no_changes(target: RollbackTarget) -> RollbackResult:
    """Return a RollbackResult with no changes (already at target)."""
    return RollbackResult(target=target)


class TestRollbackTargetNotFound:
    """test_rollback_target_not_found -- unknown event ID shows error."""

    def test_rollback_target_not_found(self, tmp_path: Path) -> None:
        """Unknown event ID prints error message and exits with code 1."""
        _write_state(tmp_path, {"export_events": [], "apply_events": []})

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
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(
                app,
                ["rollback", "nonexistent-id", "--dir", str(tmp_path)],
            )

        assert result.exit_code == 1
        assert "not found" in result.output


class TestRollbackNoChanges:
    """test_rollback_no_changes -- target matches current state."""

    def test_rollback_no_changes(self, tmp_path: Path) -> None:
        """When plan shows no changes, prints 'Already at target state' and exits 0."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "initial-export",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Baseline",
                        "changes": [],
                    }
                ]
            },
        )

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

            result = runner.invoke(
                app,
                ["rollback", "initial-export", "--dir", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "Already at target state" in result.output


class TestRollbackWithConfirmation:
    """test_rollback_with_confirmation -- shows plan and asks for confirmation."""

    def test_rollback_with_yes_flag(self, tmp_path: Path) -> None:
        """Rollback with --yes flag skips confirmation and runs apply."""
        target = _mock_target()

        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "initial-export",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Baseline",
                        "changes": [],
                    }
                ]
            },
        )

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
                "portctl.services.rollback.execute_rollback",
                new_callable=AsyncMock,
                return_value=_mock_rollback_result_success(target),
            ) as mock_execute,
            patch("portctl.services.state.record_apply"),
            patch("portctl.client.port_client.PortClient") as mock_client_cls,
        ):
            mock_instance = AsyncMock()
            mock_client_cls.return_value = mock_instance
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)

            result = runner.invoke(
                app,
                ["rollback", "initial-export", "--yes", "--dir", str(tmp_path)],
            )

        mock_execute.assert_called_once()
        assert result.exit_code == 0
        assert "Rollback complete" in result.output
