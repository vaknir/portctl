"""State tracker for ~/.portctl/state.yaml and .portctl-state.yaml."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

EXPORT_STATE_FILENAME = ".portctl-state.yaml"


@dataclass
class ResourceEntry:
    """A single resource change within a state entry.

    Attributes:
        resource_type: Type of resource (e.g. "blueprint", "scorecard").
        identifier: Resource identifier.
        action: Action performed (e.g. "imported", "created", "updated").
    """

    resource_type: str
    identifier: str
    action: str


@dataclass
class ExportStateEntry:
    """Record of a single export operation for baseline tracking.

    Attributes:
        id: Unique identifier for this export event.
        timestamp: ISO-format timestamp of the export.
        applied_by: User or CI context that performed the export.
        via: How the state was created (e.g. "export", "apply").
        note: Human-readable description of the event.
        changes: List of resources included in the export.
    """

    id: str
    timestamp: str  # ISO format
    applied_by: str
    via: str
    note: str
    changes: list[ResourceEntry] = field(default_factory=list)


def record_export_state(state_path: Path, entry: ExportStateEntry) -> None:
    """Append an export state entry to the state file.

    Creates the file if it does not exist. Appends to existing entries
    if the file already has data.

    Args:
        state_path: Path to the .portctl-state.yaml file.
        entry: The export state entry to record.
    """
    state: dict[str, Any] = {}

    if state_path.exists():
        with state_path.open() as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                state = loaded

    events: list[dict[str, Any]] = state.get("export_events", [])
    events.append(asdict(entry))
    state["export_events"] = events

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)

    logger.info("Recorded export state entry: %s", entry.id)


@dataclass
class ApplyEvent:
    """Record of a single apply operation."""

    org: str
    timestamp: str  # ISO format
    git_commit: str | None
    resources_changed: list[str] = field(default_factory=list)


def record_apply(state_path: Path, event: ApplyEvent) -> None:
    """Append an apply event to the state file.

    Args:
        state_path: Path to the state YAML file.
        event: The apply event to record.
    """
    state: dict[str, Any] = {}

    if state_path.exists():
        with state_path.open() as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                state = loaded

    events: list[dict[str, Any]] = state.get("apply_events", [])
    events.append(asdict(event))
    state["apply_events"] = events

    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)


def get_last_apply(state_path: Path, org: str) -> ApplyEvent | None:
    """Get the most recent apply event for an org.

    Args:
        state_path: Path to the state YAML file.
        org: Organization alias to look up.

    Returns:
        The most recent ApplyEvent for the org, or None if not found.
    """
    if not state_path.exists():
        return None

    with state_path.open() as f:
        loaded = yaml.safe_load(f)

    if not isinstance(loaded, dict):
        return None

    events: list[dict[str, Any]] = loaded.get("apply_events", [])

    # Filter to the given org and return the last one
    org_events = [e for e in events if e.get("org") == org]
    if not org_events:
        return None

    last = org_events[-1]
    return ApplyEvent(
        org=last["org"],
        timestamp=last["timestamp"],
        git_commit=last.get("git_commit"),
        resources_changed=last.get("resources_changed", []),
    )
