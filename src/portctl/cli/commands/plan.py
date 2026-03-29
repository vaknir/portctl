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

console = Console()


def diff_command(
    org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Source org (or only org for local diff). Uses default org if not specified.",
    ),
    target_org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Target org for cross-org comparison. If provided, compares two live orgs directly.",
    ),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Filter by resource type (blueprints, scorecards, actions, pages).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output plan as JSON for machine consumption.",
    ),
) -> None:
    """Show a dry-run diff of local YAML vs live Port.io config.

    When two org names are provided, performs a cross-org comparison between
    two live Port.io orgs instead of a local-vs-remote diff.
    """
    from portctl.cli.guard import require_config

    config = require_config()

    if target_org is not None:
        # Cross-org diff mode: compare two live orgs
        source_name = org or config.default_org
        if source_name is None:
            console.print("[red]No source org specified and no default_org set.[/red]")
            raise typer.Exit(code=1)
        if not json_output:
            console.print(f"[dim]Comparing {source_name} vs {target_org}...[/dim]")
        try:
            asyncio.run(_cross_org_diff_run(source_name, target_org, resource, json_output, config))
        except PortctlError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from None
        return

    # Local-vs-remote diff mode (original behaviour)
    org_name = org or config.default_org
    if org_name is None:
        console.print("[red]No default org set. Specify an org or set default_org in config.[/red]")
        raise typer.Exit(code=1)
    if not json_output:
        console.print(f"[dim]Running diff on {org_name}...[/dim]")
    try:
        asyncio.run(_plan_run(org_name, resource, json_output, config))
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

    import sys

    steps = ["Validating local YAML", "Fetching remote state", "Computing diff"]

    def _step(idx: int) -> None:
        if json_output:
            return
        if idx > 0:
            sys.stdout.write("\033[1A\033[2K")
        icon = "\033[36m⠋\033[0m"
        sys.stdout.write(f"  [{icon}] {steps[idx]}...\n")
        sys.stdout.flush()

    def _done() -> None:
        if json_output:
            return
        sys.stdout.write("\033[1A\033[2K")
        sys.stdout.write("  [\033[32m✓\033[0m] Diff complete\n\n")
        sys.stdout.flush()

    _step(0)
    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        _step(1)
        result = await plan_org(client, Path.cwd(), resource_filter=resource)
    _step(2)
    _done()

    if json_output:
        format_plan_json(result, console)
    else:
        format_plan(result, console)

    # Exit code: 0 if no changes, 2 if changes exist
    if result.validation_result is not None and result.validation_result.has_errors:
        raise typer.Exit(code=1)
    if result.has_changes:
        raise typer.Exit(code=2)


async def _cross_org_diff_run(
    source_org: str,
    target_org: str,
    resource: str | None,
    json_output: bool,
    config: PortctlConfig,
) -> None:
    """Async implementation of the cross-org diff command.

    Args:
        source_org: Source organization alias from config.
        target_org: Target organization alias from config.
        resource: Optional resource type filter.
        json_output: Whether to output as JSON.
        config: Validated portctl configuration.
    """
    from portctl.cli.formatters.diffs import format_cross_org_diff, format_cross_org_diff_json
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.differ import diff_orgs

    source_config = get_org(config, source_org)
    target_config = get_org(config, target_org)
    source_id, source_secret = resolve_credentials(source_org, config)
    target_id, target_secret = resolve_credentials(target_org, config)

    import sys

    steps = [f"Fetching {source_org}", f"Fetching {target_org}", "Computing diff"]

    def _step(idx: int) -> None:
        if json_output:
            return
        if idx > 0:
            sys.stdout.write("\033[1A\033[2K")
        icon = "\033[36m⠋\033[0m"
        sys.stdout.write(f"  [{icon}] {steps[idx]}...\n")
        sys.stdout.flush()

    def _done() -> None:
        if json_output:
            return
        sys.stdout.write("\033[1A\033[2K")
        sys.stdout.write("  [\033[32m✓\033[0m] Diff complete\n\n")
        sys.stdout.flush()

    _step(0)
    async with (
        PortClient(
            client_id=source_id,
            client_secret=source_secret,
            api_base=source_config.api_url,
        ) as source_client,
        PortClient(
            client_id=target_id,
            client_secret=target_secret,
            api_base=target_config.api_url,
        ) as target_client,
    ):
        _step(1)
        result = await diff_orgs(source_client, target_client, resource_filter=resource)
    _step(2)
    _done()

    if json_output:
        format_cross_org_diff_json(result, source_org, target_org, console)
    else:
        format_cross_org_diff(result, source_org, target_org, console)

    if result.has_changes:
        raise typer.Exit(code=2)
