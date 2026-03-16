"""Plan/diff output formatting."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rich.console import Console

    from portctl.services.planner import PlanResult


def _format_diff_detail(diff: dict[str, Any]) -> list[str]:
    """Extract human-readable change descriptions from a DeepDiff dict.

    Args:
        diff: A DeepDiff result dict.

    Returns:
        List of formatted change description strings.
    """
    lines: list[str] = []

    # values_changed: {"root['key']": {"new_value": ..., "old_value": ...}}
    for path, change in diff.get("values_changed", {}).items():
        clean_path = path.replace("root", "").replace("['", ".").replace("']", "")
        if clean_path.startswith("."):
            clean_path = clean_path[1:]
        old = change.get("old_value", "?")
        new = change.get("new_value", "?")
        lines.append(f"  {clean_path}: {old} -> {new}")

    # dictionary_item_added
    for path in diff.get("dictionary_item_added", []):
        clean_path = str(path).replace("root", "").replace("['", ".").replace("']", "")
        if clean_path.startswith("."):
            clean_path = clean_path[1:]
        lines.append(f"  + {clean_path}")

    # dictionary_item_removed
    for path in diff.get("dictionary_item_removed", []):
        clean_path = str(path).replace("root", "").replace("['", ".").replace("']", "")
        if clean_path.startswith("."):
            clean_path = clean_path[1:]
        lines.append(f"  - {clean_path}")

    # type_changes
    for path, change in diff.get("type_changes", {}).items():
        clean_path = path.replace("root", "").replace("['", ".").replace("']", "")
        if clean_path.startswith("."):
            clean_path = clean_path[1:]
        old_type = change.get("old_type", "?")
        new_type = change.get("new_type", "?")
        if isinstance(old_type, type):
            old_type = old_type.__name__
        if isinstance(new_type, type):
            new_type = new_type.__name__
        lines.append(f"  {clean_path}: {old_type} -> {new_type}")

    return lines


def format_plan(plan: PlanResult, console: Console) -> None:
    """Print plan output using rich.

    Formats changes as:
        + Blueprint: service (create)
        ~ Blueprint: deployment (update)
          properties.coverage_pct: number -> string
        - Scorecard: old_card (delete) WARNING BREAKING

        Plan: 3 changes, 1 breaking, 0 errors

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

    for change in plan.changes:
        resource_label = change.resource_type.capitalize()

        if change.action == "create":
            console.print(
                f"[green]+[/green] {resource_label}: {change.identifier} "
                f"[green](create)[/green]"
            )
        elif change.action == "update":
            console.print(
                f"[yellow]~[/yellow] {resource_label}: {change.identifier} "
                f"[yellow](update)[/yellow]"
            )
            if change.diff:
                for detail in _format_diff_detail(change.diff):
                    console.print(f"[dim]{detail}[/dim]")
        elif change.action == "delete":
            breaking_marker = " [red]WARNING BREAKING[/red]" if change.breaking else ""
            console.print(
                f"[red]-[/red] {resource_label}: {change.identifier} "
                f"[red](delete)[/red]{breaking_marker}"
            )

    console.print()
    error_count = 0
    if plan.validation_result is not None:
        error_count = plan.validation_result.error_count
    console.print(
        f"Plan: {plan.change_count} change(s) "
        f"[dim]|[/dim] {plan.breaking_count} breaking "
        f"[dim]|[/dim] {error_count} error(s)"
    )


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
