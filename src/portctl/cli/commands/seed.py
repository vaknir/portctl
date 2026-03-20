"""Seed command: populate Port.io with demo data."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from portctl.exceptions import PortctlError

app = typer.Typer(no_args_is_help=False)
console = Console()


@app.command(name="run")
def seed_run(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias to seed into. Uses default org if not specified.",
    ),
    cleanup: bool = typer.Option(
        False,
        "--cleanup",
        help="Remove all seeded demo data instead of creating it.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
) -> None:
    """Seed demo data into your Port.io organization."""
    from portctl.cli.guard import require_config

    config = require_config()
    try:
        if cleanup:
            asyncio.run(_cleanup(org, config, yes))
        else:
            asyncio.run(_seed(org, config, yes))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _seed(
    org: str | None,
    config: object,
    yes: bool,
) -> None:
    """Async implementation of the seed command.

    Args:
        org: Organization alias or None for default.
        config: Validated portctl configuration.
        yes: If True, skip confirmation prompt.
    """
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.seeder import (
        BLUEPRINTS,
        ENVIRONMENTS,
        MICROSERVICES,
        SCORECARDS,
        TEAMS,
        SeedResult,
        _generate_deployments,
        seed_demo_data,
    )

    org_config = get_org(config, org)  # type: ignore[arg-type]
    org_name = org or config.default_org  # type: ignore[union-attr]
    client_id, client_secret = resolve_credentials(org_name, config)  # type: ignore[arg-type]

    deployments = _generate_deployments()

    # Welcome panel
    console.print()
    console.print(
        Panel(
            "[bold]Seed Demo Data[/bold]\n"
            "Populate your portal with a realistic\n"
            "engineering organization setup",
            border_style="blue",
        )
    )
    console.print()

    # Summary table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Resource", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Blueprints", str(len(BLUEPRINTS)))
    table.add_row("Scorecards", str(len(SCORECARDS)))
    table.add_row("Teams", str(len(TEAMS)))
    table.add_row("Environments", str(len(ENVIRONMENTS)))
    table.add_row("Microservices", str(len(MICROSERVICES)))
    table.add_row("Deployments", str(len(deployments)))
    console.print("  This will create:")
    console.print(table)
    console.print()

    if not yes and not typer.confirm("Proceed?", default=True):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(code=0)

    current_step = ""

    def on_progress(step: str, item: str, detail: str = "") -> None:
        nonlocal current_step
        if step != current_step:
            current_step = step
            console.print()
            console.print(f"  [bold]Creating {step}...[/bold]")

        suffix = f"  {detail}" if detail else ""
        console.print(f"    [green]\\u2713[/green] {item}{suffix}")

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        result: SeedResult = await seed_demo_data(client, on_progress=on_progress)

    console.print()
    total_entities = result.entities_created
    console.print(
        Panel(
            f"[green bold]\\u2713 Demo data seeded![/green bold]\n\n"
            f"{result.blueprints_created} blueprints, "
            f"{result.scorecards_created} scorecard, "
            f"{total_entities} entities\n\n"
            f"Explore:\n"
            f"  [bold]portctl blueprint show microservice[/bold]\n"
            f"  [bold]portctl export {org_name}[/bold]",
            border_style="green",
        )
    )


async def _cleanup(
    org: str | None,
    config: object,
    yes: bool,
) -> None:
    """Async implementation of the cleanup command.

    Args:
        org: Organization alias or None for default.
        config: Validated portctl configuration.
        yes: If True, skip confirmation prompt.
    """
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.services.seeder import (
        BLUEPRINTS,
        ENVIRONMENTS,
        MICROSERVICES,
        SCORECARDS,
        TEAMS,
        _generate_deployments,
        cleanup_demo_data,
    )

    org_config = get_org(config, org)  # type: ignore[arg-type]
    org_name = org or config.default_org  # type: ignore[union-attr]
    client_id, client_secret = resolve_credentials(org_name, config)  # type: ignore[arg-type]

    deployments = _generate_deployments()
    total_entities = len(TEAMS) + len(ENVIRONMENTS) + len(MICROSERVICES) + len(deployments)

    # Cleanup panel
    console.print()
    console.print(
        Panel(
            "[bold]Cleanup Demo Data[/bold]\n"
            "Remove all seeded demo resources",
            border_style="yellow",
        )
    )
    console.print()

    if not yes and not typer.confirm(
        f"This will delete {len(BLUEPRINTS)} blueprints, "
        f"{len(SCORECARDS)} scorecard, and {total_entities} entities. Proceed?",
        default=False,
    ):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(code=0)

    current_step = ""

    def on_progress(step: str, item: str, detail: str = "") -> None:
        nonlocal current_step
        if step != current_step:
            current_step = step
            console.print()
            console.print(f"  [bold]Deleting {step}...[/bold]")

        console.print(f"    [green]\\u2713[/green] {item}")

    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        deleted = await cleanup_demo_data(client, on_progress=on_progress)

    console.print()
    console.print(
        Panel(
            f"[green bold]\\u2713 Demo data cleaned up![/green bold]\n"
            f"Removed {deleted} resources",
            border_style="green",
        )
    )
