"""Audit command: detect configuration drift between local files and live Port org."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from portctl.exceptions import PortctlError

if TYPE_CHECKING:
    from typing import Any

    from portctl.models.config import PortctlConfig
    from portctl.services.auditor import AuditResult, DriftItem

console = Console()

_DRIFT_COLORS = {
    "modified": "yellow",
    "added_remotely": "cyan",
    "removed_remotely": "red",
}

_DRIFT_LABELS = {
    "modified": "Modified",
    "added_remotely": "Added remotely",
    "removed_remotely": "Removed remotely",
}


def audit_command(
    org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Organization to audit. Uses default org if not specified.",
    ),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Filter by resource type (blueprints, scorecards).",
    ),
    output_format: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--output",
        "-o",
        help="Output format (json).",
    ),
) -> None:
    """Detect configuration drift between local files and live Port org."""
    from portctl.cli.guard import require_config

    config = require_config()
    org_name = org or config.default_org
    if org_name is None:
        console.print("[red]No default org set. Specify an org or set default_org in config.[/red]")
        raise typer.Exit(code=1)
    if output_format is None:
        console.print(f"[dim]Auditing {org_name} for drift...[/dim]")
    try:
        asyncio.run(_audit_run(org_name, resource, output_format, config))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _audit_run(
    org: str,
    resource: str | None,
    output_format: str | None,
    config: PortctlConfig,
) -> None:
    """Async implementation of the audit command.

    Args:
        org: Organization alias from config.
        resource: Optional resource type filter.
        output_format: Output format ("json" or None for table).
        config: Validated portctl configuration.
    """
    from pathlib import Path

    from portctl.cli.formatters.progress import StepProgress
    from portctl.client.port_client import PortClient
    from portctl.services.auditor import audit_org
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    progress = StepProgress(quiet=output_format == "json")

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        result = await audit_org(
            client, Path.cwd(), resource_filter=resource, on_step=progress.make_callback()
        )
    progress.finish()

    if output_format == "json":
        _format_audit_json(result)
    else:
        _format_audit_report(result)

    if result.has_drift:
        raise typer.Exit(code=1)


def _format_diff_details(diff: dict[str, Any]) -> list[str]:
    """Extract readable change descriptions from a DeepDiff dict.

    Args:
        diff: A DeepDiff result dict.

    Returns:
        List of human-readable change strings.
    """
    lines: list[str] = []

    for path, change in diff.get("values_changed", {}).items():
        clean = path.replace("root", "").replace("['", ".").replace("']", "").lstrip(".")
        old = change.get("old_value", "?")
        new = change.get("new_value", "?")
        lines.append(f"~ {clean}: {old} → {new}")

    for path in diff.get("dictionary_item_added", {}):
        clean = str(path).replace("root", "").replace("['", ".").replace("']", "").lstrip(".")
        lines.append(f"+ {clean}")

    for path in diff.get("dictionary_item_removed", {}):
        clean = str(path).replace("root", "").replace("['", ".").replace("']", "").lstrip(".")
        lines.append(f"- {clean}")

    for _path, value in diff.get("iterable_item_added", {}).items():
        label = value.get("identifier", "") if isinstance(value, dict) else ""
        lines.append(f"+ {label or 'item'}")

    for _path, value in diff.get("iterable_item_removed", {}).items():
        label = value.get("identifier", "") if isinstance(value, dict) else ""
        lines.append(f"- {label or 'item'}")

    return lines


def _format_attribution(drift: DriftItem) -> str:
    """Format who/when for a drift item.

    Args:
        drift: A DriftItem with optional updated_by and updated_at.

    Returns:
        Attribution string like "by user@email 2h ago" or "".
    """
    parts: list[str] = []
    if drift.updated_by:
        parts.append(f"by {drift.updated_by}")
    if drift.updated_at:
        parts.append(_relative_time(drift.updated_at))
    return " ".join(parts)


def _relative_time(iso_str: str) -> str:
    """Convert an ISO timestamp to a relative time string.

    Args:
        iso_str: ISO 8601 timestamp string.

    Returns:
        Relative time like "2h ago", "3d ago".
    """
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(tz=UTC) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"
    except (ValueError, TypeError):
        return ""


def _format_audit_report(result: AuditResult) -> None:
    """Print audit results as a grouped drift report.

    Args:
        result: The audit result to display.
    """
    from portctl.cli.formatters.diffs import render_change_panel
    from portctl.services.planner import ResourceChange

    if not result.has_drift:
        console.print("[green]No drift detected.[/green]")
        return

    console.print("[bold]Configuration Drift Report[/bold]\n")

    # Group drifts by resource type
    grouped: dict[str, list[DriftItem]] = {}
    for drift in result.drifts:
        grouped.setdefault(drift.resource_type, []).append(drift)

    for resource_type in ("blueprint", "scorecard", "action", "page"):
        drifts = grouped.get(resource_type, [])
        if not drifts:
            continue

        console.print(f"[bold]{resource_type.capitalize()}s[/bold]")

        for drift in drifts:
            if drift.drift_type == "modified" and drift.diff is not None:
                change = ResourceChange(
                    resource_type=drift.resource_type,
                    identifier=drift.identifier,
                    action="update",
                    diff=drift.diff,
                )
                console.print(render_change_panel(change))
            else:
                symbol = "+" if drift.drift_type == "added_remotely" else "-"
                color = "green" if drift.drift_type == "added_remotely" else "red"
                label = (
                    "added remotely" if drift.drift_type == "added_remotely" else "removed remotely"
                )
                console.print(f"  [{color}]{symbol}[/{color}] {drift.identifier} ({label})")
                attribution = _format_attribution(drift)
                if attribution:
                    console.print(f"    [dim]{attribution}[/dim]")

        console.print()

    # Summary
    added = sum(1 for d in result.drifts if d.drift_type == "added_remotely")
    removed = sum(1 for d in result.drifts if d.drift_type == "removed_remotely")
    modified = sum(1 for d in result.drifts if d.drift_type == "modified")
    parts: list[str] = []
    if added:
        parts.append(f"[green]{added} added[/green]")
    if removed:
        parts.append(f"[red]{removed} removed[/red]")
    if modified:
        parts.append(f"[yellow]{modified} modified[/yellow]")
    summary = f"Summary: {', '.join(parts)}  |  "
    summary += f"[bold]{result.drift_count} resource(s) drifted[/bold]"
    console.print(summary)


def _format_audit_json(result: AuditResult) -> None:
    """Print audit results as JSON.

    Args:
        result: The audit result to display.
    """
    data = {
        "has_drift": result.has_drift,
        "drift_count": result.drift_count,
        "drifts": [
            {
                "resource_type": d.resource_type,
                "identifier": d.identifier,
                "drift_type": d.drift_type,
                "diff": d.diff,
            }
            for d in result.drifts
        ],
    }
    console.print_json(json.dumps(data))
