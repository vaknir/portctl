"""Typer app factory and top-level command group for portctl."""

from __future__ import annotations

from typing import Optional

import typer

from portctl.cli.commands.apply import push_command
from portctl.cli.commands.auth import app as auth_app
from portctl.cli.commands.blueprint import app as blueprint_app
from portctl.cli.commands.export import pull_command
from portctl.cli.commands.init import init_command
from portctl.cli.commands.org import app as org_app
from portctl.cli.commands.plan import diff_command
from portctl.cli.commands.seed import seed_command
from portctl.cli.commands.validate import validate_command
from portctl.cli.commands.whoami import whoami  # noqa: I001
from portctl.constants import VERSION

app = typer.Typer(
    name="portctl",
    help="GitOps CLI for Port.io -- kubectl for your developer portal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"portctl {VERSION}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(  # noqa: UP007, UP045
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """portctl - GitOps CLI for Port.io."""


# -- Setup --
app.command(name="init", rich_help_panel="Setup")(init_command)
app.add_typer(
    auth_app, name="auth", help="Authenticate with Port.io.",
    rich_help_panel="Setup",
)
app.add_typer(
    org_app, name="org", help="Manage organizations.",
    rich_help_panel="Setup",
)

# -- Workflow --
app.command(name="pull", rich_help_panel="Workflow")(pull_command)
app.command(name="diff", rich_help_panel="Workflow")(diff_command)
app.command(name="push", rich_help_panel="Workflow")(push_command)
app.command(name="validate", rich_help_panel="Workflow")(validate_command)

# -- Utilities --
app.command(name="whoami", rich_help_panel="Utilities")(whoami)
app.add_typer(
    blueprint_app, name="blueprint", help="Inspect blueprints.",
    rich_help_panel="Utilities",
)
app.command(name="seed", rich_help_panel="Utilities")(seed_command)


def main() -> None:
    """Entry point for the portctl CLI."""
    app()
