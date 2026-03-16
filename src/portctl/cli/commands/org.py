"""Org commands: list, add, remove."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from portctl.exceptions import ConfigError
from portctl.services.config import list_orgs, load_config

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="list")
def list_orgs_cmd() -> None:
    """List configured organizations."""
    try:
        config = load_config()
    except ConfigError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    orgs = list_orgs(config)

    if not orgs:
        console.print("[yellow]No orgs configured.[/yellow] Run 'portctl org add' to add one.")
        return

    table = Table(title="Configured Organizations")
    table.add_column("", style="green", no_wrap=True)  # default marker
    table.add_column("Alias", style="bold")
    table.add_column("Name")
    table.add_column("Role")
    table.add_column("API URL")

    for org in orgs:
        table.add_row(
            org["default"],
            org["alias"],
            org["name"],
            org["role"],
            org["api_url"],
        )

    console.print(table)
