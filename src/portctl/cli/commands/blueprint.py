"""Blueprint commands: show blueprint details."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console

from portctl.client.port_client import PortClient
from portctl.exceptions import PortAPIError, PortctlError
from portctl.services.auth import resolve_credentials
from portctl.services.config import get_org, load_config

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def show(
    identifier: str = typer.Argument(help="Blueprint identifier to inspect."),
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias. Defaults to the default_org from config.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON instead of the rich structured view.",
    ),
) -> None:
    """Show details of a blueprint."""
    try:
        asyncio.run(_show(identifier, org, output_json))
    except PortctlError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from None


async def _show(identifier: str, org: str | None, output_json: bool) -> None:
    """Async implementation of blueprint show.

    Args:
        identifier: Blueprint identifier to fetch.
        org: Organization alias from config, or None to use default.
        output_json: When True, print raw JSON; otherwise render rich view.

    Raises:
        PortctlError: On config, auth, or API errors.
    """
    from portctl.cli.formatters.panels import render_blueprint

    config = load_config()
    org_config = get_org(config, org)
    org_name = org if org is not None else config.default_org

    client_id, client_secret = resolve_credentials(org_name, config)  # type: ignore[arg-type]

    try:
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            blueprint_data = await client.get_blueprint(identifier)
    except PortAPIError as exc:
        if exc.status_code == 404:
            console.print(f"[red]Blueprint '{identifier}' not found.[/red]")
            raise typer.Exit(code=1) from None
        raise

    if output_json:
        console.print(json.dumps(blueprint_data))
    else:
        render_blueprint(blueprint_data, console)
