"""Shared Rich helpers for live progress, gates, timelines, and summary panels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console


class PullProgress:
    """Simple progress display for pull operations using status lines."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._status: dict[str, tuple[str, int, int]] = {}
        self._printed = False

    def add_task(self, name: str, total: int = 1) -> None:
        """Add a resource type to track."""
        self._status[name] = ("waiting", 0, total)

    def update(self, name: str, completed: int | None = None, total: int | None = None) -> None:
        """Update progress for a resource type."""
        status, cur_comp, cur_total = self._status.get(name, ("waiting", 0, 1))
        new_comp = completed if completed is not None else cur_comp
        new_total = total if total is not None else cur_total
        self._status[name] = (status, new_comp, new_total)
        self._print()

    def set_status(self, name: str, status: str) -> None:
        """Set the status text for a resource type."""
        _, cur_comp, cur_total = self._status.get(name, ("waiting", 0, 1))
        self._status[name] = (status, cur_comp, cur_total)
        self._print()

    def _print(self) -> None:
        """Print current status using direct stdout writes for ANSI escape support."""
        import sys

        lines = []
        for name, (status, completed, _total) in self._status.items():
            if status == "done":
                icon = "\033[32m✓\033[0m"
                line = f"  [{icon}] {name}: {completed} fetched"
            elif status in ("fetching", "writing"):
                icon = "\033[36m⠋\033[0m"
                line = f"  [{icon}] {name}: {status}... ({completed})"
            else:
                icon = "○"
                line = f"  [{icon}] {name}: waiting..."
            lines.append(line)

        # Move cursor up to overwrite previous output
        if self._printed:
            sys.stdout.write(f"\033[{len(lines)}A")

        for line in lines:
            sys.stdout.write(f"\033[2K{line}\n")
        sys.stdout.flush()
        self._printed = True

    def __enter__(self) -> PullProgress:
        """Enter context manager — print initial waiting state."""
        import sys

        # Print initial state without setting _printed, so the first
        # update will overwrite these lines cleanly.
        for name in self._status:
            sys.stdout.write(f"\033[2K  [○] {name}: waiting...\n")
        sys.stdout.flush()
        self._printed = True
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        # Print final state
        for name in list(self._status.keys()):
            comp, tot = self._status[name][1], self._status[name][2]
            self._status[name] = ("done", comp, tot)
        self._print()


def make_pull_progress(console: Console) -> PullProgress:
    """Create a progress display for pull operations."""
    return PullProgress(console)


class StepProgress:
    """Generic step-by-step progress for any multi-resource operation.

    Displays live-updating steps with spinner/check/waiting icons using
    direct ANSI escapes via sys.stdout.write (not Rich, which escapes ANSI codes).
    """

    def __init__(self, *, quiet: bool = False) -> None:
        """Initialize step progress.

        Args:
            quiet: If True, suppresses all output (for JSON mode).
        """
        self._quiet = quiet
        self._steps: dict[str, tuple[str, str]] = {}  # name -> (status, detail)
        self._printed = False

    def start(self, name: str) -> None:
        """Mark a step as in-progress.

        Args:
            name: The step name to display.
        """
        self._steps[name] = ("running", "")
        self._print()

    def complete(self, name: str, detail: str = "") -> None:
        """Mark a step as done with optional detail.

        Args:
            name: The step name to mark complete.
            detail: Optional detail text (e.g. "15 checked").
        """
        self._steps[name] = ("done", detail)
        self._print()

    def finish(self) -> None:
        """Print final newline after all steps done."""
        if not self._quiet:
            import sys

            sys.stdout.write("\n")
            sys.stdout.flush()

    def _print(self) -> None:
        """Render all steps, overwriting previous output."""
        if self._quiet:
            return

        import sys

        lines: list[str] = []
        for name, (status, detail) in self._steps.items():
            if status == "done":
                icon = "\033[32m\u2713\033[0m"
                suffix = f": {detail}" if detail else ""
                line = f"  [{icon}] {name}{suffix}"
            elif status == "running":
                icon = "\033[36m\u280b\033[0m"
                line = f"  [{icon}] {name}: checking..."
            else:
                icon = "\u25cb"
                line = f"  [{icon}] {name}: waiting..."
            lines.append(line)

        if self._printed:
            sys.stdout.write(f"\033[{len(lines)}A")

        for line in lines:
            sys.stdout.write(f"\033[2K{line}\n")
        sys.stdout.flush()
        self._printed = True

    def make_callback(self) -> Any:
        """Create an on_step callback for service layer functions.

        Returns:
            A callback function with signature ``(name: str, status: str) -> None``
            that drives this progress display, or None if quiet.
        """
        if self._quiet:
            return None

        def _on_step(name: str, status: str) -> None:
            if status == "start":
                self.start(name)
            elif status == "done":
                self.complete(name)

        return _on_step


