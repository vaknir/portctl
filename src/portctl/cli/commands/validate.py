"""Validate command: check local YAML files for errors."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - typer needs Path at runtime for CLI arg

import typer
from rich.console import Console

from portctl.validation.pipeline import validate

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command(name="run")
def validate_run(
    config_dir: Path = typer.Argument(  # noqa: B008
        ".",
        help="Root directory containing blueprints/ and scorecards/ subdirectories.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Validate local YAML configuration files."""
    result = validate(config_dir)

    if not result.issues:
        console.print("[green]All checks passed.[/green]")
        raise typer.Exit(code=0)

    for issue in result.issues:
        location = issue.file_path
        if issue.line is not None:
            location = f"{location}:{issue.line}"

        icon = "[red]x[/red]" if issue.severity == "error" else "[yellow]![/yellow]"

        console.print(f"  {icon} {location} -> {issue.message}")
        if issue.suggestion:
            console.print(f"    [dim]{issue.suggestion}[/dim]")

    error_count = result.error_count
    warning_count = len(result.issues) - error_count

    parts: list[str] = []
    if error_count:
        parts.append(f"[red]{error_count} error(s)[/red]")
    if warning_count:
        parts.append(f"[yellow]{warning_count} warning(s)[/yellow]")

    console.print()
    console.print(f"{' . '.join(parts)} -- fix before applying")

    if result.has_errors:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)
