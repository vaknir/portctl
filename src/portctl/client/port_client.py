"""httpx async client wrapper for Port API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from portctl.client.auth import TokenManager
from portctl.client.endpoints import (
    ACTION_BY_ID,
    ACTIONS,
    BLUEPRINT_BY_ID,
    BLUEPRINTS,
    ENTITIES,
    ENTITY_BY_ID,
    INTEGRATION_LOGS,
    INTEGRATIONS,
    ME,
    PAGE_BY_ID,
    PAGES,
    PORT_API_BASE_URL,
    SCORECARD_BY_ID,
    SCORECARDS,
)
from portctl.exceptions import PortAPIError

logger = logging.getLogger(__name__)

# Retry configuration
_MAX_RETRIES_429 = 3
_MAX_RETRIES_5XX = 1
_BACKOFF_BASE = 0.5  # seconds
_RETRYABLE_5XX = {500, 502, 503, 504}


class PortClient:
    """Async client for Port.io REST API.

    Handles authentication, retries, and response parsing. Use as an
    async context manager to ensure proper cleanup of HTTP connections.

    Example::

        async with PortClient(client_id, client_secret) as client:
            blueprints = await client.get_blueprints()
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        api_base: str = PORT_API_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token_manager = TokenManager(client_id, client_secret, api_base, transport=transport)
        client_kwargs: dict[str, Any] = {
            "base_url": api_base,
            "timeout": httpx.Timeout(30.0, read=60.0),
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._client = httpx.AsyncClient(**client_kwargs)

    async def __aenter__(self) -> PortClient:
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit async context manager, closing the HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated request with retry logic.

        Attaches Bearer token, retries on 429 with exponential backoff
        (up to 3 attempts), retries once on 5xx, and raises PortAPIError
        on non-2xx responses.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: URL path relative to the API base.
            **kwargs: Additional arguments passed to httpx request.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            PortAPIError: On non-2xx responses after retries are exhausted.
        """
        token = await self._token_manager.get_token()
        headers = kwargs.pop("headers", {})
        headers["authorization"] = f"Bearer {token}"

        retries_429 = 0
        retries_5xx = 0

        while True:
            response = await self._client.request(method, path, headers=headers, **kwargs)

            if response.status_code == 429 and retries_429 < _MAX_RETRIES_429:
                retries_429 += 1
                retry_after = float(
                    response.headers.get("retry-after", _BACKOFF_BASE * (2 ** (retries_429 - 1)))
                )
                logger.warning(
                    "Rate limited (429), retrying in %.1fs (attempt %d/%d)",
                    retry_after,
                    retries_429,
                    _MAX_RETRIES_429,
                )
                await asyncio.sleep(retry_after)
                continue

            if response.status_code in _RETRYABLE_5XX and retries_5xx < _MAX_RETRIES_5XX:
                retries_5xx += 1
                wait = _BACKOFF_BASE * (2 ** (retries_5xx - 1))
                logger.warning(
                    "Server error (%d), retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    wait,
                    retries_5xx,
                    _MAX_RETRIES_5XX,
                )
                await asyncio.sleep(wait)
                continue

            break

        if response.status_code >= 400:
            try:
                detail = response.json().get("message", response.text)
            except Exception:
                detail = response.text
            raise PortAPIError(
                status_code=response.status_code,
                detail=detail,
                resource=path,
            )

        return response.json()  # type: ignore[no-any-return]

    # ── Blueprint operations ────────────────────────────────────────

    async def get_blueprints(self) -> list[dict[str, Any]]:
        """Get all blueprints.

        Returns:
            List of blueprint dictionaries.
        """
        data = await self._request("GET", BLUEPRINTS)
        return data.get("blueprints", [])  # type: ignore[no-any-return]

    async def get_blueprint(self, identifier: str) -> dict[str, Any]:
        """Get a single blueprint by identifier.

        Args:
            identifier: Blueprint identifier.

        Returns:
            Blueprint dictionary.
        """
        path = BLUEPRINT_BY_ID.format(identifier=identifier)
        data = await self._request("GET", path)
        return data.get("blueprint", {})  # type: ignore[no-any-return]

    async def upsert_blueprint(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a blueprint.

        Tries POST (create) first, falls back to PUT (update) on 409 conflict.

        Args:
            data: Blueprint data including 'identifier'.

        Returns:
            The upserted blueprint dictionary.
        """
        identifier = data["identifier"]
        try:
            response = await self._request("POST", BLUEPRINTS, json=data)
            return response.get("blueprint", {})  # type: ignore[no-any-return]
        except PortAPIError as exc:
            if exc.status_code == 409:
                path = BLUEPRINT_BY_ID.format(identifier=identifier)
                response = await self._request("PUT", path, json=data)
                return response.get("blueprint", {})  # type: ignore[no-any-return]
            raise

    async def delete_blueprint(self, identifier: str) -> None:
        """Delete a blueprint by identifier.

        Args:
            identifier: Blueprint identifier to delete.
        """
        path = BLUEPRINT_BY_ID.format(identifier=identifier)
        await self._request("DELETE", path)

    # ── Scorecard operations ────────────────────────────────────────

    async def get_scorecards(self, blueprint_id: str) -> list[dict[str, Any]]:
        """Get all scorecards for a blueprint.

        Args:
            blueprint_id: Blueprint identifier.

        Returns:
            List of scorecard dictionaries.
        """
        path = SCORECARDS.format(blueprint_id=blueprint_id)
        data = await self._request("GET", path)
        return data.get("scorecards", [])  # type: ignore[no-any-return]

    async def upsert_scorecard(self, blueprint_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a scorecard.

        Tries POST (create) first, falls back to PUT (update) on 409 conflict.

        Args:
            blueprint_id: Blueprint identifier.
            data: Scorecard data including 'identifier'.

        Returns:
            The upserted scorecard dictionary.
        """
        identifier = data["identifier"]
        scorecards_path = SCORECARDS.format(blueprint_id=blueprint_id)
        try:
            response = await self._request("POST", scorecards_path, json=data)
            return response.get("scorecard", {})  # type: ignore[no-any-return]
        except PortAPIError as exc:
            if exc.status_code == 409:
                path = SCORECARD_BY_ID.format(blueprint_id=blueprint_id, identifier=identifier)
                response = await self._request("PUT", path, json=data)
                return response.get("scorecard", {})  # type: ignore[no-any-return]
            raise

    async def delete_scorecard(self, blueprint_id: str, identifier: str) -> None:
        """Delete a scorecard.

        Args:
            blueprint_id: Blueprint identifier.
            identifier: Scorecard identifier to delete.
        """
        path = SCORECARD_BY_ID.format(blueprint_id=blueprint_id, identifier=identifier)
        await self._request("DELETE", path)

    # ── Action operations ───────────────────────────────────────────

    async def get_actions(self) -> list[dict[str, Any]]:
        """Get all actions.

        Returns:
            List of action dictionaries.
        """
        data = await self._request("GET", ACTIONS)
        return data.get("actions", [])  # type: ignore[no-any-return]

    async def upsert_action(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update an action.

        Tries POST (create) first, falls back to PUT (update) on 409 conflict.

        Args:
            data: Action data including 'identifier'.

        Returns:
            The upserted action dictionary.
        """
        identifier = data["identifier"]
        try:
            response = await self._request("POST", ACTIONS, json=data)
            return response.get("action", {})  # type: ignore[no-any-return]
        except PortAPIError as exc:
            if exc.status_code == 409:
                path = ACTION_BY_ID.format(identifier=identifier)
                response = await self._request("PUT", path, json=data)
                return response.get("action", {})  # type: ignore[no-any-return]
            raise

    async def delete_action(self, identifier: str) -> None:
        """Delete an action.

        Args:
            identifier: Action identifier to delete.
        """
        path = ACTION_BY_ID.format(identifier=identifier)
        await self._request("DELETE", path)

    # ── Page operations ─────────────────────────────────────────────

    async def get_pages(self) -> list[dict[str, Any]]:
        """Get all pages.

        Returns:
            List of page dictionaries.
        """
        data = await self._request("GET", PAGES)
        return data.get("pages", [])  # type: ignore[no-any-return]

    async def upsert_page(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a page.

        Tries POST (create) first, falls back to PUT (update) on 409 conflict.

        Args:
            data: Page data including 'identifier'.

        Returns:
            The upserted page dictionary.
        """
        identifier = data["identifier"]
        try:
            response = await self._request("POST", PAGES, json=data)
            return response.get("page", {})  # type: ignore[no-any-return]
        except PortAPIError as exc:
            if exc.status_code == 409:
                path = PAGE_BY_ID.format(identifier=identifier)
                response = await self._request("PUT", path, json=data)
                return response.get("page", {})  # type: ignore[no-any-return]
            raise

    async def delete_page(self, identifier: str) -> None:
        """Delete a page by identifier.

        Args:
            identifier: Page identifier to delete.
        """
        path = PAGE_BY_ID.format(identifier=identifier)
        await self._request("DELETE", path)

    # ── Entity operations ───────────────────────────────────────────

    async def get_entities(self, blueprint_id: str) -> list[dict[str, Any]]:
        """Get all entities for a blueprint.

        Args:
            blueprint_id: Blueprint identifier.

        Returns:
            List of entity dictionaries.
        """
        path = ENTITIES.format(blueprint_id=blueprint_id)
        data = await self._request("GET", path)
        return data.get("entities", [])  # type: ignore[no-any-return]

    async def upsert_entity(self, blueprint_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update an entity.

        Uses POST with upsert=true to handle both create and update.

        Args:
            blueprint_id: Blueprint identifier the entity belongs to.
            data: Entity data including 'identifier'.

        Returns:
            The upserted entity dictionary.
        """
        path = ENTITIES.format(blueprint_id=blueprint_id)
        response = await self._request("POST", path, json=data, params={"upsert": "true"})
        return response.get("entity", {})  # type: ignore[no-any-return]

    async def delete_entity(self, blueprint_id: str, identifier: str) -> None:
        """Delete an entity.

        Args:
            blueprint_id: Blueprint identifier the entity belongs to.
            identifier: Entity identifier to delete.
        """
        path = ENTITY_BY_ID.format(blueprint_id=blueprint_id, identifier=identifier)
        await self._request("DELETE", path)

    # ── Integration operations ──────────────────────────────────────

    async def get_integrations(self) -> list[dict[str, Any]]:
        """Get all integrations.

        Returns:
            List of integration dictionaries.
        """
        data = await self._request("GET", INTEGRATIONS)
        return data.get("integrations", [])  # type: ignore[no-any-return]

    async def get_integration_logs(self, integration_id: str) -> list[dict[str, Any]]:
        """Get logs for an integration.

        Args:
            integration_id: Integration installation ID.

        Returns:
            List of log entry dictionaries.
        """
        path = INTEGRATION_LOGS.format(integration_id=integration_id)
        data = await self._request("GET", path)
        return data.get("logs", [])  # type: ignore[no-any-return]

    # ── Auth ────────────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """Get current user info.

        Returns:
            User info dictionary.
        """
        data = await self._request("GET", ME)
        return data.get("user", {})  # type: ignore[no-any-return]
