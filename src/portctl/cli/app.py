"""Typer app factory and top-level command group for portctl."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from typer.core import TyperGroup

from portctl.cli.commands.apply import push_command
from portctl.cli.commands.audit import audit_command
from portctl.cli.commands.auth import app as auth_app
from portctl.cli.commands.blueprint import app as blueprint_app
from portctl.cli.commands.export import pull_command
from portctl.cli.commands.history import history_command
from portctl.cli.commands.init import init_command
from portctl.cli.commands.org import app as org_app
from portctl.cli.commands.plan import diff_command
from portctl.cli.commands.rollback import rollback_command
from portctl.cli.commands.seed import seed_command
from portctl.cli.commands.validate import validate_command
from portctl.cli.commands.whoami import whoami  # noqa: I001
from portctl.constants import VERSION


class _VerboseGroup(TyperGroup):
    """Custom Click Group that extracts -v/--verbose from anywhere in argv.

    This lets users write ``portctl pull -v`` or ``portctl -v pull`` —
    the flag is consumed before sub-command argument parsing begins.
    """

    def parse_args(self, ctx: typer.Context, args: list[str]) -> list[str]:  # type: ignore[override]
        """Strip -v/--verbose from *args* and activate debug logging."""
        cleaned: list[str] = []
        verbose = False
        for arg in args:
            if arg in ("-v", "--verbose"):
                verbose = True
            else:
                cleaned.append(arg)
        if verbose:
            # Only enable debug logging for portctl — suppress noisy httpx/httpcore
            portctl_logger = logging.getLogger("portctl")
            portctl_logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("\033[2m%(name)s\033[0m %(message)s")
            )
            portctl_logger.addHandler(handler)
            # Show httpx request summaries but not httpcore wire-level noise
            logging.getLogger("httpx").setLevel(logging.INFO)
            httpx_handler = logging.StreamHandler()
            httpx_handler.setFormatter(
                logging.Formatter("\033[2m%(message)s\033[0m")
            )
            logging.getLogger("httpx").addHandler(httpx_handler)
            logging.getLogger("httpcore").setLevel(logging.WARNING)
            ctx.params["verbose"] = True
        return super().parse_args(ctx, cleaned)


app = typer.Typer(
    name="portctl",
    help="GitOps CLI for Port.io -- kubectl for your developer portal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    cls=_VerboseGroup,
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
    verbose: bool = typer.Option(  # noqa: ARG001
        False,
        "--verbose",
        "-v",
        help="Enable verbose output (debug logging).",
    ),
) -> None:
    """portctl - GitOps CLI for Port.io."""


# -- Setup --
app.command(name="init", rich_help_panel="Setup")(init_command)
app.add_typer(
    auth_app,
    name="auth",
    help="Authenticate with Port.io.",
    rich_help_panel="Setup",
)
app.add_typer(
    org_app,
    name="org",
    help="Manage organizations.",
    rich_help_panel="Setup",
)

# -- Workflow --
app.command(name="pull", rich_help_panel="Workflow")(pull_command)
app.command(name="diff", rich_help_panel="Workflow")(diff_command)
app.command(name="push", rich_help_panel="Workflow")(push_command)
app.command(name="validate", rich_help_panel="Workflow")(validate_command)
app.command(name="audit", rich_help_panel="Workflow")(audit_command)
app.command(name="rollback", rich_help_panel="Workflow")(rollback_command)

# -- Utilities --
app.command(name="whoami", rich_help_panel="Utilities")(whoami)
app.add_typer(
    blueprint_app,
    name="blueprint",
    help="Inspect blueprints.",
    rich_help_panel="Utilities",
)
app.command(name="seed", rich_help_panel="Utilities")(seed_command)
app.command(name="history", rich_help_panel="Utilities")(history_command)


def main() -> None:
    """Entry point for the portctl CLI."""
    app()
