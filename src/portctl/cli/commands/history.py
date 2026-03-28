"""History command: show apply and export event log from .portctl-state.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()


def _load_state(config_dir: Path) -> dict[str, Any]:
    """Load the state YAML file from the given directory.

    Args:
        config_dir: Directory containing the .portctl-state.yaml file.

    Returns:
        Parsed state dict, or empty dict if the file does not exist.
    """
    from portctl.services.state import EXPORT_STATE_FILENAME

    state_path = config_dir / EXPORT_STATE_FILENAME
    if not state_path.exists():
        return {}

    with state_path.open() as f:
        loaded = yaml.safe_load(f)

    return loaded if isinstance(loaded, dict) else {}


def _collect_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect and normalise all events from the state dict.

    Each returned dict has the keys: timestamp, event_type, id, by, resources, note.

    Args:
        state: Parsed state YAML dict.

    Returns:
        List of normalised event dicts sorted by timestamp descending.
    """
    events: list[dict[str, Any]] = []

    for raw in state.get("export_events", []):
        changes: list[str] = [
            f"{c.get('resource_type', '')}:{c.get('identifier', '')}"
            for c in raw.get("changes", [])
        ]
        events.append(
            {
                "timestamp": raw.get("timestamp", ""),
                "event_type": "export",
                "id": raw.get("id", ""),
                "by": raw.get("applied_by", ""),
                "resources": ", ".join(changes) if changes else "-",
                "note": raw.get("note", ""),
            }
        )

    for raw in state.get("apply_events", []):
        resources = raw.get("resources_changed", [])
        events.append(
            {
                "timestamp": raw.get("timestamp", ""),
                "event_type": "apply",
                "id": raw.get("git_commit") or raw.get("org", ""),
                "by": raw.get("org", ""),
                "resources": ", ".join(resources) if resources else "-",
                "note": "",
            }
        )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events


def history_command(
    limit: Optional[int] = typer.Option(  # noqa: UP007, UP045
        20,
        "--limit",
        "-n",
        help="Maximum number of events to show.",
    ),
    config_dir: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--dir",
        help="Project directory containing .portctl-state.yaml. Defaults to current directory.",
    ),
) -> None:
    """Show apply and export history for this project.

    Reads .portctl-state.yaml from the project directory and displays
    a combined log of all export and apply events, newest first.
    """
    directory = Path(config_dir) if config_dir is not None else Path.cwd()
    state = _load_state(directory)
    events = _collect_events(state)

    if not events:
        console.print("[dim]No history found.[/dim]")
        raise typer.Exit(code=0)

    if limit is not None and limit > 0:
        events = events[:limit]

    table = Table(show_header=True, header_style="bold")
    table.add_column("Time", style="dim", min_width=24)
    table.add_column("Type", min_width=6)
    table.add_column("ID", min_width=16)
    table.add_column("By", min_width=8)
    table.add_column("Resources")
    table.add_column("Note")

    for event in events:
        event_type = event["event_type"]
        type_label = (
            f"[blue]{event_type}[/blue]"
            if event_type == "export"
            else f"[green]{event_type}[/green]"
        )
        table.add_row(
            event["timestamp"],
            type_label,
            event["id"],
            event["by"],
            event["resources"],
            event["note"],
        )

    console.print(table)
