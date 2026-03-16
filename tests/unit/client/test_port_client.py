"""Tests for Port API client."""

from __future__ import annotations

from datetime import UTC
from typing import Any

import httpx
import pytest

from portctl.client.endpoints import (
    AUTH_TOKEN,
)
from portctl.client.port_client import PortClient
from portctl.exceptions import PortAPIError

# The base URL path prefix that httpx prepends when using base_url.
_V1 = "/v1"


def _strip_base(path: str) -> str:
    """Strip the /v1 base path prefix from a request URL path."""
    if path.startswith(_V1):
        return path[len(_V1) :]
    return path


def _auth_response(
    access_token: str = "test-token",
) -> httpx.Response:
    """Build a standard auth token response."""
    return httpx.Response(
        200,
        json={
            "ok": True,
            "accessToken": access_token,
            "expiresIn": 3600,
            "tokenType": "Bearer",
        },
    )


def _make_transport(
    responses: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    handler: Any = None,
) -> httpx.MockTransport:
    """Create a mock transport with predefined responses.

    Args:
        responses: Mapping of URL paths (without /v1 prefix) to JSON response bodies.
        status_code: Default status code for all responses.
        handler: Custom handler function (overrides responses).
    """
    if handler is not None:
        return httpx.MockTransport(handler)

    default_responses = responses or {}

    def _handler(request: httpx.Request) -> httpx.Response:
        path = _strip_base(request.url.path)
        if path == AUTH_TOKEN:
            return _auth_response()
        if path in default_responses:
            body = default_responses[path]
            return httpx.Response(status_code, json=body)
        return httpx.Response(404, json={"ok": False, "message": f"Not found: {path}"})

    return httpx.MockTransport(_handler)


def _make_client(
    responses: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    handler: Any = None,
) -> PortClient:
    """Create a PortClient with mock transport."""
    transport = _make_transport(responses, status_code=status_code, handler=handler)
    return PortClient(
        client_id="test-id",
        client_secret="test-secret",
        transport=transport,
    )


class TestPortClientBlueprints:
    """Blueprint operation tests."""

    async def test_get_blueprints(self) -> None:
        """get_blueprints returns a list of blueprints."""
        client = _make_client(
            {"/blueprints": {"ok": True, "blueprints": [{"identifier": "service"}]}}
        )
        async with client:
            result = await client.get_blueprints()
        assert result == [{"identifier": "service"}]

    async def test_get_blueprint(self) -> None:
        """get_blueprint returns a single blueprint."""
        client = _make_client(
            {
                "/blueprints/service": {
                    "ok": True,
                    "blueprint": {"identifier": "service", "title": "Service"},
                }
            }
        )
        async with client:
            result = await client.get_blueprint("service")
        assert result == {"identifier": "service", "title": "Service"}

    async def test_upsert_blueprint(self) -> None:
        """upsert_blueprint sends PUT and returns the blueprint."""
        request_log: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            request_log.append(request)
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            if path == "/blueprints/service" and request.method == "PUT":
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "blueprint": {"identifier": "service", "title": "Service"},
                    },
                )
            return httpx.Response(404, json={"ok": False})

        client = _make_client(handler=handler)
        async with client:
            result = await client.upsert_blueprint(
                {"identifier": "service", "title": "Service"}
            )
        assert result == {"identifier": "service", "title": "Service"}

    async def test_delete_blueprint(self) -> None:
        """delete_blueprint sends DELETE request."""
        request_log: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            request_log.append(request)
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            if path == "/blueprints/service" and request.method == "DELETE":
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404, json={"ok": False})

        client = _make_client(handler=handler)
        async with client:
            await client.delete_blueprint("service")

        delete_requests = [r for r in request_log if r.method == "DELETE"]
        assert len(delete_requests) == 1


class TestPortClientScorecards:
    """Scorecard operation tests."""

    async def test_get_scorecards(self) -> None:
        """get_scorecards returns list of scorecards for a blueprint."""
        client = _make_client(
            {
                "/blueprints/service/scorecards": {
                    "ok": True,
                    "scorecards": [{"identifier": "production-readiness"}],
                }
            }
        )
        async with client:
            result = await client.get_scorecards("service")
        assert result == [{"identifier": "production-readiness"}]

    async def test_upsert_scorecard(self) -> None:
        """upsert_scorecard sends PUT and returns the scorecard."""

        def handler(request: httpx.Request) -> httpx.Response:
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            if (
                path == "/blueprints/service/scorecards/prod-ready"
                and request.method == "PUT"
            ):
                return httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "scorecard": {"identifier": "prod-ready"},
                    },
                )
            return httpx.Response(404, json={"ok": False})

        client = _make_client(handler=handler)
        async with client:
            result = await client.upsert_scorecard(
                "service", {"identifier": "prod-ready"}
            )
        assert result == {"identifier": "prod-ready"}

    async def test_delete_scorecard(self) -> None:
        """delete_scorecard sends DELETE request."""

        def handler(request: httpx.Request) -> httpx.Response:
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            if (
                path == "/blueprints/service/scorecards/prod-ready"
                and request.method == "DELETE"
            ):
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404, json={"ok": False})

        client = _make_client(handler=handler)
        async with client:
            await client.delete_scorecard("service", "prod-ready")


