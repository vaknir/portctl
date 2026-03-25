"""Smoke tests verifying basic connectivity to the Port.io API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from portctl.client.auth import TokenManager
from portctl.client.endpoints import PORT_API_BASE_URL

if TYPE_CHECKING:
    from portctl.client.port_client import PortClient

pytestmark = pytest.mark.integration


class TestAuthTokenFetch:
    """Verify that we can obtain a JWT from the Port API."""

    async def test_auth_token_fetch(self, port_credentials: tuple[str, str]) -> None:
        """TokenManager should return a non-empty JWT string."""
        client_id, client_secret = port_credentials
        manager = TokenManager(client_id, client_secret, PORT_API_BASE_URL)

        token = await manager.get_token()

        assert isinstance(token, str)
        assert len(token) > 0

    async def test_token_is_reusable(self, port_credentials: tuple[str, str]) -> None:
        """Fetching the token twice should return the cached value."""
        client_id, client_secret = port_credentials
        manager = TokenManager(client_id, client_secret, PORT_API_BASE_URL)

        token_a = await manager.get_token()
        token_b = await manager.get_token()

        assert token_a == token_b


class TestGetBlueprints:
    """Verify that we can list blueprints."""

    async def test_get_blueprints_returns_list(self, port_client: PortClient) -> None:
        """GET /blueprints should return a list."""
        blueprints = await port_client.get_blueprints()

        assert isinstance(blueprints, list)

    async def test_blueprints_have_identifier(self, port_client: PortClient) -> None:
        """Each blueprint should contain an 'identifier' key."""
        blueprints = await port_client.get_blueprints()

        for bp in blueprints:
            assert "identifier" in bp, f"Blueprint missing 'identifier': {bp}"


class TestGetScorecards:
    """Verify that we can list scorecards for each blueprint."""

    async def test_get_scorecards_for_blueprints(self, port_client: PortClient) -> None:
        """GET scorecards for every blueprint should return lists without errors."""
        blueprints = await port_client.get_blueprints()

        for bp in blueprints:
            identifier = bp["identifier"]
            scorecards = await port_client.get_scorecards(identifier)
            assert isinstance(scorecards, list), (
                f"Expected list of scorecards for blueprint '{identifier}'"
            )


class TestGetCurrentUser:
    """Verify the /me endpoint behaviour with our token.

    Note: service-account tokens (client credentials) may not support /me,
    so we accept either a successful dict or a 404 PortAPIError.
    """

    async def test_get_current_user(self, port_client: PortClient) -> None:
        """GET /me should return a dict or raise 404 for service accounts."""
        from portctl.exceptions import PortAPIError

        try:
            user = await port_client.get_me()
            assert isinstance(user, dict)
        except PortAPIError as exc:
            # Service-account tokens don't have a /me route -- that's expected.
            if exc.status_code == 404:
                pytest.skip("/me endpoint not available for service-account tokens")
            raise
