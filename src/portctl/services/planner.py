"""Plan logic: diff local YAML vs live API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import yaml
from deepdiff import DeepDiff

from portctl.validation.pipeline import validate

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient
    from portctl.validation.errors import ValidationResult

logger = logging.getLogger(__name__)

# Prefixes that indicate internal/system blueprints
_INTERNAL_PREFIXES = ("_", "$")


@dataclass
class ResourceChange:
    """A single resource change detected by plan."""

    resource_type: str  # "blueprint" or "scorecard"
    identifier: str
    action: Literal["create", "update", "delete", "unchanged"]
    diff: dict[str, Any] | None = None  # property-level diff for updates
    breaking: bool = False  # True if deletion with existing entities


@dataclass
class PlanResult:
    """Result of a plan operation."""

    changes: list[ResourceChange] = field(default_factory=list)
    validation_result: ValidationResult | None = None

    @property
    def has_changes(self) -> bool:
        """Return True if there are any non-unchanged changes."""
        return len(self.changes) > 0

    @property
    def change_count(self) -> int:
        """Return the total number of changes."""
        return len(self.changes)

    @property
    def breaking_count(self) -> int:
        """Return the number of breaking changes."""
        return sum(1 for c in self.changes if c.breaking)

    @property
    def creates(self) -> list[ResourceChange]:
        """Return all create changes."""
        return [c for c in self.changes if c.action == "create"]

    @property
    def updates(self) -> list[ResourceChange]:
        """Return all update changes."""
        return [c for c in self.changes if c.action == "update"]

    @property
    def deletes(self) -> list[ResourceChange]:
        """Return all delete changes."""
        return [c for c in self.changes if c.action == "delete"]


def _is_internal(identifier: str) -> bool:
    """Check if a blueprint identifier is internal/system-generated.

    Args:
        identifier: Blueprint identifier string.

    Returns:
        True if the blueprint should be skipped.
    """
    return any(identifier.startswith(prefix) for prefix in _INTERNAL_PREFIXES)


def _map_api_blueprint_to_local(api_data: dict[str, Any]) -> dict[str, Any]:
    """Map a Port API blueprint response to the local YAML format.

    Converts the API schema format (with nested schema.properties and
    schema.required) into the flat local format used in YAML files.

    Args:
        api_data: Raw blueprint dict from the Port API.

    Returns:
        A dict matching the local YAML file format.
    """
    schema = api_data.get("schema", {})
    required_props: list[str] = schema.get("required", [])

    properties: dict[str, Any] = {}
    for name, prop_data in schema.get("properties", {}).items():
        mapped = dict(prop_data)
        if name in required_props:
            mapped["required"] = True
        properties[name] = mapped

    result: dict[str, Any] = {
        "identifier": api_data["identifier"],
        "title": api_data["title"],
    }

    if api_data.get("icon") is not None:
        result["icon"] = api_data["icon"]
    if api_data.get("description") is not None:
        result["description"] = api_data["description"]
    if properties:
        result["properties"] = properties
    if api_data.get("relations"):
        result["relations"] = api_data["relations"]
    if api_data.get("mirrorProperties"):
        result["mirror_properties"] = api_data["mirrorProperties"]
    if api_data.get("calculationProperties"):
        result["calculation_properties"] = api_data["calculationProperties"]

    return result


def _load_local_blueprints(config_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all local blueprint YAML files.

    Args:
        config_dir: Root config directory containing blueprints/.

    Returns:
        Dict mapping blueprint identifier to parsed YAML data.
    """
    blueprints: dict[str, dict[str, Any]] = {}
    blueprint_dir = config_dir / "blueprints"

    if not blueprint_dir.is_dir():
        return blueprints

    for bp_file in sorted(blueprint_dir.glob("*.yaml")):
        try:
            with bp_file.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "identifier" in data:
                blueprints[data["identifier"]] = data
        except yaml.YAMLError:
            logger.warning("Skipping unparseable YAML: %s", bp_file)
            continue

    return blueprints


