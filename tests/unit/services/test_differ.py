"""Tests for the cross-org diff service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from portctl.services.differ import CrossOrgDiffResult, diff_orgs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(
    blueprints: list[dict[str, Any]] | None = None,
    scorecards: dict[str, list[dict[str, Any]]] | None = None,
    pages: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock PortClient with predefined responses.

    Args:
        blueprints: List of raw blueprint API dicts.
        scorecards: Dict mapping blueprint_id to list of scorecard dicts.
        pages: List of raw page API dicts.

    Returns:
        A MagicMock configured to mimic PortClient async methods.
    """
    client = MagicMock()
    client.get_blueprints = AsyncMock(return_value=blueprints or [])
    client.get_pages = AsyncMock(return_value=pages or [])

    _scorecards = scorecards or {}

    async def _get_scorecards(blueprint_id: str) -> list[dict[str, Any]]:
        return _scorecards.get(blueprint_id, [])

    client.get_scorecards = AsyncMock(side_effect=_get_scorecards)

    client.get_actions = AsyncMock(return_value=[])
    return client


def _api_blueprint(
    identifier: str = "service",
    title: str = "Service",
    icon: str = "Microservice",
) -> dict[str, Any]:
    """Build a minimal Port API blueprint response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "icon": icon,
        "description": f"The {title} blueprint",
        "schema": {
            "properties": {
                "language": {"type": "string", "title": "Language"},
            },
            "required": [],
        },
        "relations": {},
        "mirrorProperties": {},
        "calculationProperties": {},
    }


def _api_scorecard(
    identifier: str = "production-readiness",
    blueprint: str = "service",
    title: str = "Production Readiness",
) -> dict[str, Any]:
    """Build a minimal Port API scorecard response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "blueprint": blueprint,
        "levels": [
            {"identifier": "bronze", "title": "Bronze", "color": "orange"},
        ],
        "rules": [],
    }


