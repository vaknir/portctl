"""Plan/diff output formatting with Rich panels and grouped changes."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console

    from portctl.services.differ import CrossOrgDiffResult
    from portctl.services.planner import PlanResult, ResourceChange

# Mapping of action to border style and symbol
_ACTION_STYLES: dict[str, tuple[str, str]] = {
    "create": ("green", "+"),
    "update": ("yellow", "~"),
    "delete": ("red", "-"),
}

# Regex to extract a clean dotted path from DeepDiff root paths
_ROOT_PATH_RE = re.compile(r"root(?:\['([^']+)'\])+")


def _clean_path(path: str) -> str:
    """Convert a DeepDiff path like ``root['a']['b']`` to ``a.b``.

    Args:
        path: DeepDiff-style path string.

    Returns:
        A human-readable dotted path.
    """
    return path.replace("root", "").replace("['", ".").replace("']", "").lstrip(".")


def _is_property_path(path: str) -> bool:
    """Check if a clean path refers to a property field.

    Args:
        path: A cleaned dotted path.

    Returns:
        True if the path starts with ``properties.``.
    """
    return path.startswith("properties.")


def _is_relation_path(path: str) -> bool:
    """Check if a clean path refers to a relation field.

    Args:
        path: A cleaned dotted path.

    Returns:
        True if the path starts with ``relations.``.
    """
    return path.startswith("relations.")


def _extract_property_name(path: str) -> str:
    """Extract the property name from a path like ``properties.code_coverage``.

    Args:
        path: A cleaned dotted path starting with ``properties.``.

    Returns:
        The property name portion.
    """
    parts = path.split(".", 2)
    return parts[1] if len(parts) >= 2 else path


def _extract_type_info(diff: dict[str, Any], path: str) -> str:
    """Try to extract type info for an added property from the diff.

    Looks into dictionary_item_added values for ``type`` and ``format`` fields.

    Args:
        diff: The full DeepDiff result dict.
        path: The original DeepDiff path (root[...] format).

    Returns:
        A string like ``number`` or ``string (email)``, or empty string.
    """
    added = diff.get("dictionary_item_added", {})
    if isinstance(added, dict):
        value = added.get(path, {})
    else:
        return ""
    if isinstance(value, dict):
        prop_type = value.get("type", "")
        fmt = value.get("format", "")
        if fmt:
            return f"{prop_type} ({fmt})"
        return str(prop_type)
    return ""


def _humanize_identifier(identifier: str) -> str:
    """Split a camelCase or PascalCase identifier into readable words.

    Args:
        identifier: An identifier like ``ProductionReadinessGithubOcean``.

    Returns:
        A human-readable string like ``Production Readiness Github Ocean``.
    """
    # Insert space before uppercase letters that follow lowercase/digits
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier)
    # Insert space between consecutive uppercase followed by lowercase
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return spaced


def _format_value(value: Any) -> Any:
    """Format a value for diff display, using JSON for complex types.

    Args:
        value: The value to format.

    Returns:
        JSON string for dicts/lists, raw value otherwise.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


def _build_dict_sub_diff(
    parent_path: str,
    old: dict[str, Any],
    new: dict[str, Any],
) -> list[tuple[str, str]]:
    """Compute field-level sub-diff between two dicts.

    Instead of showing ``{full_old} → {full_new}``, shows only the fields
    that actually changed with ``+``, ``-``, and ``~`` prefixes.

    Args:
        parent_path: The cleaned path prefix (e.g. ``rules[2]``).
        old: The old dict value.
        new: The new dict value.

    Returns:
        List of (line, style) tuples for rendering.
    """
    lines: list[tuple[str, str]] = []

    # Extract a label from the dict (e.g. rule identifier)
    label = new.get("identifier") or old.get("identifier") or ""
    header = f"  {parent_path}" + (f" ({label}):" if label else ":")
    lines.append((header, "bold"))

    all_keys = sorted(set(old.keys()) | set(new.keys()))
    has_field_changes = False

    for key in all_keys:
        in_old = key in old
        in_new = key in new
        if in_old and in_new:
            if old[key] != new[key]:
                old_repr = _format_value(old[key])
                new_repr = _format_value(new[key])
                lines.append(
                    (
                        f"    ~ {key}: {old_repr} → {new_repr}",
                        "yellow",
                    )
                )
                has_field_changes = True
        elif in_old and not in_new:
            lines.append((f"    - {key}", "red"))
            has_field_changes = True
        elif in_new and not in_old:
            new_repr = _format_value(new[key])
            lines.append((f"    + {key}: {new_repr}", "green"))
            has_field_changes = True

    if not has_field_changes:
        # All fields are identical — no real change (ordering only)
        return []

    return lines


