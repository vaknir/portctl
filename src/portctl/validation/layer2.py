"""Remote checks: validate local YAML against live Port API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml

from portctl.validation.errors import ValidationIssue, ValidationResult

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient

logger = logging.getLogger(__name__)


def _load_yaml_files(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load all YAML files from a directory, returning (path, data) pairs.

    Silently skips files that cannot be parsed -- Layer 1 already caught those.

    Args:
        directory: Directory containing .yaml files.

    Returns:
        List of (file_path, parsed_data) tuples for valid YAML mappings.
    """
    results: list[tuple[Path, dict[str, Any]]] = []
    if not directory.is_dir():
        return results

    for yaml_file in sorted(directory.glob("*.yaml")):
        try:
            with yaml_file.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                results.append((yaml_file, data))
        except yaml.YAMLError:
            continue
    return results


def _collect_known_blueprint_ids(
    config_dir: Path,
    remote_bps: dict[str, dict[str, Any]],
) -> set[str]:
    """Build the set of known blueprint identifiers from remote + local sources.

    Args:
        config_dir: Root config directory containing blueprints/ subdirectory.
        remote_bps: Remote blueprints keyed by identifier.

    Returns:
        Set of all known blueprint identifiers.
    """
    blueprint_dir = config_dir / "blueprints"
    local_bp_ids: set[str] = {
        data["identifier"] for _, data in _load_yaml_files(blueprint_dir) if data.get("identifier")
    }
    return set(remote_bps.keys()) | local_bp_ids


async def _fetch_remote_blueprints(client: PortClient) -> dict[str, dict[str, Any]]:
    """Fetch all remote blueprints, keyed by identifier.

    Args:
        client: Authenticated Port API client.

    Returns:
        Mapping of blueprint identifier to blueprint data.
    """
    remote_list = await client.get_blueprints()
    return {bp["identifier"]: bp for bp in remote_list if "identifier" in bp}


async def validate_blueprint_relations(
    config_dir: Path,
    client: PortClient,
) -> list[ValidationIssue]:
    """Check that relation targets reference existing remote blueprints.

    For each local blueprint that defines relations, verifies that every
    relation's ``target`` blueprint exists on the remote Port org or locally.

    Args:
        config_dir: Root config directory containing blueprints/ subdirectory.
        client: Authenticated Port API client.

    Returns:
        List of validation issues for missing relation targets.
    """
    issues: list[ValidationIssue] = []
    blueprint_dir = config_dir / "blueprints"
    local_blueprints = _load_yaml_files(blueprint_dir)

    if not local_blueprints:
        return issues

    remote_bps = await _fetch_remote_blueprints(client)
    known_ids = _collect_known_blueprint_ids(config_dir, remote_bps)

    for file_path, data in local_blueprints:
        relations = data.get("relations", {})
        if not isinstance(relations, dict):
            continue

        bp_id = data.get("identifier", "?")

        for rel_key, rel_def in relations.items():
            if not isinstance(rel_def, dict):
                continue

            target = rel_def.get("target")
            if not target or not isinstance(target, str):
                continue

            if target not in known_ids:
                issues.append(
                    ValidationIssue(
                        file_path=str(file_path),
                        line=None,
                        message=(
                            f"Blueprint '{bp_id}' relation '{rel_key}' targets "
                            f"blueprint '{target}' which does not exist on remote "
                            f"or locally"
                        ),
                        severity="error",
                        suggestion=(f"Create blueprint '{target}' or fix the relation target"),
                    )
                )

    return issues


async def validate_scorecard_blueprints(
    config_dir: Path,
    client: PortClient,
) -> list[ValidationIssue]:
    """Check that scorecard blueprint references exist on the remote or locally.

    Args:
        config_dir: Root config directory containing scorecards/ subdirectory.
        client: Authenticated Port API client.

    Returns:
        List of validation issues for missing scorecard blueprint references.
    """
    issues: list[ValidationIssue] = []
    scorecard_dir = config_dir / "scorecards"
    local_scorecards = _load_yaml_files(scorecard_dir)

    if not local_scorecards:
        return issues

    remote_bps = await _fetch_remote_blueprints(client)
    known_ids = _collect_known_blueprint_ids(config_dir, remote_bps)

    for file_path, data in local_scorecards:
        bp_ref = data.get("blueprint")
        if not bp_ref or not isinstance(bp_ref, str):
            continue

        sc_id = data.get("identifier", "?")

        if bp_ref not in known_ids:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Scorecard '{sc_id}' references blueprint '{bp_ref}' "
                        f"which does not exist on remote or locally"
                    ),
                    severity="error",
                    suggestion=(
                        f"Create blueprint '{bp_ref}' or fix the scorecard's blueprint field"
                    ),
                )
            )

    return issues


