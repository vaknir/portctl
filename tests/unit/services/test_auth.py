"""Tests for auth service -- credential storage, resolution, and verification."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from portctl.exceptions import AuthError
from portctl.models.config import OrgConfig, PortctlConfig
from portctl.services.auth import (
    delete_credentials,
    get_credentials,
    resolve_credentials,
    store_credentials,
    verify_token,
)

KEYRING_MODULE = "portctl.services.auth.keyring"


class TestStoreCredentials:
    """Tests for store_credentials function."""

    @patch(KEYRING_MODULE)
    def test_store_credentials(self, mock_keyring: MagicMock) -> None:
        """Stores client_id and client_secret in OS keyring."""
        store_credentials("my-org", "cid-123", "csecret-456")

        mock_keyring.set_password.assert_any_call(
            "portctl:my-org:client_id", "portctl", "cid-123"
        )
        mock_keyring.set_password.assert_any_call(
            "portctl:my-org:client_secret", "portctl", "csecret-456"
        )
        assert mock_keyring.set_password.call_count == 2


class TestGetCredentials:
    """Tests for get_credentials function."""

    @patch(KEYRING_MODULE)
    def test_get_credentials(self, mock_keyring: MagicMock) -> None:
        """Retrieves client_id and client_secret from keyring."""
        mock_keyring.get_password.side_effect = lambda service, _user: {
            "portctl:prod:client_id": "cid-abc",
            "portctl:prod:client_secret": "csecret-xyz",
        }.get(service)

        result = get_credentials("prod")

        assert result == ("cid-abc", "csecret-xyz")

    @patch(KEYRING_MODULE)
    def test_get_credentials_not_found(self, mock_keyring: MagicMock) -> None:
        """Returns None when credentials are not in keyring."""
        mock_keyring.get_password.return_value = None

        result = get_credentials("nonexistent")

        assert result is None


class TestDeleteCredentials:
    """Tests for delete_credentials function."""

    @patch(KEYRING_MODULE)
    def test_delete_credentials(self, mock_keyring: MagicMock) -> None:
        """Removes client_id and client_secret from keyring."""
        delete_credentials("my-org")

        mock_keyring.delete_password.assert_any_call(
            "portctl:my-org:client_id", "portctl"
        )
        mock_keyring.delete_password.assert_any_call(
            "portctl:my-org:client_secret", "portctl"
        )
        assert mock_keyring.delete_password.call_count == 2


class TestResolveCredentials:
    """Tests for resolve_credentials function."""

    def _make_config(
        self,
        *,
        client_id: str = "cfg-id",
        client_secret: str = "cfg-secret",
    ) -> PortctlConfig:
        """Create a PortctlConfig with a single org for testing."""
        return PortctlConfig(
            default_org="prod",
            orgs={
                "prod": OrgConfig(
                    name="Production",
                    client_id=client_id,
                    client_secret=client_secret,
                    role="production",
                ),
            },
        )

    @patch(KEYRING_MODULE)
    def test_resolve_credentials_env_vars(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Environment variables take highest priority."""
        monkeypatch.setenv("PORT_CLIENT_ID", "env-id")
        monkeypatch.setenv("PORT_CLIENT_SECRET", "env-secret")

        config = self._make_config()
        result = resolve_credentials("prod", config)

        assert result == ("env-id", "env-secret")
        mock_keyring.get_password.assert_not_called()

    @patch(KEYRING_MODULE)
    def test_resolve_credentials_keyring(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keyring credentials used when no env vars set."""
        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)

        mock_keyring.get_password.side_effect = lambda service, _user: {
            "portctl:prod:client_id": "kr-id",
            "portctl:prod:client_secret": "kr-secret",
        }.get(service)

        config = self._make_config()
        result = resolve_credentials("prod", config)

        assert result == ("kr-id", "kr-secret")

    @patch(KEYRING_MODULE)
    def test_resolve_credentials_config(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config file credentials used as last resort."""
        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.return_value = None

        config = self._make_config(client_id="cfg-id", client_secret="cfg-secret")
        result = resolve_credentials("prod", config)

        assert result == ("cfg-id", "cfg-secret")

    @patch(KEYRING_MODULE)
    def test_resolve_credentials_none(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Raises AuthError when no credentials found anywhere."""
        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.return_value = None

        config = PortctlConfig(
            default_org=None,
            orgs={},
        )

        with pytest.raises(AuthError, match="No credentials found"):
            resolve_credentials("prod", config)


class TestVerifyToken:
    """Tests for verify_token function."""

    async def test_verify_token_success(self) -> None:
        """Returns user info when credentials are valid."""

        def handler(request: httpx.Request) -> httpx.Response:
            if "/auth/access_token" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "accessToken": "jwt-token",
                        "expiresIn": 3600,
                        "tokenType": "Bearer",
                    },
                )
            if "/me" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "user": {"id": "user-1", "email": "test@example.com"},
                    },
                )
            return httpx.Response(404, json={"ok": False})

        transport = httpx.MockTransport(handler)
        api_url = "https://api.getport.io/v1"
        result = await verify_token("cid", "csecret", api_url, transport=transport)

        assert result["id"] == "user-1"
        assert result["email"] == "test@example.com"

    async def test_verify_token_failure(self) -> None:
        """Raises AuthError when credentials are invalid."""

        def handler(request: httpx.Request) -> httpx.Response:
            if "/auth/access_token" in str(request.url):
                return httpx.Response(
                    401,
                    json={"ok": False, "message": "Invalid credentials"},
                )
            return httpx.Response(404, json={"ok": False})

        transport = httpx.MockTransport(handler)

        api_url = "https://api.getport.io/v1"
        with pytest.raises(AuthError, match="[Ff]ailed|[Ii]nvalid|[Aa]uthenticat"):
            await verify_token("bad-id", "bad-secret", api_url, transport=transport)
