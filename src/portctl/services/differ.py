"""Cross-org diff service: compare two live Port.io orgs directly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from portctl.services.planner import (
    ResourceChange,
    _diff_resources,
    _fetch_remote_actions,
    _fetch_remote_blueprints,
    _fetch_remote_pages,
    _fetch_remote_scorecards,
)

if TYPE_CHECKING:
    from portctl.client.port_client import PortClient


@dataclass
class CrossOrgDiffResult:
    """Result of a cross-org diff operation.

    Changes are described from the source org's perspective:
    - ``create`` means the resource exists only in the source org.
    - ``delete`` means the resource exists only in the target org.
    - ``update`` means the resource exists in both orgs but differs.
    """

    changes: list[ResourceChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Return True if there are any changes between the two orgs."""
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
    def only_in_source(self) -> list[ResourceChange]:
        """Return resources that exist only in the source org (action='create')."""
        return [c for c in self.changes if c.action == "create"]

    @property
    def only_in_target(self) -> list[ResourceChange]:
        """Return resources that exist only in the target org (action='delete')."""
        return [c for c in self.changes if c.action == "delete"]

    @property
    def modified(self) -> list[ResourceChange]:
        """Return resources that exist in both orgs but differ (action='update')."""
        return [c for c in self.changes if c.action == "update"]

    @property
    def creates(self) -> list[ResourceChange]:
        """Return all create changes (source-only resources)."""
        return [c for c in self.changes if c.action == "create"]

    @property
    def updates(self) -> list[ResourceChange]:
        """Return all update changes (resources that differ between orgs)."""
        return [c for c in self.changes if c.action == "update"]

    @property
    def deletes(self) -> list[ResourceChange]:
        """Return all delete changes (target-only resources)."""
        return [c for c in self.changes if c.action == "delete"]


def _diff_resource_sets(
    source: dict[str, Any],
    target: dict[str, Any],
    resource_type: str,
    parent_map: dict[str, str] | None = None,
) -> list[ResourceChange]:
    """Diff two resource sets (source vs target), producing ResourceChange entries.

    Args:
        source: Dict mapping identifier to resource data for the source org.
        target: Dict mapping identifier to resource data for the target org.
        resource_type: Human-readable resource type label (e.g. "blueprint").
        parent_map: Optional mapping of identifier to parent blueprint identifier,
            used to populate ``parent_identifier`` on scorecards and actions.

    Returns:
        List of ResourceChange entries describing the differences.
    """
    changes: list[ResourceChange] = []

    # Source-only -> "create" (exists in source but not in target)
    for identifier, source_data in source.items():
        if identifier not in target:
            changes.append(
                ResourceChange(
                    resource_type=resource_type,
                    identifier=identifier,
                    action="create",
                )
            )
        else:
            # Both exist -> compare
            diff = _diff_resources(source_data, target[identifier])
            if diff is not None:
                changes.append(
                    ResourceChange(
                        resource_type=resource_type,
                        identifier=identifier,
                        action="update",
                        diff=diff,
                    )
                )
            # else: identical, skip

    # Target-only -> "delete" (exists in target but not in source)
    for identifier, target_data in target.items():
        if identifier not in source:
            parent = None
            if parent_map is not None:
                parent = parent_map.get(identifier)
            elif isinstance(target_data, dict):
                parent = target_data.get("blueprint")
            changes.append(
                ResourceChange(
                    resource_type=resource_type,
                    identifier=identifier,
                    action="delete",
                    breaking=True,
                    parent_identifier=parent,
                )
            )

    return changes


async def diff_orgs(
    source_client: PortClient,
    target_client: PortClient,
    resource_filter: str | None = None,
) -> CrossOrgDiffResult:
    """Compare two live Port.io orgs and return the differences.

    Fetches all resources from both orgs and computes a cross-org diff:
    - Resource in source only -> action="create"
    - Resource in target only -> action="delete"
    - Resource in both but different -> action="update"
    - Resource in both and identical -> omitted

    Args:
        source_client: Authenticated PortClient for the source org.
        target_client: Authenticated PortClient for the target org.
        resource_filter: Optional filter -- "blueprints", "scorecards",
            "actions", or "pages". If None, all resource types are compared.

    Returns:
        A CrossOrgDiffResult with all detected differences.
    """
    changes: list[ResourceChange] = []

    # Fetch blueprints from both orgs (always needed for scorecard/action lookup)
    source_blueprints = await _fetch_remote_blueprints(source_client)
    target_blueprints = await _fetch_remote_blueprints(target_client)

    # Fetch dependent resources using each org's own blueprint IDs
    source_bp_ids = list(source_blueprints.keys())
    target_bp_ids = list(target_blueprints.keys())

    source_scorecards = await _fetch_remote_scorecards(source_client, source_bp_ids)
    target_scorecards = await _fetch_remote_scorecards(target_client, target_bp_ids)

    source_actions = await _fetch_remote_actions(source_client)
    target_actions = await _fetch_remote_actions(target_client)

    source_pages = await _fetch_remote_pages(source_client)
    target_pages = await _fetch_remote_pages(target_client)

    # Diff blueprints
    if resource_filter is None or resource_filter == "blueprints":
        changes.extend(_diff_resource_sets(source_blueprints, target_blueprints, "blueprint"))

    # Diff scorecards
    if resource_filter is None or resource_filter == "scorecards":
        changes.extend(_diff_resource_sets(source_scorecards, target_scorecards, "scorecard"))

    # Diff actions
    if resource_filter is None or resource_filter == "actions":
        changes.extend(_diff_resource_sets(source_actions, target_actions, "action"))

    # Diff pages
    if resource_filter is None or resource_filter == "pages":
        changes.extend(_diff_resource_sets(source_pages, target_pages, "page"))

    return CrossOrgDiffResult(changes=changes)
