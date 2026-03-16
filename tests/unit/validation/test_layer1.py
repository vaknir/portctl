"""Tests for Layer 1 local validation checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

from portctl.validation.layer1 import (
    run_layer1,
    validate_blueprint_schema,
    validate_cross_file_refs,
    validate_property_refs,
    validate_scorecard_level_refs,
    validate_scorecard_schema,
    validate_yaml_syntax,
)


def _write_yaml(path: Path, data: dict | str) -> None:  # type: ignore[type-arg]
    """Write data as YAML to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data)
    else:
        path.write_text(yaml.dump(data, default_flow_style=False))


class TestValidateYamlSyntax:
    """Tests for YAML syntax validation."""

    def test_valid_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "valid.yaml"
        _write_yaml(f, {"identifier": "svc", "title": "Service"})

        issues = validate_yaml_syntax(f)
        assert len(issues) == 0

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("key: [unclosed\n  bad: yaml\n")

        issues = validate_yaml_syntax(f)
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert issues[0].line is not None
        assert "syntax" in issues[0].message.lower() or "yaml" in issues[0].message.lower()


class TestValidateBlueprintSchema:
    """Tests for blueprint schema validation."""

    def test_blueprint_missing_identifier(self, tmp_path: Path) -> None:
        f = tmp_path / "bp.yaml"
        data: dict[str, str] = {"title": "Service"}
        issues = validate_blueprint_schema(f, data)
        assert len(issues) >= 1
        assert any("identifier" in i.message for i in issues)

    def test_blueprint_missing_title(self, tmp_path: Path) -> None:
        f = tmp_path / "bp.yaml"
        data: dict[str, str] = {"identifier": "svc"}
        issues = validate_blueprint_schema(f, data)
        assert len(issues) >= 1
        assert any("title" in i.message for i in issues)

    def test_blueprint_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "bp.yaml"
        data: dict[str, str] = {"identifier": "svc", "title": "Service"}
        issues = validate_blueprint_schema(f, data)
        assert len(issues) == 0


class TestValidateScorecardSchema:
    """Tests for scorecard schema validation."""

    def test_scorecard_missing_blueprint(self, tmp_path: Path) -> None:
        f = tmp_path / "sc.yaml"
        data: dict[str, str] = {"identifier": "prod-readiness", "title": "Production Readiness"}
        issues = validate_scorecard_schema(f, data)
        assert len(issues) >= 1
        assert any("blueprint" in i.message for i in issues)


class TestValidateScorecardLevelRefs:
    """Tests for scorecard rule-level cross-references."""

    def test_scorecard_invalid_rule_level(self, tmp_path: Path) -> None:
        f = tmp_path / "sc.yaml"
        data = {
            "identifier": "prod",
            "title": "Prod",
            "blueprint": "svc",
            "levels": [{"title": "Bronze", "color": "orange"}],
            "rules": [{"identifier": "has-docs", "title": "Has docs", "level": "Gold"}],
        }
        issues = validate_scorecard_level_refs(f, data)
        assert len(issues) >= 1
        assert any("Gold" in i.message for i in issues)

    def test_scorecard_valid_rule_level(self, tmp_path: Path) -> None:
        f = tmp_path / "sc.yaml"
        data = {
            "identifier": "prod",
            "title": "Prod",
            "blueprint": "svc",
            "levels": [{"title": "Bronze", "color": "orange"}],
            "rules": [{"identifier": "has-docs", "title": "Has docs", "level": "Bronze"}],
        }
        issues = validate_scorecard_level_refs(f, data)
        assert len(issues) == 0


