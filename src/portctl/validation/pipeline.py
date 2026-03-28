"""Orchestrates Layer 1 + Layer 2 validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from portctl.validation.layer1 import run_layer1

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient
    from portctl.validation.errors import ValidationResult


def validate(config_dir: Path) -> ValidationResult:
    """Run Layer 1 (local) validation on a config directory.

    Args:
        config_dir: Root directory containing blueprints/, scorecards/, etc.

    Returns:
        ValidationResult with all local issues found.
    """
    return run_layer1(config_dir)


async def validate_remote(config_dir: Path, client: PortClient) -> ValidationResult:
    """Run Layer 1 + Layer 2 validation.

    Runs local checks first. If Layer 1 finds errors, returns immediately
    without hitting the API -- no point validating remotely if local files
    are broken.

    Args:
        config_dir: Root directory containing blueprints/, scorecards/, etc.
        client: Authenticated Port API client for remote checks.

    Returns:
        Combined ValidationResult with all issues from both layers.
    """
    from portctl.validation.layer2 import run_layer2

    result = run_layer1(config_dir)

    if result.has_errors:
        return result

    l2_result = await run_layer2(config_dir, client)
    result.issues.extend(l2_result.issues)
    return result
