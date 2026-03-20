"""Config guard: ensure portctl is configured before running commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel

from portctl.exceptions import ConfigError
from portctl.services.config import load_config

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig

console = Console()

_NOT_CONFIGURED_MESSAGE = (
    "portctl is not configured yet.\n\n"
    "You need to connect to your Port.io organization\n"
    "before running commands."
)


def require_config(*, interactive: bool = True) -> PortctlConfig:
    """Load config, or guide the user through setup if missing.

    Args:
        interactive: When True, offer to run init interactively.
            When False, print a message and exit with code 1.

    Returns:
        A validated PortctlConfig instance.

    Raises:
        typer.Exit: If config is missing and the user declines setup
            or interactive mode is disabled.
    """
    try:
        return load_config()
    except ConfigError:
        pass

    console.print(Panel(_NOT_CONFIGURED_MESSAGE, title="Setup Required", border_style="yellow"))

    if not interactive:
        console.print("Run [bold]portctl init[/bold] to get started.")
        raise typer.Exit(code=1)

    if not typer.confirm("Would you like to set up now?", default=True):
        console.print("Run [bold]portctl init[/bold] when you're ready.")
        raise typer.Exit(code=0)

    from portctl.cli.commands.init import init_command

    init_command()

    return load_config()
