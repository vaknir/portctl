"""Tests for the seeder service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from portctl.exceptions import PortAPIError
from portctl.services.seeder import (
    BLUEPRINTS,
    ENVIRONMENTS,
    GITHUB_ORGANIZATIONS,
    GITHUB_TEAMS,
    GITHUB_USERS,
    GROUPS,
    JIRA_PROJECTS,
    JIRA_USERS,
    MICROSERVICES,
    SCORECARDS,
    SERVICES,
    TEAMS,
    WORKLOADS,
    _entity_detail,
    _generate_deployments,
    _generate_github_pull_requests,
    _generate_github_repositories,
    _generate_jira_issues,
    cleanup_demo_data,
    seed_demo_data,
)

# Total entity count across all blueprint types
_TOTAL_ENTITIES = (
    len(GROUPS) + len(TEAMS) + len(ENVIRONMENTS) + len(GITHUB_ORGANIZATIONS)
    + len(GITHUB_USERS) + len(JIRA_PROJECTS) + len(JIRA_USERS)
    + len(GITHUB_TEAMS) + len(_generate_github_repositories())
    + len(MICROSERVICES) + len(SERVICES) + len(_generate_github_pull_requests())
    + len(_generate_jira_issues()) + len(_generate_deployments()) + len(WORKLOADS)
)

# Total resources: blueprints + scorecards + entities
_TOTAL_RESOURCES = len(BLUEPRINTS) + len(SCORECARDS) + _TOTAL_ENTITIES


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
        """All scorecards are created on microservice."""
        client = _mock_client()
        await seed_demo_data(client)

        assert client.upsert_scorecard.call_count == 3
        identifiers = [c.args[1]["identifier"] for c in client.upsert_scorecard.call_args_list]
        assert "production-readiness" in identifiers
        assert "security" in identifiers
        assert "code-quality" in identifiers
        for call in client.upsert_scorecard.call_args_list:
            assert call.args[0] == "microservice"

    async def test_creates_entities_in_dependency_order(self) -> None:
        """Entities are created in dependency order."""
        client = _mock_client()
        await seed_demo_data(client)

        entity_calls = client.upsert_entity.call_args_list
        bp_ids = [c.args[0] for c in entity_calls]

        # Build ordered list of blueprint IDs as they appear
        seen_order: list[str] = []
        for bp_id in bp_ids:
            if not seen_order or seen_order[-1] != bp_id:
                seen_order.append(bp_id)

        expected_order = [
            "group", "team", "environment",
            "githubOrganization", "githubUser",
            "jiraProject", "jiraUser",
            "githubTeam", "githubRepository",
            "microservice", "service",
            "githubPullRequest", "jiraIssue",
            "deployment", "workload",
        ]
        assert seen_order == expected_order

    async def test_returns_correct_counts(self) -> None:
        """SeedResult has accurate counts."""
        client = _mock_client()
        result = await seed_demo_data(client)

        assert result.blueprints_created == 4
        assert result.scorecards_created == 3
        assert result.entities_created == _TOTAL_ENTITIES
        assert result.entity_breakdown["teams"] == 3
        assert result.entity_breakdown["environments"] == 3
        assert result.entity_breakdown["microservices"] == 8
        assert result.entity_breakdown["deployments"] == 11
        assert result.entity_breakdown["groups"] == 2
        assert result.entity_breakdown["github_organizations"] == 1
        assert result.entity_breakdown["github_users"] == 5
        assert result.entity_breakdown["github_teams"] == 3
        assert result.entity_breakdown["github_repositories"] == 8
        assert result.entity_breakdown["github_pull_requests"] == 6
        assert result.entity_breakdown["jira_projects"] == 2
        assert result.entity_breakdown["jira_users"] == 4
        assert result.entity_breakdown["jira_issues"] == 8
        assert result.entity_breakdown["services"] == 8
        assert result.entity_breakdown["workloads"] == 6

    async def test_progress_callback_called(self) -> None:
        """Progress callback is invoked for each created resource."""
        client = _mock_client()
        progress_calls: list[tuple[str, str, str]] = []

        def on_progress(step: str, item: str, detail: str = "") -> None:
            progress_calls.append((step, item, detail))

        await seed_demo_data(client, on_progress=on_progress)

        # 4 blueprints + 3 scorecards + entities = total progress calls
        expected = len(BLUEPRINTS) + len(SCORECARDS) + _TOTAL_ENTITIES
        assert len(progress_calls) == expected
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

        # entities + 1 scorecard + 4 blueprints
        assert deleted == _TOTAL_RESOURCES

    async def test_skips_404_on_entity(self) -> None:
        """Already-deleted entities (404) are silently skipped."""
        client = _mock_client()
        client.delete_entity = AsyncMock(
            side_effect=PortAPIError(status_code=404, detail="Not found")
        )

        deleted = await cleanup_demo_data(client)

        # Only scorecards (3) and blueprints (4) count as deleted
        assert deleted == len(SCORECARDS) + len(BLUEPRINTS)

    async def test_skips_404_on_blueprint(self) -> None:
        """Already-deleted blueprints (404) are silently skipped."""
        client = _mock_client()
        client.delete_blueprint = AsyncMock(
            side_effect=PortAPIError(status_code=404, detail="Not found")
        )

        deleted = await cleanup_demo_data(client)

        # entities + scorecards, 0 blueprints
        assert deleted == _TOTAL_ENTITIES + len(SCORECARDS)

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


class TestGenerateGitHubEntities:
    """Tests for GitHub entity generators."""

    def test_generates_8_repositories(self) -> None:
        """Generates exactly 8 repository entities."""
        repos = _generate_github_repositories()
        assert len(repos) == 8

    def test_repos_have_required_fields(self) -> None:
        """Each repository has all expected properties and relations."""
        for repo in _generate_github_repositories():
            assert "identifier" in repo
            assert "title" in repo
            assert "readme" in repo["properties"]
            assert "url" in repo["properties"]
            assert "defaultBranch" in repo["properties"]
            assert "language" in repo["properties"]
            assert "githubTeams" in repo["relations"]
            assert "organization" in repo["relations"]

    def test_generates_6_pull_requests(self) -> None:
        """Generates exactly 6 PR entities."""
        prs = _generate_github_pull_requests()
        assert len(prs) == 6

    def test_prs_have_required_fields(self) -> None:
        """Each PR has expected properties and relations."""
        for pr in _generate_github_pull_requests():
            assert "identifier" in pr
            assert "status" in pr["properties"]
            assert pr["properties"]["status"] in ("merged", "open", "closed")
            assert "repository" in pr["relations"]
            assert "git_hub_creator" in pr["relations"]

    def test_merged_prs_have_merged_at(self) -> None:
        """Merged PRs include mergedAt and leadTimeHours."""
        for pr in _generate_github_pull_requests():
            if pr["properties"]["status"] == "merged":
                assert "mergedAt" in pr["properties"]
                assert "leadTimeHours" in pr["properties"]


class TestGenerateJiraIssues:
    """Tests for Jira issue generator."""

    def test_generates_8_issues(self) -> None:
        """Generates exactly 8 Jira issue entities."""
        issues = _generate_jira_issues()
        assert len(issues) == 8

    def test_issues_have_required_fields(self) -> None:
        """Each issue has expected properties and relations."""
        for issue in _generate_jira_issues():
            assert "identifier" in issue
            assert "url" in issue["properties"]
            assert "status" in issue["properties"]
            assert "issueType" in issue["properties"]
            assert "priority" in issue["properties"]
            assert "project" in issue["relations"]
            assert "jira_user_reporter" in issue["relations"]

    def test_issues_have_valid_statuses(self) -> None:
        """All issues have realistic Jira statuses."""
        valid = {"Done", "In Progress", "To Do", "In Review"}
        for issue in _generate_jira_issues():
            assert issue["properties"]["status"] in valid


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
        assert _entity_detail(entity) == "-> platform, \\[staging, production]"

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

    def test_github_teams_reference_valid_users(self) -> None:
        """All GitHub team member relations reference defined GitHub users."""
        user_ids = {u["identifier"] for u in GITHUB_USERS}
        for team in GITHUB_TEAMS:
            for member in team["relations"].get("members", []):
                assert member in user_ids, f"{team['identifier']} references unknown user {member}"

    def test_github_repos_reference_valid_teams(self) -> None:
        """All GitHub repo team relations reference defined GitHub teams."""
        team_ids = {t["identifier"] for t in GITHUB_TEAMS}
        for repo in _generate_github_repositories():
            for team in repo["relations"].get("githubTeams", []):
                assert team in team_ids, f"{repo['identifier']} references unknown team {team}"

    def test_github_repos_reference_valid_org(self) -> None:
        """All GitHub repos reference the defined organization."""
        org_ids = {o["identifier"] for o in GITHUB_ORGANIZATIONS}
        for repo in _generate_github_repositories():
            org = repo["relations"]["organization"]
            assert org in org_ids, f"{repo['identifier']} references unknown org {org}"

    def test_github_prs_reference_valid_repos(self) -> None:
        """All PRs reference defined repositories."""
        repo_ids = {r["identifier"] for r in _generate_github_repositories()}
        for pr in _generate_github_pull_requests():
            repo = pr["relations"]["repository"]
            assert repo in repo_ids, f"{pr['identifier']} references unknown repo {repo}"

    def test_github_prs_reference_valid_users(self) -> None:
        """All PRs reference defined GitHub users."""
        user_ids = {u["identifier"] for u in GITHUB_USERS}
        for pr in _generate_github_pull_requests():
            creator = pr["relations"]["git_hub_creator"]
            assert creator in user_ids, f"{pr['identifier']} references unknown user {creator}"

    def test_jira_issues_reference_valid_projects(self) -> None:
        """All Jira issues reference defined projects."""
        project_ids = {p["identifier"] for p in JIRA_PROJECTS}
        for issue in _generate_jira_issues():
            project = issue["relations"]["project"]
            assert project in project_ids, (
                f"{issue['identifier']} references unknown project {project}"
            )

    def test_jira_issues_reference_valid_users(self) -> None:
        """All Jira issues reference defined Jira users."""
        user_ids = {u["identifier"] for u in JIRA_USERS}
        for issue in _generate_jira_issues():
            reporter = issue["relations"]["jira_user_reporter"]
            assert reporter in user_ids, (
                f"{issue['identifier']} references unknown user {reporter}"
            )

    def test_services_reference_valid_repos(self) -> None:
        """All service entities reference defined GitHub repositories."""
        repo_ids = {r["identifier"] for r in _generate_github_repositories()}
        for svc in SERVICES:
            repo = svc["relations"]["repository"]
            assert repo in repo_ids, f"{svc['identifier']} references unknown repo {repo}"

    def test_workloads_reference_valid_services(self) -> None:
        """All workload entities reference defined services."""
        svc_ids = {s["identifier"] for s in SERVICES}
        env_ids = {e["identifier"] for e in ENVIRONMENTS}
        for wl in WORKLOADS:
            svc = wl["relations"]["service"]
            env = wl["relations"]["environment"]
            assert svc in svc_ids, f"{wl['identifier']} references unknown service {svc}"
            assert env in env_ids, f"{wl['identifier']} references unknown env {env}"

    def test_blueprint_identifiers_unique(self) -> None:
        """All blueprint identifiers are unique."""
        ids = [bp["identifier"] for bp in BLUEPRINTS]
        assert len(ids) == len(set(ids))

    def test_entity_identifiers_unique_per_blueprint(self) -> None:
        """Entity identifiers are unique within each blueprint type."""
        entity_lists = [
            TEAMS, ENVIRONMENTS, MICROSERVICES, _generate_deployments(),
            GITHUB_ORGANIZATIONS, GITHUB_USERS, GITHUB_TEAMS,
            _generate_github_repositories(), _generate_github_pull_requests(),
            JIRA_PROJECTS, JIRA_USERS, _generate_jira_issues(),
            SERVICES, WORKLOADS, GROUPS,
        ]
        for entities in entity_lists:
            ids = [e["identifier"] for e in entities]
            assert len(ids) == len(set(ids))
