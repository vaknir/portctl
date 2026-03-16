"""Tests for Port API token management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from portctl.client.auth import TokenInfo, TokenManager
from portctl.client.endpoints import AUTH_TOKEN, PORT_API_BASE_URL


def _make_auth_transport(
    *,
    access_token: str = "test-jwt-token",
    expires_in: int = 3600,
    status_code: int = 200,
) -> httpx.MockTransport:
    """Create a mock transport that responds to auth requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(AUTH_TOKEN):
            return httpx.Response(
                status_code,
                json={
                    "ok": True,
                    "accessToken": access_token,
                    "expiresIn": expires_in,
                    "tokenType": "Bearer",
                },
            )
        return httpx.Response(404, json={"ok": False, "message": "Not found"})

    return httpx.MockTransport(handler)


class TestTokenInfo:
    """Tests for TokenInfo dataclass."""

    def test_token_info_fields(self) -> None:
        """TokenInfo stores access_token and expires_at."""
        now = datetime.now(tz=UTC)
        info = TokenInfo(access_token="abc", expires_at=now)
        assert info.access_token == "abc"
        assert info.expires_at == now


class TestTokenManager:
    """Tests for TokenManager."""

    @pytest.fixture()
    def token_manager(self) -> TokenManager:
        """Create a TokenManager with mock transport."""
        transport = _make_auth_transport()
        return TokenManager(
            client_id="test-id",
            client_secret="test-secret",
            api_base=PORT_API_BASE_URL,
            transport=transport,
        )

    async def test_fetch_token(self, token_manager: TokenManager) -> None:
        """POST to /auth/access_token returns TokenInfo."""
        token_info = await token_manager._fetch_token()
        assert token_info.access_token == "test-jwt-token"
        assert token_info.expires_at > datetime.now(tz=UTC)

    async def test_is_expired_true(self) -> None:
        """is_expired returns True when token has expired."""
        transport = _make_auth_transport()
        manager = TokenManager(
            client_id="id",
            client_secret="secret",
            api_base=PORT_API_BASE_URL,
            transport=transport,
        )
        # Manually set an expired token
        manager._token = TokenInfo(
            access_token="old",
            expires_at=datetime.now(tz=UTC) - timedelta(minutes=5),
        )
        assert manager.is_expired is True

    async def test_is_expired_false(self) -> None:
        """is_expired returns False when token is still valid."""
        transport = _make_auth_transport()
        manager = TokenManager(
            client_id="id",
            client_secret="secret",
            api_base=PORT_API_BASE_URL,
            transport=transport,
        )
        manager._token = TokenInfo(
            access_token="valid",
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        assert manager.is_expired is False

    async def test_is_expired_true_when_no_token(self) -> None:
        """is_expired returns True when no token exists."""
        transport = _make_auth_transport()
        manager = TokenManager(
            client_id="id",
            client_secret="secret",
            api_base=PORT_API_BASE_URL,
            transport=transport,
        )
        assert manager.is_expired is True

    async def test_get_token_caches(self, token_manager: TokenManager) -> None:
        """get_token returns cached token when still valid."""
        token1 = await token_manager.get_token()
        token2 = await token_manager.get_token()
        assert token1 == token2
        assert token1 == "test-jwt-token"

    async def test_get_token_refreshes(self) -> None:
        """get_token fetches new token when expired."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "accessToken": f"token-{call_count}",
                    "expiresIn": 3600,
                    "tokenType": "Bearer",
                },
            )

        transport = httpx.MockTransport(handler)
        manager = TokenManager(
            client_id="id",
            client_secret="secret",
            api_base=PORT_API_BASE_URL,
            transport=transport,
        )

        # First call fetches
        token1 = await manager.get_token()
        assert token1 == "token-1"

        # Force expiry
        manager._token = TokenInfo(
            access_token="token-1",
            expires_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )

        # Second call should re-fetch
        token2 = await manager.get_token()
        assert token2 == "token-2"
        assert call_count == 2
