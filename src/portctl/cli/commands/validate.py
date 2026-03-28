"""Validate command: check local YAML files for errors, optionally against remote API."""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003 - typer needs Path at runtime for CLI arg
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console

from portctl.exceptions import PortctlError
from portctl.validation.pipeline import validate

if TYPE_CHECKING:
    from portctl.validation.errors import ValidationResult

console = Console()


def validate_command(
    config_dir: Path = typer.Argument(  # noqa: B008
        ".",
        help="Root directory containing blueprints/ and scorecards/ subdirectories.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    remote: bool = typer.Option(  # noqa: B008
        False,
        "--remote",
        help="Also validate against the live Port API.",
    ),
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045, B008
        None,
        "--org",
        help="Organization for remote validation. Uses default org if not specified.",
    ),
) -> None:
    """Validate local YAML syntax, schema, and cross-references.

    By default this checks your local files only. Use --remote to also
    validate against the live Port API (checks relation targets exist,
    scorecard/action blueprint references, and property type consistency).
    """
    if remote:
        try:
            asyncio.run(_validate_remote(config_dir, org))
        except PortctlError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from None
        return

    result = validate(config_dir)
    _print_result(result)


async def _validate_remote(config_dir: Path, org_name: str | None) -> None:
    """Run local + remote validation and print results.

    Args:
        config_dir: Root config directory.
        org_name: Organization alias, or None for default.
    """
    from portctl.cli.guard import require_config
    from portctl.client.port_client import PortClient
    from portctl.services.auth import resolve_credentials
    from portctl.services.config import get_org
    from portctl.validation.pipeline import validate_remote

    config = require_config()
    resolved_org = org_name or config.default_org
    if resolved_org is None:
        console.print("[red]No default org set. Specify --org or set default_org in config.[/red]")
        raise typer.Exit(code=1)

    org_config = get_org(config, resolved_org)
    client_id, client_secret = resolve_credentials(resolved_org, config)

    with console.status("[blue]Validating against remote...[/blue]"):
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            result = await validate_remote(config_dir, client)

    _print_result(result, remote=True)


def _print_result(
    result: ValidationResult,
    *,
    remote: bool = False,
) -> None:
    """Format and print validation results.

    Args:
        result: The validation result to display.
        remote: Whether remote checks were included.
    """
    if not result.issues:
        label = "Local + remote" if remote else "Local YAML"
        console.print(f"[green]{label} validation passed.[/green]")
        if not remote:
            console.print(
                "[dim]Run 'portctl validate --remote' to also check against the live API.[/dim]"
            )
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
    console.print(f"{' . '.join(parts)} -- fix before pushing")

    if result.has_errors:
        raise typer.Exit(code=1)
    raise typer.Exit(code=0)
