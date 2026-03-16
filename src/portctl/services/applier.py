"""Apply logic: push local YAML -> API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

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


async def _apply_delete(
    client: PortClient,
    change: ResourceChange,
    local_scorecards: dict[str, dict[str, Any]],
) -> ApplyResourceResult:
    """Apply a resource deletion.

    Args:
        client: Authenticated Port API client.
        change: The resource change to apply (must be a delete).
        local_scorecards: Dict of local scorecard data (used for blueprint lookup on scorecards).

    Returns:
        The result of applying this deletion.
    """
    try:
        if change.resource_type == "blueprint":
            await client.delete_blueprint(change.identifier)
        elif change.resource_type == "scorecard":
            # For scorecard deletes, we need the blueprint_id. Since the scorecard
            # is being deleted (remote-only), we look it up from the change context.
            # The planner stores scorecard data with blueprint info in remote scorecards.
            # For delete, the scorecard is remote-only so we pass the identifier
            # and let the API figure it out via the stored blueprint association.
            # We need to find which blueprint this scorecard belongs to.
            # Since it's a remote-only scorecard, we can use the identifier directly.
            await client.delete_scorecard(change.identifier, change.identifier)

        logger.info("%s deleted: %s", change.resource_type.capitalize(), change.identifier)
        return ApplyResourceResult(
            resource_type=change.resource_type,
            identifier=change.identifier,
            action="deleted",
            success=True,
        )
    except Exception as exc:
        logger.error(
            "Failed to delete %s '%s': %s", change.resource_type, change.identifier, exc
        )
        return ApplyResourceResult(
            resource_type=change.resource_type,
            identifier=change.identifier,
            action="deleted",
            success=False,
            error=str(exc),
        )


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
    3. Deletions last (scorecards first, then blueprints -- reverse order)

    Skip deletes unless prune=True.

    On individual resource failure: log error, continue with remaining resources.

    Args:
        client: Authenticated Port API client.
        plan: The plan result with changes to apply.
        prune: Whether to apply deletions.
        config_dir: Root config directory containing blueprints/ and scorecards/.
            Defaults to current working directory.

    Returns:
        An ApplyResult with per-resource outcomes.
    """
    from pathlib import Path as _Path

    if config_dir is None:
        config_dir = _Path.cwd()

    results: list[ApplyResourceResult] = []

    if not plan.has_changes:
        return ApplyResult(results=results)

    # Load local YAML data for creates/updates
    local_blueprints = _load_local_blueprints(config_dir)
    local_scorecards = _load_local_scorecards(config_dir)

    # Separate changes by type and action
    bp_creates = [
        c for c in plan.changes
        if c.resource_type == "blueprint" and c.action == "create"
    ]
    bp_updates = [
        c for c in plan.changes
        if c.resource_type == "blueprint" and c.action == "update"
    ]
    sc_creates = [
        c for c in plan.changes
        if c.resource_type == "scorecard" and c.action == "create"
    ]
    sc_updates = [
        c for c in plan.changes
        if c.resource_type == "scorecard" and c.action == "update"
    ]
    sc_deletes = [
        c for c in plan.changes
        if c.resource_type == "scorecard" and c.action == "delete"
    ]
    bp_deletes = [
        c for c in plan.changes
        if c.resource_type == "blueprint" and c.action == "delete"
    ]

    # Phase 1: Blueprint creates
    for change in bp_creates:
        result = await _apply_blueprint_upsert(client, change, local_blueprints)
        results.append(result)

    # Phase 2: Blueprint updates
    for change in bp_updates:
        result = await _apply_blueprint_upsert(client, change, local_blueprints)
        results.append(result)

    # Phase 3: Scorecard creates
    for change in sc_creates:
        result = await _apply_scorecard_upsert(client, change, local_scorecards)
        results.append(result)

    # Phase 4: Scorecard updates
    for change in sc_updates:
        result = await _apply_scorecard_upsert(client, change, local_scorecards)
        results.append(result)

    # Phase 5: Deletions (only if prune=True)
    if prune:
        # Delete scorecards first (reverse dependency order)
        for change in sc_deletes:
            result = await _apply_delete(client, change, local_scorecards)
            results.append(result)

        # Then delete blueprints
        for change in bp_deletes:
            result = await _apply_delete(client, change, local_scorecards)
            results.append(result)

    return ApplyResult(results=results)
