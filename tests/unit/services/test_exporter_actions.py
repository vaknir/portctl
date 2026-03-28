"""Tests for export_actions, export_pages, and ExportResult with action/page support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import yaml

if TYPE_CHECKING:
    from pathlib import Path

from portctl.models.action import Action
from portctl.models.page import Page
from portctl.services.exporter import (
    ExportResult,
    export_actions,
    export_all,
    export_pages,
)


def _make_mock_client(
    blueprints: list[dict[str, Any]] | None = None,
    scorecards: dict[str, list[dict[str, Any]]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    pages: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock PortClient with predefined responses.

    Args:
        blueprints: List of blueprint dicts to return from get_blueprints.
        scorecards: Mapping of blueprint_id -> list of scorecard dicts.
        actions: Flat list of all action dicts to return from get_actions.
        pages: List of page dicts to return from get_pages.
    """
    client = MagicMock()
    client.get_blueprints = AsyncMock(return_value=blueprints or [])
    client.get_pages = AsyncMock(return_value=pages or [])

    _scorecards = scorecards or {}

    async def _get_scorecards(blueprint_id: str) -> list[dict[str, Any]]:
        return _scorecards.get(blueprint_id, [])

    client.get_scorecards = AsyncMock(side_effect=_get_scorecards)

    client.get_actions = AsyncMock(return_value=actions or [])
    return client


def _sample_blueprint_api(
    identifier: str = "service",
    title: str = "Service",
) -> dict[str, Any]:
    """Build a minimal sample blueprint API response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "schema": {"properties": {}, "required": []},
        "relations": {},
        "mirrorProperties": {},
        "calculationProperties": {},
    }


def _sample_action_api(
    identifier: str = "deploy-service",
    blueprint: str = "service",
) -> dict[str, Any]:
    """Build a sample action API response dict."""
    return {
        "identifier": identifier,
        "title": "Deploy Service",
        "blueprint": blueprint,
        "trigger": {
            "type": "self-service",
            "operation": "DAY-2",
        },
        "invocationMethod": {
            "type": "WEBHOOK",
            "url": "https://example.com/deploy",
        },
        "userInputs": {
            "properties": {
                "environment": {"type": "string", "title": "Environment"},
            },
        },
        "requiredApproval": False,
    }


def _sample_page_api(
    identifier: str = "service-overview",
    title: str = "Service Overview",
) -> dict[str, Any]:
    """Build a sample page API response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "type": "dashboard",
        "icon": "Service",
        "widgets": [
            {
                "type": "table-entities-explorer",
                "title": "Services",
                "blueprint": "service",
            },
        ],
    }


class TestExportActions:
    """Tests for export_actions function."""

    async def test_export_actions_writes_yaml(self, tmp_path: Path) -> None:
        """Exported actions are written as YAML files."""
        client = _make_mock_client(
            actions=[_sample_action_api()],
        )
        result = await export_actions(client, tmp_path)

        assert result == ["deploy-service"]
        assert (tmp_path / "actions" / "deploy-service.yaml").exists()

    async def test_export_actions_multiple_blueprints(self, tmp_path: Path) -> None:
        """Actions from multiple blueprints are all exported."""
        client = _make_mock_client(
            actions=[
                _sample_action_api("deploy-svc", "service"),
                _sample_action_api("create-env", "environment"),
            ],
        )
        result = await export_actions(client, tmp_path)

        assert sorted(result) == ["create-env", "deploy-svc"]
        assert (tmp_path / "actions" / "deploy-svc.yaml").exists()
        assert (tmp_path / "actions" / "create-env.yaml").exists()

    async def test_export_actions_valid_yaml(self, tmp_path: Path) -> None:
        """Written YAML files can be parsed back and contain expected data."""
        client = _make_mock_client(
            actions=[_sample_action_api()],
        )
        await export_actions(client, tmp_path)

        yaml_path = tmp_path / "actions" / "deploy-service.yaml"
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        assert parsed["identifier"] == "deploy-service"
        assert parsed["title"] == "Deploy Service"
        assert parsed["blueprint"] == "service"

    async def test_export_actions_empty(self, tmp_path: Path) -> None:
        """Returns empty list when there are no actions."""
        client = _make_mock_client(actions=[])
        result = await export_actions(client, tmp_path)
        assert result == []

    async def test_export_actions_creates_directory(self, tmp_path: Path) -> None:
        """The actions subdirectory is created if it does not exist."""
        client = _make_mock_client(
            actions=[_sample_action_api()],
        )
        await export_actions(client, tmp_path)
        assert (tmp_path / "actions").is_dir()


