"""Audit logic: detect configuration drift between local YAML and live Port API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from portctl.services.ignore import load_ignore_filter
from portctl.services.planner import (
    _diff_resources,
    _fetch_remote_actions,
    _fetch_remote_blueprints,
    _fetch_remote_pages,
    _fetch_remote_scorecards,
    _load_local_actions,
    _load_local_blueprints,
    _load_local_pages,
    _load_local_scorecards,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from portctl.client.port_client import PortClient

logger = logging.getLogger(__name__)


@dataclass
class DriftItem:
    """A single resource that has drifted between local and remote state.

    Attributes:
        resource_type: The kind of resource (e.g. "blueprint", "scorecard").
        identifier: The resource identifier.
        drift_type: How the resource drifted: "modified", "added_remotely", or
            "removed_remotely".
        diff: Property-level diff details for modified resources, or None.
    """

    resource_type: str
    identifier: str
    drift_type: Literal["modified", "added_remotely", "removed_remotely"]
    diff: dict[str, Any] | None = None
    updated_by: str | None = None
    updated_at: str | None = None


@dataclass
class AuditResult:
    """Result of an audit operation.

    Attributes:
        drifts: List of detected drift items.
    """

    drifts: list[DriftItem] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        """Return True if any drift was detected."""
        return len(self.drifts) > 0

    @property
    def drift_count(self) -> int:
        """Return the total number of drifted resources."""
        return len(self.drifts)


async def _build_user_lookup(client: PortClient) -> dict[str, str]:
    """Build a mapping from Port user/client IDs to display names.

    Args:
        client: Authenticated Port API client.

    Returns:
        Dict mapping user ID to display name (e.g. "Nir Vaknin").
    """
    try:
        data = await client._request("GET", "/users")
        users = data.get("users", []) or []
        return {
            u["id"]: f"{u.get('firstName', '')} {u.get('lastName', '')}".strip()
            for u in users
            if "id" in u
        }
    except Exception:  # noqa: BLE001
        logger.debug("Could not fetch user list for display names")
        return {}


async def _fetch_raw_metadata(
    client: PortClient,
    user_lookup: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Fetch updatedBy/updatedAt metadata for all blueprints from the Port API.

    Args:
        client: Authenticated Port API client.
        user_lookup: Mapping from user ID to display name.

    Returns:
        Dict mapping identifier to {"updated_by": ..., "updated_at": ...}.
    """
    raw_blueprints = await client.get_blueprints()
    metadata: dict[str, dict[str, str]] = {}
    for raw in raw_blueprints:
        identifier = raw.get("identifier", "")
        raw_user = raw.get("updatedBy", "")
        display_name = user_lookup.get(raw_user, raw_user)
        metadata[identifier] = {
            "updated_by": display_name,
            "updated_at": raw.get("updatedAt", ""),
        }
    return metadata


