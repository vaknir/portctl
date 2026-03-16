"""Tests for export service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import yaml

if TYPE_CHECKING:
    from pathlib import Path

from portctl.models.blueprint import Blueprint, BlueprintProperty, BlueprintRelation
from portctl.models.scorecard import Scorecard
from portctl.services.exporter import export_all, export_blueprints, export_scorecards


def _make_mock_client(
    blueprints: list[dict[str, Any]] | None = None,
    scorecards: dict[str, list[dict[str, Any]]] | None = None,
) -> MagicMock:
    """Create a mock PortClient with predefined responses.

    Args:
        blueprints: List of blueprint dicts to return from get_blueprints.
        scorecards: Mapping of blueprint_id -> list of scorecard dicts.
    """
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
    icon: str = "Microservice",
) -> dict[str, Any]:
    """Build a sample blueprint API response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "icon": icon,
        "description": f"The {title} blueprint",
        "schema": {
            "properties": {
                "language": {"type": "string", "title": "Language"},
                "version": {"type": "string"},
            },
            "required": ["language"],
        },
        "relations": {
            "environment": {
                "target": "environment",
                "title": "Environment",
                "many": True,
                "required": False,
            },
        },
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
            {"identifier": "gold", "title": "Gold", "color": "gold"},
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


class TestExportBlueprints:
    """Tests for export_blueprints function."""

    async def test_export_blueprints_writes_yaml(self, tmp_path: Path) -> None:
        """Exported blueprints are written as YAML files."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service"), _sample_blueprint_api("environment")],
        )
        result = await export_blueprints(client, tmp_path)

        assert sorted(result) == ["environment", "service"]
        assert (tmp_path / "blueprints" / "service.yaml").exists()
        assert (tmp_path / "blueprints" / "environment.yaml").exists()

    async def test_export_blueprints_skips_internal(self, tmp_path: Path) -> None:
        """Blueprints starting with _ or $ are skipped."""
        client = _make_mock_client(
            blueprints=[
                _sample_blueprint_api("service"),
                _sample_blueprint_api("_internal"),
                _sample_blueprint_api("$system"),
            ],
        )
        result = await export_blueprints(client, tmp_path)

        assert result == ["service"]
        assert not (tmp_path / "blueprints" / "_internal.yaml").exists()
        assert not (tmp_path / "blueprints" / "$system.yaml").exists()

    async def test_export_blueprints_valid_yaml(self, tmp_path: Path) -> None:
        """Written YAML files can be parsed back and contain expected data."""
        client = _make_mock_client(blueprints=[_sample_blueprint_api()])
        await export_blueprints(client, tmp_path)

        yaml_path = tmp_path / "blueprints" / "service.yaml"
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        assert parsed["identifier"] == "service"
        assert parsed["title"] == "Service"
        assert "language" in parsed["properties"]
        assert parsed["properties"]["language"]["type"] == "string"
        assert parsed["relations"]["environment"]["target"] == "environment"

    async def test_export_blueprints_creates_directory(self, tmp_path: Path) -> None:
        """The blueprints subdirectory is created if it does not exist."""
        client = _make_mock_client(blueprints=[_sample_blueprint_api()])
        await export_blueprints(client, tmp_path)
        assert (tmp_path / "blueprints").is_dir()

    async def test_export_blueprints_empty(self, tmp_path: Path) -> None:
        """Returns empty list when no blueprints exist."""
        client = _make_mock_client(blueprints=[])
        result = await export_blueprints(client, tmp_path)
        assert result == []


class TestExportScorecards:
    """Tests for export_scorecards function."""

    async def test_export_scorecards_writes_yaml(self, tmp_path: Path) -> None:
        """Exported scorecards are written as YAML files."""
        client = _make_mock_client(
            scorecards={"service": [_sample_scorecard_api()]},
        )
        result = await export_scorecards(client, ["service"], tmp_path)

        assert result == ["production-readiness"]
        assert (tmp_path / "scorecards" / "production-readiness.yaml").exists()

    async def test_export_scorecards_groups_by_blueprint(self, tmp_path: Path) -> None:
        """Scorecards from multiple blueprints are all exported."""
        client = _make_mock_client(
            scorecards={
                "service": [_sample_scorecard_api("svc-readiness", "service")],
                "environment": [_sample_scorecard_api("env-readiness", "environment")],
            },
        )
        result = await export_scorecards(client, ["service", "environment"], tmp_path)

        assert sorted(result) == ["env-readiness", "svc-readiness"]
        assert (tmp_path / "scorecards" / "svc-readiness.yaml").exists()
        assert (tmp_path / "scorecards" / "env-readiness.yaml").exists()

    async def test_export_scorecards_valid_yaml(self, tmp_path: Path) -> None:
        """Written YAML files can be parsed back and contain expected data."""
        client = _make_mock_client(
            scorecards={"service": [_sample_scorecard_api()]},
        )
        await export_scorecards(client, ["service"], tmp_path)

        yaml_path = tmp_path / "scorecards" / "production-readiness.yaml"
        parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

        assert parsed["identifier"] == "production-readiness"
        assert parsed["blueprint"] == "service"
        assert len(parsed["levels"]) == 2
        assert len(parsed["rules"]) == 1

    async def test_export_scorecards_empty(self, tmp_path: Path) -> None:
        """Returns empty list when blueprints have no scorecards."""
        client = _make_mock_client(scorecards={"service": []})
        result = await export_scorecards(client, ["service"], tmp_path)
        assert result == []


class TestExportAll:
    """Tests for export_all orchestrator."""

    async def test_export_all_summary(self, tmp_path: Path) -> None:
        """Returns correct counts of exported resources."""
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
        summary = await export_all(client, tmp_path)

        assert summary["blueprints"] == 2
        assert summary["scorecards"] == 1

    async def test_export_all_resource_filter_blueprints(self, tmp_path: Path) -> None:
        """--resource=blueprints only exports blueprints, skips scorecards."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service")],
            scorecards={"service": [_sample_scorecard_api()]},
        )
        summary = await export_all(client, tmp_path, resource="blueprints")

        assert summary["blueprints"] == 1
        assert summary["scorecards"] == 0
        client.get_scorecards.assert_not_called()

    async def test_export_all_resource_filter_scorecards(self, tmp_path: Path) -> None:
        """--resource=scorecards only exports scorecards, skips blueprints."""
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("service")],
            scorecards={"service": [_sample_scorecard_api()]},
        )
        summary = await export_all(client, tmp_path, resource="scorecards")

        # Still fetches blueprints for the identifiers list, but doesn't write them
        assert summary["blueprints"] == 0
        assert summary["scorecards"] == 1
        assert not (tmp_path / "blueprints").exists()


