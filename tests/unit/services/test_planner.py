"""Tests for plan service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

if TYPE_CHECKING:
    from pathlib import Path

import yaml

from portctl.services.planner import PlanResult, ResourceChange, plan_org


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


def _sample_blueprint_yaml(
    identifier: str = "service",
    title: str = "Service",
    icon: str = "Microservice",
) -> dict[str, Any]:
    """Build a sample blueprint YAML dict (local file format)."""
    return {
        "identifier": identifier,
        "title": title,
        "icon": icon,
        "description": f"The {title} blueprint",
        "properties": {
            "language": {
                "type": "string",
                "title": "Language",
                "required": True,
            },
            "version": {"type": "string"},
        },
        "relations": {
            "environment": {
                "target": "environment",
                "title": "Environment",
                "many": True,
                "required": False,
            },
        },
    }


def _sample_blueprint_api(
    identifier: str = "service",
    title: str = "Service",
    icon: str = "Microservice",
) -> dict[str, Any]:
    """Build a sample blueprint API response dict (remote format)."""
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


def _sample_scorecard_yaml(
    identifier: str = "production-readiness",
    blueprint: str = "service",
) -> dict[str, Any]:
    """Build a sample scorecard YAML dict (local file format)."""
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
                "identifier": "has-language",
                "title": "Has Language",
                "level": "Bronze",
                "query": {
                    "combinator": "and",
                    "conditions": [
                        {"property": "language", "operator": "isNotEmpty"},
                    ],
                },
            },
        ],
    }


def _sample_scorecard_api(
    identifier: str = "production-readiness",
    blueprint: str = "service",
) -> dict[str, Any]:
    """Build a sample scorecard API response dict (remote format).

    Scorecards have the same format in API and local YAML.
    """
    return _sample_scorecard_yaml(identifier, blueprint)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict as YAML to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


class TestPlanNoChanges:
    """test_plan_no_changes -- identical local and remote, no changes."""

    async def test_plan_no_changes(self, tmp_path: Path) -> None:
        """When local and remote are identical, plan returns no changes."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await plan_org(client, tmp_path)

        assert not result.has_changes
        assert result.change_count == 0
        assert len(result.changes) == 0


class TestPlanCreateBlueprint:
    """test_plan_create_blueprint -- local exists, remote doesn't -> create."""

    async def test_plan_create_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that exists locally but not remotely is a create."""
        bp_data = _sample_blueprint_yaml("new-service")
        _write_yaml(tmp_path / "blueprints" / "new-service.yaml", bp_data)

        client = _make_mock_client(blueprints=[], scorecards={})

        result = await plan_org(client, tmp_path)

        assert result.has_changes
        assert len(result.creates) == 1
        assert result.creates[0].identifier == "new-service"
        assert result.creates[0].action == "create"
        assert result.creates[0].resource_type == "blueprint"


class TestPlanUpdateBlueprint:
    """test_plan_update_blueprint -- local differs from remote -> update with diff."""

    async def test_plan_update_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that differs between local and remote is an update."""
        bp_data = _sample_blueprint_yaml()
        bp_data["title"] = "Updated Service"
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await plan_org(client, tmp_path)

        assert result.has_changes
        assert len(result.updates) == 1
        assert result.updates[0].identifier == "service"
        assert result.updates[0].action == "update"
        assert result.updates[0].diff is not None


class TestPlanDeleteBlueprint:
    """test_plan_delete_blueprint -- remote exists, local doesn't -> delete (breaking)."""

    async def test_plan_delete_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that exists remotely but not locally is a delete (breaking)."""
        # Create blueprints dir but no files
        (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("old-service")],
            scorecards={"old-service": []},
        )

        result = await plan_org(client, tmp_path)

        assert result.has_changes
        assert len(result.deletes) == 1
        assert result.deletes[0].identifier == "old-service"
        assert result.deletes[0].action == "delete"
        assert result.deletes[0].breaking is True


class TestPlanCreateScorecard:
    """test_plan_create_scorecard -- new scorecard."""

    async def test_plan_create_scorecard(self, tmp_path: Path) -> None:
        """A scorecard that exists locally but not remotely is a create."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_data = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await plan_org(client, tmp_path)

        scorecard_creates = [
            c for c in result.creates if c.resource_type == "scorecard"
        ]
        assert len(scorecard_creates) == 1
        assert scorecard_creates[0].identifier == "production-readiness"


