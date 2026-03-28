"""Port API contract tests for detecting breaking changes.

These tests exercise the full CRUD lifecycle of Port resources (blueprints,
scorecards, actions, entities) against the live API. They validate response
schemas, status codes, and upsert semantics to catch regressions early.

All test resources use a ``_portctl_test_`` prefix and are cleaned up in
fixture teardown so they don't pollute the target organisation.

Requires PORT_CLIENT_ID and PORT_CLIENT_SECRET environment variables.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC
from typing import TYPE_CHECKING, Any

import pytest

from portctl.exceptions import PortAPIError

if TYPE_CHECKING:
    from portctl.client.port_client import PortClient

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PREFIX = "_portctl_test_"


def _uid() -> str:
    """Return a short unique suffix for test resource identifiers."""
    return uuid.uuid4().hex[:8]


# Required fields every blueprint response must contain.
_BLUEPRINT_REQUIRED_KEYS = {
    "identifier",
    "title",
    "schema",
    "createdAt",
    "updatedAt",
}

# Required fields every scorecard response must contain.
_SCORECARD_REQUIRED_KEYS = {
    "identifier",
    "title",
    "rules",
}

# Required fields every action response must contain.
_ACTION_REQUIRED_KEYS = {
    "identifier",
    "title",
}

# Required fields every entity response must contain.
_ENTITY_REQUIRED_KEYS = {
    "identifier",
    "title",
    "blueprint",
}


def _assert_keys(data: dict[str, Any], required: set[str], label: str) -> None:
    """Assert that *data* contains all *required* keys."""
    missing = required - set(data.keys())
    assert not missing, f"{label} response missing keys: {missing}"


# ---------------------------------------------------------------------------
# Fixtures – ephemeral blueprint used by several test classes
# ---------------------------------------------------------------------------


@pytest.fixture()
async def test_blueprint(port_client: PortClient) -> dict[str, Any]:
    """Create a throwaway blueprint and delete it after the test."""
    identifier = f"{_PREFIX}bp_{_uid()}"
    bp_data: dict[str, Any] = {
        "identifier": identifier,
        "title": "portctl CI contract test",
        "icon": "Blueprint",
        "schema": {
            "properties": {
                "text_prop": {"type": "string", "title": "A text property"},
                "num_prop": {"type": "number", "title": "A number property"},
                "bool_prop": {"type": "boolean", "title": "A boolean property"},
            },
            "required": [],
        },
        "relations": {},
    }
    created = await port_client.upsert_blueprint(bp_data)
    yield created

    # Teardown – best-effort delete (ignore errors so other tests still run).
    with contextlib.suppress(PortAPIError):
        await port_client.delete_blueprint(identifier)


# ---------------------------------------------------------------------------
# Auth contract
# ---------------------------------------------------------------------------


class TestAuthContract:
    """Verify the auth token exchange contract hasn't changed."""

    async def test_token_is_jwt_format(
        self, port_credentials: tuple[str, str], api_base: str
    ) -> None:
        """The token must look like a JWT (three dot-separated base64 parts)."""
        from portctl.client.auth import TokenManager

        manager = TokenManager(*port_credentials, api_base)
        token = await manager.get_token()

        parts = token.split(".")
        assert len(parts) == 3, f"Expected JWT with 3 parts, got {len(parts)}"

    async def test_token_expiry_is_positive(
        self, port_credentials: tuple[str, str], api_base: str
    ) -> None:
        """TokenManager should report a future expiry after fetching."""
        from datetime import datetime

        from portctl.client.auth import TokenManager

        manager = TokenManager(*port_credentials, api_base)
        await manager.get_token()

        assert manager._token is not None
        assert manager._token.expires_at > datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Blueprint CRUD contract
# ---------------------------------------------------------------------------


