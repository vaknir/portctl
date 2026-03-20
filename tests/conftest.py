"""Shared test fixtures for portctl."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from dotenv import find_dotenv, load_dotenv

if TYPE_CHECKING:
    from pathlib import Path

# Load .env if present so PORT_CLIENT_ID / PORT_CLIENT_SECRET are available.
# Does nothing when the file is absent -- existing unit tests are unaffected.
load_dotenv(find_dotenv(usecwd=True))


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
