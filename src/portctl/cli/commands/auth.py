"""Auth commands: login, status, logout."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def login() -> None:
    """Authenticate with Port.io using client credentials."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show current authentication status."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
