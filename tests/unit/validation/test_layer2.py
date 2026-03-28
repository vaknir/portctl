"""Tests for Layer 2 remote validation checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
import yaml

from portctl.validation.layer2 import (
    run_layer2,
    validate_action_blueprints,
    validate_blueprint_relations,
    validate_property_types,
    validate_scorecard_blueprints,
)

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write data as YAML to a file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False))


def _mock_client(remote_blueprints: list[dict[str, Any]]) -> PortClient:
    """Create a mock PortClient that returns the given blueprints.

    Args:
        remote_blueprints: List of blueprint dicts the mock API returns.

    Returns:
        A mock PortClient with get_blueprints stubbed.
    """
    client = AsyncMock()
    client.get_blueprints = AsyncMock(return_value=remote_blueprints)
    return client


class TestValidateBlueprintRelations:
    """Tests for blueprint relation target validation."""

    @pytest.mark.asyncio
    async def test_valid_relations(self, tmp_path: Path) -> None:
        """All relation targets exist on remote -- no issues."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "relations": {
                    "team": {"target": "team", "title": "Owning Team"},
                },
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
                {"identifier": "team", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_blueprint_relations(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_missing_target(self, tmp_path: Path) -> None:
        """Relation targets a blueprint that does not exist -- error."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "relations": {
                    "team": {"target": "nonexistent", "title": "Owning Team"},
                },
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_blueprint_relations(tmp_path, client)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "nonexistent" in issues[0].message

    @pytest.mark.asyncio
    async def test_target_exists_locally(self, tmp_path: Path) -> None:
        """Relation target exists only locally (not remote) -- no issue."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "relations": {
                    "team": {"target": "team", "title": "Owning Team"},
                },
            },
        )
        _write_yaml(
            bp_dir / "team.yaml",
            {"identifier": "team", "title": "Team"},
        )

        # Remote only knows about "service", but "team" exists locally
        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_blueprint_relations(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_no_blueprints_dir(self, tmp_path: Path) -> None:
        """No blueprints directory -- returns empty list."""
        client = _mock_client([])
        issues = await validate_blueprint_relations(tmp_path, client)
        assert len(issues) == 0


class TestValidateScorecardBlueprints:
    """Tests for scorecard blueprint reference validation."""

    @pytest.mark.asyncio
    async def test_scorecard_blueprint_exists(self, tmp_path: Path) -> None:
        """Scorecard references existing blueprint on remote -- no issues."""
        sc_dir = tmp_path / "scorecards"
        _write_yaml(
            sc_dir / "prod.yaml",
            {
                "identifier": "prod-readiness",
                "title": "Production Readiness",
                "blueprint": "service",
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_scorecard_blueprints(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_scorecard_blueprint_missing(self, tmp_path: Path) -> None:
        """Scorecard references non-existent blueprint -- error."""
        sc_dir = tmp_path / "scorecards"
        _write_yaml(
            sc_dir / "prod.yaml",
            {
                "identifier": "prod-readiness",
                "title": "Production Readiness",
                "blueprint": "nonexistent",
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_scorecard_blueprints(tmp_path, client)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "nonexistent" in issues[0].message
        assert "prod-readiness" in issues[0].message

    @pytest.mark.asyncio
    async def test_scorecard_blueprint_exists_locally(self, tmp_path: Path) -> None:
        """Scorecard references a blueprint that only exists locally -- no issue."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {"identifier": "service", "title": "Service"},
        )

        sc_dir = tmp_path / "scorecards"
        _write_yaml(
            sc_dir / "prod.yaml",
            {
                "identifier": "prod-readiness",
                "title": "Production Readiness",
                "blueprint": "service",
            },
        )

        # Remote has no blueprints, but local has "service"
        client = _mock_client([])

        issues = await validate_scorecard_blueprints(tmp_path, client)
        assert len(issues) == 0


class TestValidateActionBlueprints:
    """Tests for action blueprint reference validation."""

    @pytest.mark.asyncio
    async def test_action_blueprint_exists(self, tmp_path: Path) -> None:
        """Action references existing blueprint on remote -- no issues."""
        ac_dir = tmp_path / "actions"
        _write_yaml(
            ac_dir / "deploy.yaml",
            {
                "identifier": "deploy",
                "title": "Deploy Service",
                "blueprint": "service",
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_action_blueprints(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_action_blueprint_missing(self, tmp_path: Path) -> None:
        """Action references non-existent blueprint -- error."""
        ac_dir = tmp_path / "actions"
        _write_yaml(
            ac_dir / "deploy.yaml",
            {
                "identifier": "deploy",
                "title": "Deploy Service",
                "blueprint": "nonexistent",
            },
        )

        client = _mock_client(
            [
                {"identifier": "service", "schema": {"properties": {}}},
            ]
        )

        issues = await validate_action_blueprints(tmp_path, client)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "nonexistent" in issues[0].message
        assert "deploy" in issues[0].message


class TestValidatePropertyTypes:
    """Tests for property type change detection."""

    @pytest.mark.asyncio
    async def test_property_type_change(self, tmp_path: Path) -> None:
        """Local property type differs from remote -- warning."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "properties": {
                    "tier": {"type": "number", "title": "Service Tier"},
                },
            },
        )

        client = _mock_client(
            [
                {
                    "identifier": "service",
                    "schema": {
                        "properties": {
                            "tier": {"type": "string", "title": "Service Tier"},
                        },
                    },
                },
            ]
        )

        issues = await validate_property_types(tmp_path, client)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "string" in issues[0].message
        assert "number" in issues[0].message
        assert "tier" in issues[0].message

    @pytest.mark.asyncio
    async def test_property_types_match(self, tmp_path: Path) -> None:
        """Local property types match remote -- no issues."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "properties": {
                    "tier": {"type": "string", "title": "Service Tier"},
                },
            },
        )

        client = _mock_client(
            [
                {
                    "identifier": "service",
                    "schema": {
                        "properties": {
                            "tier": {"type": "string", "title": "Service Tier"},
                        },
                    },
                },
            ]
        )

        issues = await validate_property_types(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_new_blueprint_skipped(self, tmp_path: Path) -> None:
        """Blueprint exists locally but not on remote -- no type comparison."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "new_bp.yaml",
            {
                "identifier": "new_bp",
                "title": "New Blueprint",
                "properties": {
                    "name": {"type": "string"},
                },
            },
        )

        client = _mock_client([])

        issues = await validate_property_types(tmp_path, client)
        assert len(issues) == 0

    @pytest.mark.asyncio
    async def test_new_property_skipped(self, tmp_path: Path) -> None:
        """New local property not on remote -- no warning."""
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "properties": {
                    "new_field": {"type": "boolean"},
                },
            },
        )

        client = _mock_client(
            [
                {
                    "identifier": "service",
                    "schema": {
                        "properties": {
                            "tier": {"type": "string"},
                        },
                    },
                },
            ]
        )

        issues = await validate_property_types(tmp_path, client)
        assert len(issues) == 0


