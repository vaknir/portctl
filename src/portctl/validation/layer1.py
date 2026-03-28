"""Local checks: YAML syntax, schema, refs, enums."""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

import yaml

from portctl.validation.errors import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from pathlib import Path

_BLUEPRINT_REQUIRED_FIELDS = ("identifier", "title")
_SCORECARD_REQUIRED_FIELDS = ("identifier", "title", "blueprint")
_ACTION_REQUIRED_FIELDS = ("identifier", "title", "blueprint")
_PAGE_REQUIRED_FIELDS = ("identifier", "title")


def validate_yaml_syntax(file_path: Path) -> list[ValidationIssue]:
    """Parse a YAML file and return syntax errors with line numbers."""
    try:
        with file_path.open() as f:
            yaml.safe_load(f)
    except yaml.YAMLError as exc:
        line: int | None = None
        if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
            line = exc.problem_mark.line + 1
        return [
            ValidationIssue(
                file_path=str(file_path),
                line=line,
                message=f"YAML syntax error: {exc}",
                severity="error",
            )
        ]
    return []


def validate_blueprint_schema(file_path: Path, data: dict) -> list[ValidationIssue]:  # type: ignore[type-arg]
    """Validate that a blueprint has all required fields with correct types."""
    issues: list[ValidationIssue] = []
    for field_name in _BLUEPRINT_REQUIRED_FIELDS:
        if field_name not in data:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=f"Missing required field: {field_name}",
                    severity="error",
                    suggestion=f"Add '{field_name}' to the blueprint definition",
                )
            )
        elif not isinstance(data[field_name], str):
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Field '{field_name}' must be a string, "
                        f"got {type(data[field_name]).__name__}"
                    ),
                    severity="error",
                )
            )
    return issues


def validate_scorecard_schema(file_path: Path, data: dict) -> list[ValidationIssue]:  # type: ignore[type-arg]
    """Validate that a scorecard has all required fields with correct types."""
    issues: list[ValidationIssue] = []
    for field_name in _SCORECARD_REQUIRED_FIELDS:
        if field_name not in data:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=f"Missing required field: {field_name}",
                    severity="error",
                    suggestion=f"Add '{field_name}' to the scorecard definition",
                )
            )
        elif not isinstance(data[field_name], str):
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Field '{field_name}' must be a string, "
                        f"got {type(data[field_name]).__name__}"
                    ),
                    severity="error",
                )
            )
    return issues


def validate_action_schema(file_path: Path, data: dict) -> list[ValidationIssue]:  # type: ignore[type-arg]
    """Validate that an action has all required fields with correct types."""
    issues: list[ValidationIssue] = []
    for field_name in _ACTION_REQUIRED_FIELDS:
        if field_name not in data:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=f"Missing required field: {field_name}",
                    severity="error",
                    suggestion=f"Add '{field_name}' to the action definition",
                )
            )
        elif not isinstance(data[field_name], str):
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Field '{field_name}' must be a string, "
                        f"got {type(data[field_name]).__name__}"
                    ),
                    severity="error",
                )
            )
    return issues


def validate_page_schema(file_path: Path, data: dict) -> list[ValidationIssue]:  # type: ignore[type-arg]
    """Validate that a page has all required fields with correct types."""
    issues: list[ValidationIssue] = []
    for field_name in _PAGE_REQUIRED_FIELDS:
        if field_name not in data:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=f"Missing required field: {field_name}",
                    severity="error",
                    suggestion=f"Add '{field_name}' to the page definition",
                )
            )
        elif not isinstance(data[field_name], str):
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Field '{field_name}' must be a string, "
                        f"got {type(data[field_name]).__name__}"
                    ),
                    severity="error",
                )
            )
    return issues


