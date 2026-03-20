"""Tests for the seeder service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from portctl.exceptions import PortAPIError
from portctl.services.seeder import (
    BLUEPRINTS,
    ENVIRONMENTS,
    MICROSERVICES,
    TEAMS,
    _entity_detail,
    _generate_deployments,
    cleanup_demo_data,
    seed_demo_data,
)


def _mock_client() -> AsyncMock:
    """Create a mock PortClient with all required async methods."""
    client = AsyncMock()
    client.upsert_blueprint = AsyncMock(return_value={})
    client.upsert_scorecard = AsyncMock(return_value={})
    client.upsert_entity = AsyncMock(return_value={})
    client.delete_blueprint = AsyncMock(return_value=None)
    client.delete_scorecard = AsyncMock(return_value=None)
    client.delete_entity = AsyncMock(return_value=None)
    return client


class TestSeedDemoData:
    """Tests for seed_demo_data."""

    async def test_creates_all_blueprints(self) -> None:
        """All 4 blueprints are upserted in dependency order."""
        client = _mock_client()
        await seed_demo_data(client)

        assert client.upsert_blueprint.call_count == 4
        bp_ids = [c.args[0]["identifier"] for c in client.upsert_blueprint.call_args_list]
        assert bp_ids == ["environment", "team", "microservice", "deployment"]

    async def test_creates_scorecards(self) -> None:
        """Production readiness scorecard is created on microservice."""
        client = _mock_client()
        await seed_demo_data(client)

        assert client.upsert_scorecard.call_count == 1
        sc_call = client.upsert_scorecard.call_args_list[0]
        assert sc_call.args[0] == "microservice"
        assert sc_call.args[1]["identifier"] == "production-readiness"

    async def test_creates_entities_in_order(self) -> None:
        """Entities are created in dependency order: teams, envs, services, deploys."""
        client = _mock_client()
        await seed_demo_data(client)

        entity_calls = client.upsert_entity.call_args_list
        bp_ids = [c.args[0] for c in entity_calls]

        # First 3 should be teams
        assert bp_ids[:3] == ["team", "team", "team"]
        # Next 3 should be environments
        assert bp_ids[3:6] == ["environment", "environment", "environment"]
        # Next 8 should be microservices
        assert all(bp == "microservice" for bp in bp_ids[6:14])
        # Remaining should be deployments
        assert all(bp == "deployment" for bp in bp_ids[14:])

    async def test_returns_correct_counts(self) -> None:
        """SeedResult has accurate counts."""
        client = _mock_client()
        result = await seed_demo_data(client)

        assert result.blueprints_created == 4
        assert result.scorecards_created == 1
        assert result.entities_created == 25
        assert result.entity_breakdown["teams"] == 3
        assert result.entity_breakdown["environments"] == 3
        assert result.entity_breakdown["microservices"] == 8
        assert result.entity_breakdown["deployments"] == 11

    async def test_progress_callback_called(self) -> None:
        """Progress callback is invoked for each created resource."""
        client = _mock_client()
        progress_calls: list[tuple[str, str, str]] = []

        def on_progress(step: str, item: str, detail: str = "") -> None:
            progress_calls.append((step, item, detail))

        await seed_demo_data(client, on_progress=on_progress)

        # 4 blueprints + 1 scorecard + 25 entities = 30 progress calls
        assert len(progress_calls) == 30
        assert progress_calls[0] == ("blueprints", "environment", "")
        assert progress_calls[4] == ("scorecards", "production-readiness", "")

    async def test_idempotent_upsert(self) -> None:
        """Running seed twice calls upsert (not create), so it doesn't fail."""
        client = _mock_client()
        await seed_demo_data(client)
        await seed_demo_data(client)

        assert client.upsert_blueprint.call_count == 8  # 4 * 2


