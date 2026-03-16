"""Typer app factory and top-level command group for portctl."""

from __future__ import annotations

from typing import Optional

import typer

from portctl.cli.commands.apply import app as apply_app
from portctl.cli.commands.auth import app as auth_app
from portctl.cli.commands.blueprint import app as blueprint_app
from portctl.cli.commands.export import app as export_app
from portctl.cli.commands.org import app as org_app
from portctl.cli.commands.plan import app as plan_app
from portctl.cli.commands.validate import app as validate_app
from portctl.constants import VERSION

app = typer.Typer(
    name="portctl",
    help="GitOps CLI for Port.io -- kubectl for your developer portal.",
    no_args_is_help=True,
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


app.add_typer(auth_app, name="auth", help="Authenticate with Port.io.")
app.add_typer(org_app, name="org", help="Manage organizations.")
app.add_typer(export_app, name="export", help="Export portal configuration to YAML.")
app.add_typer(plan_app, name="plan", help="Show a dry-run diff of local vs live config.")
app.add_typer(apply_app, name="apply", help="Apply local YAML config to Port.io.")
app.add_typer(validate_app, name="validate", help="Validate local YAML config.")
app.add_typer(blueprint_app, name="blueprint", help="Inspect blueprints.")


def main() -> None:
    """Entry point for the portctl CLI."""
    app()
