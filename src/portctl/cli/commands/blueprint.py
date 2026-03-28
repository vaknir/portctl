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


def _fetch_blueprints(org: str | None) -> list[dict[str, str]]:
    """Fetch non-internal blueprints from the API.

    Args:
        org: Organization alias, or None for default.

    Returns:
        List of dicts with 'identifier' and 'title' keys.
    """
    config = load_config()
    org_config = get_org(config, org)
    org_name = org if org is not None else config.default_org
    client_id, client_secret = resolve_credentials(org_name, config)  # type: ignore[arg-type]

    async def _fetch() -> list[dict[str, str]]:
        async with PortClient(
            client_id=client_id,
            client_secret=client_secret,
            api_base=org_config.api_url,
        ) as client:
            raw = await client.get_blueprints()
            return [
                {"identifier": bp["identifier"], "title": bp.get("title", "")}
                for bp in raw
                if not bp.get("identifier", "").startswith(("_", "$"))
            ]

    return asyncio.run(_fetch())


@app.command()
def show(
    identifier: Optional[str] = typer.Argument(  # noqa: UP007, UP045
        None,
        help="Blueprint identifier to inspect. Omit to pick from a list.",
    ),
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
        if identifier is not None:
            asyncio.run(_show(identifier, org, output_json))
            return

        # Interactive loop: pick → show → pick again or quit
        import questionary

        blueprints = _fetch_blueprints(org)
        if not blueprints:
            console.print("[yellow]No blueprints found.[/yellow]")
            raise typer.Exit(code=0)

        choices = [
            questionary.Choice(
                title=f"{bp['identifier']}  ({bp['title']})",
                value=bp["identifier"],
            )
            for bp in blueprints
        ]

        while True:
            selected = questionary.select(
                "Select a blueprint:",
                choices=choices,
                use_arrow_keys=True,
                use_shortcuts=False,
            ).ask()

            if selected is None:
                break

            asyncio.run(_show(selected, org, output_json))
            console.print()

            if not questionary.confirm("View another blueprint?", default=True).ask():
                break
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
