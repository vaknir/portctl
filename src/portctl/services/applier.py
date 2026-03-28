"""Apply logic: push local YAML -> API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

from portctl.services.ignore import load_ignore_filter

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient
    from portctl.services.planner import PlanResult, ResourceChange

logger = logging.getLogger(__name__)


@dataclass
class ApplyResourceResult:
    """Result of applying a single resource."""

    resource_type: str
    identifier: str
    action: str  # "created", "updated", "deleted"
    success: bool
    error: str | None = None


@dataclass
class ApplyResult:
    """Result of an apply operation."""

    results: list[ApplyResourceResult] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        """Count of successfully created resources."""
        return sum(1 for r in self.results if r.action == "created" and r.success)

    @property
    def updated_count(self) -> int:
        """Count of successfully updated resources."""
        return sum(1 for r in self.results if r.action == "updated" and r.success)

    @property
    def deleted_count(self) -> int:
        """Count of successfully deleted resources."""
        return sum(1 for r in self.results if r.action == "deleted" and r.success)

    @property
    def failed_count(self) -> int:
        """Count of failed resources."""
        return sum(1 for r in self.results if not r.success)

    @property
    def has_failures(self) -> bool:
        """Return True if any resource failed."""
        return self.failed_count > 0


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


async def _apply_blueprint_upsert(
    client: PortClient,
    change: ResourceChange,
    local_blueprints: dict[str, dict[str, Any]],
) -> ApplyResourceResult:
    """Apply a blueprint create or update.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply.
        local_blueprints: Dict of local blueprint data keyed by identifier.

    Returns:
        The result of applying this resource.
    """
    action = "created" if change.action == "create" else "updated"
    data = local_blueprints.get(change.identifier)
    if data is None:
        return ApplyResourceResult(
            resource_type="blueprint",
            identifier=change.identifier,
            action=action,
            success=False,
            error=f"Local YAML not found for blueprint '{change.identifier}'",
        )

    try:
        await client.upsert_blueprint(data)
        logger.info("Blueprint %s: %s", action, change.identifier)
        return ApplyResourceResult(
            resource_type="blueprint",
            identifier=change.identifier,
            action=action,
            success=True,
        )
    except Exception as exc:
        logger.error("Failed to %s blueprint '%s': %s", change.action, change.identifier, exc)
        return ApplyResourceResult(
            resource_type="blueprint",
            identifier=change.identifier,
            action=action,
            success=False,
            error=str(exc),
        )


async def _apply_scorecard_upsert(
    client: PortClient,
    change: ResourceChange,
    local_scorecards: dict[str, dict[str, Any]],
) -> ApplyResourceResult:
    """Apply a scorecard create or update.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply.
        local_scorecards: Dict of local scorecard data keyed by identifier.

    Returns:
        The result of applying this resource.
    """
    action = "created" if change.action == "create" else "updated"
    data = local_scorecards.get(change.identifier)
    if data is None:
        return ApplyResourceResult(
            resource_type="scorecard",
            identifier=change.identifier,
            action=action,
            success=False,
            error=f"Local YAML not found for scorecard '{change.identifier}'",
        )

    blueprint_id = data.get("blueprint", "")
    try:
        await client.upsert_scorecard(blueprint_id, data)
        logger.info("Scorecard %s: %s", action, change.identifier)
        return ApplyResourceResult(
            resource_type="scorecard",
            identifier=change.identifier,
            action=action,
            success=True,
        )
    except Exception as exc:
        logger.error("Failed to %s scorecard '%s': %s", change.action, change.identifier, exc)
        return ApplyResourceResult(
            resource_type="scorecard",
            identifier=change.identifier,
            action=action,
            success=False,
            error=str(exc),
        )


async def _apply_action_upsert(
    client: PortClient,
    change: ResourceChange,
    local_actions: dict[str, dict[str, Any]],
) -> ApplyResourceResult:
    """Apply an action create or update.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply.
        local_actions: Dict of local action data keyed by identifier.

    Returns:
        The result of applying this resource.
    """
    action = "created" if change.action == "create" else "updated"
    data = local_actions.get(change.identifier)
    if data is None:
        return ApplyResourceResult(
            resource_type="action",
            identifier=change.identifier,
            action=action,
            success=False,
            error=f"Local YAML not found for action '{change.identifier}'",
        )

    try:
        await client.upsert_action(data)
        logger.info("Action %s: %s", action, change.identifier)
        return ApplyResourceResult(
            resource_type="action",
            identifier=change.identifier,
            action=action,
            success=True,
        )
    except Exception as exc:
        logger.error("Failed to %s action '%s': %s", change.action, change.identifier, exc)
        return ApplyResourceResult(
            resource_type="action",
            identifier=change.identifier,
            action=action,
            success=False,
            error=str(exc),
        )


async def _apply_page_upsert(
    client: PortClient,
    change: ResourceChange,
    local_pages: dict[str, dict[str, Any]],
) -> ApplyResourceResult:
    """Apply a page create or update.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply.
        local_pages: Dict of local page data keyed by identifier.

    Returns:
        The result of applying this resource.
    """
    action = "created" if change.action == "create" else "updated"
    data = local_pages.get(change.identifier)
    if data is None:
        return ApplyResourceResult(
            resource_type="page",
            identifier=change.identifier,
            action=action,
            success=False,
            error=f"Local YAML not found for page '{change.identifier}'",
        )

    try:
        await client.upsert_page(data)
        logger.info("Page %s: %s", action, change.identifier)
        return ApplyResourceResult(
            resource_type="page",
            identifier=change.identifier,
            action=action,
            success=True,
        )
    except Exception as exc:
        logger.error("Failed to %s page '%s': %s", change.action, change.identifier, exc)
        return ApplyResourceResult(
            resource_type="page",
            identifier=change.identifier,
            action=action,
            success=False,
            error=str(exc),
        )


async def _apply_delete(
    client: PortClient,
    change: ResourceChange,
) -> ApplyResourceResult:
    """Apply a resource deletion.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply (must be a delete).

    Returns:
        The result of applying this deletion.
    """
    try:
        if change.resource_type == "blueprint":
            await client.delete_blueprint(change.identifier)
        elif change.resource_type == "scorecard":
            if change.parent_identifier is None:
                raise ValueError(
                    f"Cannot delete scorecard '{change.identifier}': "
                    f"parent_identifier (blueprint) is not set"
                )
            await client.delete_scorecard(change.parent_identifier, change.identifier)
        elif change.resource_type == "action":
            if change.parent_identifier is None:
                raise ValueError(
                    f"Cannot delete action '{change.identifier}': "
                    f"parent_identifier (blueprint) is not set"
                )
            await client.delete_action(change.identifier)
        elif change.resource_type == "page":
            await client.delete_page(change.identifier)

        logger.info("%s deleted: %s", change.resource_type.capitalize(), change.identifier)
        return ApplyResourceResult(
            resource_type=change.resource_type,
            identifier=change.identifier,
            action="deleted",
            success=True,
        )
    except Exception as exc:
        logger.error("Failed to delete %s '%s': %s", change.resource_type, change.identifier, exc)
        return ApplyResourceResult(
            resource_type=change.resource_type,
            identifier=change.identifier,
            action="deleted",
            success=False,
            error=str(exc),
        )


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


async def apply_org(
    client: PortClient,
    plan: PlanResult,
    prune: bool = False,
    *,
    config_dir: Path | None = None,
) -> ApplyResult:
    """Apply planned changes to Port org.

    Apply in dependency order:
    1. Blueprints (creates first, then updates)
    2. Scorecards (creates first, then updates)
    3. Actions (creates first, then updates)
    4. Pages (creates first, then updates)
    5. Deletions last (pages, actions, scorecards, blueprints -- reverse order)

    Skip deletes unless prune=True.

    On individual resource failure: log error, continue with remaining resources.

    Args:
        client: Authenticated Port API client.
        plan: The plan result with changes to apply.
        prune: Whether to apply deletions.
        config_dir: Root config directory containing blueprints/, scorecards/,
            actions/, and pages/. Defaults to current working directory.

    Returns:
        An ApplyResult with per-resource outcomes.
    """
    from pathlib import Path as _Path

    if config_dir is None:
        config_dir = _Path.cwd()

    results: list[ApplyResourceResult] = []

    if not plan.has_changes:
        return ApplyResult(results=results)

    # Filter out ignored resources from the plan
    ignore = load_ignore_filter(config_dir)
    # ResourceChange uses singular resource_type ("blueprint", "scorecard", etc.)
    # but ignore rules use plural directory names ("blueprints", "scorecards", etc.).
    filtered_changes = [
        c for c in plan.changes if not ignore.is_ignored(f"{c.resource_type}s", c.identifier)
    ]

    if not filtered_changes:
        return ApplyResult(results=results)

    # Load local YAML data for creates/updates
    local_blueprints = _load_local_blueprints(config_dir)
    local_scorecards = _load_local_scorecards(config_dir)
    local_actions = _load_local_actions(config_dir)
    local_pages = _load_local_pages(config_dir)

    # Helper to filter changes by type and action
    def _filter(rtype: str, act: str) -> list[ResourceChange]:
        return [c for c in filtered_changes if c.resource_type == rtype and c.action == act]

    # Phase 1: Blueprint creates & updates
    for change in _filter("blueprint", "create"):
        result = await _apply_blueprint_upsert(client, change, local_blueprints)
        results.append(result)
    for change in _filter("blueprint", "update"):
        result = await _apply_blueprint_upsert(client, change, local_blueprints)
        results.append(result)

    # Phase 2: Scorecard creates & updates
    for change in _filter("scorecard", "create"):
        result = await _apply_scorecard_upsert(client, change, local_scorecards)
        results.append(result)
    for change in _filter("scorecard", "update"):
        result = await _apply_scorecard_upsert(client, change, local_scorecards)
        results.append(result)

    # Phase 3: Action creates & updates
    for change in _filter("action", "create"):
        result = await _apply_action_upsert(client, change, local_actions)
        results.append(result)
    for change in _filter("action", "update"):
        result = await _apply_action_upsert(client, change, local_actions)
        results.append(result)

    # Phase 4: Page creates & updates
    for change in _filter("page", "create"):
        result = await _apply_page_upsert(client, change, local_pages)
        results.append(result)
    for change in _filter("page", "update"):
        result = await _apply_page_upsert(client, change, local_pages)
        results.append(result)

    # Phase 5: Deletions (only if prune=True) -- reverse dependency order
    if prune:
        for change in _filter("page", "delete"):
            result = await _apply_delete(client, change)
            results.append(result)
        for change in _filter("action", "delete"):
            result = await _apply_delete(client, change)
            results.append(result)
        for change in _filter("scorecard", "delete"):
            result = await _apply_delete(client, change)
            results.append(result)
        for change in _filter("blueprint", "delete"):
            result = await _apply_delete(client, change)
            results.append(result)

    return ApplyResult(results=results)
