"""Rollback command: restore a Port org to a previous apply or export state."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from portctl.exceptions import PortctlError

console = Console()


def rollback_command(
    event_id: str = typer.Argument(
        help="Event ID to roll back to (from 'portctl history').",
    ),
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization. Uses default org if not specified.",
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
    config_dir: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--dir",
        help="Project directory. Defaults to current directory.",
    ),
) -> None:
    """Roll back to a previous apply or export state.

    Uses the event ID from 'portctl history' to identify the target state.
    If the target event has a git commit, files are restored from that commit
    and then pushed via the normal plan+apply pipeline.
    """
    from portctl.cli.guard import require_config

    config = require_config()
    org_name = org or config.default_org
    if org_name is None:
        console.print("[red]No default org set. Specify an org or set default_org in config.[/red]")
        raise typer.Exit(code=1)

    try:
        asyncio.run(
            _rollback_run(
                event_id=event_id,
                org=org_name,
                yes=yes,
                prune=prune,
                config_dir=config_dir,
                config=config,
            )
        )
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _rollback_run(
    event_id: str,
    org: str,
    yes: bool,
    prune: bool,
    config_dir: str | None,
    config: object,
) -> None:
    """Async implementation of the rollback command.

    Args:
        event_id: Event ID to roll back to.
        org: Organization alias from config.
        yes: Whether to skip confirmation.
        prune: Whether to delete remote-only resources.
        config_dir: Optional project directory override.
        config: Validated portctl configuration.
    """
    from datetime import UTC, datetime

    from portctl.cli.formatters.diffs import format_plan
    from portctl.client.port_client import PortClient
    from portctl.models.config import PortctlConfig
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.planner import plan_org
    from portctl.services.rollback import (
        execute_rollback,
        find_rollback_target,
    )
    from portctl.services.state import EXPORT_STATE_FILENAME, ApplyEvent, record_apply

    assert isinstance(config, PortctlConfig)

    directory = Path(config_dir) if config_dir is not None else Path.cwd()
    state_path = directory / EXPORT_STATE_FILENAME

    # Step 1: Find the target event
    target = find_rollback_target(state_path, event_id)
    if target is None:
        console.print(
            f"[red]Event '{event_id}' not found in state history.[/red]\n"
            "[dim]Run 'portctl history' to see available events.[/dim]"
        )
        raise typer.Exit(code=1)

    # Step 2: Show target info
    console.print("[bold]Rollback target:[/bold]")
    console.print(f"  Event ID:  {target.event_id}")
    console.print(f"  Timestamp: {target.timestamp}")
    console.print(f"  Via:       {target.via}")
    if target.git_commit:
        console.print(f"  Commit:    {target.git_commit}")
    console.print()

    # Step 3: Connect and run
    org_config = get_org(config, org)
    client_id, client_secret = resolve_credentials(org, config)

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        # Step 3a: If git commit, preview the plan first using the rollback
        # service which handles temp dir checkout
        if target.git_commit:
            import tempfile

            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_path = Path(temp_dir_obj.name)
            try:
                from portctl.services.rollback import _checkout_files_at_commit

                _checkout_files_at_commit(target.git_commit, directory, temp_path)
                with console.status("[blue]Planning rollback...[/blue]"):
                    plan = await plan_org(client, temp_path)
            except Exception as exc:
                temp_dir_obj.cleanup()
                console.print(
                    f"[red]Failed to checkout files at commit {target.git_commit}: {exc}[/red]"
                )
                raise typer.Exit(code=1) from None
        else:
            temp_dir_obj = None
            temp_path = None
            with console.status("[blue]Planning rollback...[/blue]"):
                plan = await plan_org(client, directory)

        # Step 4: Check for changes
        if not plan.has_changes:
            console.print("[green]Already at target state. Nothing to do.[/green]")
            if temp_dir_obj is not None:
                temp_dir_obj.cleanup()
            return

        # Step 5: Show plan and ask for confirmation
        format_plan(plan, console)
        console.print()

        if plan.breaking_count > 0 and not yes:
            console.print("[red bold]This rollback includes breaking changes.[/red bold]")
            confirmation = typer.prompt("Type 'yes' to confirm rollback")
            if confirmation != "yes":
                console.print("[yellow]Rollback cancelled.[/yellow]")
                if temp_dir_obj is not None:
                    temp_dir_obj.cleanup()
                raise typer.Exit(code=0)
        elif not yes:
            if not typer.confirm("Apply this rollback?"):
                console.print("[yellow]Rollback cancelled.[/yellow]")
                if temp_dir_obj is not None:
                    temp_dir_obj.cleanup()
                raise typer.Exit(code=0)

        # Step 6: Execute the rollback (apply the plan)
        with console.status("[blue]Applying rollback...[/blue]"):
            result = await execute_rollback(client, target, directory, prune=prune)

        if temp_dir_obj is not None:
            temp_dir_obj.cleanup()

    # Step 7: Print per-resource results
    if result.apply_result is not None:
        for r in result.apply_result.results:
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

    # Step 8: Print summary
    console.print()
    if result.success:
        console.print(f"[green]Rollback complete[/green] -- restored to event {target.event_id}")
    else:
        error_detail = result.error or "some resources failed"
        console.print(f"[red]Rollback completed with errors[/red] -- {error_detail}")

    # Step 9: Record the rollback as a new apply event
    git_commit = _get_git_commit()
    resources_changed: list[str] = []
    if result.apply_result is not None:
        resources_changed = [
            f"{r.resource_type}:{r.identifier}" for r in result.apply_result.results if r.success
        ]

    event = ApplyEvent(
        org=org,
        timestamp=datetime.now(UTC).isoformat(),
        git_commit=git_commit,
        resources_changed=resources_changed,
    )
    record_apply(state_path, event)

    # Step 10: Exit code
    if not result.success:
        raise typer.Exit(code=1)


def _get_git_commit() -> str | None:
    """Get the current git commit hash, or None if not in a git repo.

    Returns:
        The short git commit hash, or None.
    """
    import subprocess

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
