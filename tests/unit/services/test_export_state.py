"""Tests for export state baseline recording (VAK-320)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import yaml

from portctl.services.exporter import ExportResult, export_all
from portctl.services.state import ExportStateEntry, ResourceEntry, record_export_state

if TYPE_CHECKING:
    from pathlib import Path

STATE_FILENAME = ".portctl-state.yaml"


def _make_mock_client(
    blueprints: list[dict[str, Any]] | None = None,
    scorecards: dict[str, list[dict[str, Any]]] | None = None,
) -> MagicMock:
    """Create a mock PortClient with predefined responses."""
    client = MagicMock()
    client.get_blueprints = AsyncMock(return_value=blueprints or [])

    _scorecards = scorecards or {}

    async def _get_scorecards(blueprint_id: str) -> list[dict[str, Any]]:
        return _scorecards.get(blueprint_id, [])

    client.get_scorecards = AsyncMock(side_effect=_get_scorecards)
    return client


def _sample_blueprint_api(
    identifier: str = "service",
    title: str = "Service",
) -> dict[str, Any]:
    """Build a sample blueprint API response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "icon": "Microservice",
        "description": f"The {title} blueprint",
        "schema": {
            "properties": {"language": {"type": "string", "title": "Language"}},
            "required": ["language"],
        },
        "relations": {},
        "mirrorProperties": {},
        "calculationProperties": {},
    }


def _sample_scorecard_api(
    identifier: str = "production-readiness",
    blueprint: str = "service",
) -> dict[str, Any]:
    """Build a sample scorecard API response dict."""
    return {
        "identifier": identifier,
        "title": "Production Readiness",
        "blueprint": blueprint,
        "levels": [
            {"identifier": "bronze", "title": "Bronze", "color": "orange"},
        ],
        "rules": [
            {
                "identifier": "has-readme",
                "title": "Has README",
                "level": "bronze",
                "query": {
                    "combinator": "and",
                    "conditions": [
                        {"property": "readme", "operator": "isNotEmpty"},
                    ],
                },
            },
        ],
    }


class TestExportWritesStateEntry:
    """After export, a state baseline entry is written."""

    def test_record_export_state_writes_file(self, tmp_path: Path) -> None:
        """After recording an export state, the state file exists with correct structure."""
        state_path = tmp_path / STATE_FILENAME
        entry = ExportStateEntry(
            id="initial-export",
            timestamp="2026-03-20T10:00:00Z",
            applied_by="local-user",
            via="export",
            note="Initial export -- baseline snapshot",
            changes=[
                ResourceEntry(resource_type="blueprint", identifier="service", action="imported"),
            ],
        )

        record_export_state(state_path, entry)

        assert state_path.exists()
        loaded = yaml.safe_load(state_path.read_text())
        assert isinstance(loaded, dict)
        assert "export_events" in loaded
        assert len(loaded["export_events"]) == 1
        event = loaded["export_events"][0]
        assert event["id"] == "initial-export"
        assert event["via"] == "export"
        assert event["note"] == "Initial export -- baseline snapshot"


class TestExportStateListsAllResources:
    """State entry lists all exported blueprints and scorecards."""

    def test_state_entry_lists_all_resources(self, tmp_path: Path) -> None:
        """State entry changes list includes all exported resources."""
        state_path = tmp_path / STATE_FILENAME
        entry = ExportStateEntry(
            id="initial-export",
            timestamp="2026-03-20T10:00:00Z",
            applied_by="local-user",
            via="export",
            note="Initial export -- baseline snapshot",
            changes=[
                ResourceEntry(resource_type="blueprint", identifier="service", action="imported"),
                ResourceEntry(
                    resource_type="blueprint", identifier="environment", action="imported"
                ),
                ResourceEntry(
                    resource_type="scorecard",
                    identifier="production-readiness",
                    action="imported",
                ),
            ],
        )

        record_export_state(state_path, entry)

        loaded = yaml.safe_load(state_path.read_text())
        changes = loaded["export_events"][0]["changes"]
        identifiers = [c["identifier"] for c in changes]
        assert "service" in identifiers
        assert "environment" in identifiers
        assert "production-readiness" in identifiers
        assert all(c["action"] == "imported" for c in changes)


