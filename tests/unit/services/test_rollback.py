"""Tests for the rollback service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from portctl.services.rollback import (
    find_rollback_target,
    get_available_targets,
)

if TYPE_CHECKING:
    from pathlib import Path

STATE_FILENAME = ".portctl-state.yaml"


def _write_state(tmp_path: Path, data: dict[str, Any]) -> Path:
    """Write a .portctl-state.yaml file and return its path.

    Args:
        tmp_path: Temporary directory to write to.
        data: State data dict to serialise as YAML.

    Returns:
        Path to the written state file.
    """
    state_file = tmp_path / STATE_FILENAME
    with state_file.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return state_file


class TestFindRollbackTargetFound:
    """find_rollback_target returns a target when ID matches an export event."""

    def test_find_rollback_target_found(self, tmp_path: Path) -> None:
        """Finds an export event by its id field."""
        state_path = _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "initial-export",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Baseline",
                        "changes": [
                            {
                                "resource_type": "blueprint",
                                "identifier": "service",
                                "action": "imported",
                            }
                        ],
                    }
                ]
            },
        )

        target = find_rollback_target(state_path, "initial-export")

        assert target is not None
        assert target.event_id == "initial-export"
        assert target.timestamp == "2026-03-25T10:00:00+00:00"
        assert target.via == "export"
        assert target.git_commit is None


class TestFindRollbackTargetNotFound:
    """find_rollback_target returns None for an unknown event ID."""

    def test_find_rollback_target_not_found(self, tmp_path: Path) -> None:
        """Returns None when no event matches the given ID."""
        state_path = _write_state(
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

        target = find_rollback_target(state_path, "nonexistent-id")

        assert target is None

    def test_find_rollback_target_not_found_empty_state(self, tmp_path: Path) -> None:
        """Returns None when the state file is empty."""
        state_path = _write_state(tmp_path, {})

        target = find_rollback_target(state_path, "any-id")

        assert target is None

    def test_find_rollback_target_not_found_no_file(self, tmp_path: Path) -> None:
        """Returns None when the state file does not exist."""
        state_path = tmp_path / STATE_FILENAME

        target = find_rollback_target(state_path, "any-id")

        assert target is None


class TestFindRollbackTargetInApplyEvents:
    """find_rollback_target searches apply_events by git_commit."""

    def test_find_rollback_target_in_apply_events(self, tmp_path: Path) -> None:
        """Finds an apply event by its git_commit field."""
        state_path = _write_state(
            tmp_path,
            {
                "apply_events": [
                    {
                        "org": "prod",
                        "timestamp": "2026-03-25T20:00:00+00:00",
                        "git_commit": "abc123",
                        "resources_changed": ["blueprint:service"],
                    }
                ]
            },
        )

        target = find_rollback_target(state_path, "abc123")

        assert target is not None
        assert target.event_id == "abc123"
        assert target.git_commit == "abc123"
        assert target.via == "apply"
        assert target.timestamp == "2026-03-25T20:00:00+00:00"

    def test_find_rollback_target_apply_by_org(self, tmp_path: Path) -> None:
        """Falls back to org field when git_commit is None."""
        state_path = _write_state(
            tmp_path,
            {
                "apply_events": [
                    {
                        "org": "staging",
                        "timestamp": "2026-03-25T20:00:00+00:00",
                        "git_commit": None,
                        "resources_changed": [],
                    }
                ]
            },
        )

        target = find_rollback_target(state_path, "staging")

        assert target is not None
        assert target.event_id == "staging"
        assert target.git_commit is None
        assert target.via == "apply"


class TestGetAvailableTargets:
    """get_available_targets returns all events as rollback targets."""

    def test_get_available_targets(self, tmp_path: Path) -> None:
        """Returns targets from both export and apply events, sorted by timestamp."""
        state_path = _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "old-export",
                        "timestamp": "2026-03-24T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Old baseline",
                        "changes": [],
                    },
                ],
                "apply_events": [
                    {
                        "org": "prod",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "git_commit": "deadbeef",
                        "resources_changed": ["blueprint:service"],
                    },
                ],
            },
        )

        targets = get_available_targets(state_path)

        assert len(targets) == 2
        # Newest first
        assert targets[0].event_id == "deadbeef"
        assert targets[0].via == "apply"
        assert targets[1].event_id == "old-export"
        assert targets[1].via == "export"


class TestGetAvailableTargetsEmpty:
    """get_available_targets returns empty list for empty or missing state."""

    def test_get_available_targets_empty_state(self, tmp_path: Path) -> None:
        """Empty state file yields empty list."""
        state_path = _write_state(tmp_path, {})

        targets = get_available_targets(state_path)

        assert targets == []

    def test_get_available_targets_no_file(self, tmp_path: Path) -> None:
        """Missing state file yields empty list."""
        state_path = tmp_path / STATE_FILENAME

        targets = get_available_targets(state_path)

        assert targets == []
