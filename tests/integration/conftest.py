"""Shared fixtures for integration tests against the live Port.io API."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from dotenv import find_dotenv, load_dotenv

from portctl.client.endpoints import PORT_API_BASE_URL
from portctl.client.port_client import PortClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# Ensure .env is loaded even when running integration tests in isolation.
load_dotenv(find_dotenv(usecwd=True))


def _get_credentials() -> tuple[str, str] | None:
    """Read Port credentials from environment variables.

    Returns:
        Tuple of (client_id, client_secret), or None if either is missing.
    """
    client_id = os.environ.get("PORT_CLIENT_ID")
    client_secret = os.environ.get("PORT_CLIENT_SECRET")
    if client_id and client_secret:
        return (client_id, client_secret)
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def port_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env vars, or skip the test."""
    creds = _get_credentials()
    if creds is None:
        pytest.skip("PORT_CLIENT_ID and PORT_CLIENT_SECRET must be set to run integration tests")
    return creds


@pytest.fixture()
def api_base() -> str:
    """Return the Port API base URL."""
    return PORT_API_BASE_URL


@pytest.fixture()
async def port_client(
    port_credentials: tuple[str, str],
) -> AsyncGenerator[PortClient, None]:
    """Yield an authenticated PortClient connected to the live API."""
    client_id, client_secret = port_credentials
    async with PortClient(client_id, client_secret) as client:
        yield client
