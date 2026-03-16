"""Validate command: check local YAML files for errors."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def validate_run() -> None:
    """Validate local YAML configuration files."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