class TestBlueprintModelFromApi:
    """Tests for mapping API responses to Blueprint model."""

    def test_blueprint_model_from_api(self) -> None:
        """API response dict maps correctly to Blueprint model fields."""
        api_data = _sample_blueprint_api()

        # Simulate the mapping the exporter does
        schema = api_data.get("schema", {})
        required_props = schema.get("required", [])
        properties: dict[str, BlueprintProperty] = {}
        for name, prop_data in schema.get("properties", {}).items():
            mapped = dict(prop_data)
            if name in required_props:
                mapped["required"] = True
            properties[name] = BlueprintProperty(**mapped)

        relations = {
            k: BlueprintRelation(**v)
            for k, v in api_data.get("relations", {}).items()
        }

        bp = Blueprint(
            identifier=api_data["identifier"],
            title=api_data["title"],
            icon=api_data.get("icon"),
            description=api_data.get("description"),
            properties=properties,
            relations=relations,
        )

        assert bp.identifier == "service"
        assert bp.properties["language"].required is True
        assert bp.properties["version"].required is False
        assert bp.relations["environment"].target == "environment"


class TestScorecardModelFromApi:
    """Tests for mapping API responses to Scorecard model."""

    def test_scorecard_model_from_api(self) -> None:
        """API response dict maps directly to Scorecard model."""
        api_data = _sample_scorecard_api()
        sc = Scorecard(**api_data)

        assert sc.identifier == "production-readiness"
        assert sc.blueprint == "service"
        assert len(sc.levels) == 2
        assert sc.levels[0].identifier == "bronze"
        assert len(sc.rules) == 1
        assert sc.rules[0].query.combinator == "and"
        assert sc.rules[0].query.conditions[0].property == "readme"