class TestPlanMixedChanges:
    """test_plan_mixed_changes -- creates + updates + deletes in one plan."""

    async def test_plan_mixed_changes(self, tmp_path: Path) -> None:
        """Plan correctly identifies creates, updates, and deletes together."""
        # Local: new-bp (create), service (update), scorecard (create)
        new_bp = _sample_blueprint_yaml("new-bp", "New Blueprint")
        _write_yaml(tmp_path / "blueprints" / "new-bp.yaml", new_bp)

        changed_bp = _sample_blueprint_yaml("service")
        changed_bp["title"] = "Changed Service"
        _write_yaml(tmp_path / "blueprints" / "service.yaml", changed_bp)

        sc_data = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        # Remote: service (existing), old-bp (to delete)
        client = _make_mock_client(
            blueprints=[
                _sample_blueprint_api("service"),
                _sample_blueprint_api("old-bp", "Old Blueprint"),
            ],
            scorecards={"service": [], "old-bp": []},
        )

        result = await plan_org(client, tmp_path)

        assert result.has_changes
        assert len(result.creates) == 2  # new-bp + scorecard
        assert len(result.updates) == 1  # service
        assert len(result.deletes) == 1  # old-bp


class TestPlanResourceFilter:
    """test_plan_resource_filter -- only shows blueprints when filtered."""

    async def test_plan_resource_filter(self, tmp_path: Path) -> None:
        """When resource_filter is set, only that resource type is shown."""
        bp_data = _sample_blueprint_yaml("new-bp")
        _write_yaml(tmp_path / "blueprints" / "new-bp.yaml", bp_data)

        # Also write a scorecard that references new-bp so validation passes
        sc_data = _sample_scorecard_yaml(blueprint="new-bp")
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        client = _make_mock_client(blueprints=[], scorecards={})

        result = await plan_org(client, tmp_path, resource_filter="blueprints")

        assert all(c.resource_type == "blueprint" for c in result.changes)
        assert len(result.changes) == 1


class TestPlanValidationFailure:
    """test_plan_validation_failure -- validation errors abort plan."""

    async def test_plan_validation_failure(self, tmp_path: Path) -> None:
        """Plan aborts with validation result when Layer 1 has errors."""
        # Write invalid YAML (missing required fields)
        _write_yaml(tmp_path / "blueprints" / "bad.yaml", {"bad": "data"})

        client = _make_mock_client(blueprints=[])

        result = await plan_org(client, tmp_path)

        assert result.validation_result is not None
        assert result.validation_result.has_errors
        assert len(result.changes) == 0


class TestPlanResultProperties:
    """test_plan_result_properties -- has_changes, change_count, breaking_count."""

    def test_plan_result_empty(self) -> None:
        """Empty PlanResult reports no changes."""
        result = PlanResult(changes=[])
        assert not result.has_changes
        assert result.change_count == 0
        assert result.breaking_count == 0

    def test_plan_result_with_changes(self) -> None:
        """PlanResult correctly counts changes and breaking changes."""
        changes = [
            ResourceChange(
                resource_type="blueprint",
                identifier="svc",
                action="create",
            ),
            ResourceChange(
                resource_type="blueprint",
                identifier="old",
                action="delete",
                breaking=True,
            ),
            ResourceChange(
                resource_type="scorecard",
                identifier="sc",
                action="update",
                diff={"title": {"old": "A", "new": "B"}},
            ),
        ]
        result = PlanResult(changes=changes)
        assert result.has_changes
        assert result.change_count == 3
        assert result.breaking_count == 1
        assert len(result.creates) == 1
        assert len(result.updates) == 1
        assert len(result.deletes) == 1


