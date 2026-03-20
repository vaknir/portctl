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

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def export_run(
    org: str = typer.Argument(help="Organization to export from."),
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
    try:
        asyncio.run(_export_run(org, resource, output_dir, config))
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
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.exporter import export_all

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    with console.status("[blue]Exporting...[/blue]"):
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            summary = await export_all(client, output_dir, resource=resource)

    bp_count = summary["blueprints"]
    sc_count = summary["scorecards"]
    console.print(
        f"[green]Exported {bp_count} blueprint(s), {sc_count} scorecard(s)[/green]"
    )
