"""Tests for history CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
import yaml
from typer.testing import CliRunner

from portctl.cli.app import app

runner = CliRunner()


def _write_state(tmp_path: Path, data: dict) -> None:
    """Write a .portctl-state.yaml file to tmp_path.

    Args:
        tmp_path: Temporary directory to write to.
        data: State data dict to serialise as YAML.
    """
    state_file = tmp_path / ".portctl-state.yaml"
    with state_file.open("w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


class TestHistoryNoEvents:
    """test_history_no_events -- empty state file prints 'No history'."""

    def test_history_no_events_empty_state(self, tmp_path: Path) -> None:
        """Empty state file (no export_events or apply_events) prints 'No history'."""
        _write_state(tmp_path, {})
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No history found" in result.output

    def test_history_no_events_empty_lists(self, tmp_path: Path) -> None:
        """State file with empty event lists prints 'No history'."""
        _write_state(tmp_path, {"export_events": [], "apply_events": []})
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No history found" in result.output


class TestHistoryNoStateFile:
    """test_history_no_state_file -- missing .portctl-state.yaml prints 'No history'."""

    def test_history_no_state_file(self, tmp_path: Path) -> None:
        """Missing .portctl-state.yaml exits 0 and prints 'No history'."""
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "No history found" in result.output


class TestHistoryShowsEvents:
    """test_history_shows_events -- events appear in table output."""

    def test_history_shows_export_event(self, tmp_path: Path) -> None:
        """Export events appear with correct type label and metadata."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "initial-export",
                        "timestamp": "2026-03-25T19:58:00.937816+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Initial export -- baseline snapshot",
                        "changes": [
                            {
                                "resource_type": "blueprint",
                                "identifier": "group",
                                "action": "imported",
                            }
                        ],
                    }
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "initial-export" in result.output
        assert "vaknir" in result.output
        assert "export" in result.output
        # Rich may truncate long cell values or omit columns in narrow terminals
        assert "blueprint:" in result.output
        assert "vaknir" in result.output

    def test_history_shows_apply_event(self, tmp_path: Path) -> None:
        """Apply events appear with correct type label and metadata."""
        _write_state(
            tmp_path,
            {
                "apply_events": [
                    {
                        "org": "testing",
                        "timestamp": "2026-03-25T20:00:00+00:00",
                        "git_commit": "abc123",
                        "resources_changed": ["blueprints/service.yaml"],
                    }
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "apply" in result.output
        assert "abc123" in result.output
        assert "testing" in result.output
        # Rich may truncate long cell values in narrow terminals; check the prefix
        assert "blueprints/" in result.output

    def test_history_shows_both_event_types(self, tmp_path: Path) -> None:
        """Both export and apply events appear when state has both."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "init-exp",
                        "timestamp": "2026-03-25T19:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Baseline",
                        "changes": [],
                    }
                ],
                "apply_events": [
                    {
                        "org": "prod",
                        "timestamp": "2026-03-25T20:00:00+00:00",
                        "git_commit": "deadbeef",
                        "resources_changed": [],
                    }
                ],
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "export" in result.output
        assert "apply" in result.output
        assert "init-exp" in result.output
        assert "deadbeef" in result.output

    def test_history_sorted_newest_first(self, tmp_path: Path) -> None:
        """Events are displayed newest-first (descending timestamp)."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "old-export",
                        "timestamp": "2026-03-24T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "Old",
                        "changes": [],
                    },
                    {
                        "id": "new-export",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "New",
                        "changes": [],
                    },
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        new_pos = result.output.index("new-export")
        old_pos = result.output.index("old-export")
        assert new_pos < old_pos, "Newest event should appear before older event"


class TestHistoryLimit:
    """test_history_limit -- --limit truncates output."""

    def test_history_limit_one(self, tmp_path: Path) -> None:
        """--limit 1 shows only the single most recent event."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": f"export-{i}",
                        "timestamp": f"2026-03-2{i}T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": f"Event {i}",
                        "changes": [],
                    }
                    for i in range(1, 4)
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path), "--limit", "1"])
        assert result.exit_code == 0
        # Only the most recent id should appear
        assert "export-3" in result.output
        assert "export-1" not in result.output

    def test_history_limit_default_twenty(self, tmp_path: Path) -> None:
        """Default limit of 20 shows at most 20 events from 25 available."""
        _write_state(
            tmp_path,
            {
                "apply_events": [
                    {
                        "org": "prod",
                        "timestamp": f"2026-03-01T{i:02d}:00:00+00:00",
                        "git_commit": f"commit{i:02d}",
                        "resources_changed": [],
                    }
                    for i in range(25)
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        # commit00 is the oldest; with limit=20 and descending sort it should be cut off
        assert "commit00" not in result.output
        assert "commit24" in result.output

    @pytest.mark.parametrize("limit_flag", ["-n", "--limit"])
    def test_history_limit_flag_aliases(self, tmp_path: Path, limit_flag: str) -> None:
        """Both -n and --limit flags are accepted."""
        _write_state(
            tmp_path,
            {
                "export_events": [
                    {
                        "id": "export-1",
                        "timestamp": "2026-03-25T10:00:00+00:00",
                        "applied_by": "vaknir",
                        "via": "export",
                        "note": "",
                        "changes": [],
                    }
                ]
            },
        )
        result = runner.invoke(app, ["history", "--dir", str(tmp_path), limit_flag, "5"])
        assert result.exit_code == 0
        assert "export-1" in result.output