class TestBlueprintCRUDContract:
    """Full create → read → update → delete lifecycle for blueprints."""

    async def test_create_blueprint(self, port_client: PortClient) -> None:
        """POST /blueprints should return a blueprint with required fields."""
        identifier = f"{_PREFIX}bp_create_{_uid()}"
        bp_data: dict[str, Any] = {
            "identifier": identifier,
            "title": "CI create test",
            "icon": "Blueprint",
            "schema": {"properties": {}, "required": []},
            "relations": {},
        }
        try:
            result = await port_client.upsert_blueprint(bp_data)
            _assert_keys(result, _BLUEPRINT_REQUIRED_KEYS, "Blueprint create")
            assert result["identifier"] == identifier
            assert result["title"] == "CI create test"
        finally:
            with contextlib.suppress(PortAPIError):
                await port_client.delete_blueprint(identifier)

    async def test_read_blueprint(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """GET /blueprints/{id} should return the same blueprint."""
        identifier = test_blueprint["identifier"]
        fetched = await port_client.get_blueprint(identifier)
        _assert_keys(fetched, _BLUEPRINT_REQUIRED_KEYS, "Blueprint read")
        assert fetched["identifier"] == identifier

    async def test_update_blueprint(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """PUT (via upsert) should update the title and preserve identifier."""
        identifier = test_blueprint["identifier"]
        updated_data: dict[str, Any] = {
            "identifier": identifier,
            "title": "Updated title",
            "icon": "Blueprint",
            "schema": test_blueprint.get("schema", {"properties": {}, "required": []}),
            "relations": {},
        }
        result = await port_client.upsert_blueprint(updated_data)
        _assert_keys(result, _BLUEPRINT_REQUIRED_KEYS, "Blueprint update")
        assert result["identifier"] == identifier
        assert result["title"] == "Updated title"

    async def test_delete_blueprint(self, port_client: PortClient) -> None:
        """DELETE /blueprints/{id} should succeed, then GET should 404."""
        identifier = f"{_PREFIX}bp_del_{_uid()}"
        bp_data: dict[str, Any] = {
            "identifier": identifier,
            "title": "CI delete test",
            "icon": "Blueprint",
            "schema": {"properties": {}, "required": []},
            "relations": {},
        }
        await port_client.upsert_blueprint(bp_data)
        await port_client.delete_blueprint(identifier)

        with pytest.raises(PortAPIError) as exc_info:
            await port_client.get_blueprint(identifier)
        assert exc_info.value.status_code == 404

    async def test_list_blueprints_schema(self, port_client: PortClient) -> None:
        """GET /blueprints should return a list of dicts with required keys."""
        blueprints = await port_client.get_blueprints()
        assert isinstance(blueprints, list)
        for bp in blueprints:
            assert isinstance(bp, dict)
            _assert_keys(bp, _BLUEPRINT_REQUIRED_KEYS, "Blueprint list item")

    async def test_blueprint_schema_property_types(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """Blueprint schema structure should be preserved through round-trip."""
        identifier = test_blueprint["identifier"]
        fetched = await port_client.get_blueprint(identifier)

        schema = fetched.get("schema", {})
        assert isinstance(schema, dict), "schema must be a dict"
        props = schema.get("properties", {})
        assert isinstance(props, dict), "schema.properties must be a dict"
        assert "text_prop" in props, "text_prop should survive round-trip"
        assert props["text_prop"]["type"] == "string"


# ---------------------------------------------------------------------------
# Scorecard CRUD contract
# ---------------------------------------------------------------------------


class TestScorecardCRUDContract:
    """Create → read → delete lifecycle for scorecards."""

    async def test_scorecard_crud(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """Full scorecard lifecycle against a test blueprint."""
        bp_id = test_blueprint["identifier"]
        sc_id = f"{_PREFIX}sc_{_uid()}"

        sc_data: dict[str, Any] = {
            "identifier": sc_id,
            "title": "CI scorecard test",
            "rules": [
                {
                    "identifier": f"{_PREFIX}rule_{_uid()}",
                    "title": "Test rule",
                    "level": "Bronze",
                    "query": {
                        "combinator": "and",
                        "conditions": [
                            {
                                "operator": "isNotEmpty",
                                "property": "text_prop",
                            }
                        ],
                    },
                }
            ],
        }

        # Create
        created = await port_client.upsert_scorecard(bp_id, sc_data)
        _assert_keys(created, _SCORECARD_REQUIRED_KEYS, "Scorecard create")
        assert created["identifier"] == sc_id

        # List
        scorecards = await port_client.get_scorecards(bp_id)
        assert isinstance(scorecards, list)
        ids = [s["identifier"] for s in scorecards]
        assert sc_id in ids, "Created scorecard should appear in list"

        # Delete
        await port_client.delete_scorecard(bp_id, sc_id)
        scorecards_after = await port_client.get_scorecards(bp_id)
        ids_after = [s["identifier"] for s in scorecards_after]
        assert sc_id not in ids_after, "Deleted scorecard should not appear in list"


# ---------------------------------------------------------------------------
# Action CRUD contract
# ---------------------------------------------------------------------------


class TestActionCRUDContract:
    """Create → read → delete lifecycle for actions."""

    async def test_action_crud(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """Full action lifecycle tied to a test blueprint."""
        action_id = f"{_PREFIX}act_{_uid()}"

        action_data: dict[str, Any] = {
            "identifier": action_id,
            "title": "CI action test",
            "trigger": {
                "type": "self-service",
                "operation": "CREATE",
                "userInputs": {
                    "properties": {},
                    "required": [],
                },
            },
        }

        # Create
        created = await port_client.upsert_action(action_data)
        _assert_keys(created, _ACTION_REQUIRED_KEYS, "Action create")
        assert created["identifier"] == action_id

        # List
        actions = await port_client.get_actions()
        assert isinstance(actions, list)
        ids = [a["identifier"] for a in actions]
        assert action_id in ids, "Created action should appear in list"

        # Delete
        await port_client.delete_action(action_id)
        actions_after = await port_client.get_actions()
        ids_after = [a["identifier"] for a in actions_after]
        assert action_id not in ids_after, "Deleted action should not appear in list"


# ---------------------------------------------------------------------------
# Entity CRUD contract
# ---------------------------------------------------------------------------


class TestEntityCRUDContract:
    """Create → read → delete lifecycle for entities."""

    async def test_entity_crud(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """Full entity lifecycle on the test blueprint."""
        bp_id = test_blueprint["identifier"]
        entity_id = f"{_PREFIX}ent_{_uid()}"

        entity_data: dict[str, Any] = {
            "identifier": entity_id,
            "title": "CI entity test",
            "properties": {
                "text_prop": "hello",
                "num_prop": 42,
                "bool_prop": True,
            },
        }

        # Create (upsert)
        created = await port_client.upsert_entity(bp_id, entity_data)
        _assert_keys(created, _ENTITY_REQUIRED_KEYS, "Entity create")
        assert created["identifier"] == entity_id
        assert created["blueprint"] == bp_id

        # List
        entities = await port_client.get_entities(bp_id)
        assert isinstance(entities, list)
        ids = [e["identifier"] for e in entities]
        assert entity_id in ids, "Created entity should appear in list"

        # Update (upsert again with changed property)
        entity_data["properties"]["text_prop"] = "updated"
        updated = await port_client.upsert_entity(bp_id, entity_data)
        assert updated["identifier"] == entity_id

        # Delete
        await port_client.delete_entity(bp_id, entity_id)
        entities_after = await port_client.get_entities(bp_id)
        ids_after = [e["identifier"] for e in entities_after]
        assert entity_id not in ids_after, "Deleted entity should not appear in list"


# ---------------------------------------------------------------------------
# Error response contract
# ---------------------------------------------------------------------------


class TestErrorResponseContract:
    """Verify error responses match the expected contract."""

    async def test_404_on_missing_blueprint(self, port_client: PortClient) -> None:
        """GET for a non-existent blueprint should raise 404 PortAPIError."""
        with pytest.raises(PortAPIError) as exc_info:
            await port_client.get_blueprint(f"{_PREFIX}nonexistent_{_uid()}")
        assert exc_info.value.status_code == 404
        assert isinstance(exc_info.value.detail, str)

    async def test_422_on_invalid_blueprint(self, port_client: PortClient) -> None:
        """POST with an invalid schema should raise a 4xx PortAPIError."""
        bad_data: dict[str, Any] = {
            "identifier": f"{_PREFIX}bad_{_uid()}",
            "title": "Bad blueprint",
            "schema": {"properties": "not-a-dict"},  # intentionally wrong type
        }
        with pytest.raises(PortAPIError) as exc_info:
            await port_client.upsert_blueprint(bad_data)
        # Port should reject with 400 or 422
        assert exc_info.value.status_code in {400, 422}

    async def test_upsert_idempotency(
        self, port_client: PortClient, test_blueprint: dict[str, Any]
    ) -> None:
        """Upserting the same blueprint twice should not error (409 handled)."""
        identifier = test_blueprint["identifier"]
        data: dict[str, Any] = {
            "identifier": identifier,
            "title": test_blueprint.get("title", "CI test"),
            "icon": "Blueprint",
            "schema": test_blueprint.get("schema", {"properties": {}, "required": []}),
            "relations": {},
        }
        # Second upsert should hit 409 → PUT path and succeed
        result = await port_client.upsert_blueprint(data)
        assert result["identifier"] == identifier


# ---------------------------------------------------------------------------
# Integration list contract
# ---------------------------------------------------------------------------


class TestIntegrationListContract:
    """Verify integration list endpoint contract."""

    async def test_get_integrations_returns_list(self, port_client: PortClient) -> None:
        """GET /integrations should return a list of dicts."""
        integrations = await port_client.get_integrations()
        assert isinstance(integrations, list)
        for item in integrations:
            assert isinstance(item, dict)
