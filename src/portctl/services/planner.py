"""Plan logic: diff local YAML vs live API."""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import yaml
from deepdiff import DeepDiff

from portctl.services.ignore import load_ignore_filter
from portctl.validation.pipeline import validate

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient
    from portctl.validation.errors import ValidationResult

logger = logging.getLogger(__name__)

# Prefixes that indicate internal/system blueprints
_INTERNAL_PREFIXES = ("_", "$")

# Fields to exclude from diffs (metadata injected by the API)
_EXCLUDE_PATHS = {
    "root['id']",
    "root['createdAt']",
    "root['createdBy']",
    "root['updatedAt']",
    "root['updatedBy']",
}

# Regex patterns for fields that should be excluded from diffs
_EXCLUDE_REGEX = [
    re.compile(r"root\['properties'\]\['\w+'\]\['required'\]"),  # required: false vs missing
    re.compile(r"root\['properties'\]\['\w+'\]\['enumColors'\]"),  # API-injected color map
    re.compile(r"root\['properties'\]\['\w+'\]\['items'\]"),  # API-injected array schema
    re.compile(r"root\['calculation_properties'\]\['\w+'\]\['icon'\]"),  # API default icon
    re.compile(r"root\['calculation_properties'\]\['\w+'\]\['description'\]"),  # API desc
    re.compile(r"root\['relations'\]\['\w+'\]\['description'\]"),  # API-injected relation desc
]

# Keys whose empty-dict values should be stripped before diffing
_EMPTY_DICT_KEYS = {"properties", "mirror_properties", "calculation_properties", "relations"}


@dataclass
class ResourceChange:
    """A single resource change detected by plan."""

    resource_type: str  # "blueprint", "scorecard", "action", or "page"
    identifier: str
    action: Literal["create", "update", "delete", "unchanged"]
    diff: dict[str, Any] | None = None  # property-level diff for updates
    breaking: bool = False  # True if deletion with existing entities
    parent_identifier: str | None = None  # e.g. blueprint ID for scorecards


@dataclass
class PlanResult:
    """Result of a plan operation."""

    changes: list[ResourceChange] = field(default_factory=list)
    validation_result: ValidationResult | None = None
    total_local_blueprints: int = 0
    total_local_scorecards: int = 0
    total_local_actions: int = 0
    total_local_pages: int = 0

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


