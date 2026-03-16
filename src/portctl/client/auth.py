"""JWT token fetch and auto-refresh."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from portctl.client.endpoints import AUTH_TOKEN


@dataclass
class TokenInfo:
    """Holds an access token and its expiration time."""

    access_token: str
    expires_at: datetime


class TokenManager:
    """Manages Port API JWT token lifecycle.

    Handles fetching, caching, and refreshing JWT tokens using client
    credentials. Tokens are refreshed automatically when expired or
    within a safety margin of expiration.
    """

    # Refresh tokens 60 seconds before actual expiry to avoid races
    _EXPIRY_MARGIN = timedelta(seconds=60)

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        api_base: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_base = api_base
        self._token: TokenInfo | None = None
        self._transport = transport

    @property
    def is_expired(self) -> bool:
        """Check if the current token is expired or missing."""
        if self._token is None:
            return True
        return datetime.now(tz=UTC) >= (
            self._token.expires_at - self._EXPIRY_MARGIN
        )

    async def get_token(self) -> str:
        """Get a valid token, refreshing if expired.

        Returns:
            A valid JWT access token string.
        """
        if self.is_expired:
            self._token = await self._fetch_token()
        assert self._token is not None  # noqa: S101
        return self._token.access_token

    async def _fetch_token(self) -> TokenInfo:
        """POST /auth/access_token to get a new JWT.

        Returns:
            TokenInfo with the new access token and expiration.

        Raises:
            AuthError: If the token request fails.
        """
        from portctl.exceptions import AuthError

        client_kwargs: dict[str, object] = {
            "base_url": self._api_base,
            "timeout": httpx.Timeout(30.0),
        }
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
            response = await client.post(
                AUTH_TOKEN,
                json={
                    "clientId": self._client_id,
                    "clientSecret": self._client_secret,
                },
            )

        if response.status_code != 200:
            detail = response.text
            raise AuthError(f"Failed to obtain access token: {detail}")

        data = response.json()
        expires_in = data.get("expiresIn", 3600)
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_in)

        return TokenInfo(
            access_token=data["accessToken"],
            expires_at=expires_at,
        )
