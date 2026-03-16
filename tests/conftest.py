"""Shared test fixtures for portctl."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def tmp_config_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for portctl config."""
    config_dir = tmp_path / ".portctl"
    config_dir.mkdir()
    return config_dir


@pytest.fixture()
def tmp_export_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for exported YAML files."""
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    return export_dir