class TestPortClientAuth:
    """Auth-related tests."""

    async def test_auth_token_attached(self) -> None:
        """Bearer token is attached to all authenticated requests."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response("my-jwt")
            captured_headers.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True, "blueprints": []})

        client = _make_client(handler=handler)
        async with client:
            await client.get_blueprints()

        assert captured_headers.get("authorization") == "Bearer my-jwt"

    async def test_token_refresh_on_expiry(self) -> None:
        """Client fetches a new token when the current one expires."""
        from datetime import datetime, timedelta

        from portctl.client.auth import TokenInfo

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
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
            return httpx.Response(200, json={"ok": True, "blueprints": []})

        client = _make_client(handler=handler)
        async with client:
            await client.get_blueprints()
            assert call_count == 1

            # Force token expiry
            client._token_manager._token = TokenInfo(
                access_token="token-1",
                expires_at=datetime.now(tz=UTC) - timedelta(minutes=1),
            )
            await client.get_blueprints()
            assert call_count == 2


class TestPortClientRetry:
    """Retry logic tests."""

    async def test_retry_on_429(self) -> None:
        """Client retries on 429 with exponential backoff."""
        attempt = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            attempt += 1
            if attempt < 3:
                return httpx.Response(
                    429,
                    json={"ok": False, "message": "Rate limited"},
                    headers={"retry-after": "0"},
                )
            return httpx.Response(200, json={"ok": True, "blueprints": []})

        client = _make_client(handler=handler)
        async with client:
            result = await client.get_blueprints()
        assert result == []
        assert attempt == 3

    async def test_retry_on_5xx(self) -> None:
        """Client retries once on 5xx errors."""
        attempt = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempt
            path = _strip_base(request.url.path)
            if path == AUTH_TOKEN:
                return _auth_response()
            attempt += 1
            if attempt == 1:
                return httpx.Response(
                    502, json={"ok": False, "message": "Bad gateway"}
                )
            return httpx.Response(200, json={"ok": True, "blueprints": []})

        client = _make_client(handler=handler)
        async with client:
            result = await client.get_blueprints()
        assert result == []
        assert attempt == 2

    async def test_raises_port_api_error_on_4xx(self) -> None:
        """Client raises PortAPIError on non-retryable 4xx."""
        client = _make_client(
            {"/blueprints": {"ok": False, "message": "Forbidden"}},
            status_code=403,
        )
        async with client:
            with pytest.raises(PortAPIError) as exc_info:
                await client.get_blueprints()
        assert exc_info.value.status_code == 403


class TestPortClientContextManager:
    """Context manager tests."""

    async def test_context_manager(self) -> None:
        """PortClient works as async context manager."""
        client = _make_client({"/me": {"ok": True, "user": {"name": "test"}}})
        async with client as c:
            assert c is client
            result = await c.get_me()
        assert result == {"name": "test"}


class TestPortClientOther:
    """Tests for other endpoint methods."""

    async def test_get_me(self) -> None:
        """get_me returns user info."""
        client = _make_client({"/me": {"ok": True, "user": {"name": "test-user"}}})
        async with client:
            result = await client.get_me()
        assert result == {"name": "test-user"}

    async def test_get_actions(self) -> None:
        """get_actions returns list of actions for a blueprint."""
        client = _make_client(
            {
                "/blueprints/service/actions": {
                    "ok": True,
                    "actions": [{"identifier": "deploy"}],
                }
            }
        )
        async with client:
            result = await client.get_actions("service")
        assert result == [{"identifier": "deploy"}]

    async def test_get_pages(self) -> None:
        """get_pages returns list of pages."""
        client = _make_client(
            {"/pages": {"ok": True, "pages": [{"identifier": "home"}]}}
        )
        async with client:
            result = await client.get_pages()
        assert result == [{"identifier": "home"}]

    async def test_get_entities(self) -> None:
        """get_entities returns list of entities for a blueprint."""
        client = _make_client(
            {
                "/blueprints/service/entities": {
                    "ok": True,
                    "entities": [{"identifier": "my-svc"}],
                }
            }
        )
        async with client:
            result = await client.get_entities("service")
        assert result == [{"identifier": "my-svc"}]

    async def test_get_integrations(self) -> None:
        """get_integrations returns list of integrations."""
        client = _make_client(
            {
                "/integrations": {
                    "ok": True,
                    "integrations": [{"installationId": "abc"}],
                }
            }
        )
        async with client:
            result = await client.get_integrations()
        assert result == [{"installationId": "abc"}]

    async def test_get_integration_logs(self) -> None:
        """get_integration_logs returns logs for an integration."""
        client = _make_client(
            {
                "/integrations/abc/logs": {
                    "ok": True,
                    "logs": [{"message": "synced"}],
                }
            }
        )
        async with client:
            result = await client.get_integration_logs("abc")
        assert result == [{"message": "synced"}]
