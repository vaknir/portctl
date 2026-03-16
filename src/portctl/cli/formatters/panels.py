"""Status panels and entity detail views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console


def render_blueprint(blueprint_data: dict[str, Any], console: Console) -> None:
    """Render a blueprint in a rich structured view.

    Displays a summary panel with title, icon, and description followed by
    tables for properties and relations.

    Example output::

        ┌─ Blueprint: service ──────────────────┐
        │ Title: Microservice                    │
        │ Icon: Microservice                     │
        │ Description: A microservice component  │
        └────────────────────────────────────────┘

        Properties:
        ┌──────────┬────────┬──────┐
        │ Name     │ Type   │ Req  │
        ├──────────┼────────┼──────┤
        │ language │ string │ ✓    │
        │ coverage │ number │ —    │
        └──────────┴────────┴──────┘

        Relations:
        ┌──────────┬─────────────┬──────┐
        │ Name     │ Target      │ Many │
        ├──────────┼─────────────┼──────┤
        │ team     │ team        │ No   │
        │ services │ service     │ Yes  │
        └──────────┴─────────────┴──────┘

    Args:
        blueprint_data: Raw blueprint dictionary from the Port API.
        console: Rich Console instance to render into.
    """
    identifier = blueprint_data.get("identifier", "")
    title = blueprint_data.get("title", identifier)
    icon = blueprint_data.get("icon") or ""
    description = blueprint_data.get("description") or ""

    # --- Summary panel ---
    lines: list[str] = []
    lines.append(f"Title: {title}")
    if icon:
        lines.append(f"Icon: {icon}")
    if description:
        lines.append(f"Description: {description}")

    panel_body = "\n".join(lines)
    console.print(
        Panel(
            panel_body,
            title=f"Blueprint: {identifier}",
            title_align="left",
        )
    )

    # --- Properties table ---
    schema = blueprint_data.get("schema", {})
    properties: dict[str, Any] = schema.get("properties", {}) if schema else {}
    required_list: list[str] = schema.get("required", []) if schema else []

    if properties:
        console.print()
        console.print("[bold]Properties:[/bold]")
        prop_table = Table(show_header=True, header_style="bold")
        prop_table.add_column("Name")
        prop_table.add_column("Type")
        prop_table.add_column("Req")

        for prop_name, prop_def in properties.items():
            prop_type = prop_def.get("type", "") if isinstance(prop_def, dict) else ""
            is_required = prop_name in required_list
            req_marker = "\u2713" if is_required else "\u2014"
            prop_table.add_row(prop_name, prop_type, req_marker)

        console.print(prop_table)

    # --- Relations table ---
    relations: dict[str, Any] = blueprint_data.get("relations", {})

    if relations:
        console.print()
        console.print("[bold]Relations:[/bold]")
        rel_table = Table(show_header=True, header_style="bold")
        rel_table.add_column("Name")
        rel_table.add_column("Target")
        rel_table.add_column("Many")

        for rel_name, rel_def in relations.items():
            target = rel_def.get("target", "") if isinstance(rel_def, dict) else ""
            many = rel_def.get("many", False) if isinstance(rel_def, dict) else False
            many_label = "Yes" if many else "No"
            rel_table.add_row(rel_name, target, many_label)

        console.print(rel_table)


__all__ = ["render_blueprint"]
