"""Config loader for ~/.portctl/config.yaml."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from portctl.constants import CONFIG_FILE, DEFAULT_API_URL
from portctl.exceptions import ConfigError
from portctl.models.config import OrgConfig, PortctlConfig

if TYPE_CHECKING:
    from pathlib import Path

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} patterns with environment variable values.

    Args:
        value: String potentially containing ${VAR_NAME} references.

    Returns:
        The string with all environment variable references resolved.

    Raises:
        ConfigError: If a referenced environment variable is not set.
    """

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        try:
            return os.environ[var_name]
        except KeyError:
            raise ConfigError(
                f"Environment variable '{var_name}' is not set "
                f"(referenced in config as ${{{var_name}}})"
            ) from None

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _resolve_env_vars_recursive(data: Any) -> Any:  # noqa: ANN401
    """Recursively resolve ${VAR} patterns in all string values within a data structure.

    Args:
        data: A nested dict/list/str structure from parsed YAML.

    Returns:
        The same structure with all string values having env vars resolved.
    """
    if isinstance(data, str):
        return resolve_env_vars(data)
    if isinstance(data, dict):
        return {key: _resolve_env_vars_recursive(val) for key, val in data.items()}
    if isinstance(data, list):
        return [_resolve_env_vars_recursive(item) for item in data]
    return data


def load_config(path: Path | None = None) -> PortctlConfig:
    """Load and validate the portctl configuration file.

    Args:
        path: Explicit path to the config file. Defaults to ~/.portctl/config.yaml.

    Returns:
        A validated PortctlConfig instance.

    Raises:
        ConfigError: If the file is missing, unparseable, or fails validation.
    """
    config_path = path if path is not None else CONFIG_FILE

    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. Run 'portctl org add' to create one."
        )

    raw_text = config_path.read_text(encoding="utf-8")

    try:
        raw_data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ConfigError(
            f"Invalid config format in {config_path}: expected a YAML mapping, "
            f"got {type(raw_data).__name__}"
        )

    resolved_data = _resolve_env_vars_recursive(raw_data)

    try:
        return PortctlConfig.model_validate(resolved_data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration in {config_path}: {exc}") from exc


def save_config(config: PortctlConfig, path: Path | None = None) -> None:
    """Save the portctl configuration to disk.

    Args:
        config: The config to persist.
        path: Explicit path. Defaults to ~/.portctl/config.yaml.
    """
    config_path = path if path is not None else CONFIG_FILE

    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json", exclude_defaults=True)
    config_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def ensure_org(
    org_name: str,
    *,
    client_id: str = "",
    client_secret: str = "",
    api_url: str = DEFAULT_API_URL,
    set_default: bool = False,
    path: Path | None = None,
) -> PortctlConfig:
    """Add an org to the config file, creating the file if needed.

    Args:
        org_name: Organization alias.
        client_id: Port API client ID (can be empty if stored in keyring).
        client_secret: Port API client secret (can be empty if stored in keyring).
        api_url: Port API base URL.
        set_default: Whether to set this org as the default.
        path: Explicit config path. Defaults to ~/.portctl/config.yaml.

    Returns:
        The updated config.
    """
    try:
        config = load_config(path)
    except ConfigError:
        config = PortctlConfig(orgs={})

    if org_name not in config.orgs:
        config.orgs[org_name] = OrgConfig(
            name=org_name,
            client_id=client_id,
            client_secret=client_secret,
            api_url=api_url,
        )

    if set_default or config.default_org is None:
        config.default_org = org_name

    save_config(config, path)
    return config


def list_orgs(config: PortctlConfig) -> list[dict[str, str]]:
    """Return a list of org info dicts for display.

    Args:
        config: The loaded portctl configuration.

    Returns:
        A list of dicts with keys: alias, name, role, api_url, default.
        ``default`` is ``"*"`` for the default org and ``""`` otherwise.
    """
    result = []
    for alias, org in config.orgs.items():
        result.append(
            {
                "alias": alias,
                "name": org.name,
                "role": org.role,
                "api_url": org.api_url,
                "default": "*" if alias == config.default_org else "",
            }
        )
    return result


def get_org(config: PortctlConfig, name: str | None = None) -> OrgConfig:
    """Retrieve an organization config by name or default.

    Args:
        config: The loaded portctl configuration.
        name: Organization alias to look up. Uses default_org if not provided.

    Returns:
        The OrgConfig for the requested organization.

    Raises:
        ConfigError: If the org is not found or no default is set.
    """
    if name is None:
        if config.default_org is None:
            raise ConfigError(
                "No default organization set. Specify --org or set 'default_org' in config."
            )
        name = config.default_org

    if name not in config.orgs:
        available = ", ".join(sorted(config.orgs.keys()))
        raise ConfigError(
            f"Organization '{name}' not found in config. Available: {available or '(none)'}"
        )

    return config.orgs[name]
