"""Validation error collection and formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ValidationIssue:
    """A single validation problem found in a config file."""

    file_path: str
    line: int | None
    message: str
    severity: Literal["error", "warning"]
    suggestion: str | None = None


@dataclass
class ValidationResult:
    """Collects all validation issues across files."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Return True if any issue is an error."""
        return any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        """Return the number of error-severity issues."""
        return sum(1 for i in self.issues if i.severity == "error")

    def add_error(
        self,
        file_path: str,
        message: str,
        line: int | None = None,
        suggestion: str | None = None,
    ) -> None:
        """Add an error-severity issue."""
        self.issues.append(
            ValidationIssue(
                file_path=file_path,
                line=line,
                message=message,
                severity="error",
                suggestion=suggestion,
            )
        )

    def add_warning(
        self,
        file_path: str,
        message: str,
        line: int | None = None,
    ) -> None:
        """Add a warning-severity issue."""
        self.issues.append(
            ValidationIssue(
                file_path=file_path,
                line=line,
                message=message,
                severity="warning",
            )
        )