async def validate_action_blueprints(
    config_dir: Path,
    client: PortClient,
) -> list[ValidationIssue]:
    """Check that action blueprint references exist on the remote or locally.

    Args:
        config_dir: Root config directory containing actions/ subdirectory.
        client: Authenticated Port API client.

    Returns:
        List of validation issues for missing action blueprint references.
    """
    issues: list[ValidationIssue] = []
    action_dir = config_dir / "actions"
    local_actions = _load_yaml_files(action_dir)

    if not local_actions:
        return issues

    remote_bps = await _fetch_remote_blueprints(client)
    known_ids = _collect_known_blueprint_ids(config_dir, remote_bps)

    for file_path, data in local_actions:
        bp_ref = data.get("blueprint")
        if not bp_ref or not isinstance(bp_ref, str):
            continue

        action_id = data.get("identifier", "?")

        if bp_ref not in known_ids:
            issues.append(
                ValidationIssue(
                    file_path=str(file_path),
                    line=None,
                    message=(
                        f"Action '{action_id}' references blueprint '{bp_ref}' "
                        f"which does not exist on remote or locally"
                    ),
                    severity="error",
                    suggestion=(f"Create blueprint '{bp_ref}' or fix the action's blueprint field"),
                )
            )

    return issues


async def validate_property_types(
    config_dir: Path,
    client: PortClient,
) -> list[ValidationIssue]:
    """Warn about property type changes between local and remote blueprints.

    Compares each local blueprint's property types against the remote version.
    Emits a warning (not error) when a property type would change, since this
    may cause data loss or break existing entities.

    Args:
        config_dir: Root config directory containing blueprints/ subdirectory.
        client: Authenticated Port API client.

    Returns:
        List of validation issues (warnings) for property type mismatches.
    """
    issues: list[ValidationIssue] = []
    blueprint_dir = config_dir / "blueprints"
    local_blueprints = _load_yaml_files(blueprint_dir)

    if not local_blueprints:
        return issues

    remote_bps = await _fetch_remote_blueprints(client)

    for file_path, data in local_blueprints:
        bp_id = data.get("identifier")
        if not bp_id or bp_id not in remote_bps:
            continue

        local_props = data.get("properties", {})
        if not isinstance(local_props, dict):
            continue

        remote_schema = remote_bps[bp_id].get("schema", {})
        remote_props = remote_schema.get("properties", {})
        if not isinstance(remote_props, dict):
            continue

        for prop_name, local_prop_def in local_props.items():
            if not isinstance(local_prop_def, dict):
                continue

            local_type = local_prop_def.get("type")
            if not local_type:
                continue

            remote_prop_def = remote_props.get(prop_name)
            if remote_prop_def is None or not isinstance(remote_prop_def, dict):
                continue

            remote_type = remote_prop_def.get("type")
            if not remote_type:
                continue

            if local_type != remote_type:
                issues.append(
                    ValidationIssue(
                        file_path=str(file_path),
                        line=None,
                        message=(
                            f"Blueprint '{bp_id}' property '{prop_name}' "
                            f"type changes from '{remote_type}' to '{local_type}' "
                            f"-- this may cause data loss or break existing entities"
                        ),
                        severity="warning",
                    )
                )

    return issues


async def run_layer2(config_dir: Path, client: PortClient) -> ValidationResult:
    """Run all Layer 2 (remote) validation checks.

    Collects all issues across all checks before returning.

    Args:
        config_dir: Root config directory containing blueprints/, scorecards/, etc.
        client: Authenticated Port API client.

    Returns:
        Combined ValidationResult with all remote validation issues.
    """
    result = ValidationResult()
    result.issues.extend(await validate_blueprint_relations(config_dir, client))
    result.issues.extend(await validate_scorecard_blueprints(config_dir, client))
    result.issues.extend(await validate_action_blueprints(config_dir, client))
    result.issues.extend(await validate_property_types(config_dir, client))
    return result