class TestExportStateHasTimestamp:
    """State entry has a valid ISO timestamp."""

    def test_state_entry_has_valid_timestamp(self, tmp_path: Path) -> None:
        """The timestamp field parses as a valid ISO datetime."""
        state_path = tmp_path / STATE_FILENAME
        now = datetime.now(tz=UTC).isoformat()
        entry = ExportStateEntry(
            id="initial-export",
            timestamp=now,
            applied_by="local-user",
            via="export",
            note="Initial export -- baseline snapshot",
            changes=[],
        )

        record_export_state(state_path, entry)

        loaded = yaml.safe_load(state_path.read_text())
        ts = loaded["export_events"][0]["timestamp"]
        # Should not raise
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None


class TestExportStateHasViaExport:
    """State entry has via: export."""

    def test_state_entry_has_via_export(self, tmp_path: Path) -> None:
        """The via field is 'export'."""
        state_path = tmp_path / STATE_FILENAME
        entry = ExportStateEntry(
            id="initial-export",
            timestamp="2026-03-20T10:00:00Z",
            applied_by="local-user",
            via="export",
            note="Initial export -- baseline snapshot",
            changes=[],
        )

        record_export_state(state_path, entry)

        loaded = yaml.safe_load(state_path.read_text())
        assert loaded["export_events"][0]["via"] == "export"


class TestExportStateAppendsToExisting:
    """If state file exists, new entry is appended."""

    def test_appends_to_existing_state(self, tmp_path: Path) -> None:
        """A second export state entry is appended, not overwritten."""
        state_path = tmp_path / STATE_FILENAME
        entry1 = ExportStateEntry(
            id="initial-export",
            timestamp="2026-03-20T09:00:00Z",
            applied_by="user-a",
            via="export",
            note="First export",
            changes=[
                ResourceEntry(resource_type="blueprint", identifier="service", action="imported"),
            ],
        )
        entry2 = ExportStateEntry(
            id="re-export-001",
            timestamp="2026-03-20T10:00:00Z",
            applied_by="user-b",
            via="export",
            note="Second export",
            changes=[
                ResourceEntry(resource_type="blueprint", identifier="service", action="imported"),
                ResourceEntry(resource_type="blueprint", identifier="library", action="imported"),
            ],
        )

        record_export_state(state_path, entry1)
        record_export_state(state_path, entry2)

        loaded = yaml.safe_load(state_path.read_text())
        events = loaded["export_events"]
        assert len(events) == 2
        assert events[0]["id"] == "initial-export"
        assert events[1]["id"] == "re-export-001"


class TestExportStateEmptyExport:
    """If nothing was exported, state entry has empty changes list."""

    def test_empty_export_has_empty_changes(self, tmp_path: Path) -> None:
        """When no resources are exported, changes list is empty."""
        state_path = tmp_path / STATE_FILENAME
        entry = ExportStateEntry(
            id="initial-export",
            timestamp="2026-03-20T10:00:00Z",
            applied_by="local-user",
            via="export",
            note="Initial export -- baseline snapshot",
            changes=[],
        )

        record_export_state(state_path, entry)

        loaded = yaml.safe_load(state_path.read_text())
        assert loaded["export_events"][0]["changes"] == []


class TestExportAllReturnsExportResult:
    """export_all returns an ExportResult with resource identifiers."""

    async def test_export_all_returns_identifiers(self, tmp_path: Path) -> None:
        """export_all returns identifiers for all exported resources."""
        client = _make_mock_client(
            blueprints=[
                _sample_blueprint_api("service"),
                _sample_blueprint_api("environment"),
            ],
            scorecards={
                "service": [_sample_scorecard_api("svc-readiness", "service")],
                "environment": [],
            },
        )
        result = await export_all(client, tmp_path)

        assert isinstance(result, ExportResult)
        assert result.blueprint_count == 2
        assert result.scorecard_count == 1
        assert sorted(result.blueprint_ids) == ["environment", "service"]
        assert result.scorecard_ids == ["svc-readiness"]

    async def test_export_all_empty_returns_empty_lists(self, tmp_path: Path) -> None:
        """export_all with no resources returns empty identifier lists."""
        client = _make_mock_client(blueprints=[], scorecards={})
        result = await export_all(client, tmp_path)

        assert result.blueprint_count == 0
        assert result.scorecard_count == 0
        assert result.blueprint_ids == []
        assert result.scorecard_ids == []
