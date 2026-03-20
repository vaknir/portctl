"""Init command: initialize a new portctl project."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from portctl.constants import DEFAULT_API_URL
from portctl.exceptions import ConfigError, PortctlError
from portctl.services.initializer import InitOptions, init_project

console = Console()


def init_command(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias for this project.",
    ),
    mode: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--mode",
        help="Init mode: 'existing' (export live config) or 'fresh' (scaffold templates).",
    ),
    client_id: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--client-id",
        help="Port API client ID (required for 'existing' mode).",
    ),
    client_secret: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--client-secret",
        help="Port API client secret (required for 'existing' mode).",
    ),
    api_url: str = typer.Option(
        DEFAULT_API_URL,
        "--api-url",
        help="Port API base URL.",
    ),
    no_ci: bool = typer.Option(
        False,
        "--no-ci",
        help="Skip CI workflow generation.",
    ),
    no_ignore: bool = typer.Option(
        False,
        "--no-ignore",
        help="Skip .portctlignore generation.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Run without interactive prompts. Requires --org and --mode.",
    ),
    directory: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--dir",
        "-d",
        help="Project directory. Defaults to current directory.",
    ),
) -> None:
    """Initialize a new portctl project."""
    project_dir = Path(directory) if directory is not None else Path.cwd()

    if non_interactive:
        if org is None:
            console.print("[red]Error: --org is required in non-interactive mode.[/red]")
            raise typer.Exit(code=1)
        if mode is None:
            console.print("[red]Error: --mode is required in non-interactive mode.[/red]")
            raise typer.Exit(code=1)
    else:
        # Interactive prompts
        if org is None:
            org = typer.prompt("Organization alias")
        if mode is None:
            mode = typer.prompt(
                "Init mode",
                type=str,
                default="fresh",
                show_choices=True,
            )

    if mode not in ("existing", "fresh"):
        console.print(f"[red]Error: Invalid mode '{mode}'. Must be 'existing' or 'fresh'.[/red]")
        raise typer.Exit(code=1)

    # For existing mode, prompt for credentials if not provided
    if mode == "existing" and not non_interactive:
        if client_id is None:
            client_id = typer.prompt("Port Client ID")
        if client_secret is None:
            client_secret = typer.prompt("Port Client Secret", hide_input=True)

    options = InitOptions(
        org_name=org,
        mode=mode,  # type: ignore[arg-type]
        client_id=client_id,
        client_secret=client_secret,
        api_url=api_url,
        generate_ci=not no_ci,
        generate_ignore=not no_ignore,
        project_dir=project_dir,
    )

    try:
        result = asyncio.run(init_project(options))
    except ConfigError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None

    # Print success summary
    console.print()
    console.print("[green]Project initialized successfully![/green]")
    console.print()

    console.print(f"  Config:  {result.config_path}")
    console.print(f"  State:   {result.state_path}")

    if result.ignore_path:
        console.print(f"  Ignore:  {result.ignore_path}")
    if result.ci_workflow_path:
        console.print(f"  CI:      {result.ci_workflow_path}")

    if result.scaffolded_templates:
        console.print()
        console.print(f"  Scaffolded {len(result.scaffolded_templates)} template(s):")
        for tmpl in result.scaffolded_templates:
            console.print(f"    - {tmpl}")

    if result.exported_resources > 0:
        console.print()
        console.print(f"  Exported {result.exported_resources} resource(s) from live portal.")

    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print("[dim]  1. Run 'portctl auth login' to store credentials[/dim]")
    console.print("[dim]  2. Edit blueprints/ and scorecards/ as needed[/dim]")
    console.print("[dim]  3. Run 'portctl validate' to check your config[/dim]")
    console.print("[dim]  4. Run 'portctl plan <org>' to preview changes[/dim]")
