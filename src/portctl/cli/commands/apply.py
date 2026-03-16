"""Apply command: push local YAML config to Port.io."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def apply_run(
    org: str = typer.Argument(help="Organization to apply to."),
) -> None:
    """Apply local YAML configuration to Port.io."""
    console.print(f"[yellow]Apply for '{org}' not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
