"""Pull command: pull live config to local YAML files."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from portctl.exceptions import PortctlError

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig
    from portctl.services.planner import PlanResult

console = Console()


def _has_local_files(config_dir: Path) -> bool:
    """Check if local blueprint/scorecard YAML files already exist.

    Args:
        config_dir: Root directory containing blueprints/ and scorecards/.

    Returns:
        True if any YAML files exist that would be overwritten.
    """
    for subdir in ("blueprints", "scorecards"):
        target = config_dir / subdir
        if target.is_dir() and any(target.glob("*.yaml")):
            return True
    return False


def pull_command(
    org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Organization to pull from. Uses default org if not specified.",
    ),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Pull only a specific resource type (blueprints, scorecards).",
    ),
    output: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--output",
        "-o",
        help="Output directory for pulled YAML files. Defaults to current directory.",
    ),
) -> None:
    """Pull portal configuration from Port.io to local YAML files."""
    from portctl.cli.guard import require_config

    output_dir = Path(output) if output is not None else Path.cwd()
    config = require_config()
    org_name = org or config.default_org
    if org_name is None:
        console.print(
            "[red]No default org set. Specify an org or set default_org in config.[/red]"
        )
        raise typer.Exit(code=1)
    console.print(f"[dim]Pulling from {org_name}...[/dim]")
    try:
        # Check for local changes that would be overwritten
        if _has_local_files(output_dir):
            plan = asyncio.run(
                _check_for_diff(org_name, resource, output_dir, config)
            )
            if plan.has_changes:
                from portctl.cli.formatters.diffs import format_plan

                console.print(
                    "[yellow]Warning: local files differ from remote. "
                    "Pull will overwrite these changes:[/yellow]\n"
                )
                format_plan(plan, console)
                console.print()
                if not typer.confirm("Continue?", default=False):
                    raise typer.Exit(code=0)
        asyncio.run(_export_run(org_name, resource, output_dir, config))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _check_for_diff(
    org: str,
    resource: str | None,
    config_dir: Path,
    config: PortctlConfig,
) -> PlanResult:
    """Check if local files differ from remote.

    Args:
        org: Organization alias.
        resource: Optional resource type filter.
        config_dir: Root directory with blueprints/ and scorecards/.
        config: Validated portctl configuration.

    Returns:
        PlanResult with any detected differences.
    """
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.planner import plan_org

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        return await plan_org(client, config_dir, resource_filter=resource)


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

    with console.status("[blue]Pulling...[/blue]"):
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
        f"[green]Pulled {bp_count} blueprint(s), {sc_count} scorecard(s)[/green]"
    )
