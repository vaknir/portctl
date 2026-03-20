"""Whoami command: show current identity, org, and environment."""

from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from portctl.services.whoami import gather_whoami_info

console = Console()


def whoami(
    org: Optional[str] = typer.Option(  # noqa: UP007, UP045
        None,
        "--org",
        help="Organization alias. Defaults to the default_org from config.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON for CI/scripting.",
    ),
) -> None:
    """Show current identity, org, and environment."""
    info = asyncio.run(gather_whoami_info(org=org))

    if output_json:
        data = {
            "version": info.version,
            "org": info.org_name,
            "role": info.org_role,
            "api_url": info.api_url,
            "credential_source": info.credential_source,
            "authenticated": info.authenticated,
            "ci": info.is_ci,
            "ci_provider": info.ci_provider,
            "config_path": str(info.config_path) if info.config_path else None,
            "state_path": str(info.state_path) if info.state_path else None,
        }
        console.print(json.dumps(data, indent=2))
        return

    # Build a rich table for the panel body
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold", no_wrap=True)
    table.add_column("Value")

    org_display = info.org_name or "[dim]not set[/dim]"
    if info.org_role and info.org_name:
        org_display = f"{info.org_name} ({info.org_role})"

    table.add_row("Org:", org_display)
    table.add_row("API:", info.api_url or "[dim]not set[/dim]")
    table.add_row("Credentials:", info.credential_source or "[dim]none[/dim]")
    table.add_row("Config:", str(info.config_path) if info.config_path else "[dim]not found[/dim]")
    table.add_row("State:", str(info.state_path) if info.state_path else "[dim]not found[/dim]")

    ci_display = f"yes ({info.ci_provider})" if info.is_ci else "no"
    table.add_row("CI:", ci_display)

    auth_display = (
        "[green]authenticated[/green]"
        if info.authenticated
        else "[yellow]not authenticated[/yellow]"
    )
    table.add_row("Auth:", auth_display)

    panel = Panel(
        table,
        title=f"portctl v{info.version}",
        border_style="blue",
    )
    console.print(panel)
