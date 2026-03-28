"""Rollback service: restore a Port org to a previous state via git history."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient
    from portctl.services.applier import ApplyResult

logger = logging.getLogger(__name__)


@dataclass
class RollbackTarget:
    """Information about the rollback target.

    Attributes:
        event_id: Unique identifier for the event being rolled back to.
        timestamp: ISO-format timestamp of the original event.
        git_commit: Short git commit hash, or None if not recorded.
        via: How the original state was created (e.g. "export" or "apply").
    """

    event_id: str
    timestamp: str
    git_commit: str | None
    via: str  # "export" or "apply"


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        target: The rollback target that was used.
        apply_result: Result from the apply pipeline, or None if skipped.
        error: Error message if the rollback failed, or None on success.
    """

    target: RollbackTarget
    apply_result: ApplyResult | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Return True if the rollback completed without errors."""
        return self.error is None and (
            self.apply_result is None or not self.apply_result.has_failures
        )


def _read_state(state_path: Path) -> dict[str, Any]:
    """Read and parse the state YAML file.

    Args:
        state_path: Path to the .portctl-state.yaml file.

    Returns:
        Parsed state dict, or empty dict if file does not exist or is invalid.
    """
    if not state_path.exists():
        return {}

    with state_path.open() as f:
        loaded = yaml.safe_load(f)

    return loaded if isinstance(loaded, dict) else {}


def find_rollback_target(state_path: Path, event_id: str) -> RollbackTarget | None:
    """Find a state event by ID.

    Searches both export_events and apply_events for a matching ID.
    For export_events, matches against the ``id`` field.
    For apply_events, matches against ``git_commit`` or ``org`` field.

    Args:
        state_path: Path to the .portctl-state.yaml file.
        event_id: Event ID to search for.

    Returns:
        A RollbackTarget if found, or None.
    """
    state = _read_state(state_path)

    # Search export_events first
    for raw in state.get("export_events", []):
        if raw.get("id") == event_id:
            return RollbackTarget(
                event_id=raw["id"],
                timestamp=raw.get("timestamp", ""),
                git_commit=None,  # export events don't track git commits
                via="export",
            )

    # Search apply_events
    for raw in state.get("apply_events", []):
        # Match on git_commit or org (same logic as history display)
        candidate_id = raw.get("git_commit") or raw.get("org", "")
        if candidate_id == event_id:
            return RollbackTarget(
                event_id=candidate_id,
                timestamp=raw.get("timestamp", ""),
                git_commit=raw.get("git_commit"),
                via="apply",
            )

    return None


def get_available_targets(state_path: Path) -> list[RollbackTarget]:
    """List all events that can be rolled back to.

    Args:
        state_path: Path to the .portctl-state.yaml file.

    Returns:
        List of RollbackTarget instances, sorted by timestamp descending.
    """
    state = _read_state(state_path)
    targets: list[RollbackTarget] = []

    for raw in state.get("export_events", []):
        targets.append(
            RollbackTarget(
                event_id=raw.get("id", ""),
                timestamp=raw.get("timestamp", ""),
                git_commit=None,
                via="export",
            )
        )

    for raw in state.get("apply_events", []):
        targets.append(
            RollbackTarget(
                event_id=raw.get("git_commit") or raw.get("org", ""),
                timestamp=raw.get("timestamp", ""),
                git_commit=raw.get("git_commit"),
                via="apply",
            )
        )

    targets.sort(key=lambda t: t.timestamp, reverse=True)
    return targets


def _checkout_files_at_commit(commit: str, config_dir: Path, temp_dir: Path) -> None:
    """Checkout YAML resource files from a git commit into a temporary directory.

    Iterates over the standard resource subdirectories (blueprints, scorecards,
    actions, pages) and uses ``git show`` to extract each file at the given commit.
    Files that did not exist at the target commit are silently skipped.

    Args:
        commit: Git commit hash (short or full).
        config_dir: Root config directory (must be inside a git repo).
        temp_dir: Temporary directory to write restored files into.
    """
    for subdir in ("blueprints", "scorecards", "actions", "pages"):
        source = config_dir / subdir
        if not source.is_dir():
            continue
        target = temp_dir / subdir
        target.mkdir(parents=True, exist_ok=True)
        for yaml_file in source.glob("*.yaml"):
            rel_path = f"{subdir}/{yaml_file.name}"
            try:
                result = subprocess.run(
                    ["git", "show", f"{commit}:{rel_path}"],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=str(config_dir),
                    timeout=10,
                )
                (target / yaml_file.name).write_text(result.stdout)
            except subprocess.CalledProcessError:
                # File didn't exist at that commit -- skip
                logger.debug("File %s did not exist at commit %s, skipping", rel_path, commit)
            except subprocess.TimeoutExpired:
                logger.warning("Timed out reading %s at commit %s, skipping", rel_path, commit)


async def execute_rollback(
    client: PortClient,
    target: RollbackTarget,
    config_dir: Path,
    prune: bool = False,
) -> RollbackResult:
    """Execute a rollback to a target state.

    Strategy:
    1. If target has git_commit: use git to checkout YAML files at that commit
       into a temp directory, then plan+apply from there.
    2. If no git_commit: just re-run plan+apply from current local files
       (best-effort -- the state entry records WHAT was applied but not the content).

    Args:
        client: Authenticated Port API client.
        target: The rollback target to restore to.
        config_dir: Root config directory containing YAML resources.
        prune: Whether to delete remote-only resources.

    Returns:
        A RollbackResult with the outcome.
    """
    import tempfile
    from pathlib import Path as _Path

    from portctl.services.applier import apply_org
    from portctl.services.planner import plan_org

    # Determine the directory to plan from
    work_dir = config_dir

    temp_dir_obj = None
    try:
        if target.git_commit is not None:
            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_path = _Path(temp_dir_obj.name)
            try:
                _checkout_files_at_commit(target.git_commit, config_dir, temp_path)
            except Exception as exc:
                return RollbackResult(
                    target=target,
                    error=f"Failed to checkout files at commit {target.git_commit}: {exc}",
                )
            work_dir = temp_path

        # Run plan against the work directory
        plan = await plan_org(client, work_dir)

        if not plan.has_changes:
            return RollbackResult(target=target)

        # Apply the plan
        result = await apply_org(client, plan, prune=prune, config_dir=work_dir)
        return RollbackResult(target=target, apply_result=result)

    finally:
        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()