def _load_local_scorecards(config_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all local scorecard YAML files.

    Args:
        config_dir: Root config directory containing scorecards/.

    Returns:
        Dict mapping scorecard identifier to parsed YAML data.
    """
    scorecards: dict[str, dict[str, Any]] = {}
    scorecard_dir = config_dir / "scorecards"

    if not scorecard_dir.is_dir():
        return scorecards

    for sc_file in sorted(scorecard_dir.glob("*.yaml")):
        try:
            with sc_file.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "identifier" in data:
                scorecards[data["identifier"]] = data
        except yaml.YAMLError:
            logger.warning("Skipping unparseable YAML: %s", sc_file)
            continue

    return scorecards


def _diff_resources(
    local: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any] | None:
    """Compute a structured diff between local and remote resource data.

    Args:
        local: Local YAML resource data.
        remote: Remote API resource data (already normalised to local format).

    Returns:
        A dict of changes if any, or None if identical.
    """
    diff = DeepDiff(remote, local, ignore_order=True)
    if not diff:
        return None
    return dict(diff)


async def _fetch_remote_blueprints(client: PortClient) -> dict[str, dict[str, Any]]:
    """Fetch all non-internal blueprints from the Port API.

    Args:
        client: Authenticated Port API client.

    Returns:
        Dict mapping blueprint identifier to normalised local-format data.
    """
    raw_blueprints = await client.get_blueprints()
    result: dict[str, dict[str, Any]] = {}

    for raw in raw_blueprints:
        identifier = raw.get("identifier", "")
        if _is_internal(identifier):
            continue
        result[identifier] = _map_api_blueprint_to_local(raw)

    return result


async def _fetch_remote_scorecards(
    client: PortClient, blueprint_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Fetch all scorecards for the given blueprints from the Port API.

    Args:
        client: Authenticated Port API client.
        blueprint_ids: List of blueprint identifiers to fetch scorecards for.

    Returns:
        Dict mapping scorecard identifier to raw API data.
    """
    result: dict[str, dict[str, Any]] = {}

    for bp_id in blueprint_ids:
        raw_scorecards = await client.get_scorecards(bp_id)
        for raw in raw_scorecards:
            identifier = raw.get("identifier", "")
            if identifier:
                result[identifier] = raw

    return result


async def plan_org(
    client: PortClient,
    config_dir: Path,
    resource_filter: str | None = None,
) -> PlanResult:
    """Compare local YAML against live Port state.

    1. Run Layer 1 validation -- abort on errors
    2. Load all local YAML files (blueprints/*.yaml, scorecards/*.yaml)
    3. Fetch live state from Port API
    4. Diff each resource using deepdiff:
       - Local only -> create
       - Both exist, differ -> update (include property-level diff)
       - Remote only -> delete (flag as breaking)
       - Both exist, identical -> unchanged (silent)
    5. Return PlanResult

    Args:
        client: Authenticated Port API client.
        config_dir: Root directory containing blueprints/, scorecards/, etc.
        resource_filter: Optional filter -- "blueprints" or "scorecards".

    Returns:
        A PlanResult with all detected changes.
    """
    # Step 1: Run Layer 1 validation
    validation_result = validate(config_dir)
    if validation_result.has_errors:
        return PlanResult(changes=[], validation_result=validation_result)

    changes: list[ResourceChange] = []

    # Step 2: Load local state
    local_blueprints = _load_local_blueprints(config_dir)
    local_scorecards = _load_local_scorecards(config_dir)

    # Step 3: Fetch remote state
    remote_blueprints = await _fetch_remote_blueprints(client)

    # Fetch remote scorecards for all known remote blueprints
    remote_scorecards = await _fetch_remote_scorecards(
        client, list(remote_blueprints.keys())
    )

    # Step 4: Diff blueprints
    if resource_filter is None or resource_filter == "blueprints":
        # Local only -> create
        for identifier, local_data in local_blueprints.items():
            if identifier not in remote_blueprints:
                changes.append(
                    ResourceChange(
                        resource_type="blueprint",
                        identifier=identifier,
                        action="create",
                    )
                )
            else:
                # Both exist -> diff
                diff = _diff_resources(local_data, remote_blueprints[identifier])
                if diff is not None:
                    changes.append(
                        ResourceChange(
                            resource_type="blueprint",
                            identifier=identifier,
                            action="update",
                            diff=diff,
                        )
                    )
                # else: unchanged, skip

        # Remote only -> delete
        for identifier in remote_blueprints:
            if identifier not in local_blueprints:
                changes.append(
                    ResourceChange(
                        resource_type="blueprint",
                        identifier=identifier,
                        action="delete",
                        breaking=True,
                    )
                )

    # Step 4b: Diff scorecards
    if resource_filter is None or resource_filter == "scorecards":
        # Local only -> create
        for identifier, local_data in local_scorecards.items():
            if identifier not in remote_scorecards:
                changes.append(
                    ResourceChange(
                        resource_type="scorecard",
                        identifier=identifier,
                        action="create",
                    )
                )
            else:
                # Both exist -> diff
                diff = _diff_resources(local_data, remote_scorecards[identifier])
                if diff is not None:
                    changes.append(
                        ResourceChange(
                            resource_type="scorecard",
                            identifier=identifier,
                            action="update",
                            diff=diff,
                        )
                    )

        # Remote only -> delete
        for identifier in remote_scorecards:
            if identifier not in local_scorecards:
                changes.append(
                    ResourceChange(
                        resource_type="scorecard",
                        identifier=identifier,
                        action="delete",
                        breaking=True,
                    )
                )

    return PlanResult(changes=changes)
