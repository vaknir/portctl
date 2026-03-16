"""Tests for apply service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import yaml

from portctl.services.applier import ApplyResourceResult, ApplyResult, apply_org
from portctl.services.planner import PlanResult, ResourceChange

if TYPE_CHECKING:
    from pathlib import Path


def _make_mock_client(
    upsert_blueprint_side_effect: Any = None,
    upsert_scorecard_side_effect: Any = None,
    delete_blueprint_side_effect: Any = None,
    delete_scorecard_side_effect: Any = None,
) -> MagicMock:
    """Create a mock PortClient for apply tests."""
    client = MagicMock()
    client.upsert_blueprint = AsyncMock(
        side_effect=upsert_blueprint_side_effect,
        return_value={"identifier": "test"},
    )
    client.upsert_scorecard = AsyncMock(
        side_effect=upsert_scorecard_side_effect,
        return_value={"identifier": "test"},
    )
    client.delete_blueprint = AsyncMock(side_effect=delete_blueprint_side_effect)
    client.delete_scorecard = AsyncMock(side_effect=delete_scorecard_side_effect)
    return client


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict as YAML to the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(data, f)


def _sample_blueprint_yaml(
    identifier: str = "service",
    title: str = "Service",
) -> dict[str, Any]:
    """Build a sample blueprint YAML dict."""
    return {
        "identifier": identifier,
        "title": title,
        "icon": "Microservice",
        "properties": {
            "language": {"type": "string", "title": "Language"},
        },
    }


def _sample_scorecard_yaml(
    identifier: str = "production-readiness",
    blueprint: str = "service",
) -> dict[str, Any]:
    """Build a sample scorecard YAML dict."""
    return {
        "identifier": identifier,
        "title": "Production Readiness",
        "blueprint": blueprint,
        "levels": [
            {"identifier": "bronze", "title": "Bronze", "color": "orange"},
        ],
        "rules": [],
    }


class TestApplyCreateBlueprint:
    """test_apply_create_blueprint -- calls upsert_blueprint."""

    async def test_apply_create_blueprint(self, tmp_path: Path) -> None:
        """Creating a blueprint calls upsert_blueprint with local YAML data."""
        bp_data = _sample_blueprint_yaml("new-bp")
        _write_yaml(tmp_path / "blueprints" / "new-bp.yaml", bp_data)

        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="new-bp",
                    action="create",
                ),
            ],
        )

        client = _make_mock_client()
        result = await apply_org(client, plan, config_dir=tmp_path)

        client.upsert_blueprint.assert_called_once_with(bp_data)
        assert len(result.results) == 1
        assert result.results[0].action == "created"
        assert result.results[0].success is True


class TestApplyUpdateBlueprint:
    """test_apply_update_blueprint -- calls upsert_blueprint for update."""

    async def test_apply_update_blueprint(self, tmp_path: Path) -> None:
        """Updating a blueprint calls upsert_blueprint with local YAML data."""
        bp_data = _sample_blueprint_yaml("existing-bp")
        _write_yaml(tmp_path / "blueprints" / "existing-bp.yaml", bp_data)

        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="existing-bp",
                    action="update",
                    diff={"values_changed": {}},
                ),
            ],
        )

        client = _make_mock_client()
        result = await apply_org(client, plan, config_dir=tmp_path)

        client.upsert_blueprint.assert_called_once_with(bp_data)
        assert result.results[0].action == "updated"
        assert result.results[0].success is True


class TestApplyCreateScorecard:
    """test_apply_create_scorecard -- calls upsert_scorecard."""

    async def test_apply_create_scorecard(self, tmp_path: Path) -> None:
        """Creating a scorecard calls upsert_scorecard."""
        sc_data = _sample_scorecard_yaml("new-sc", "service")
        _write_yaml(tmp_path / "scorecards" / "new-sc.yaml", sc_data)

        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="scorecard",
                    identifier="new-sc",
                    action="create",
                ),
            ],
        )

        client = _make_mock_client()
        result = await apply_org(client, plan, config_dir=tmp_path)

        client.upsert_scorecard.assert_called_once_with("service", sc_data)
        assert result.results[0].action == "created"
        assert result.results[0].success is True


class TestApplyDeleteSkippedWithoutPrune:
    """test_apply_delete_skipped_without_prune -- deletes not applied."""

    async def test_apply_delete_skipped_without_prune(self, tmp_path: Path) -> None:
        """Delete changes are skipped when prune=False (default)."""
        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="old-bp",
                    action="delete",
                    breaking=True,
                ),
            ],
        )

        client = _make_mock_client()
        result = await apply_org(client, plan, config_dir=tmp_path)

        client.delete_blueprint.assert_not_called()
        client.delete_scorecard.assert_not_called()
        assert len(result.results) == 0


class TestApplyDeleteWithPrune:
    """test_apply_delete_with_prune -- deletes applied when prune=True."""

    async def test_apply_delete_with_prune(self, tmp_path: Path) -> None:
        """Delete changes are applied when prune=True."""
        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="old-bp",
                    action="delete",
                    breaking=True,
                ),
            ],
        )

        client = _make_mock_client()
        result = await apply_org(client, plan, prune=True, config_dir=tmp_path)

        client.delete_blueprint.assert_called_once_with("old-bp")
        assert len(result.results) == 1
        assert result.results[0].action == "deleted"
        assert result.results[0].success is True


class TestApplyDependencyOrder:
    """test_apply_dependency_order -- blueprints before scorecards."""

    async def test_apply_dependency_order(self, tmp_path: Path) -> None:
        """Blueprints are applied before scorecards."""
        bp_data = _sample_blueprint_yaml("bp1")
        _write_yaml(tmp_path / "blueprints" / "bp1.yaml", bp_data)

        sc_data = _sample_scorecard_yaml("sc1", "bp1")
        _write_yaml(tmp_path / "scorecards" / "sc1.yaml", sc_data)

        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="scorecard",
                    identifier="sc1",
                    action="create",
                ),
                ResourceChange(
                    resource_type="blueprint",
                    identifier="bp1",
                    action="create",
                ),
            ],
        )

        call_order: list[str] = []

        async def track_bp(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("blueprint")
            return {"identifier": "bp1"}

        async def track_sc(*args: Any, **kwargs: Any) -> dict[str, Any]:
            call_order.append("scorecard")
            return {"identifier": "sc1"}

        client = _make_mock_client()
        client.upsert_blueprint = AsyncMock(side_effect=track_bp)
        client.upsert_scorecard = AsyncMock(side_effect=track_sc)

        await apply_org(client, plan, config_dir=tmp_path)

        assert call_order == ["blueprint", "scorecard"]


class TestApplyPartialFailure:
    """test_apply_partial_failure -- continues on failure, reports errors."""

    async def test_apply_partial_failure(self, tmp_path: Path) -> None:
        """When one resource fails, other resources still get applied."""
        bp1_data = _sample_blueprint_yaml("bp1")
        bp2_data = _sample_blueprint_yaml("bp2", title="BP2")
        _write_yaml(tmp_path / "blueprints" / "bp1.yaml", bp1_data)
        _write_yaml(tmp_path / "blueprints" / "bp2.yaml", bp2_data)

        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="bp1",
                    action="create",
                ),
                ResourceChange(
                    resource_type="blueprint",
                    identifier="bp2",
                    action="create",
                ),
            ],
        )

        call_count = 0

        async def fail_first(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API error")
            return {"identifier": data["identifier"]}

        client = _make_mock_client()
        client.upsert_blueprint = AsyncMock(side_effect=fail_first)

        result = await apply_org(client, plan, config_dir=tmp_path)

        assert len(result.results) == 2
        assert result.has_failures
        assert result.failed_count == 1
        assert result.created_count == 1


class TestApplyResultCounts:
    """test_apply_result_counts -- created/updated/deleted/failed counts correct."""

    def test_apply_result_counts(self) -> None:
        """ApplyResult correctly counts by action and success."""
        results = ApplyResult(
            results=[
                ApplyResourceResult("blueprint", "a", "created", True),
                ApplyResourceResult("blueprint", "b", "updated", True),
                ApplyResourceResult("scorecard", "c", "deleted", True),
                ApplyResourceResult("blueprint", "d", "created", False, error="failed"),
            ],
        )

        assert results.created_count == 1
        assert results.updated_count == 1
        assert results.deleted_count == 1
        assert results.failed_count == 1
        assert results.has_failures is True


class TestApplyNoChanges:
    """test_apply_no_changes -- empty plan returns empty result."""

    async def test_apply_no_changes(self, tmp_path: Path) -> None:
        """An empty plan returns an empty ApplyResult."""
        plan = PlanResult(changes=[])
        client = _make_mock_client()

        result = await apply_org(client, plan, config_dir=tmp_path)

        assert len(result.results) == 0
        assert result.created_count == 0
        assert result.has_failures is False


class TestApplyDeleteOrder:
    """test_apply_delete_order -- scorecards deleted before blueprints."""

    async def test_apply_delete_order(self, tmp_path: Path) -> None:
        """When pruning, scorecards are deleted before blueprints (reverse dep order)."""
        plan = PlanResult(
            changes=[
                ResourceChange(
                    resource_type="blueprint",
                    identifier="bp1",
                    action="delete",
                    breaking=True,
                ),
                ResourceChange(
                    resource_type="scorecard",
                    identifier="sc1",
                    action="delete",
                    breaking=True,
                    parent_identifier="bp1",
                ),
            ],
        )

        call_order: list[str] = []

        async def track_delete_bp(identifier: str) -> None:
            call_order.append(f"blueprint:{identifier}")

        async def track_delete_sc(blueprint_id: str, identifier: str) -> None:
            call_order.append(f"scorecard:{identifier}")

        client = _make_mock_client()
        client.delete_blueprint = AsyncMock(side_effect=track_delete_bp)
        client.delete_scorecard = AsyncMock(side_effect=track_delete_sc)

        await apply_org(client, plan, prune=True, config_dir=tmp_path)

        assert call_order[0].startswith("scorecard")
        assert call_order[1].startswith("blueprint")