def _build_change_lines(diff: dict[str, Any]) -> Text:
    """Build formatted Rich Text lines from a DeepDiff result dict.

    Groups changes into:
    - Top-level field changes
    - Properties section
    - Relations section

    Args:
        diff: A DeepDiff result dict.

    Returns:
        Rich Text with formatted change details.
    """
    top_lines: list[tuple[str, str]] = []  # (text, style)
    prop_lines: list[tuple[str, str]] = []
    rel_lines: list[tuple[str, str]] = []

    # values_changed: field: old -> new
    for path, change in diff.get("values_changed", {}).items():
        clean = _clean_path(path)
        old = change.get("old_value", "?")
        new = change.get("new_value", "?")

        # When both old and new are dicts, show field-level sub-diff instead of blob
        if isinstance(old, dict) and isinstance(new, dict):
            sub_lines = _build_dict_sub_diff(clean, old, new)
            top_lines.extend(sub_lines)
            continue

        line = f"  {clean}: {old} \u2192 {new}"
        if _is_property_path(clean):
            prop_lines.append((line, "yellow"))
        elif _is_relation_path(clean):
            rel_lines.append((line, "yellow"))
        else:
            top_lines.append((line, "yellow"))

    # type_changes: field: type_a -> type_b
    for path, change in diff.get("type_changes", {}).items():
        clean = _clean_path(path)
        old_type = change.get("old_type", "?")
        new_type = change.get("new_type", "?")
        if isinstance(old_type, type):
            old_type = old_type.__name__
        if isinstance(new_type, type):
            new_type = new_type.__name__
        line = f"  {clean}: {old_type} \u2192 {new_type}"
        if _is_property_path(clean):
            prop_lines.append((line, "yellow"))
        elif _is_relation_path(clean):
            rel_lines.append((line, "yellow"))
        else:
            top_lines.append((line, "yellow"))

    # dictionary_item_added: local has it, remote doesn't → will add
    added = diff.get("dictionary_item_added", {})
    added_paths = added if isinstance(added, dict) else {p: None for p in added}
    for path in added_paths:
        clean = _clean_path(str(path))
        type_info = _extract_type_info(diff, path)
        suffix = f"  ({type_info})" if type_info else ""
        line = f"  + add {clean}{suffix}"
        if _is_property_path(clean):
            prop_lines.append((line, "green"))
        elif _is_relation_path(clean):
            rel_lines.append((line, "green"))
        else:
            top_lines.append((line, "green"))

    # dictionary_item_removed: remote has it, local doesn't → will remove
    removed = diff.get("dictionary_item_removed", {})
    removed_paths = removed if isinstance(removed, dict) else list(removed)
    for path in removed_paths:
        clean = _clean_path(str(path))
        line = f"  - remove {clean} (exists on remote only)"
        if _is_property_path(clean):
            prop_lines.append((line, "red"))
        elif _is_relation_path(clean):
            rel_lines.append((line, "red"))
        else:
            top_lines.append((line, "red"))

    # iterable_item_added: new item in local → will add
    for path, value in diff.get("iterable_item_added", {}).items():
        clean = _clean_path(str(path))
        label = value.get("identifier", "") if isinstance(value, dict) else ""
        display = label or clean
        top_lines.append((f"  + add rule '{display}'", "green"))

    # iterable_item_removed: item only on remote → will remove
    for path, value in diff.get("iterable_item_removed", {}).items():
        clean = _clean_path(str(path))
        label = value.get("identifier", "") if isinstance(value, dict) else ""
        display = label or clean
        top_lines.append((f"  - remove rule '{display}' (remote only)", "red"))

    text = Text()
    for line, style in top_lines:
        text.append(line + "\n", style=style)

    if prop_lines:
        text.append("\n  Properties:\n", style="bold")
        for line, style in prop_lines:
            text.append(f"  {line}\n", style=style)

    if rel_lines:
        text.append("\n  Relations:\n", style="bold")
        for line, style in rel_lines:
            text.append(f"  {line}\n", style=style)

    return text