def validate_scorecard_level_refs(file_path: Path, data: dict) -> list[ValidationIssue]:  # type: ignore[type-arg]
    """Validate that each rule.level references a defined level in the same scorecard."""
    issues: list[ValidationIssue] = []
    levels = data.get("levels", [])
    if not isinstance(levels, list):
        return issues

    level_titles: set[str] = {
        lvl["title"] for lvl in levels if isinstance(lvl, dict) and lvl.get("title") is not None
    }

    rules = data.get("rules", [])
    if not isinstance(rules, list):
        return issues

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_level = rule.get("level")
        if rule_level and rule_level not in level_titles:
            available = ", ".join(sorted(level_titles)) if level_titles else "none defined"
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Rule '{rule.get('identifier', '?')}' references level '{rule_level}' "
                        f"which is not defined. Available levels: {available}"
                    ),
                    severity="error",
                    suggestion=f"Use one of: {available}",
                )
            )
    return issues


def validate_cross_file_refs(
    scorecard_path: Path,
    scorecard_data: dict,  # type: ignore[type-arg]
    blueprint_dir: Path,
) -> list[ValidationIssue]:
    """Validate that scorecard.blueprint references an existing blueprint file on disk."""
    issues: list[ValidationIssue] = []
    bp_ref = scorecard_data.get("blueprint")
    if not bp_ref or not isinstance(bp_ref, str):
        return issues

    if not blueprint_dir.is_dir():
        issues.append(
            ValidationIssue(
                file_path=str(scorecard_path),
                line=None,
                message=f"Blueprint directory not found: {blueprint_dir}",
                severity="error",
            )
        )
        return issues

    # Collect all blueprint identifiers from YAML files on disk
    bp_identifiers: list[str] = []
    for bp_file in sorted(blueprint_dir.glob("*.yaml")):
        try:
            with bp_file.open() as f:
                bp_data = yaml.safe_load(f)
            if isinstance(bp_data, dict) and "identifier" in bp_data:
                bp_identifiers.append(bp_data["identifier"])
        except yaml.YAMLError:
            continue

    if bp_ref not in bp_identifiers:
        suggestion: str | None = None
        close = difflib.get_close_matches(bp_ref, bp_identifiers, n=1, cutoff=0.6)
        if close:
            suggestion = f"Did you mean '{close[0]}'?"

        # Detect resource type from file path for a meaningful error message
        resource_type = "Resource"
        parent_dir = scorecard_path.parent.name
        if parent_dir == "scorecards":
            resource_type = "Scorecard"
        elif parent_dir == "actions":
            resource_type = "Action"

        issues.append(
            ValidationIssue(
                file_path=str(scorecard_path),
                line=None,
                message=(
                    f"{resource_type} references blueprint '{bp_ref}' "
                    f"which does not exist in {blueprint_dir}"
                ),
                severity="error",
                suggestion=suggestion,
            )
        )
    return issues


def validate_property_refs(
    scorecard_path: Path,
    scorecard_data: dict,  # type: ignore[type-arg]
    blueprint_data: dict,  # type: ignore[type-arg]
) -> list[ValidationIssue]:
    """Validate rule query property conditions reference blueprint properties."""
    issues: list[ValidationIssue] = []
    bp_properties = set(blueprint_data.get("properties", {}).keys())

    # Include mirror properties — these are derived from relations
    mirror_props = blueprint_data.get("mirror_properties", {})
    if isinstance(mirror_props, dict):
        bp_properties.update(mirror_props.keys())

    # Include calculation properties — these are computed fields
    calc_props = blueprint_data.get("calculation_properties", {})
    if isinstance(calc_props, dict):
        bp_properties.update(calc_props.keys())

    # Include relation-prefixed properties (e.g. $team, $repository)
    relations = blueprint_data.get("relations", {})
    if isinstance(relations, dict):
        for rel_key in relations:
            bp_properties.add(f"${rel_key}")

    rules = scorecard_data.get("rules", [])
    if not isinstance(rules, list):
        return issues

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        query = rule.get("query")
        if not isinstance(query, dict):
            continue
        conditions = query.get("conditions", [])
        if not isinstance(conditions, list):
            continue
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            prop = condition.get("property")
            if prop and prop.startswith("$"):
                # $-prefixed properties reference relations or meta-properties
                # that may not be declared in the blueprint schema (e.g. $team
                # can reference a Port-internal relation). Skip validation.
                continue
            if prop and prop not in bp_properties:
                issues.append(
                    ValidationIssue(
                        file_path=str(scorecard_path),
                        line=None,
                        message=(
                            f"Rule '{rule.get('identifier', '?')}' references property "
                            f"'{prop}' which is not defined in blueprint "
                            f"'{blueprint_data.get('identifier', '?')}'"
                        ),
                        severity="error",
                    )
                )
    return issues


