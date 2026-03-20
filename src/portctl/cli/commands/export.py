"""Export command: pull live config to local YAML files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from portctl.exceptions import PortctlError

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig

console = Console()


def export_command(
    org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Organization to export from. Uses default org if not specified.",
    ),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Export only a specific resource type (blueprints, scorecards).",
    ),
    output: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--output",
        "-o",
        help="Output directory for exported YAML files. Defaults to current directory.",
    ),
) -> None:
    """Export portal configuration from Port.io to local YAML files."""
    from portctl.cli.guard import require_config

    output_dir = Path(output) if output is not None else Path.cwd()
    config = require_config()
    org_name = org or config.default_org
    if org_name is None:
        console.print(
            "[red]No default org set. Specify an org or set default_org in config.[/red]"
        )
        raise typer.Exit(code=1)
    console.print(f"[dim]Running export on {org_name}...[/dim]")
    try:
        asyncio.run(_export_run(org_name, resource, output_dir, config))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _export_run(
    org: str, resource: str | None, output_dir: Path, config: PortctlConfig
) -> None:
    """Async implementation of the export command.

    Args:
        org: Organization alias from config.
        resource: Optional resource type filter.
        output_dir: Root directory for exported YAML files.
        config: Validated portctl configuration.
    """
    import os
    from datetime import UTC, datetime

    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.exporter import export_all
    from portctl.services.state import (
        EXPORT_STATE_FILENAME,
        ExportStateEntry,
        ResourceEntry,
        record_export_state,
    )

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    with console.status("[blue]Exporting...[/blue]"):
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            result = await export_all(client, output_dir, resource=resource)

    # Build state baseline entry
    changes: list[ResourceEntry] = []
    for bp_id in result.blueprint_ids:
        changes.append(
            ResourceEntry(resource_type="blueprint", identifier=bp_id, action="imported")
        )
    for sc_id in result.scorecard_ids:
        changes.append(
            ResourceEntry(resource_type="scorecard", identifier=sc_id, action="imported")
        )

    applied_by = os.environ.get("USER", os.environ.get("CI_ACTOR", "unknown"))
    entry = ExportStateEntry(
        id="initial-export",
        timestamp=datetime.now(tz=UTC).isoformat(),
        applied_by=applied_by,
        via="export",
        note="Initial export -- baseline snapshot",
        changes=changes,
    )
    state_path = output_dir / EXPORT_STATE_FILENAME
    record_export_state(state_path, entry)

    bp_count = result.blueprint_count
    sc_count = result.scorecard_count
    console.print(
        f"[green]Exported {bp_count} blueprint(s), {sc_count} scorecard(s)[/green]"
    )