def _normalize_for_diff(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize resource data to remove noise before diffing.

    Strips fields that commonly cause false-positive diffs:
    - Empty dict values for mirror_properties, calculation_properties, relations
    - ``required: false`` on properties (it's the default)
    - Empty-string ``identifier`` on scorecard levels

    Args:
        data: Raw resource dict (local or remote).

    Returns:
        A cleaned copy of the data suitable for diffing.
    """
    result = copy.deepcopy(data)

    # Remove keys whose value is an empty dict
    for key in _EMPTY_DICT_KEYS:
        if key in result and result[key] == {}:
            del result[key]

    # Remove `required: false` from each property (it's the default)
    properties = result.get("properties")
    if isinstance(properties, dict):
        for prop_data in properties.values():
            if isinstance(prop_data, dict) and prop_data.get("required") is False:
                del prop_data["required"]

    # Remove empty-string `identifier` from scorecard levels
    levels = result.get("levels")
    if isinstance(levels, list):
        for level in levels:
            if isinstance(level, dict) and level.get("identifier") == "":
                del level["identifier"]

    # Remove `locked: false` from pages (it's the default — API omits it)
    if result.get("locked") is False:
        del result["locked"]

    # Remove `required_approval: false` from actions (it's the default)
    if result.get("required_approval") is False:
        del result["required_approval"]

    # Remove empty user_properties
    if result.get("user_properties") == {}:
        del result["user_properties"]

    # Normalize scorecard rules: strip API-injected `description`, sort by identifier.
    # The Port API auto-generates `description` on scorecard rules — it is not
    # user-authored content, so we strip it from both sides before diffing.
    rules = result.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict):
                rule.pop("description", None)
        result["rules"] = sorted(
            rules,
            key=lambda r: r.get("identifier", "") if isinstance(r, dict) else "",
        )

    return result


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


def _load_local_actions(config_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all local action YAML files.

    Args:
        config_dir: Root config directory containing actions/.

    Returns:
        Dict mapping action identifier to parsed YAML data.
    """
    actions: dict[str, dict[str, Any]] = {}
    action_dir = config_dir / "actions"

    if not action_dir.is_dir():
        return actions

    for ac_file in sorted(action_dir.glob("*.yaml")):
        try:
            with ac_file.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "identifier" in data:
                actions[data["identifier"]] = data
        except yaml.YAMLError:
            logger.warning("Skipping unparseable YAML: %s", ac_file)
            continue

    return actions


def _load_local_pages(config_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all local page YAML files.

    Args:
        config_dir: Root config directory containing pages/.

    Returns:
        Dict mapping page identifier to parsed YAML data.
    """
    pages: dict[str, dict[str, Any]] = {}
    page_dir = config_dir / "pages"

    if not page_dir.is_dir():
        return pages

    for pg_file in sorted(page_dir.glob("*.yaml")):
        try:
            with pg_file.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "identifier" in data:
                pages[data["identifier"]] = data
        except yaml.YAMLError:
            logger.warning("Skipping unparseable YAML: %s", pg_file)
            continue

    return pages


def _diff_resources(
    local: dict[str, Any],
    remote: dict[str, Any],
) -> dict[str, Any] | None:
    """Compute a structured diff between local and remote resource data.

    Both sides are normalised before comparison to eliminate false positives
    from empty dicts, default values, and API metadata fields.

    Args:
        local: Local YAML resource data.
        remote: Remote API resource data (already normalised to local format).

    Returns:
        A dict of changes if any, or None if identical.
    """
    norm_local = _normalize_for_diff(local)
    norm_remote = _normalize_for_diff(remote)

    diff = DeepDiff(
        norm_remote,
        norm_local,
        ignore_order=True,
        exclude_paths=_EXCLUDE_PATHS,
        exclude_regex_paths=_EXCLUDE_REGEX,
    )
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


def _map_api_action_to_local(api_data: dict[str, Any]) -> dict[str, Any]:
    """Map a Port API action response to the local YAML format.

    Converts camelCase API fields to the snake_case format used in local YAML files.

    Args:
        api_data: Raw action dict from the Port API.

    Returns:
        A dict matching the local YAML file format.
    """
    result: dict[str, Any] = {
        "identifier": api_data["identifier"],
        "title": api_data.get("title", ""),
        "blueprint": api_data.get("blueprint", ""),
        "trigger": api_data.get("trigger", {}),
    }

    if api_data.get("invocationMethod") is not None:
        result["invocation_method"] = api_data["invocationMethod"]
    if api_data.get("description") is not None:
        result["description"] = api_data["description"]

    user_inputs = api_data.get("userInputs", {})
    if user_inputs.get("properties"):
        result["user_properties"] = user_inputs["properties"]

    if api_data.get("requiredApproval") is not None:
        result["required_approval"] = api_data["requiredApproval"]

    return result


def _map_api_page_to_local(api_data: dict[str, Any]) -> dict[str, Any]:
    """Map a Port API page response to the local YAML format.

    Strips API-only metadata fields and normalises to the local schema.

    Args:
        api_data: Raw page dict from the Port API.

    Returns:
        A dict matching the local YAML file format.
    """
    result: dict[str, Any] = {
        "identifier": api_data["identifier"],
        "title": api_data.get("title", ""),
    }

    if api_data.get("type") is not None:
        result["type"] = api_data["type"]
    if api_data.get("icon") is not None:
        result["icon"] = api_data["icon"]
    if api_data.get("description") is not None:
        result["description"] = api_data["description"]
    if api_data.get("widgets"):
        result["widgets"] = api_data["widgets"]
    if api_data.get("locked") is not None:
        result["locked"] = api_data["locked"]
    if api_data.get("parent") is not None:
        result["parent"] = api_data["parent"]

    return result


async def _fetch_remote_actions(client: PortClient) -> dict[str, dict[str, Any]]:
    """Fetch all non-internal actions from the Port API.

    Args:
        client: Authenticated Port API client.

    Returns:
        Dict mapping action identifier to normalised local-format data.
    """
    result: dict[str, dict[str, Any]] = {}

    raw_actions = await client.get_actions()
    for raw in raw_actions:
        identifier = raw.get("identifier", "")
        if identifier and not _is_internal(identifier):
            result[identifier] = _map_api_action_to_local(raw)

    return result


async def _fetch_remote_pages(client: PortClient) -> dict[str, dict[str, Any]]:
    """Fetch all non-internal pages from the Port API.

    Args:
        client: Authenticated Port API client.

    Returns:
        Dict mapping page identifier to normalised local-format data.
    """
    raw_pages = await client.get_pages()
    result: dict[str, dict[str, Any]] = {}

    for raw in raw_pages:
        identifier = raw.get("identifier", "")
        if identifier and not _is_internal(identifier):
            result[identifier] = _map_api_page_to_local(raw)

    return result


async def plan_org(
    client: PortClient,
    config_dir: Path,
    resource_filter: str | None = None,
) -> PlanResult:
    """Compare local YAML against live Port state.

    1. Run Layer 1 validation -- abort on errors
    2. Load all local YAML files (blueprints/, scorecards/, actions/, pages/)
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
        resource_filter: Optional filter -- "blueprints", "scorecards",
            "actions", or "pages".

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
    local_actions = _load_local_actions(config_dir)
    local_pages = _load_local_pages(config_dir)

    # Step 3: Fetch remote state
    remote_blueprints = await _fetch_remote_blueprints(client)

    # Fetch remote resources that depend on blueprint IDs
    all_remote_bp_ids = list(remote_blueprints.keys())
    remote_scorecards = await _fetch_remote_scorecards(client, all_remote_bp_ids)
    remote_actions = await _fetch_remote_actions(client)
    remote_pages = await _fetch_remote_pages(client)

    # Filter ignored resources from both local and remote sets
    ignore = load_ignore_filter(config_dir)
    local_blueprints = {
        k: v for k, v in local_blueprints.items() if not ignore.is_ignored("blueprints", k)
    }
    remote_blueprints = {
        k: v for k, v in remote_blueprints.items() if not ignore.is_ignored("blueprints", k)
    }
    local_scorecards = {
        k: v for k, v in local_scorecards.items() if not ignore.is_ignored("scorecards", k)
    }
    remote_scorecards = {
        k: v for k, v in remote_scorecards.items() if not ignore.is_ignored("scorecards", k)
    }
    local_actions = {k: v for k, v in local_actions.items() if not ignore.is_ignored("actions", k)}
    remote_actions = {
        k: v for k, v in remote_actions.items() if not ignore.is_ignored("actions", k)
    }
    local_pages = {k: v for k, v in local_pages.items() if not ignore.is_ignored("pages", k)}
    remote_pages = {k: v for k, v in remote_pages.items() if not ignore.is_ignored("pages", k)}

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
        for identifier, remote_data in remote_scorecards.items():
            if identifier not in local_scorecards:
                changes.append(
                    ResourceChange(
                        resource_type="scorecard",
                        identifier=identifier,
                        action="delete",
                        breaking=True,
                        parent_identifier=remote_data.get("blueprint"),
                    )
                )

    # Step 4c: Diff actions
    if resource_filter is None or resource_filter == "actions":
        for identifier, local_data in local_actions.items():
            if identifier not in remote_actions:
                changes.append(
                    ResourceChange(
                        resource_type="action",
                        identifier=identifier,
                        action="create",
                    )
                )
            else:
                diff = _diff_resources(local_data, remote_actions[identifier])
                if diff is not None:
                    changes.append(
                        ResourceChange(
                            resource_type="action",
                            identifier=identifier,
                            action="update",
                            diff=diff,
                        )
                    )

        for identifier, remote_data in remote_actions.items():
            if identifier not in local_actions:
                changes.append(
                    ResourceChange(
                        resource_type="action",
                        identifier=identifier,
                        action="delete",
                        breaking=True,
                        parent_identifier=remote_data.get("blueprint"),
                    )
                )

    # Step 4d: Diff pages
    if resource_filter is None or resource_filter == "pages":
        for identifier, local_data in local_pages.items():
            if identifier not in remote_pages:
                changes.append(
                    ResourceChange(
                        resource_type="page",
                        identifier=identifier,
                        action="create",
                    )
                )
            else:
                diff = _diff_resources(local_data, remote_pages[identifier])
                if diff is not None:
                    changes.append(
                        ResourceChange(
                            resource_type="page",
                            identifier=identifier,
                            action="update",
                            diff=diff,
                        )
                    )

        for identifier in remote_pages:
            if identifier not in local_pages:
                changes.append(
                    ResourceChange(
                        resource_type="page",
                        identifier=identifier,
                        action="delete",
                        breaking=True,
                    )
                )

    return PlanResult(
        changes=changes,
        validation_result=validation_result,
        total_local_blueprints=len(local_blueprints),
        total_local_scorecards=len(local_scorecards),
        total_local_actions=len(local_actions),
        total_local_pages=len(local_pages),
    )