def _render_change_panel(change: ResourceChange) -> Panel:
    """Render a single ResourceChange as a Rich Panel.

    Args:
        change: The resource change to render.

    Returns:
        A Rich Panel with the appropriate border colour and content.
    """
    style, symbol = _ACTION_STYLES.get(change.action, ("white", "?"))
    resource_label = change.resource_type.capitalize()
    display_name = _humanize_identifier(change.identifier)
    title = f"{symbol} {display_name} ({change.action})"

    if change.action == "create":
        body = Text(f"  New {resource_label.lower()}\n", style="green")
    elif change.action == "delete":
        body = Text()
        body.append("  ", style="default")
        body.append("WARNING", style="bold red")
        body.append(" BREAKING", style="red")
        body.append(f" -- will delete {resource_label.lower()} ", style="red")
        body.append(f"'{change.identifier}'", style="bold red")
        body.append(" from remote\n", style="red")
    elif change.action == "update" and change.diff:
        body = _build_change_lines(change.diff)
    else:
        body = Text(f"  {change.action}\n", style="dim")

    return Panel(
        body,
        title=title,
        title_align="left",
        border_style=style,
        padding=(0, 1),
    )


def format_plan(plan: PlanResult, console: Console) -> None:
    """Print plan output using Rich panels grouped by resource type.

    Each change is rendered as a coloured panel (green=create, yellow=update,
    red=delete). Unchanged resource counts and a summary line are shown at
    the bottom.

    Args:
        plan: The PlanResult to format.
        console: Rich Console instance for output.
    """
    if plan.validation_result is not None and plan.validation_result.has_errors:
        console.print("[red]Validation errors found -- plan aborted.[/red]")
        for issue in plan.validation_result.issues:
            if issue.severity == "error":
                location = issue.file_path
                if issue.line is not None:
                    location = f"{location}:{issue.line}"
                console.print(f"  [red]{location}: {issue.message}[/red]")
                if issue.suggestion:
                    console.print(f"    [yellow]{issue.suggestion}[/yellow]")
        return

    if not plan.has_changes:
        console.print("[green]No changes detected.[/green]")
        return

    # Group changes by resource type
    grouped: dict[str, list[ResourceChange]] = {}
    for change in plan.changes:
        grouped.setdefault(change.resource_type, []).append(change)

    # Render grouped panels
    for resource_type in ("blueprint", "scorecard", "action", "page"):
        changes = grouped.get(resource_type, [])
        if not changes:
            continue
        console.print()
        console.print(f"[bold]{resource_type.capitalize()}s[/bold]")

        # Separate deletes from other changes
        deletes = [c for c in changes if c.action == "delete"]
        others = [c for c in changes if c.action != "delete"]

        for change in others:
            console.print(_render_change_panel(change))

        # Compact deletes into a single panel when there are multiple
        if len(deletes) > 1:
            body = Text()
            body.append("  ", style="default")
            body.append("WARNING", style="bold red")
            body.append(
                f" BREAKING -- will delete {len(deletes)} {resource_type}(s) from remote:\n",
                style="red",
            )
            for d in deletes:
                body.append(f"    - {d.identifier}\n", style="red")
            console.print(
                Panel(
                    body,
                    title=f"- {len(deletes)} deletions",
                    title_align="left",
                    border_style="red",
                    padding=(0, 1),
                )
            )
        elif len(deletes) == 1:
            console.print(_render_change_panel(deletes[0]))

    # Per-resource-type counts
    console.print()
    for rtype, total in [
        ("blueprint", plan.total_local_blueprints),
        ("scorecard", plan.total_local_scorecards),
        ("action", plan.total_local_actions),
        ("page", plan.total_local_pages),
    ]:
        type_changes = [c for c in plan.changes if c.resource_type == rtype]
        unchanged = max(0, total - len(type_changes))
        create_n = sum(1 for c in type_changes if c.action == "create")
        update_n = sum(1 for c in type_changes if c.action == "update")
        delete_n = sum(1 for c in type_changes if c.action == "delete")

        parts: list[str] = []
        if create_n:
            parts.append(f"[green]{create_n} to create[/green]")
        if update_n:
            parts.append(f"[yellow]{update_n} to update[/yellow]")
        if delete_n:
            parts.append(f"[red]{delete_n} to delete[/red]")
        if unchanged > 0:
            parts.append(f"[dim]{unchanged} unchanged[/dim]")
        if parts:
            label = f"{rtype.capitalize()}s"
            console.print(f"  {label}: {', '.join(parts)}")

    # Summary line
    create_count = len(plan.creates)
    update_count = len(plan.updates)
    delete_count = len(plan.deletes)
    breaking = plan.breaking_count

    summary = Text()
    summary.append("\nSummary: ", style="bold")
    summary.append(f"{update_count} update(s)", style="yellow")
    summary.append(", ", style="default")
    summary.append(f"{create_count} create(s)", style="green")
    summary.append(", ", style="default")
    summary.append(f"{delete_count} delete(s)", style="red")
    summary.append(" | ", style="dim")
    breaking_style = "bold red" if breaking > 0 else "dim"
    summary.append(f"{breaking} breaking", style=breaking_style)
    console.print(summary)


