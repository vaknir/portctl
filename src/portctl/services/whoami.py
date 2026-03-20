"""Identity and environment information gathering for whoami command."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import keyring

from portctl.constants import CONFIG_FILE, STATE_FILE, VERSION
from portctl.exceptions import ConfigError
from portctl.services.config import get_org, load_config

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.models.config import PortctlConfig


@dataclass
class WhoamiInfo:
    """Collected identity and environment information."""

    version: str
    org_name: str | None
    org_role: str | None
    api_url: str | None
    user_email: str | None
    user_name: str | None
    credential_source: str | None
    config_path: Path | None
    state_path: Path | None
    is_ci: bool
    ci_provider: str | None
    authenticated: bool


def detect_ci_environment() -> tuple[bool, str | None]:
    """Detect CI environment and identify the provider.

    Checks well-known CI environment variables in order of specificity.

    Returns:
        A tuple of (is_ci, provider_name). Provider is None when not in CI.
    """
    ci_providers: list[tuple[str, str]] = [
        ("GITHUB_ACTIONS", "github-actions"),
        ("GITLAB_CI", "gitlab-ci"),
        ("JENKINS_URL", "jenkins"),
        ("CIRCLECI", "circleci"),
        ("BUILDKITE", "buildkite"),
        ("TRAVIS", "travis"),
    ]

    for env_var, provider_name in ci_providers:
        if os.environ.get(env_var):
            return (True, provider_name)

    # Generic CI detection as fallback
    if os.environ.get("CI"):
        return (True, "ci")

    return (False, None)


def detect_credential_source(
    org_name: str,
    config: PortctlConfig | None,
) -> str | None:
    """Determine which credential source would be used for the given org.

    Checks sources in priority order: env vars, keyring, config file.

    Args:
        org_name: Organization alias to check credentials for.
        config: The loaded portctl configuration, or None if unavailable.

    Returns:
        One of 'env', 'keyring', 'config', or None if no credentials found.
    """

    # 1) Environment variables (highest priority)
    env_id = os.environ.get("PORT_CLIENT_ID")
    env_secret = os.environ.get("PORT_CLIENT_SECRET")
    if env_id and env_secret:
        return "env"

    # 2) OS keyring
    try:
        kr_id = keyring.get_password(f"portctl:{org_name}:client_id", "portctl")
        kr_secret = keyring.get_password(f"portctl:{org_name}:client_secret", "portctl")
        if kr_id and kr_secret:
            return "keyring"
    except Exception:  # noqa: BLE001
        pass

    # 3) Config file
    if config is not None and org_name in config.orgs:
        org = config.orgs[org_name]
        if org.client_id and org.client_secret:
            return "config"

    return None


async def gather_whoami_info(org: str | None = None) -> WhoamiInfo:
    """Collect identity info with graceful degradation.

    Each step is wrapped in try/except so partial information is always returned.

    Args:
        org: Organization alias. Uses default from config if not provided.

    Returns:
        A WhoamiInfo dataclass with all available identity information.
    """
    is_ci, ci_provider = detect_ci_environment()

    # Defaults for graceful degradation
    org_name: str | None = None
    org_role: str | None = None
    api_url: str | None = None
    credential_source: str | None = None
    config_path: Path | None = None
    state_path: Path | None = None
    authenticated = False
    config = None

    # Try to load config
    try:
        config = load_config()
        config_path = CONFIG_FILE if CONFIG_FILE.exists() else None
    except (ConfigError, Exception):  # noqa: BLE001
        config_path = None

    # Try to resolve org
    if config is not None:
        try:
            if org is not None:
                org_name = org
            elif config.default_org is not None:
                org_name = config.default_org

            if org_name is not None:
                org_config = get_org(config, name=org_name)
                org_role = org_config.role
                api_url = org_config.api_url
        except (ConfigError, Exception):  # noqa: BLE001
            pass

    # Check state file
    if STATE_FILE.exists():
        state_path = STATE_FILE

    # Detect credential source
    if org_name is not None:
        try:
            credential_source = detect_credential_source(org_name, config)
            authenticated = credential_source is not None
        except Exception:  # noqa: BLE001
            pass

    return WhoamiInfo(
        version=VERSION,
        org_name=org_name,
        org_role=org_role,
        api_url=api_url,
        user_email=None,
        user_name=None,
        credential_source=credential_source,
        config_path=config_path,
        state_path=state_path,
        is_ci=is_ci,
        ci_provider=ci_provider,
        authenticated=authenticated,
    )
