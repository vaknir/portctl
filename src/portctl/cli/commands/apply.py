"""Push command: push local YAML config to Port.io."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from portctl.constants import STATE_FILE
from portctl.exceptions import PortctlError

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig

console = Console()


def push_command(
    org: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Organization to push to. Uses default org if not specified.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt (for CI).",
    ),
    prune: bool = typer.Option(
        False,
        "--prune",
        help="Delete remote-only resources.",
    ),
    resource: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--resource",
        "-r",
        help="Filter by resource type (blueprints, scorecards).",
    ),
) -> None:
    """Push local configuration to Port.io."""
    from portctl.cli.guard import require_config

    config = require_config()
    org_name = org or config.default_org
    if org_name is None:
        console.print("[red]No default org set. Specify an org or set default_org in config.[/red]")
        raise typer.Exit(code=1)
    console.print(f"[dim]Pushing to {org_name}...[/dim]")
    try:
        asyncio.run(_apply_run(org_name, yes, prune, resource, config))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _apply_run(
    org: str,
    yes: bool,
    prune: bool,
    resource: str | None,
    config: PortctlConfig,
) -> None:
    """Async implementation of the push command.

    Args:
        org: Organization alias from config.
        yes: Whether to skip confirmation.
        prune: Whether to delete remote-only resources.
        resource: Optional resource type filter.
        config: Validated portctl configuration.
    """
    from datetime import UTC, datetime

    from portctl.cli.formatters.diffs import format_plan
    from portctl.client.port_client import PortClient
    from portctl.services.applier import apply_org
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.planner import plan_org
    from portctl.services.state import ApplyEvent, record_apply

    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        # Step 1: Run plan internally
        with console.status("[blue]Planning...[/blue]"):
            plan = await plan_org(client, Path.cwd(), resource_filter=resource)

        # Step 2: No changes -> exit 0
        if not plan.has_changes:
            console.print("[green]Nothing to push.[/green]")
            return

        # Step 3: Print plan output
        format_plan(plan, console)
        console.print()

        # Step 4: Confirmation
        if plan.breaking_count > 0 and not yes:
            console.print("[red bold]This plan includes breaking changes.[/red bold]")
            confirmation = typer.prompt("Type 'yes' to confirm")
            if confirmation != "yes":
                console.print("[yellow]Push cancelled.[/yellow]")
                raise typer.Exit(code=0)
        elif not yes:
            if not typer.confirm("Push these changes?"):
                console.print("[yellow]Push cancelled.[/yellow]")
                raise typer.Exit(code=0)

        # Step 5: Apply changes
        with console.status("[blue]Pushing...[/blue]"):
            result = await apply_org(client, plan, prune=prune, config_dir=Path.cwd())

    # Step 6: Print per-resource results
    for r in result.results:
        resource_label = r.resource_type.capitalize()
        if r.success:
            symbol = {
                "created": "+",
                "updated": "~",
                "deleted": "-",
            }.get(r.action, "?")
            color = {
                "created": "green",
                "updated": "yellow",
                "deleted": "red",
            }.get(r.action, "white")
            console.print(
                f"  [{color}]{symbol}[/{color}] {resource_label}: {r.identifier} ({r.action})"
            )
        else:
            console.print(
                f"  [red]x[/red] {resource_label}: {r.identifier} ({r.action}) -- {r.error}"
            )

    # Step 7: Print summary
    console.print()
    if result.has_failures:
        console.print(
            f"[red]Push complete with errors[/red] "
            f"[dim]|[/dim] {result.created_count} created "
            f"[dim]|[/dim] {result.updated_count} updated "
            f"[dim]|[/dim] {result.deleted_count} deleted "
            f"[dim]|[/dim] {result.failed_count} failed"
        )
    else:
        console.print(
            f"[green]Push complete[/green] "
            f"[dim]|[/dim] {result.created_count} created "
            f"[dim]|[/dim] {result.updated_count} updated "
            f"[dim]|[/dim] {result.deleted_count} deleted "
            f"[dim]|[/dim] {result.failed_count} failed"
        )

    # Step 8: Record to state
    git_commit = _get_git_commit()
    resources_changed = [f"{r.resource_type}:{r.identifier}" for r in result.results if r.success]
    event = ApplyEvent(
        org=org,
        timestamp=datetime.now(UTC).isoformat(),
        git_commit=git_commit,
        resources_changed=resources_changed,
    )
    record_apply(STATE_FILE, event)

    # Step 9: Exit code
    if result.has_failures:
        raise typer.Exit(code=1)


def _get_git_commit() -> str | None:
    """Get the current git commit hash, or None if not in a git repo.

    Returns:
        The short git commit hash, or None.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
