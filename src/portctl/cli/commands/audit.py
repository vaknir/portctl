"""Audit command: detect configuration drift between local files and live Port org."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.table import Table

from portctl.exceptions import PortctlError

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig
    from portctl.services.auditor import AuditResult

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

    from portctl.client.port_client import PortClient
    from portctl.services.auditor import audit_org
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    with console.status("[blue]Auditing...[/blue]"):
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            result = await audit_org(client, Path.cwd(), resource_filter=resource)

    if output_format == "json":
        _format_audit_json(result)
    else:
        _format_audit_table(result)

    if result.has_drift:
        raise typer.Exit(code=1)


def _format_audit_table(result: AuditResult) -> None:
    """Print audit results as a rich table.

    Args:
        result: The audit result to display.
    """
    if not result.has_drift:
        console.print("[green]No drift detected.[/green]")
        return

    table = Table(title="Configuration Drift")
    table.add_column("Type", style="bold")
    table.add_column("Identifier", style="bold")
    table.add_column("Drift", style="bold")
    table.add_column("Details")

    for drift in result.drifts:
        color = _DRIFT_COLORS.get(drift.drift_type, "white")
        label = _DRIFT_LABELS.get(drift.drift_type, drift.drift_type)

        details = ""
        if drift.diff is not None:
            changed_keys: list[str] = []
            for _diff_type_key, changes in drift.diff.items():
                if isinstance(changes, dict):
                    changed_keys.extend(changes.keys())
            details = ", ".join(changed_keys[:5])
            if len(changed_keys) > 5:
                details += f" (+{len(changed_keys) - 5} more)"

        table.add_row(
            drift.resource_type.capitalize(),
            drift.identifier,
            f"[{color}]{label}[/{color}]",
            details,
        )

    console.print(table)
    console.print(f"\n[yellow]{result.drift_count} resource(s) drifted.[/yellow]")


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
