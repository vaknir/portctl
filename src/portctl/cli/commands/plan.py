"""Plan command: dry-run diff of local vs live config."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def plan_run(
    org: str = typer.Argument(help="Organization to plan against."),
) -> None:
    """Show a dry-run diff of local YAML vs live Port.io config."""
    console.print(f"[yellow]Plan for '{org}' not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