async def audit_org(
    client: PortClient,
    config_dir: Path,
    resource_filter: str | None = None,
    on_step: Callable[[str, str], None] | None = None,
) -> AuditResult:
    """Compare live Port API state against local YAML files to detect drift.

    Drift types:
    - **modified**: resource exists in both local and remote but they differ.
    - **added_remotely**: resource exists remotely but not locally (added via UI).
    - **removed_remotely**: resource exists locally but not remotely (deleted via UI).

    Args:
        client: Authenticated Port API client.
        config_dir: Root directory containing blueprints/, scorecards/, etc.
        resource_filter: Optional filter -- "blueprints", "scorecards", "actions", or "pages".
        on_step: Optional callback ``(step_name, status)`` where status is
            ``"start"`` or ``"done"``. Used to drive progress display.

    Returns:
        An AuditResult with all detected drift items.
    """

    def _notify(name: str, status: str) -> None:
        if on_step is not None:
            on_step(name, status)

    drifts: list[DriftItem] = []

    # Load local state
    local_blueprints = _load_local_blueprints(config_dir)
    local_scorecards = _load_local_scorecards(config_dir)
    local_actions = _load_local_actions(config_dir)
    local_pages = _load_local_pages(config_dir)

    # Fetch remote state
    _notify("Blueprints", "start")
    remote_blueprints = await _fetch_remote_blueprints(client)
    remote_scorecards = await _fetch_remote_scorecards(client, list(remote_blueprints.keys()))
    remote_actions = await _fetch_remote_actions(client)
    remote_pages = await _fetch_remote_pages(client)

    # Fetch raw API metadata (updatedBy, updatedAt) for drift attribution
    user_lookup = await _build_user_lookup(client)
    raw_metadata = await _fetch_raw_metadata(client, user_lookup)

    # Filter ignored resources
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

    def _meta(identifier: str) -> tuple[str | None, str | None]:
        """Extract updatedBy/updatedAt for a given identifier."""
        m = raw_metadata.get(identifier, {})
        return (
            m.get("updated_by") or None,
            m.get("updated_at") or None,
        )

    _notify("Blueprints", "done")

    # Diff blueprints
    if resource_filter is None or resource_filter == "blueprints":
        for identifier, local_data in local_blueprints.items():
            if identifier in remote_blueprints:
                diff = _diff_resources(local_data, remote_blueprints[identifier])
                if diff is not None:
                    updated_by, updated_at = _meta(identifier)
                    drifts.append(
                        DriftItem(
                            resource_type="blueprint",
                            identifier=identifier,
                            drift_type="modified",
                            diff=diff,
                            updated_by=updated_by,
                            updated_at=updated_at,
                        )
                    )
            else:
                drifts.append(
                    DriftItem(
                        resource_type="blueprint",
                        identifier=identifier,
                        drift_type="removed_remotely",
                    )
                )

        for identifier in remote_blueprints:
            if identifier not in local_blueprints:
                updated_by, updated_at = _meta(identifier)
                drifts.append(
                    DriftItem(
                        resource_type="blueprint",
                        identifier=identifier,
                        drift_type="added_remotely",
                        updated_by=updated_by,
                        updated_at=updated_at,
                    )
                )

    # Diff scorecards
    _notify("Scorecards", "start")
    if resource_filter is None or resource_filter == "scorecards":
        for identifier, local_data in local_scorecards.items():
            if identifier in remote_scorecards:
                diff = _diff_resources(local_data, remote_scorecards[identifier])
                if diff is not None:
                    drifts.append(
                        DriftItem(
                            resource_type="scorecard",
                            identifier=identifier,
                            drift_type="modified",
                            diff=diff,
                        )
                    )
            else:
                drifts.append(
                    DriftItem(
                        resource_type="scorecard",
                        identifier=identifier,
                        drift_type="removed_remotely",
                    )
                )

        for identifier in remote_scorecards:
            if identifier not in local_scorecards:
                drifts.append(
                    DriftItem(
                        resource_type="scorecard",
                        identifier=identifier,
                        drift_type="added_remotely",
                    )
                )

    _notify("Scorecards", "done")

    # Diff actions
    _notify("Actions", "start")
    if resource_filter is None or resource_filter == "actions":
        local_actions = {
            k: v for k, v in local_actions.items() if not ignore.is_ignored("actions", k)
        }
        remote_actions = {
            k: v for k, v in remote_actions.items() if not ignore.is_ignored("actions", k)
        }

        for identifier, local_data in local_actions.items():
            if identifier in remote_actions:
                diff = _diff_resources(local_data, remote_actions[identifier])
                if diff is not None:
                    drifts.append(
                        DriftItem(
                            resource_type="action",
                            identifier=identifier,
                            drift_type="modified",
                            diff=diff,
                        )
                    )
            else:
                drifts.append(
                    DriftItem(
                        resource_type="action",
                        identifier=identifier,
                        drift_type="removed_remotely",
                    )
                )

        for identifier in remote_actions:
            if identifier not in local_actions:
                drifts.append(
                    DriftItem(
                        resource_type="action",
                        identifier=identifier,
                        drift_type="added_remotely",
                    )
                )

    _notify("Actions", "done")

    # Diff pages
    _notify("Pages", "start")
    if resource_filter is None or resource_filter == "pages":
        local_pages = {k: v for k, v in local_pages.items() if not ignore.is_ignored("pages", k)}
        remote_pages = {k: v for k, v in remote_pages.items() if not ignore.is_ignored("pages", k)}

        for identifier, local_data in local_pages.items():
            if identifier in remote_pages:
                diff = _diff_resources(local_data, remote_pages[identifier])
                if diff is not None:
                    drifts.append(
                        DriftItem(
                            resource_type="page",
                            identifier=identifier,
                            drift_type="modified",
                            diff=diff,
                        )
                    )
            else:
                drifts.append(
                    DriftItem(
                        resource_type="page",
                        identifier=identifier,
                        drift_type="removed_remotely",
                    )
                )

        for identifier in remote_pages:
            if identifier not in local_pages:
                drifts.append(
                    DriftItem(
                        resource_type="page",
                        identifier=identifier,
                        drift_type="added_remotely",
                    )
                )

    _notify("Pages", "done")

    return AuditResult(drifts=drifts)
