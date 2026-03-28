"""Auth commands: login, status, logout."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from portctl.constants import DEFAULT_API_URL
from portctl.exceptions import AuthError, ConfigError, PortctlError
from portctl.services.auth import (
    resolve_credentials,
    store_credentials,
    verify_token,
)
from portctl.services.config import ensure_org, get_org, load_config

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def login(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias. Defaults to the default_org from config.",
    ),
    client_id: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--client-id",
        help="Port API client ID. If omitted, you will be prompted.",
    ),
    client_secret: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--client-secret",
        help="Port API client secret. If omitted, you will be prompted.",
    ),
) -> None:
    """Authenticate with Port.io using client credentials."""
    try:
        config = load_config()
    except ConfigError:
        # No config file -- require --org flag
        if org is None:
            console.print(
                "[red]No config file found and --org not specified. "
                "Run 'portctl org add' first or pass --org.[/red]"
            )
            raise typer.Exit(code=1) from None
        org_name = org
        api_url = DEFAULT_API_URL
    else:
        try:
            org_config = get_org(config, name=org)
        except ConfigError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None
        org_name = org if org is not None else config.default_org
        if org_name is None:
            console.print("[red]No default org set. Specify --org.[/red]")
            raise typer.Exit(code=1)
        api_url = org_config.api_url

    # Prompt interactively if flags not provided
    if client_id is None:
        client_id = typer.prompt("Client ID")
    if client_secret is None:
        client_secret = typer.prompt("Client Secret", hide_input=True)

    try:
        user_info = asyncio.run(verify_token(client_id, client_secret, api_url))
    except AuthError as exc:
        console.print(f"[red]Login failed: {exc}[/red]")
        raise typer.Exit(code=1) from None

    store_credentials(org_name, client_id, client_secret)

    # Ensure org exists in config file (creates ~/.portctl/config.yaml if needed)
    ensure_org(org_name, api_url=api_url)

    console.print(f"[green]\u2713 Authenticated as {org_name}[/green]")

    if user_info.get("email"):
        console.print(f"  User: {user_info['email']}")


@app.command()
def status(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias. Defaults to the default_org from config.",
    ),
) -> None:
    """Show current authentication status."""
    from portctl.cli.guard import require_config

    config = require_config()
    try:
        org_config = get_org(config, name=org)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    org_name: str = org if org is not None else config.default_org
    if org_name is None:
        console.print("[red]No default org set. Specify --org.[/red]")
        raise typer.Exit(code=1)
    api_url = org_config.api_url

    # Resolve credentials
    try:
        client_id, client_secret = resolve_credentials(
            org_name,
            config,
        )
    except (AuthError, PortctlError) as exc:
        console.print(f"[bold]{org_name}[/bold]: [red]not configured[/red]")
        console.print(f"  {exc}")
        raise typer.Exit(code=1) from None

    # Verify token is live
    try:
        user_info = asyncio.run(verify_token(client_id, client_secret, api_url))
    except AuthError:
        console.print(f"[bold]{org_name}[/bold]: [yellow]expired[/yellow]")
        console.print("  Credentials found but authentication failed. Re-run 'portctl auth login'.")
        raise typer.Exit(code=1) from None

    console.print(f"[bold]{org_name}[/bold]: [green]authenticated[/green]")
    if user_info.get("email"):
        console.print(f"  User: {user_info['email']}")


@app.command()
def logout() -> None:
    """Remove stored credentials."""
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)
