"""Tests for audit service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import yaml

from portctl.services.auditor import AuditResult, DriftItem, audit_org

if TYPE_CHECKING:
    from pathlib import Path


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

    client.get_actions = AsyncMock(return_value=[])
    client.get_pages = AsyncMock(return_value=[])
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
    """Build a sample scorecard API response dict (remote format)."""
    return _sample_scorecard_yaml(identifier, blueprint)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict as YAML to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


class TestAuditNoDrift:
    """test_audit_no_drift -- local matches remote, no drift detected."""

    async def test_audit_no_drift(self, tmp_path: Path) -> None:
        """When local and remote are identical, audit returns no drift."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await audit_org(client, tmp_path)

        assert not result.has_drift
        assert result.drift_count == 0
        assert len(result.drifts) == 0


class TestAuditModified:
    """test_audit_modified -- local differs from remote, modified drift."""

    async def test_audit_modified_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that differs between local and remote is modified drift."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        # Remote has different title
        api_bp = _sample_blueprint_api()
        api_bp["title"] = "Changed Service"

        client = _make_mock_client(
            blueprints=[api_bp],
            scorecards={"service": []},
        )

        result = await audit_org(client, tmp_path)

        assert result.has_drift
        assert result.drift_count == 1
        assert result.drifts[0].drift_type == "modified"
        assert result.drifts[0].identifier == "service"
        assert result.drifts[0].resource_type == "blueprint"
        assert result.drifts[0].diff is not None

    async def test_audit_modified_scorecard(self, tmp_path: Path) -> None:
        """A scorecard that differs between local and remote is modified drift."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_data = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        # Remote scorecard has different title
        sc_remote = _sample_scorecard_api()
        sc_remote["title"] = "Changed Title"

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [sc_remote]},
        )

        result = await audit_org(client, tmp_path)

        scorecard_drifts = [d for d in result.drifts if d.resource_type == "scorecard"]
        assert len(scorecard_drifts) == 1
        assert scorecard_drifts[0].drift_type == "modified"
        assert scorecard_drifts[0].diff is not None


class TestAuditAddedRemotely:
    """test_audit_added_remotely -- remote has resource not in local."""

    async def test_audit_added_remotely_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that exists remotely but not locally is added_remotely."""
        # Empty local blueprints dir
        (tmp_path / "blueprints").mkdir(parents=True, exist_ok=True)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api("new-remote-bp")],
            scorecards={"new-remote-bp": []},
        )

        result = await audit_org(client, tmp_path)

        assert result.has_drift
        assert result.drift_count == 1
        assert result.drifts[0].drift_type == "added_remotely"
        assert result.drifts[0].identifier == "new-remote-bp"
        assert result.drifts[0].resource_type == "blueprint"

    async def test_audit_added_remotely_scorecard(self, tmp_path: Path) -> None:
        """A scorecard that exists remotely but not locally is added_remotely."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        # No local scorecards, but remote has one
        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": [_sample_scorecard_api()]},
        )

        result = await audit_org(client, tmp_path)

        scorecard_drifts = [d for d in result.drifts if d.resource_type == "scorecard"]
        assert len(scorecard_drifts) == 1
        assert scorecard_drifts[0].drift_type == "added_remotely"
        assert scorecard_drifts[0].identifier == "production-readiness"


class TestAuditRemovedRemotely:
    """test_audit_removed_remotely -- local has resource not in remote."""

    async def test_audit_removed_remotely_blueprint(self, tmp_path: Path) -> None:
        """A blueprint that exists locally but not remotely is removed_remotely."""
        bp_data = _sample_blueprint_yaml("local-only-bp")
        _write_yaml(tmp_path / "blueprints" / "local-only-bp.yaml", bp_data)

        client = _make_mock_client(blueprints=[], scorecards={})

        result = await audit_org(client, tmp_path)

        assert result.has_drift
        assert result.drift_count == 1
        assert result.drifts[0].drift_type == "removed_remotely"
        assert result.drifts[0].identifier == "local-only-bp"
        assert result.drifts[0].resource_type == "blueprint"

    async def test_audit_removed_remotely_scorecard(self, tmp_path: Path) -> None:
        """A scorecard that exists locally but not remotely is removed_remotely."""
        bp_data = _sample_blueprint_yaml()
        _write_yaml(tmp_path / "blueprints" / "service.yaml", bp_data)

        sc_data = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        client = _make_mock_client(
            blueprints=[_sample_blueprint_api()],
            scorecards={"service": []},
        )

        result = await audit_org(client, tmp_path)

        scorecard_drifts = [d for d in result.drifts if d.resource_type == "scorecard"]
        assert len(scorecard_drifts) == 1
        assert scorecard_drifts[0].drift_type == "removed_remotely"
        assert scorecard_drifts[0].identifier == "production-readiness"


class TestAuditResourceFilter:
    """test_audit_resource_filter -- filter limits drift to one resource type."""

    async def test_audit_filter_blueprints_only(self, tmp_path: Path) -> None:
        """When resource_filter is 'blueprints', only blueprint drift is reported."""
        bp_data = _sample_blueprint_yaml("local-only-bp")
        _write_yaml(tmp_path / "blueprints" / "local-only-bp.yaml", bp_data)

        sc_data = _sample_scorecard_yaml()
        _write_yaml(tmp_path / "scorecards" / "production-readiness.yaml", sc_data)

        client = _make_mock_client(blueprints=[], scorecards={})

        result = await audit_org(client, tmp_path, resource_filter="blueprints")

        assert all(d.resource_type == "blueprint" for d in result.drifts)
        assert result.drift_count == 1


class TestAuditResultProperties:
    """test_audit_result_properties -- has_drift, drift_count."""

    def test_audit_result_empty(self) -> None:
        """Empty AuditResult reports no drift."""
        result = AuditResult(drifts=[])
        assert not result.has_drift
        assert result.drift_count == 0

    def test_audit_result_with_drifts(self) -> None:
        """AuditResult correctly counts drifts."""
        drifts = [
            DriftItem(
                resource_type="blueprint",
                identifier="svc",
                drift_type="modified",
                diff={"title": {"old": "A", "new": "B"}},
            ),
            DriftItem(
                resource_type="blueprint",
                identifier="new-bp",
                drift_type="added_remotely",
            ),
            DriftItem(
                resource_type="scorecard",
                identifier="sc",
                drift_type="removed_remotely",
            ),
        ]
        result = AuditResult(drifts=drifts)
        assert result.has_drift
        assert result.drift_count == 3