class PushProgress:
    """Simple progress display for push operations."""

    def __init__(self, console: Console, total: int) -> None:
        self.console = console
        self.total = total
        self.completed = 0
        self._printed = False

    def advance(self, _task_id: Any = None) -> None:
        """Increment the completed count and refresh display."""
        self.completed += 1
        self._print()

    def _print(self) -> None:
        """Print current progress using direct stdout writes for ANSI escape support."""
        import sys

        pct = self.completed / self.total if self.total > 0 else 0
        filled = int(pct * 20)
        bar = "\033[32m█\033[0m" * filled + "░" * (20 - filled)

        line = f"  [{bar}] {self.completed}/{self.total} applied"

        if self._printed:
            sys.stdout.write("\033[1A")

        sys.stdout.write(f"\033[2K{line}\n")
        sys.stdout.flush()
        self._printed = True

    def __enter__(self) -> PushProgress:
        """Enter context manager."""
        self._print()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager."""
        pass


def make_push_progress(console: Console, total: int) -> PushProgress:
    """Create a progress display for push operations."""
    return PushProgress(console, total)


def format_validation_gate(
    issues: list[Any],
    *,
    remote: bool = False,
    layer1_ok: bool = True,
) -> Panel:
    """Build a layered validation gate panel."""
    text = Text()

    if remote and layer1_ok:
        l1_issues: list[Any] = []
        l2_issues = issues
    else:
        l1_issues = issues
        l2_issues = []

    if l1_issues:
        text.append("Layer 1  Local syntax\n", style="bold")
        for issue in l1_issues:
            icon = "[red]✗[/red]" if issue.severity == "error" else "[yellow]![/yellow]"
            location = issue.file_path
            if issue.line is not None:
                location = f"{location}:{issue.line}"
            text.append(f"  {icon} {location}  → {issue.message}\n")
            if issue.suggestion:
                text.append(f"    [dim]{issue.suggestion}[/dim]\n")
    else:
        text.append("Layer 1  Local syntax  [green]✓[/green]\n", style="bold")

    text.append("\n")

    if remote:
        if l2_issues:
            text.append("Layer 2  Remote schema\n", style="bold")
            for issue in l2_issues:
                icon = "[red]✗[/red]" if issue.severity == "error" else "[yellow]![/yellow]"
                location = issue.file_path
                if issue.line is not None:
                    location = f"{location}:{issue.line}"
                text.append(f"  {icon} {location}  → {issue.message}\n")
                if issue.suggestion:
                    text.append(f"    [dim]{issue.suggestion}[/dim]\n")
        else:
            text.append("Layer 2  Remote schema  [green]✓[/green]\n", style="bold")

    has_errors = any(i.severity == "error" for i in issues)
    if has_errors:
        text.append("\n[red bold]FAILED[/red bold] — fix errors before pushing.")
    else:
        if issues:
            text.append("\n[yellow bold]PASSED with warnings[/yellow bold]")
        else:
            text.append("\n[green bold]PASSED[/green bold]")

    return Panel(text, title="Validation", border_style="blue")


def format_history_timeline(events: list[dict[str, Any]]) -> Text:
    """Build a git-log-style timeline from history events."""
    text = Text()
    count = len(events)
    for idx, event in enumerate(events):
        is_last = idx == count - 1
        branch = "●" if is_last else "○"
        pipe = "│" if not is_last else " "

        event_type = event.get("event_type", "")
        color = "blue" if event_type == "export" else "green"
        commit_id = event.get("id", "")[:7]
        ts = event.get("timestamp", "")[:19].replace("T", " ")
        by = event.get("by", "")
        resources = event.get("resources", "")
        note = event.get("note", "")

        text.append(f"{branch} ", style=f"bold {color}")
        text.append(f"[{commit_id}]  ", style="dim")
        text.append(f"{ts}  ", style="dim")
        text.append(f"{event_type}", style=color)
        if by:
            text.append(f" by {by}", style="default")
        text.append("\n")

        text.append(f"{pipe}  ")
        if resources and resources != "-":
            res_list = resources.split(", ")
            if len(res_list) > 3:
                text.append(f"{', '.join(res_list[:3])} +{len(res_list) - 3} more", style="dim")
            else:
                text.append(resources, style="dim")
        if note:
            text.append(f"  — {note}", style="italic dim")
        text.append("\n")
        if not is_last:
            text.append(f"{pipe}\n")

    return text


def format_push_summary(
    created: int,
    updated: int,
    deleted: int,
    failed: int,
    git_commit: str | None,
) -> Panel:
    """Build a rich summary panel for push results."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="bold", no_wrap=True)
    table.add_column("Value")

    table.add_row("Created", f"[green]{created}[/green]")
    table.add_row("Updated", f"[yellow]{updated}[/yellow]")
    table.add_row("Deleted", f"[red]{deleted}[/red]")
    if failed:
        table.add_row("Failed", f"[bold red]{failed}[/bold red]")
    if git_commit:
        table.add_row("Git commit", f"[dim]{git_commit}[/dim]")

    border = "red" if failed else "green"
    return Panel(table, title="Push Summary", border_style=border)


def format_entity_table(entities: list[dict[str, Any]], wide: bool = False) -> Table:
    """Build a compact or wide table for entity search results."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Identifier")
    table.add_column("Blueprint")
    if wide:
        table.add_column("Title")
        table.add_column("Team")
        table.add_column("Updated")

    for ent in entities:
        identifier = ent.get("identifier", "")
        blueprint = ent.get("blueprint", "")
        title = ent.get("title", "")
        team = ""
        updated = ""
        if wide:
            props = ent.get("properties", {})
            team = props.get("team", "") if isinstance(props, dict) else ""
            updated = (ent.get("updatedAt", "") or "")[:10]
        row = [identifier, blueprint]
        if wide:
            row.extend([title, team, updated])
        table.add_row(*row)

    return table
