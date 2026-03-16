"""Tests for state service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from portctl.services.state import ApplyEvent, get_last_apply, record_apply

if TYPE_CHECKING:
    from pathlib import Path


class TestRecordApply:
    """test_record_apply -- writes state file."""

    def test_record_apply(self, tmp_path: Path) -> None:
        """Recording an apply event writes it to the state file."""
        state_path = tmp_path / "state.yaml"

        event = ApplyEvent(
            org="prod",
            timestamp="2026-03-16T10:00:00Z",
            git_commit="abc1234",
            resources_changed=["blueprint:service", "scorecard:readiness"],
        )

        record_apply(state_path, event)

        assert state_path.exists()
        content = state_path.read_text()
        assert "prod" in content
        assert "abc1234" in content


class TestGetLastApply:
    """test_get_last_apply -- reads most recent event."""

    def test_get_last_apply(self, tmp_path: Path) -> None:
        """Getting last apply returns the most recent event for the org."""
        state_path = tmp_path / "state.yaml"

        event1 = ApplyEvent(
            org="prod",
            timestamp="2026-03-16T09:00:00Z",
            git_commit="aaa1111",
            resources_changed=["blueprint:old"],
        )
        event2 = ApplyEvent(
            org="prod",
            timestamp="2026-03-16T10:00:00Z",
            git_commit="bbb2222",
            resources_changed=["blueprint:new"],
        )

        record_apply(state_path, event1)
        record_apply(state_path, event2)

        last = get_last_apply(state_path, "prod")

        assert last is not None
        assert last.git_commit == "bbb2222"
        assert last.timestamp == "2026-03-16T10:00:00Z"


class TestGetLastApplyNotFound:
    """test_get_last_apply_not_found -- returns None."""

    def test_get_last_apply_not_found(self, tmp_path: Path) -> None:
        """Returns None when no state file exists."""
        state_path = tmp_path / "state.yaml"

        result = get_last_apply(state_path, "prod")

        assert result is None

    def test_get_last_apply_wrong_org(self, tmp_path: Path) -> None:
        """Returns None when org has no recorded events."""
        state_path = tmp_path / "state.yaml"

        event = ApplyEvent(
            org="staging",
            timestamp="2026-03-16T10:00:00Z",
            git_commit="abc1234",
            resources_changed=["blueprint:service"],
        )
        record_apply(state_path, event)

        result = get_last_apply(state_path, "prod")

        assert result is None