class TestCleanupDemoData:
    """Tests for cleanup_demo_data."""

    async def test_deletes_in_reverse_order(self) -> None:
        """Entities deleted before scorecards before blueprints."""
        client = _mock_client()
        call_order: list[str] = []

        async def track_entity(*args: Any) -> None:
            call_order.append(f"entity:{args[0]}")

        async def track_scorecard(*args: Any) -> None:
            call_order.append(f"scorecard:{args[0]}")

        async def track_blueprint(*args: Any) -> None:
            call_order.append(f"blueprint:{args[0]}")

        client.delete_entity = AsyncMock(side_effect=track_entity)
        client.delete_scorecard = AsyncMock(side_effect=track_scorecard)
        client.delete_blueprint = AsyncMock(side_effect=track_blueprint)

        await cleanup_demo_data(client)

        # Find indices of first occurrence of each type
        first_entity = next(i for i, c in enumerate(call_order) if c.startswith("entity:"))
        first_scorecard = next(i for i, c in enumerate(call_order) if c.startswith("scorecard:"))
        first_blueprint = next(i for i, c in enumerate(call_order) if c.startswith("blueprint:"))

        assert first_entity < first_scorecard < first_blueprint

    async def test_returns_total_deleted(self) -> None:
        """Total deleted count includes all resource types."""
        client = _mock_client()
        deleted = await cleanup_demo_data(client)

        # 25 entities + 1 scorecard + 4 blueprints = 30
        assert deleted == 30

    async def test_skips_404_on_entity(self) -> None:
        """Already-deleted entities (404) are silently skipped."""
        client = _mock_client()
        client.delete_entity = AsyncMock(
            side_effect=PortAPIError(status_code=404, detail="Not found")
        )

        deleted = await cleanup_demo_data(client)

        # Only scorecards (1) and blueprints (4) count as deleted
        assert deleted == 5

    async def test_skips_404_on_blueprint(self) -> None:
        """Already-deleted blueprints (404) are silently skipped."""
        client = _mock_client()
        client.delete_blueprint = AsyncMock(
            side_effect=PortAPIError(status_code=404, detail="Not found")
        )

        deleted = await cleanup_demo_data(client)

        # 25 entities + 1 scorecard, 0 blueprints
        assert deleted == 26

    async def test_reraises_non_404_errors(self) -> None:
        """Non-404 API errors are propagated."""
        client = _mock_client()
        client.delete_entity = AsyncMock(
            side_effect=PortAPIError(status_code=500, detail="Server error")
        )

        with pytest.raises(PortAPIError) as exc_info:
            await cleanup_demo_data(client)
        assert exc_info.value.status_code == 500

    async def test_blueprints_deleted_in_reverse(self) -> None:
        """Blueprints are deleted in reverse creation order."""
        client = _mock_client()
        await cleanup_demo_data(client)

        bp_calls = client.delete_blueprint.call_args_list
        bp_ids = [c.args[0] for c in bp_calls]
        assert bp_ids == ["deployment", "microservice", "team", "environment"]


class TestGenerateDeployments:
    """Tests for _generate_deployments."""

    def test_generates_11_deployments(self) -> None:
        """Generates exactly 11 deployment entities."""
        deployments = _generate_deployments()
        assert len(deployments) == 11

    def test_all_have_required_fields(self) -> None:
        """Each deployment has identifier, title, properties, and relations."""
        for dep in _generate_deployments():
            assert "identifier" in dep
            assert "title" in dep
            assert "version" in dep["properties"]
            assert "status" in dep["properties"]
            assert "deployed_at" in dep["properties"]
            assert "commit_sha" in dep["properties"]
            assert "service" in dep["relations"]
            assert "target" in dep["relations"]

    def test_all_running_status(self) -> None:
        """All generated deployments have 'running' status."""
        for dep in _generate_deployments():
            assert dep["properties"]["status"] == "running"


class TestEntityDetail:
    """Tests for _entity_detail helper."""

    def test_microservice_with_relations(self) -> None:
        """Microservice entity shows team and environments."""
        entity = {
            "relations": {
                "owned_by": "platform",
                "deployed_to": ["staging", "production"],
            }
        }
        assert _entity_detail(entity) == "-> platform, [staging, production]"

    def test_entity_without_relations(self) -> None:
        """Entity without owned_by/deployed_to returns empty string."""
        entity: dict[str, Any] = {"relations": {}}
        assert _entity_detail(entity) == ""

    def test_entity_no_relations_key(self) -> None:
        """Entity without relations key returns empty string."""
        entity: dict[str, Any] = {}
        assert _entity_detail(entity) == ""


class TestDataIntegrity:
    """Tests validating the demo data definitions are consistent."""

    def test_microservice_relations_reference_valid_teams(self) -> None:
        """All microservice owned_by relations reference defined teams."""
        team_ids = {t["identifier"] for t in TEAMS}
        for svc in MICROSERVICES:
            owned_by = svc["relations"].get("owned_by")
            if owned_by:
                msg = f"{svc['identifier']} references unknown team {owned_by}"
                assert owned_by in team_ids, msg

    def test_microservice_relations_reference_valid_environments(self) -> None:
        """All microservice deployed_to relations reference defined environments."""
        env_ids = {e["identifier"] for e in ENVIRONMENTS}
        for svc in MICROSERVICES:
            deployed_to = svc["relations"].get("deployed_to", [])
            for env in deployed_to:
                assert env in env_ids, f"{svc['identifier']} references unknown env {env}"

    def test_deployment_relations_reference_valid_services(self) -> None:
        """All deployment service relations reference defined microservices."""
        svc_ids = {s["identifier"] for s in MICROSERVICES}
        for dep in _generate_deployments():
            service = dep["relations"]["service"]
            assert service in svc_ids, f"{dep['identifier']} references unknown service {service}"

    def test_deployment_relations_reference_valid_environments(self) -> None:
        """All deployment target relations reference defined environments."""
        env_ids = {e["identifier"] for e in ENVIRONMENTS}
        for dep in _generate_deployments():
            target = dep["relations"]["target"]
            assert target in env_ids, f"{dep['identifier']} references unknown env {target}"

    def test_blueprint_identifiers_unique(self) -> None:
        """All blueprint identifiers are unique."""
        ids = [bp["identifier"] for bp in BLUEPRINTS]
        assert len(ids) == len(set(ids))

    def test_entity_identifiers_unique_per_blueprint(self) -> None:
        """Entity identifiers are unique within each blueprint type."""
        for entities in [TEAMS, ENVIRONMENTS, MICROSERVICES, _generate_deployments()]:
            ids = [e["identifier"] for e in entities]
            assert len(ids) == len(set(ids))
