"""Constants and default values for portctl."""

from __future__ import annotations

from pathlib import Path

VERSION = "0.1.0"
APP_NAME = "portctl"
DEFAULT_API_URL = "https://api.getport.io/v1"
CONFIG_DIR = Path.home() / ".portctl"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
STATE_FILE = CONFIG_DIR / "state.yaml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials"
