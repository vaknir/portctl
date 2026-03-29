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

    from portctl.cli.formatters.progress import StepProgress

    progress = StepProgress(quiet=False)
    progress.start("Layer 1 (local)")
    l1_result = validate(config_dir)
    progress.complete("Layer 1 (local)")

    if l1_result.has_errors:
        progress.finish()
        _print_result(l1_result, remote=True)
        return

    progress.start("Layer 2 (remote)")
    async with PortClient(
        client_id=client_id,
        client_secret=client_secret,
        api_base=org_config.api_url,
    ) as client:
        result = await validate_remote(config_dir, client)
    progress.complete("Layer 2 (remote)")
    progress.finish()

    _print_result(result, remote=True)


def _print_result(
    result: ValidationResult,
    *,
    remote: bool = False,
) -> None:
    """Format and print validation results as layered gates.

    Args:
        result: The validation result to display.
        remote: Whether remote checks were included.
    """
    from portctl.cli.formatters.progress import format_validation_gate

    # Infer layer partitioning: if remote=True and there are errors, they must be
    # layer 1 errors because layer2 is skipped when layer1 fails.
    layer1_ok = not result.has_errors
    console.print(format_validation_gate(result.issues, remote=remote, layer1_ok=layer1_ok))

    if result.has_errors:
        raise typer.Exit(code=1)
    if not remote and not result.issues:
        console.print(
            "\n[dim]Run 'portctl validate --remote' to also check against the live API.[/dim]"
        )
    raise typer.Exit(code=0)
