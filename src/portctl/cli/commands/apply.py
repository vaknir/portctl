"""Apply command: push local YAML config to Port.io."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from portctl.constants import STATE_FILE
from portctl.exceptions import PortctlError

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def apply_run(
    org: str = typer.Argument(help="Organization to apply to."),
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
    """Apply local YAML configuration to Port.io."""
    try:
        asyncio.run(_apply_run(org, yes, prune, resource))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _apply_run(
    org: str,
    yes: bool,
    prune: bool,
    resource: str | None,
) -> None:
    """Async implementation of the apply command.

    Args:
        org: Organization alias from config.
        yes: Whether to skip confirmation.
        prune: Whether to delete remote-only resources.
        resource: Optional resource type filter.
    """
    from datetime import UTC, datetime

    from portctl.cli.formatters.diffs import format_plan
    from portctl.client.port_client import PortClient
    from portctl.services.applier import apply_org
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org, load_config
    from portctl.services.planner import plan_org
    from portctl.services.state import ApplyEvent, record_apply

    config = load_config()
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
            console.print("[green]Nothing to apply.[/green]")
            return

        # Step 3: Print plan output
        format_plan(plan, console)
        console.print()

        # Step 4: Confirmation
        if plan.breaking_count > 0 and not yes:
            console.print(
                "[red bold]This plan includes breaking changes.[/red bold]"
            )
            confirmation = typer.prompt("Type 'yes' to confirm")
            if confirmation != "yes":
                console.print("[yellow]Apply cancelled.[/yellow]")
                raise typer.Exit(code=0)
        elif not yes:
            if not typer.confirm("Apply these changes?"):
                console.print("[yellow]Apply cancelled.[/yellow]")
                raise typer.Exit(code=0)

        # Step 5: Apply changes
        with console.status("[blue]Applying...[/blue]"):
            result = await apply_org(
                client, plan, prune=prune, config_dir=Path.cwd()
            )

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
                f"  [{color}]{symbol}[/{color}] {resource_label}: "
                f"{r.identifier} ({r.action})"
            )
        else:
            console.print(
                f"  [red]x[/red] {resource_label}: "
                f"{r.identifier} ({r.action}) -- {r.error}"
            )

    # Step 7: Print summary
    console.print()
    if result.has_failures:
        console.print(
            f"[red]Apply complete with errors[/red] "
            f"[dim]|[/dim] {result.created_count} created "
            f"[dim]|[/dim] {result.updated_count} updated "
            f"[dim]|[/dim] {result.deleted_count} deleted "
            f"[dim]|[/dim] {result.failed_count} failed"
        )
    else:
        console.print(
            f"[green]Apply complete[/green] "
            f"[dim]|[/dim] {result.created_count} created "
            f"[dim]|[/dim] {result.updated_count} updated "
            f"[dim]|[/dim] {result.deleted_count} deleted "
            f"[dim]|[/dim] {result.failed_count} failed"
        )

    # Step 8: Record to state
    git_commit = _get_git_commit()
    resources_changed = [
        f"{r.resource_type}:{r.identifier}"
        for r in result.results
        if r.success
    ]
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
