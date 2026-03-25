"""Init command: interactive onboarding wizard for portctl."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from portctl.constants import DEFAULT_API_URL
from portctl.exceptions import AuthError, ConfigError, PortctlError
from portctl.services.initializer import InitOptions, InitResult, init_project

logger = logging.getLogger(__name__)

console = Console()


def _render_welcome_banner(con: Console) -> None:
    """Print the welcome panel at the start of the wizard.

    Args:
        con: Rich console for output.
    """
    con.print()
    con.print(
        Panel(
            "[bold]Welcome to portctl![/bold]\n"
            "GitOps CLI for your developer portal",
            border_style="blue",
        )
    )
    con.print()


def _render_step_header(con: Console, step: int, total: int, title: str) -> None:
    """Print a step header line.

    Args:
        con: Rich console for output.
        step: Current step number.
        total: Total number of steps.
        title: Step title.
    """
    con.print(f"[bold blue]Step {step}/{total}[/bold blue] -- [bold]{title}[/bold]")


def _render_summary(
    con: Console,
    result: InitResult,
    org_name: str,
    blueprint_count: int = 0,
    scorecard_count: int = 0,
) -> None:
    """Print the final summary panel with a table of created resources.

    Args:
        con: Rich console for output.
        result: The init workflow result.
        org_name: Organization alias.
        blueprint_count: Number of blueprints discovered.
        scorecard_count: Number of scorecards discovered.
    """
    table = Table(show_header=False, show_edge=False, pad_edge=False)
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("Config:", str(result.config_path))
    table.add_row("State:", str(result.state_path))

    if result.ignore_path:
        table.add_row("Ignore:", str(result.ignore_path))
    if result.ci_workflow_path:
        table.add_row("CI:", str(result.ci_workflow_path))

    total_resources = result.exported_resources
    if result.scaffolded_templates:
        total_resources = len(result.scaffolded_templates)

    if total_resources > 0:
        table.add_row("Resources:", f"{total_resources} exported/scaffolded")

    con.print()
    con.print(Panel(table, title="portctl initialized!", border_style="green"))
    con.print()
    con.print("[dim]Next steps:[/dim]")
    con.print(f"[dim]  portctl plan {org_name}[/dim]")
    con.print("[dim]  portctl validate[/dim]")
    con.print()


async def _discover_resources(
    client_id: str,
    client_secret: str,
    api_url: str,
) -> tuple[int, int]:
    """Discover live blueprint and scorecard counts from Port API.

    Best-effort: returns (0, 0) on any failure.

    Args:
        client_id: Port API client ID.
        client_secret: Port API client secret.
        api_url: Port API base URL.

    Returns:
        Tuple of (blueprint_count, scorecard_count).
    """
    try:
        from portctl.client.port_client import PortClient

        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=api_url,
        ) as client:
            blueprints = await client.get_blueprints()
            blueprint_count = len(blueprints)

            scorecard_count = 0
            for bp in blueprints:
                bp_id = bp.get("identifier", "")
                if bp_id:
                    try:
                        scorecards = await client.get_scorecards(bp_id)
                        scorecard_count += len(scorecards)
                    except Exception:
                        pass

            return blueprint_count, scorecard_count
    except Exception:
        logger.debug("Failed to discover live resources", exc_info=True)
        return 0, 0


async def _run_init(
    org: str,
    org_id: str,
    mode: str,
    client_id: str | None,
    client_secret: str | None,
    api_url: str,
    generate_ci: bool,
    generate_ignore: bool,
    project_dir: Path,
    blueprint_count: int = 0,
    scorecard_count: int = 0,
) -> None:
    """Create InitOptions, run init_project, store credentials, render summary.

    Args:
        org: Organization alias.
        org_id: Port organization ID.
        mode: Init mode ('existing' or 'fresh').
        client_id: Port API client ID.
        client_secret: Port API client secret.
        api_url: Port API base URL.
        generate_ci: Whether to generate CI workflow.
        generate_ignore: Whether to generate .portctlignore.
        project_dir: Project directory.
        blueprint_count: Number of discovered blueprints.
        scorecard_count: Number of discovered scorecards.
    """
    options = InitOptions(
        org_name=org,
        org_id=org_id,
        mode=mode,  # type: ignore[arg-type]
        client_id=client_id,
        client_secret=client_secret,
        api_url=api_url,
        generate_ci=generate_ci,
        generate_ignore=generate_ignore,
        project_dir=project_dir,
    )

    result = await init_project(options)

    # Store credentials in keyring after successful init
    if client_id and client_secret:
        try:
            from portctl.services.auth import store_credentials

            store_credentials(org, client_id, client_secret)
        except Exception:
            logger.debug("Failed to store credentials in keyring", exc_info=True)
            console.print(
                "[yellow]Warning: Could not store credentials in keyring. "
                "Run 'portctl auth login' to store them manually.[/yellow]"
            )

    _render_summary(console, result, org, blueprint_count, scorecard_count)


def init_command(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias for this project.",
    ),
    mode: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--mode",
        help="Init mode: 'existing' (pull live config) or 'fresh' (scaffold templates).",
    ),
    org_id: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org-id",
        help="Port organization ID.",
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
        _run_non_interactive(
            org=org,
            org_id=org_id or "",
            mode=mode,
            client_id=client_id,
            client_secret=client_secret,
            api_url=api_url,
            no_ci=no_ci,
            no_ignore=no_ignore,
            project_dir=project_dir,
        )
    else:
        _run_wizard(
            org=org,
            org_id=org_id,
            mode=mode,
            client_id=client_id,
            client_secret=client_secret,
            api_url=api_url,
            no_ci=no_ci,
            no_ignore=no_ignore,
            project_dir=project_dir,
        )


def _run_non_interactive(
    *,
    org: str | None,
    org_id: str,
    mode: str | None,
    client_id: str | None,
    client_secret: str | None,
    api_url: str,
    no_ci: bool,
    no_ignore: bool,
    project_dir: Path,
) -> None:
    """Run init in non-interactive mode (no prompts).

    Args:
        org: Organization alias (required).
        org_id: Port organization ID.
        mode: Init mode (required).
        client_id: Port API client ID.
        client_secret: Port API client secret.
        api_url: Port API base URL.
        no_ci: Skip CI workflow generation.
        no_ignore: Skip .portctlignore generation.
        project_dir: Project directory.
    """
    if org is None:
        console.print("[red]Error: --org is required in non-interactive mode.[/red]")
        raise typer.Exit(code=1)
    if mode is None:
        console.print("[red]Error: --mode is required in non-interactive mode.[/red]")
        raise typer.Exit(code=1)
    if mode not in ("existing", "fresh"):
        console.print(f"[red]Error: Invalid mode '{mode}'. Must be 'existing' or 'fresh'.[/red]")
        raise typer.Exit(code=1)

    try:
        asyncio.run(
            _run_init(
                org=org,
                org_id=org_id,
                mode=mode,
                client_id=client_id,
                client_secret=client_secret,
                api_url=api_url,
                generate_ci=not no_ci,
                generate_ignore=not no_ignore,
                project_dir=project_dir,
            )
        )
    except (ConfigError, PortctlError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


def _run_wizard(
    *,
    org: str | None,
    org_id: str | None,
    mode: str | None,
    client_id: str | None,
    client_secret: str | None,
    api_url: str,
    no_ci: bool,
    no_ignore: bool,
    project_dir: Path,
) -> None:
    """Run the interactive 4-step onboarding wizard.

    Args:
        org: Pre-supplied organization alias (skips prompt if provided).
        org_id: Pre-supplied Port organization ID (skips prompt if provided).
        mode: Pre-supplied mode (skips prompt if provided).
        client_id: Pre-supplied client ID (skips prompt if provided).
        client_secret: Pre-supplied client secret (skips prompt if provided).
        api_url: Port API base URL.
        no_ci: Skip CI workflow generation.
        no_ignore: Skip .portctlignore generation.
        project_dir: Project directory.
    """
    _render_welcome_banner(console)

    # -- Step 1: Organization Setup --
    _render_step_header(console, 1, 3, "Organization Setup")

    if org_id is None:
        org_id = typer.prompt("  Port Organization ID")
    else:
        console.print(f"  Org ID: [bold]{org_id}[/bold]")

    if org is None:
        org = typer.prompt("  What should we call this org? (e.g. production, staging)")
    else:
        console.print(f"  Alias: [bold]{org}[/bold]")

    if client_id is None:
        client_id = typer.prompt("  Port API Client ID")
    if client_secret is None:
        client_secret = typer.prompt("  Port API Client Secret", hide_input=True)

    # Verify credentials and discover resources
    blueprint_count = 0
    scorecard_count = 0

    with console.status("[bold blue]Connecting to Port.io...[/bold blue]"):
        try:
            from portctl.services.auth import verify_token

            asyncio.run(verify_token(client_id, client_secret, api_url))
        except AuthError as exc:
            console.print(f"  [red]Authentication failed: {exc}[/red]")
            raise typer.Exit(code=3) from None

        blueprint_count, scorecard_count = asyncio.run(
            _discover_resources(client_id, client_secret, api_url)
        )

    console.print(
        f"  [green]Connected![/green] "
        f"Found {blueprint_count} blueprint(s), {scorecard_count} scorecard(s)"
    )
    console.print()

    # -- Step 2: Project Setup --
    _render_step_header(console, 2, 3, "Project Setup")

    if blueprint_count > 0:
        console.print(f"  You have {blueprint_count} blueprint(s) in Port.io.")
        console.print("    1) existing -- import live config")
        console.print("    2) fresh -- start from templates")

        if mode is None:
            mode_choice = typer.prompt("  Choose", default="1")
            mode = "existing" if mode_choice == "1" else "fresh"
        else:
            console.print(f"  Mode: [bold]{mode}[/bold]")
    else:
        console.print("  No blueprints found -- starting fresh with templates.")
        mode = "fresh"

    console.print()

    # -- Step 3: Extras --
    _render_step_header(console, 3, 3, "Extras")

    generate_ci = not no_ci
    generate_ignore = not no_ignore

    if not no_ci:
        ci_answer = typer.prompt("  Generate GitHub Actions workflow?", default="Y")
        generate_ci = ci_answer.strip().lower() in ("y", "yes", "")

    if not no_ignore:
        ignore_answer = typer.prompt("  Generate .portctlignore?", default="Y")
        generate_ignore = ignore_answer.strip().lower() in ("y", "yes", "")

    console.print()

    # -- Run init --
    with console.status("[bold blue]Setting up project...[/bold blue]"):
        try:
            asyncio.run(
                _run_init(
                    org=org,
                    org_id=org_id or "",
                    mode=mode,
                    client_id=client_id,
                    client_secret=client_secret,
                    api_url=api_url,
                    generate_ci=generate_ci,
                    generate_ignore=generate_ignore,
                    project_dir=project_dir,
                    blueprint_count=blueprint_count,
                    scorecard_count=scorecard_count,
                )
            )
        except (ConfigError, PortctlError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from None
