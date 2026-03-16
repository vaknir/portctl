"""Export command: pull live config to local YAML files."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def export_run(
    org: str = typer.Argument(help="Organization to export from."),
) -> None:
    """Export portal configuration from Port.io to local YAML files."""
    console.print(f"[yellow]Export for '{org}' not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
