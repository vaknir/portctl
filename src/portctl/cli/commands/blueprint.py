"""Blueprint commands: show blueprint details."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def show(
    name: str = typer.Argument(help="Blueprint identifier to inspect."),
) -> None:
    """Show details of a blueprint."""
    console.print(f"[yellow]Blueprint show for '{name}' not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