class TestExportPages:
    """Tests for export_pages function."""

    async def test_export_pages_writes_yaml(self, tmp_path: Path) -> None:
        """Exported pages are written as YAML files."""
        client = _make_mock_client(pages=[_sample_page_api()])
        result = await export_pages(client, tmp_path)

        assert result == ["service-overview"]
        assert (tmp_path / "pages" / "service-overview.yaml").exists()

    async def test_export_pages_multiple(self, tmp_path: Path) -> None:
        """Multiple pages are all exported."""
        client = _make_mock_client(
            pages=[
                _sample_page_api("overview", "Overview"),
                _sample_page_api("dashboard", "Dashboard"),
            ],
        )
        result = await export_pages(client, tmp_path)

        assert sorted(result) == ["dashboard", "overview"]

    async def test_export_pages_valid_yaml(self, tmp_path: Path) -> None:
        """Written YAML files can be parsed back and contain expected data."""
        client = _make_mock_client(pages=[_sample_page_api()])
        await export_pages(client, tmp_path)

        yaml_path = tmp_path / "pages" / "service-overview.yaml"
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        assert parsed["identifier"] == "service-overview"
        assert parsed["title"] == "Service Overview"
        assert parsed["type"] == "dashboard"
        assert len(parsed["widgets"]) == 1

    async def test_export_pages_empty(self, tmp_path: Path) -> None:
        """Returns empty list when no pages exist."""
        client = _make_mock_client(pages=[])
        result = await export_pages(client, tmp_path)
        assert result == []

    async def test_export_pages_creates_directory(self, tmp_path: Path) -> None:
        """The pages subdirectory is created if it does not exist."""
        client = _make_mock_client(pages=[_sample_page_api()])
        await export_pages(client, tmp_path)
        assert (tmp_path / "pages").is_dir()


class TestExportResultActionPages:
    """Tests for ExportResult with action and page support."""

    def test_export_result_counts(self) -> None:
        """ExportResult correctly counts actions and pages."""
        result = ExportResult(
            blueprint_ids=["svc"],
            scorecard_ids=["sc1", "sc2"],
            action_ids=["act1"],
            page_ids=["pg1", "pg2", "pg3"],
        )
        assert result.blueprint_count == 1
        assert result.scorecard_count == 2
        assert result.action_count == 1
        assert result.page_count == 3

    def test_export_result_summary(self) -> None:
        """to_summary includes all resource types."""
        result = ExportResult(
            blueprint_ids=["svc"],
            scorecard_ids=[],
            action_ids=["a1"],
            page_ids=["p1"],
        )
        summary = result.to_summary()
        assert summary == {
            "blueprints": 1,
            "scorecards": 0,
            "actions": 1,
            "pages": 1,
        }

    def test_export_result_empty(self) -> None:
        """Default ExportResult has zero counts for all types."""
        result = ExportResult()
        assert result.action_count == 0
        assert result.page_count == 0


class TestExportAllActionsPages:
    """Tests for export_all with actions and pages."""

    async def test_export_all_includes_actions_and_pages(self, tmp_path: Path) -> None:
        """export_all exports all resource types."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service")],
            scorecards={"service": []},
            actions=[_sample_action_api()],
            pages=[_sample_page_api()],
        )
        result = await export_all(client, tmp_path)

        assert result.blueprint_count == 1
        assert result.action_count == 1
        assert result.page_count == 1

    async def test_export_all_resource_filter_actions(self, tmp_path: Path) -> None:
        """--resource=actions only exports actions."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service")],
            actions=[_sample_action_api()],
            pages=[_sample_page_api()],
        )
        result = await export_all(client, tmp_path, resource="actions")

        assert result.action_count == 1
        assert result.blueprint_count == 0
        assert result.page_count == 0

    async def test_export_all_resource_filter_pages(self, tmp_path: Path) -> None:
        """--resource=pages only exports pages."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service")],
            pages=[_sample_page_api()],
        )
        result = await export_all(client, tmp_path, resource="pages")

        assert result.page_count == 1
        assert result.blueprint_count == 0
        assert result.action_count == 0
        client.get_actions.assert_not_called()


class TestActionModel:
    """Tests for the Action pydantic model."""

    def test_action_model_from_mapped_data(self) -> None:
        """Action model accepts mapped API data."""
        action = Action(
            identifier="deploy-service",
            title="Deploy Service",
            blueprint="service",
            trigger={"type": "self-service"},
            invocation_method={"type": "WEBHOOK", "url": "https://example.com"},
            user_properties={"env": {"type": "string"}},
        )
        assert action.identifier == "deploy-service"
        assert action.blueprint == "service"

    def test_action_model_minimal(self) -> None:
        """Action model works with only required fields."""
        action = Action(
            identifier="test",
            title="Test",
            blueprint="svc",
        )
        assert action.trigger == {}
        assert action.invocation_method is None
        assert action.user_properties == {}


class TestPageModel:
    """Tests for the Page pydantic model."""

    def test_page_model_from_mapped_data(self) -> None:
        """Page model accepts mapped API data."""
        page = Page(
            identifier="overview",
            title="Overview",
            type="dashboard",
            icon="Home",
            widgets=[{"type": "table", "title": "Services"}],
        )
        assert page.identifier == "overview"
        assert page.type == "dashboard"
        assert len(page.widgets) == 1

    def test_page_model_minimal(self) -> None:
        """Page model works with only required fields."""
        page = Page(identifier="test", title="Test")
        assert page.type is None
        assert page.widgets == []
        assert page.locked is False
