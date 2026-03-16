"""Org commands: list, add, remove."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="list")
def list_orgs() -> None:
    """List configured organizations."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