def _api_page(
    identifier: str = "services-page",
    title: str = "Services",
) -> dict[str, Any]:
    """Build a minimal Port API page response dict."""
    return {
        "identifier": identifier,
        "title": title,
        "blueprint": "service",
        "type": "blueprint-entities",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_orgs_no_changes() -> None:
    """Identical orgs produce an empty result with no changes."""
    bp = _api_blueprint()
    source = _make_mock_client(blueprints=[bp])
    target = _make_mock_client(blueprints=[bp])

    result = await diff_orgs(source, target)

    assert isinstance(result, CrossOrgDiffResult)
    assert not result.has_changes
    assert result.change_count == 0
    assert result.changes == []


@pytest.mark.asyncio
async def test_diff_orgs_source_only() -> None:
    """A blueprint in source but not in target is reported as 'create'."""
    bp = _api_blueprint("service")
    source = _make_mock_client(blueprints=[bp])
    target = _make_mock_client(blueprints=[])  # empty target

    result = await diff_orgs(source, target)

    assert result.has_changes
    assert len(result.only_in_source) == 1
    assert result.only_in_source[0].identifier == "service"
    assert result.only_in_source[0].action == "create"
    assert result.only_in_source[0].resource_type == "blueprint"
    assert result.only_in_target == []
    assert result.modified == []


@pytest.mark.asyncio
async def test_diff_orgs_target_only() -> None:
    """A blueprint in target but not in source is reported as 'delete'."""
    bp = _api_blueprint("service")
    source = _make_mock_client(blueprints=[])  # empty source
    target = _make_mock_client(blueprints=[bp])

    result = await diff_orgs(source, target)

    assert result.has_changes
    assert len(result.only_in_target) == 1
    change = result.only_in_target[0]
    assert change.identifier == "service"
    assert change.action == "delete"
    assert change.breaking is True
    assert change.resource_type == "blueprint"
    assert result.only_in_source == []
    assert result.modified == []


@pytest.mark.asyncio
async def test_diff_orgs_modified() -> None:
    """Same blueprint identifier but different title is reported as 'update'."""
    source_bp = _api_blueprint("service", title="Service")
    target_bp = _api_blueprint("service", title="Service RENAMED")
    source = _make_mock_client(blueprints=[source_bp])
    target = _make_mock_client(blueprints=[target_bp])

    result = await diff_orgs(source, target)

    assert result.has_changes
    assert len(result.modified) == 1
    change = result.modified[0]
    assert change.identifier == "service"
    assert change.action == "update"
    assert change.diff is not None
    assert result.only_in_source == []
    assert result.only_in_target == []


@pytest.mark.asyncio
async def test_diff_orgs_mixed() -> None:
    """Mixed scenario: source-only, target-only, and modified resources."""
    # source has: "service" (modified title), "environment" (source-only)
    # target has: "service" (different title), "team" (target-only)
    source_service = _api_blueprint("service", title="Service Source")
    source_env = _api_blueprint("environment", title="Environment")
    target_service = _api_blueprint("service", title="Service Target")
    target_team = _api_blueprint("team", title="Team")

    source = _make_mock_client(blueprints=[source_service, source_env])
    target = _make_mock_client(blueprints=[target_service, target_team])

    result = await diff_orgs(source, target)

    assert result.has_changes
    assert result.change_count == 3  # 1 create + 1 update + 1 delete

    source_only_ids = {c.identifier for c in result.only_in_source}
    target_only_ids = {c.identifier for c in result.only_in_target}
    modified_ids = {c.identifier for c in result.modified}

    assert source_only_ids == {"environment"}
    assert target_only_ids == {"team"}
    assert modified_ids == {"service"}

    # target-only entries must be breaking
    for change in result.only_in_target:
        assert change.breaking is True


@pytest.mark.asyncio
async def test_diff_orgs_resource_filter_blueprints() -> None:
    """resource_filter='blueprints' only compares blueprints, ignores pages."""
    bp_source = _api_blueprint("service")
    page_source = _api_page("page-a")
    page_target = _api_page("page-b")  # different page in target

    source = _make_mock_client(blueprints=[bp_source], pages=[page_source])
    target = _make_mock_client(blueprints=[bp_source], pages=[page_target])

    result = await diff_orgs(source, target, resource_filter="blueprints")

    # blueprints are identical -> no changes; page diff is filtered out
    assert not result.has_changes


@pytest.mark.asyncio
async def test_diff_orgs_resource_filter_pages() -> None:
    """resource_filter='pages' only compares pages, ignores blueprints."""
    bp_source = _api_blueprint("service-a")
    bp_target = _api_blueprint("service-b")  # different blueprint in target
    page = _api_page("shared-page")

    source = _make_mock_client(blueprints=[bp_source], pages=[page])
    target = _make_mock_client(blueprints=[bp_target], pages=[page])

    result = await diff_orgs(source, target, resource_filter="pages")

    # pages are identical -> no changes; blueprint diff is filtered out
    assert not result.has_changes


@pytest.mark.asyncio
async def test_diff_orgs_scorecard_source_only() -> None:
    """A scorecard present in source but not in target appears as 'create'."""
    bp = _api_blueprint("service")
    sc = _api_scorecard("prod-readiness", blueprint="service")

    source = _make_mock_client(
        blueprints=[bp],
        scorecards={"service": [sc]},
    )
    target = _make_mock_client(blueprints=[bp])

    result = await diff_orgs(source, target)

    scorecard_creates = [c for c in result.only_in_source if c.resource_type == "scorecard"]
    assert len(scorecard_creates) == 1
    assert scorecard_creates[0].identifier == "prod-readiness"


@pytest.mark.asyncio
async def test_diff_orgs_internal_blueprints_skipped() -> None:
    """Internal blueprints (prefixed with _ or $) are excluded from the diff."""
    internal_bp = _api_blueprint("_internal")
    normal_bp = _api_blueprint("service")

    source = _make_mock_client(blueprints=[internal_bp, normal_bp])
    target = _make_mock_client(blueprints=[normal_bp])

    result = await diff_orgs(source, target, resource_filter="blueprints")

    # _internal is skipped; service is identical -> no changes
    assert not result.has_changes


@pytest.mark.asyncio
async def test_cross_org_diff_result_properties() -> None:
    """CrossOrgDiffResult properties correctly partition the change list."""
    from portctl.services.planner import ResourceChange

    create_change = ResourceChange(resource_type="blueprint", identifier="a", action="create")
    update_change = ResourceChange(
        resource_type="blueprint", identifier="b", action="update", diff={"x": 1}
    )
    delete_change = ResourceChange(
        resource_type="blueprint", identifier="c", action="delete", breaking=True
    )

    result = CrossOrgDiffResult(changes=[create_change, update_change, delete_change])

    assert result.has_changes
    assert result.change_count == 3
    assert result.breaking_count == 1
    assert result.only_in_source == [create_change]
    assert result.modified == [update_change]
    assert result.only_in_target == [delete_change]
    assert result.creates == [create_change]
    assert result.updates == [update_change]
    assert result.deletes == [delete_change]