def format_plan_json(plan: PlanResult, console: Console) -> None:
    """Print plan output as JSON for machine consumption.

    Args:
        plan: The PlanResult to format.
        console: Rich Console instance for output.
    """
    output: dict[str, Any] = {
        "has_changes": plan.has_changes,
        "change_count": plan.change_count,
        "breaking_count": plan.breaking_count,
        "total_local_blueprints": plan.total_local_blueprints,
        "total_local_scorecards": plan.total_local_scorecards,
        "changes": [
            {
                "resource_type": c.resource_type,
                "identifier": c.identifier,
                "action": c.action,
                "diff": c.diff,
                "breaking": c.breaking,
            }
            for c in plan.changes
        ],
    }

    if plan.validation_result is not None and plan.validation_result.has_errors:
        output["validation_errors"] = [
            {
                "file_path": issue.file_path,
                "line": issue.line,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in plan.validation_result.issues
        ]

    console.print_json(json.dumps(output))


def format_cross_org_diff(
    result: CrossOrgDiffResult,
    source_org: str,
    target_org: str,
    console: Console,
) -> None:
    """Print cross-org diff output using Rich panels grouped by resource type.

    Changes are described from the source org's perspective:
    - ``create`` -- resource exists only in source.
    - ``delete`` -- resource exists only in target.
    - ``update`` -- resource differs between orgs.

    Args:
        result: The CrossOrgDiffResult to format.
        source_org: Source organization alias for display.
        target_org: Target organization alias for display.
        console: Rich Console instance for output.
    """
    if not result.has_changes:
        console.print(f"[green]No differences between {source_org} and {target_org}.[/green]")
        return

    console.print(
        f"\n[bold]Cross-org diff:[/bold] [blue]{source_org}[/blue]"
        f" [dim]vs[/dim] [blue]{target_org}[/blue]\n"
    )

    # Group changes by resource type
    grouped: dict[str, list[ResourceChange]] = {}
    for change in result.changes:
        grouped.setdefault(change.resource_type, []).append(change)

    for resource_type in ("blueprint", "scorecard", "action", "page"):
        changes = grouped.get(resource_type, [])
        if not changes:
            continue
        console.print(f"[bold]{resource_type.capitalize()}s[/bold]")

        deletes = [c for c in changes if c.action == "delete"]
        others = [c for c in changes if c.action != "delete"]

        for change in others:
            console.print(_render_change_panel(change))

        if len(deletes) > 1:
            body = Text()
            body.append("  ", style="default")
            body.append("NOTE", style="bold yellow")
            body.append(
                f" -- {len(deletes)} {resource_type}(s) exist only in {target_org}:\n",
                style="yellow",
            )
            for d in deletes:
                body.append(f"    - {d.identifier}\n", style="red")
            console.print(
                Panel(
                    body,
                    title=f"- {len(deletes)} target-only",
                    title_align="left",
                    border_style="red",
                    padding=(0, 1),
                )
            )
        elif len(deletes) == 1:
            console.print(_render_change_panel(deletes[0]))
        console.print()

    # Summary
    summary = Text()
    summary.append("Summary: ", style="bold")
    summary.append(f"{len(result.only_in_source)} source-only (create)", style="green")
    summary.append(", ", style="default")
    summary.append(f"{len(result.modified)} modified (update)", style="yellow")
    summary.append(", ", style="default")
    summary.append(f"{len(result.only_in_target)} target-only (delete)", style="red")
    console.print(summary)


def format_cross_org_diff_json(
    result: CrossOrgDiffResult,
    source_org: str,
    target_org: str,
    console: Console,
) -> None:
    """Print cross-org diff output as JSON for machine consumption.

    Args:
        result: The CrossOrgDiffResult to format.
        source_org: Source organization alias.
        target_org: Target organization alias.
        console: Rich Console instance for output.
    """
    output: dict[str, Any] = {
        "source_org": source_org,
        "target_org": target_org,
        "has_changes": result.has_changes,
        "change_count": result.change_count,
        "breaking_count": result.breaking_count,
        "changes": [
            {
                "resource_type": c.resource_type,
                "identifier": c.identifier,
                "action": c.action,
                "diff": c.diff,
                "breaking": c.breaking,
                "parent_identifier": c.parent_identifier,
            }
            for c in result.changes
        ],
    }

    console.print_json(json.dumps(output))
