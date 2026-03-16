"""Credential storage, resolution, and verification."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx
import keyring

from portctl.client.endpoints import AUTH_TOKEN, ME
from portctl.exceptions import AuthError

if TYPE_CHECKING:
    from portctl.models.config import PortctlConfig

_KEYRING_USER = "portctl"


def _key_client_id(org_name: str) -> str:
    """Return the keyring service name for a client ID."""
    return f"portctl:{org_name}:client_id"


def _key_client_secret(org_name: str) -> str:
    """Return the keyring service name for a client secret."""
    return f"portctl:{org_name}:client_secret"


def store_credentials(org_name: str, client_id: str, client_secret: str) -> None:
    """Store client credentials in the OS keyring.

    Args:
        org_name: Organization alias.
        client_id: Port API client ID.
        client_secret: Port API client secret.
    """
    keyring.set_password(_key_client_id(org_name), _KEYRING_USER, client_id)
    keyring.set_password(_key_client_secret(org_name), _KEYRING_USER, client_secret)


def get_credentials(org_name: str) -> tuple[str, str] | None:
    """Retrieve client credentials from the OS keyring.

    Args:
        org_name: Organization alias.

    Returns:
        Tuple of (client_id, client_secret) or None if not found.
    """
    client_id = keyring.get_password(_key_client_id(org_name), _KEYRING_USER)
    client_secret = keyring.get_password(_key_client_secret(org_name), _KEYRING_USER)

    if client_id is None or client_secret is None:
        return None

    return (client_id, client_secret)


def delete_credentials(org_name: str) -> None:
    """Remove client credentials from the OS keyring.

    Args:
        org_name: Organization alias.
    """
    keyring.delete_password(_key_client_id(org_name), _KEYRING_USER)
    keyring.delete_password(_key_client_secret(org_name), _KEYRING_USER)


def resolve_credentials(org_name: str, config: PortctlConfig) -> tuple[str, str]:
    """Resolve credentials using priority: env vars > keyring > config file.

    Args:
        org_name: Organization alias.
        config: The loaded portctl configuration.

    Returns:
        Tuple of (client_id, client_secret).

    Raises:
        AuthError: If no credentials are found from any source.
    """
    # 1) Environment variables (highest priority, for CI/CD)
    env_id = os.environ.get("PORT_CLIENT_ID")
    env_secret = os.environ.get("PORT_CLIENT_SECRET")
    if env_id and env_secret:
        return (env_id, env_secret)

    # 2) OS keyring
    keyring_creds = get_credentials(org_name)
    if keyring_creds is not None:
        return keyring_creds

    # 3) Config file (last resort)
    if org_name in config.orgs:
        org = config.orgs[org_name]
        if org.client_id and org.client_secret:
            return (org.client_id, org.client_secret)

    raise AuthError(
        f"No credentials found for org '{org_name}'. "
        f"Run 'portctl auth login --org {org_name}' or set "
        f"PORT_CLIENT_ID and PORT_CLIENT_SECRET environment variables."
    )


async def verify_token(
    client_id: str,
    client_secret: str,
    api_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    """Verify credentials by obtaining a token and fetching user info.

    Args:
        client_id: Port API client ID.
        client_secret: Port API client secret.
        api_url: Port API base URL.
        transport: Optional mock transport for testing.

    Returns:
        User info dictionary from the /me endpoint.

    Raises:
        AuthError: If authentication fails.
    """
    client_kwargs: dict[str, object] = {
        "base_url": api_url,
        "timeout": httpx.Timeout(30.0),
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
        # Step 1: Get access token
        auth_response = await client.post(
            AUTH_TOKEN,
            json={"clientId": client_id, "clientSecret": client_secret},
        )

        if auth_response.status_code != 200:
            try:
                detail = auth_response.json().get("message", auth_response.text)
            except Exception:
                detail = auth_response.text
            raise AuthError(f"Authentication failed: {detail}")

        token = auth_response.json()["accessToken"]

        # Step 2: Verify by calling /me
        me_response = await client.get(
            ME,
            headers={"authorization": f"Bearer {token}"},
        )

        if me_response.status_code != 200:
            raise AuthError("Failed to verify token: could not fetch user info")

        return me_response.json().get("user", {})  # type: ignore[no-any-return]
