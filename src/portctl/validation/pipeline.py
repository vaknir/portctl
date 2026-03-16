"""Orchestrates Layer 1 + Layer 2 validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from portctl.validation.layer1 import run_layer1

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.validation.errors import ValidationResult


def validate(config_dir: Path, *, layer2: bool = False) -> ValidationResult:
    """Run the validation pipeline on a config directory.

    Args:
        config_dir: Root directory containing blueprints/, scorecards/, etc.
        layer2: Whether to run Layer 2 (remote API) checks. Not yet implemented.

    Returns:
        Combined ValidationResult with all issues found.
    """
    result = run_layer1(config_dir)

    # Layer 2 (remote checks) will be added in a future iteration
    if layer2:
        pass  # pragma: no cover

    return result