class TestRunLayer2:
    """Tests for the Layer 2 orchestrator."""

    @pytest.mark.asyncio
    async def test_collects_all_issues(self, tmp_path: Path) -> None:
        """Verify all checks run and issues are collected together."""
        # Blueprint with bad relation
        bp_dir = tmp_path / "blueprints"
        _write_yaml(
            bp_dir / "service.yaml",
            {
                "identifier": "service",
                "title": "Service",
                "relations": {
                    "team": {"target": "ghost_bp", "title": "Team"},
                },
                "properties": {
                    "tier": {"type": "number"},
                },
            },
        )

        # Scorecard referencing non-existent blueprint
        sc_dir = tmp_path / "scorecards"
        _write_yaml(
            sc_dir / "prod.yaml",
            {
                "identifier": "prod",
                "title": "Prod",
                "blueprint": "missing_bp",
            },
        )

        # Action referencing non-existent blueprint
        ac_dir = tmp_path / "actions"
        _write_yaml(
            ac_dir / "deploy.yaml",
            {
                "identifier": "deploy",
                "title": "Deploy",
                "blueprint": "also_missing",
            },
        )

        # Remote has "service" with different property type
        client = _mock_client(
            [
                {
                    "identifier": "service",
                    "schema": {
                        "properties": {
                            "tier": {"type": "string"},
                        },
                    },
                },
            ]
        )

        result = await run_layer2(tmp_path, client)

        # Should have: 1 relation error + 1 scorecard error + 1 action error + 1 type warning
        assert len(result.issues) == 4
        errors = [i for i in result.issues if i.severity == "error"]
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(errors) == 3
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_empty_config_dir(self, tmp_path: Path) -> None:
        """Empty config directory -- no issues."""
        client = _mock_client([])
        result = await run_layer2(tmp_path, client)
        assert len(result.issues) == 0
        assert result.has_errors is False