class TestPlanUnchangedNotShown:
    """test_plan_unchanged_not_shown -- unchanged resources not in changes list."""

    async def test_plan_unchanged_not_shown(self, tmp_path: Path) -> None:
        """Unchanged resources are not included in the changes list."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await plan_org(client, tmp_path)

        assert not result.has_changes
        # No "unchanged" actions in the changes list
        assert all(c.action != "unchanged" for c in result.changes)


class TestPlanUpdateShowsDiff:
    """test_plan_update_shows_diff -- diff contains property-level changes."""

    async def test_plan_update_shows_diff(self, tmp_path: Path) -> None:
        """Update changes include a diff dict with property-level details."""
        bp_data = _sample_blueprint_yaml()
        bp_data["description"] = "Changed description"
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await plan_org(client, tmp_path)

        assert len(result.updates) == 1
        update = result.updates[0]
        assert update.diff is not None
        # The diff should contain something about the description change
        assert len(update.diff) > 0


class TestPlanScorecardRuleNormalization:
    """Tests for _normalize_for_diff rule normalization on scorecards."""

    async def test_api_injected_description_produces_no_diff(self, tmp_path: Path) -> None:
        """Scorecard rules with API-injected description on remote but not local produce no diff."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_local = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_local)

        # Remote scorecard has API-injected 'description' on rules
        sc_remote = _sample_scorecard_api()
        for rule in sc_remote["rules"]:
            rule["description"] = "Auto-generated description from API"

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [sc_remote]},
        )

        result = await plan_org(client, tmp_path)

        scorecard_updates = [c for c in result.updates if c.resource_type == "scorecard"]
        assert len(scorecard_updates) == 0

    async def test_rules_different_order_no_diff(self, tmp_path: Path) -> None:
        """Rules in different order between local/remote produce no change."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_local = _sample_scorecard_yaml()
        sc_local["rules"] = [
            {
                "identifier": "rule-b",
                "title": "Rule B",
                "level": "Bronze",
                "query": {"combinator": "and", "conditions": []},
            },
            {
                "identifier": "rule-a",
                "title": "Rule A",
                "level": "Gold",
                "query": {"combinator": "and", "conditions": []},
            },
        ]
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_local)

        # Remote has rules in opposite order
        sc_remote = _sample_scorecard_api()
        sc_remote["rules"] = [
            {
                "identifier": "rule-a",
                "title": "Rule A",
                "level": "Gold",
                "query": {"combinator": "and", "conditions": []},
            },
            {
                "identifier": "rule-b",
                "title": "Rule B",
                "level": "Bronze",
                "query": {"combinator": "and", "conditions": []},
            },
        ]

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [sc_remote]},
        )

        result = await plan_org(client, tmp_path)

        scorecard_updates = [c for c in result.updates if c.resource_type == "scorecard"]
        assert len(scorecard_updates) == 0

    async def test_rules_missing_identifier_no_crash(self, tmp_path: Path) -> None:
        """Rules with missing identifier keys don't crash, falling back to empty string."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_local = _sample_scorecard_yaml()
        sc_local["rules"] = [
            {
                "title": "No Identifier Rule",
                "level": "Bronze",
                "query": {"combinator": "and", "conditions": []},
            },
        ]
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_local)

        sc_remote = _sample_scorecard_api()
        sc_remote["rules"] = [
            {
                "title": "No Identifier Rule",
                "level": "Bronze",
                "query": {"combinator": "and", "conditions": []},
            },
        ]

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [sc_remote]},
        )

        result = await plan_org(client, tmp_path)

        scorecard_updates = [c for c in result.updates if c.resource_type == "scorecard"]
        assert len(scorecard_updates) == 0

    async def test_empty_rules_list_works(self, tmp_path: Path) -> None:
        """Empty rules list works without errors."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_local = _sample_scorecard_yaml()
        sc_local["rules"] = []
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_local)

        sc_remote = _sample_scorecard_api()
        sc_remote["rules"] = []

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [sc_remote]},
        )

        result = await plan_org(client, tmp_path)

        scorecard_updates = [c for c in result.updates if c.resource_type == "scorecard"]
        assert len(scorecard_updates) == 0