class TestValidateCrossFileRefs:
    """Tests for cross-file reference validation."""

    def test_cross_file_ref_valid(self, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        _write_yaml(bp_dir / "service.yaml", {"identifier": "service", "title": "Service"})

        sc_path = tmp_path / "scorecards" / "prod.yaml"
        sc_data = {"identifier": "prod", "title": "Prod", "blueprint": "service"}

        issues = validate_cross_file_refs(sc_path, sc_data, bp_dir)
        assert len(issues) == 0

    def test_cross_file_ref_invalid(self, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()

        sc_path = tmp_path / "scorecards" / "prod.yaml"
        sc_data = {"identifier": "prod", "title": "Prod", "blueprint": "nonexistent"}

        issues = validate_cross_file_refs(sc_path, sc_data, bp_dir)
        assert len(issues) >= 1
        assert any("nonexistent" in i.message for i in issues)

    def test_cross_file_ref_suggestion(self, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        _write_yaml(bp_dir / "service.yaml", {"identifier": "service", "title": "Service"})

        sc_path = tmp_path / "scorecards" / "prod.yaml"
        sc_data = {"identifier": "prod", "title": "Prod", "blueprint": "servce"}

        issues = validate_cross_file_refs(sc_path, sc_data, bp_dir)
        assert len(issues) >= 1
        assert any(i.suggestion and "service" in i.suggestion for i in issues)


class TestValidatePropertyRefs:
    """Tests for property reference validation in scorecards."""

    def test_property_ref_valid(self, tmp_path: Path) -> None:
        sc_path = tmp_path / "sc.yaml"
        sc_data = {
            "identifier": "prod",
            "title": "Prod",
            "blueprint": "svc",
            "rules": [
                {
                    "identifier": "has-docs",
                    "title": "Has docs",
                    "level": "Bronze",
                    "query": {
                        "combinator": "and",
                        "conditions": [
                            {"property": "has_readme", "operator": "=", "value": True},
                        ],
                    },
                },
            ],
        }
        bp_data = {
            "identifier": "svc",
            "title": "Service",
            "properties": {"has_readme": {"type": "boolean"}},
        }

        issues = validate_property_refs(sc_path, sc_data, bp_data)
        assert len(issues) == 0

    def test_property_ref_invalid(self, tmp_path: Path) -> None:
        sc_path = tmp_path / "sc.yaml"
        sc_data = {
            "identifier": "prod",
            "title": "Prod",
            "blueprint": "svc",
            "rules": [
                {
                    "identifier": "has-docs",
                    "title": "Has docs",
                    "level": "Bronze",
                    "query": {
                        "combinator": "and",
                        "conditions": [
                            {"property": "nonexistent_prop", "operator": "=", "value": True},
                        ],
                    },
                },
            ],
        }
        bp_data = {
            "identifier": "svc",
            "title": "Service",
            "properties": {"has_readme": {"type": "boolean"}},
        }

        issues = validate_property_refs(sc_path, sc_data, bp_data)
        assert len(issues) >= 1
        assert any("nonexistent_prop" in i.message for i in issues)


class TestRunLayer1:
    """Tests for the Layer 1 orchestrator."""

    def test_run_layer1_collects_all_errors(self, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        # Blueprint missing title
        _write_yaml(bp_dir / "bad.yaml", {"identifier": "svc"})

        sc_dir = tmp_path / "scorecards"
        sc_dir.mkdir()
        # Scorecard missing blueprint
        _write_yaml(sc_dir / "bad.yaml", {"identifier": "prod", "title": "Prod"})

        result = run_layer1(tmp_path)
        assert result.has_errors is True
        assert result.error_count >= 2

    def test_run_layer1_clean(self, tmp_path: Path) -> None:
        bp_dir = tmp_path / "blueprints"
        bp_dir.mkdir()
        _write_yaml(bp_dir / "svc.yaml", {"identifier": "svc", "title": "Service"})

        sc_dir = tmp_path / "scorecards"
        sc_dir.mkdir()
        _write_yaml(
            sc_dir / "prod.yaml",
            {
                "identifier": "prod",
                "title": "Prod Readiness",
                "blueprint": "svc",
                "levels": [{"title": "Bronze", "color": "orange"}],
                "rules": [
                    {"identifier": "has-docs", "title": "Has docs", "level": "Bronze"},
                ],
            },
        )

        result = run_layer1(tmp_path)
        assert result.has_errors is False
        assert result.error_count == 0