def run_layer1(config_dir: Path) -> ValidationResult:
    """Run all Layer 1 validation checks on all files in config_dir.

    Collects ALL errors before returning -- does not stop at the first failure.
    """
    result = ValidationResult()
    blueprint_dir = config_dir / "blueprints"
    scorecard_dir = config_dir / "scorecards"
    action_dir = config_dir / "actions"
    page_dir = config_dir / "pages"

    # Collect parsed blueprints for cross-file checks
    blueprints: dict[str, dict] = {}  # type: ignore[type-arg]

    # Validate blueprints
    if blueprint_dir.is_dir():
        for bp_file in sorted(blueprint_dir.glob("*.yaml")):
            syntax_issues = validate_yaml_syntax(bp_file)
            result.issues.extend(syntax_issues)
            if syntax_issues:
                continue

            with bp_file.open() as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                result.add_error(str(bp_file), "File does not contain a YAML mapping")
                continue

            result.issues.extend(validate_blueprint_schema(bp_file, data))
            bp_id = data.get("identifier")
            if bp_id:
                blueprints[bp_id] = data

    # Validate scorecards
    if scorecard_dir.is_dir():
        for sc_file in sorted(scorecard_dir.glob("*.yaml")):
            syntax_issues = validate_yaml_syntax(sc_file)
            result.issues.extend(syntax_issues)
            if syntax_issues:
                continue

            with sc_file.open() as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                result.add_error(str(sc_file), "File does not contain a YAML mapping")
                continue

            result.issues.extend(validate_scorecard_schema(sc_file, data))
            result.issues.extend(validate_scorecard_level_refs(sc_file, data))

            if blueprint_dir.is_dir():
                result.issues.extend(validate_cross_file_refs(sc_file, data, blueprint_dir))

            # Property ref validation (if blueprint exists)
            bp_ref = data.get("blueprint")
            if bp_ref and bp_ref in blueprints:
                result.issues.extend(validate_property_refs(sc_file, data, blueprints[bp_ref]))

    # Validate actions
    if action_dir.is_dir():
        for ac_file in sorted(action_dir.glob("*.yaml")):
            syntax_issues = validate_yaml_syntax(ac_file)
            result.issues.extend(syntax_issues)
            if syntax_issues:
                continue

            with ac_file.open() as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                result.add_error(str(ac_file), "File does not contain a YAML mapping")
                continue

            result.issues.extend(validate_action_schema(ac_file, data))

            # Cross-file: action.blueprint must reference an existing blueprint
            if blueprint_dir.is_dir():
                result.issues.extend(validate_cross_file_refs(ac_file, data, blueprint_dir))

    # Validate pages
    if page_dir.is_dir():
        for pg_file in sorted(page_dir.glob("*.yaml")):
            syntax_issues = validate_yaml_syntax(pg_file)
            result.issues.extend(syntax_issues)
            if syntax_issues:
                continue

            with pg_file.open() as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                result.add_error(str(pg_file), "File does not contain a YAML mapping")
                continue

            result.issues.extend(validate_page_schema(pg_file, data))

    return result
