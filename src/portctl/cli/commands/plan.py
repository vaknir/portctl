"""Plan command: dry-run diff of local vs live config."""

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
def plan_run(
    org: str = typer.Argument(help="Organization to plan against."),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Filter by resource type (blueprints, scorecards).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output plan as JSON for machine consumption.",
    ),
) -> None:
    """Show a dry-run diff of local YAML vs live Port.io config."""
    from portctl.cli.guard import require_config

    config = require_config()
    try:
        asyncio.run(_plan_run(org, resource, json_output, config))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _plan_run(
    org: str, resource: str | None, json_output: bool, config: PortctlConfig
) -> None:
    """Async implementation of the plan command.

    Args:
        org: Organization alias from config.
        resource: Optional resource type filter.
        json_output: Whether to output as JSON.
        config: Validated portctl configuration.
    """
    from portctl.cli.formatters.diffs import format_plan, format_plan_json
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.planner import plan_org

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    with console.status("[blue]Planning...[/blue]"):
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            result = await plan_org(client, Path.cwd(), resource_filter=resource)

    if json_output:
        format_plan_json(result, console)
    else:
        format_plan(result, console)

    # Exit code: 0 if no changes, 2 if changes exist
    if result.validation_result is not None and result.validation_result.has_errors:
        raise typer.Exit(code=1)
    if result.has_changes:
        raise typer.Exit(code=2)
