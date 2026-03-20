"""Seed demo data into Port.io for quick onboarding."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from portctl.exceptions import PortAPIError

if TYPE_CHECKING:
    from portctl.client.port_client import PortClient

logger = logging.getLogger(__name__)

# ── Progress callback type ───────────────────────────────────────────

ProgressCallback = Callable[[str, str, str], None]


def _noop_progress(step: str, item: str, detail: str = "") -> None:
    """Default no-op progress callback."""


# ── SeedResult ───────────────────────────────────────────────────────


@dataclass
class SeedResult:
    """Summary of seeded demo data."""

    blueprints_created: int = 0
    scorecards_created: int = 0
    entities_created: int = 0
    entity_breakdown: dict[str, int] = field(default_factory=dict)


# ── Blueprint definitions ────────────────────────────────────────────

BLUEPRINT_ENVIRONMENT: dict[str, Any] = {
    "identifier": "environment",
    "title": "Environment",
    "icon": "Environment",
    "schema": {
        "properties": {
            "type": {
                "type": "string",
                "title": "Type",
                "enum": ["development", "staging", "production"],
            },
            "cloud_provider": {
                "type": "string",
                "title": "Cloud Provider",
                "enum": ["AWS", "GCP", "Azure"],
            },
            "region": {"type": "string", "title": "Region"},
        },
        "required": ["type"],
    },
    "relations": {},
}

BLUEPRINT_TEAM: dict[str, Any] = {
    "identifier": "team",
    "title": "Team",
    "icon": "Team",
    "schema": {
        "properties": {
            "slack_channel": {"type": "string", "title": "Slack Channel"},
            "oncall_schedule": {
                "type": "string",
                "title": "On-call Schedule",
                "format": "url",
            },
            "member_count": {"type": "number", "title": "Member Count"},
        },
        "required": [],
    },
    "relations": {},
}

BLUEPRINT_MICROSERVICE: dict[str, Any] = {
    "identifier": "microservice",
    "title": "Microservice",
    "icon": "Microservice",
    "schema": {
        "properties": {
            "language": {"type": "string", "title": "Language"},
            "repository": {"type": "string", "title": "Repository", "format": "url"},
            "tier": {
                "type": "string",
                "title": "Tier",
                "enum": ["critical", "standard", "internal"],
            },
            "on_call": {"type": "string", "title": "On-call"},
            "description": {"type": "string", "title": "Description"},
        },
        "required": ["language"],
    },
    "relations": {
        "deployed_to": {
            "title": "Deployed To",
            "target": "environment",
            "many": True,
            "required": False,
        },
        "owned_by": {
            "title": "Owned By",
            "target": "team",
            "many": False,
            "required": False,
        },
    },
}

BLUEPRINT_DEPLOYMENT: dict[str, Any] = {
    "identifier": "deployment",
    "title": "Deployment",
    "icon": "Deployment",
    "schema": {
        "properties": {
            "version": {"type": "string", "title": "Version"},
            "status": {
                "type": "string",
                "title": "Status",
                "enum": ["running", "failed", "rolled_back"],
            },
            "deployed_at": {"type": "string", "title": "Deployed At"},
            "commit_sha": {"type": "string", "title": "Commit SHA"},
        },
        "required": ["version"],
    },
    "relations": {
        "service": {
            "title": "Service",
            "target": "microservice",
            "many": False,
            "required": False,
        },
        "target": {
            "title": "Target",
            "target": "environment",
            "many": False,
            "required": False,
        },
    },
}

# Order matters: targets before sources
BLUEPRINTS: list[dict[str, Any]] = [
    BLUEPRINT_ENVIRONMENT,
    BLUEPRINT_TEAM,
    BLUEPRINT_MICROSERVICE,
    BLUEPRINT_DEPLOYMENT,
]

BLUEPRINT_IDENTIFIERS: list[str] = [bp["identifier"] for bp in BLUEPRINTS]

# ── Scorecard definitions ────────────────────────────────────────────

SCORECARD_PRODUCTION_READINESS: dict[str, Any] = {
    "identifier": "production-readiness",
    "title": "Production Readiness",
    "rules": [
        {
            "identifier": "has-description",
            "title": "Has Description",
            "level": "Bronze",
            "query": {
                "combinator": "and",
                "conditions": [
                    {
                        "operator": "isNotEmpty",
                        "property": "description",
                    }
                ],
            },
        },
        {
            "identifier": "has-on-call",
            "title": "Has On-call",
            "level": "Silver",
            "query": {
                "combinator": "and",
                "conditions": [
                    {
                        "operator": "isNotEmpty",
                        "property": "on_call",
                    }
                ],
            },
        },
        {
            "identifier": "is-critical-or-standard",
            "title": "Is Critical or Standard",
            "level": "Gold",
            "query": {
                "combinator": "and",
                "conditions": [
                    {
                        "operator": "!=",
                        "property": "tier",
                        "value": "internal",
                    }
                ],
            },
        },
    ],
}

SCORECARDS: list[tuple[str, dict[str, Any]]] = [
    ("microservice", SCORECARD_PRODUCTION_READINESS),
]

# ── Entity definitions ───────────────────────────────────────────────

TEAMS: list[dict[str, Any]] = [
    {
        "identifier": "platform",
        "title": "Platform Engineering",
        "properties": {
            "slack_channel": "#platform",
            "oncall_schedule": "https://opsgenie.com/schedules/platform",
            "member_count": 8,
        },
        "relations": {},
    },
    {
        "identifier": "backend",
        "title": "Backend Services",
        "properties": {
            "slack_channel": "#backend",
            "oncall_schedule": "https://opsgenie.com/schedules/backend",
            "member_count": 12,
        },
        "relations": {},
    },
    {
        "identifier": "frontend",
        "title": "Frontend Team",
        "properties": {
            "slack_channel": "#frontend",
            "oncall_schedule": "https://opsgenie.com/schedules/frontend",
            "member_count": 6,
        },
        "relations": {},
    },
]

ENVIRONMENTS: list[dict[str, Any]] = [
    {
        "identifier": "development",
        "title": "Development",
        "properties": {
            "type": "development",
            "cloud_provider": "AWS",
            "region": "us-east-1",
        },
        "relations": {},
    },
    {
        "identifier": "staging",
        "title": "Staging",
        "properties": {
            "type": "staging",
            "cloud_provider": "AWS",
            "region": "us-east-1",
        },
        "relations": {},
    },
    {
        "identifier": "production",
        "title": "Production",
        "properties": {
            "type": "production",
            "cloud_provider": "AWS",
            "region": "us-west-2",
        },
        "relations": {},
    },
]

MICROSERVICES: list[dict[str, Any]] = [
    {
        "identifier": "api-gateway",
        "title": "API Gateway",
        "properties": {
            "language": "Go",
            "repository": "https://github.com/acme/api-gateway",
            "tier": "critical",
            "on_call": "@platform-team",
            "description": "Central API gateway handling routing and rate limiting.",
        },
        "relations": {
            "deployed_to": ["staging", "production"],
            "owned_by": "platform",
        },
    },
    {
        "identifier": "auth-service",
        "title": "Auth Service",
        "properties": {
            "language": "Python",
            "repository": "https://github.com/acme/auth-service",
            "tier": "critical",
            "on_call": "@backend-team",
            "description": "Authentication and authorization service.",
        },
        "relations": {
            "deployed_to": ["staging", "production"],
            "owned_by": "backend",
        },
    },
    {
        "identifier": "payment-service",
        "title": "Payment Service",
        "properties": {
            "language": "Java",
            "repository": "https://github.com/acme/payment-service",
            "tier": "critical",
            "on_call": "@backend-team",
            "description": "Handles payment processing and billing integration.",
        },
        "relations": {
            "deployed_to": ["production"],
            "owned_by": "backend",
        },
    },
    {
        "identifier": "notification-service",
        "title": "Notification Service",
        "properties": {
            "language": "Python",
            "repository": "https://github.com/acme/notification-service",
            "tier": "standard",
            "on_call": "@backend-team",
            "description": "Sends email, SMS, and push notifications.",
        },
        "relations": {
            "deployed_to": ["staging", "production"],
            "owned_by": "backend",
        },
    },
    {
        "identifier": "user-service",
        "title": "User Service",
        "properties": {
            "language": "TypeScript",
            "repository": "https://github.com/acme/user-service",
            "tier": "standard",
            "on_call": "@backend-team",
            "description": "User profile and preferences management.",
        },
        "relations": {
            "deployed_to": ["development", "staging", "production"],
            "owned_by": "backend",
        },
    },
    {
        "identifier": "search-service",
        "title": "Search Service",
        "properties": {
            "language": "Go",
            "repository": "https://github.com/acme/search-service",
            "tier": "standard",
            "on_call": "@platform-team",
            "description": "Full-text search powered by Elasticsearch.",
        },
        "relations": {
            "deployed_to": ["staging", "production"],
            "owned_by": "platform",
        },
    },
    {
        "identifier": "analytics-service",
        "title": "Analytics Service",
        "properties": {
            "language": "Python",
            "repository": "https://github.com/acme/analytics-service",
            "tier": "internal",
            "on_call": "@backend-team",
            "description": "Internal analytics and reporting pipeline.",
        },
        "relations": {
            "deployed_to": ["development", "staging"],
            "owned_by": "backend",
        },
    },
    {
        "identifier": "billing-service",
        "title": "Billing Service",
        "properties": {
            "language": "Java",
            "repository": "https://github.com/acme/billing-service",
            "tier": "critical",
            "on_call": "@backend-team",
            "description": "Subscription management and invoice generation.",
        },
        "relations": {
            "deployed_to": ["staging", "production"],
            "owned_by": "backend",
        },
    },
]


def _generate_deployments() -> list[dict[str, Any]]:
    """Generate realistic deployment entities with recent timestamps.

    Returns:
        List of deployment entity dicts with relative timestamps.
    """
    now = datetime.now(tz=UTC)
    raw = [
        ("api-gateway-prod", "API Gateway Prod", "api-gateway", "production", "2.4.1", 1),
        ("api-gateway-stg", "API Gateway Staging", "api-gateway", "staging", "2.5.0-rc1", 2),
        ("auth-service-prod", "Auth Service Prod", "auth-service", "production", "1.8.3", 3),
        ("auth-service-stg", "Auth Service Staging", "auth-service", "staging", "1.9.0-rc2", 4),
        ("payment-service-prod", "Payment Prod", "payment-service", "production", "3.1.0", 5),
        ("notification-prod", "Notification Prod",
         "notification-service", "production", "1.2.7", 6),
        ("notification-stg", "Notification Staging",
         "notification-service", "staging", "1.3.0-rc1", 7),
        ("user-service-prod", "User Service Prod", "user-service", "production", "4.0.2", 8),
        ("user-service-stg", "User Service Staging", "user-service", "staging", "4.1.0-rc1", 10),
        ("search-service-prod", "Search Prod", "search-service", "production", "2.0.0", 12),
        ("billing-service-prod", "Billing Prod", "billing-service", "production", "1.5.4", 14),
    ]

    shas = [
        "a1b2c3d", "e4f5g6h", "i7j8k9l", "m0n1o2p", "q3r4s5t",
        "u6v7w8x", "y9z0a1b", "c2d3e4f", "g5h6i7j", "k8l9m0n",
        "o1p2q3r",
    ]

    deployments: list[dict[str, Any]] = []
    for idx, (ident, title, service, env, version, hours_ago) in enumerate(raw):
        deployed_at = (now - timedelta(hours=hours_ago)).isoformat()
        deployments.append(
            {
                "identifier": ident,
                "title": title,
                "properties": {
                    "version": version,
                    "status": "running",
                    "deployed_at": deployed_at,
                    "commit_sha": shas[idx],
                },
                "relations": {
                    "service": service,
                    "target": env,
                },
            }
        )
    return deployments


# ── Public API ───────────────────────────────────────────────────────


async def seed_demo_data(
    client: PortClient,
    on_progress: ProgressCallback | None = None,
) -> SeedResult:
    """Create all demo data in the target Port.io organization.

    Creates blueprints, scorecards, and entities in dependency order.
    Upserts are used so running seed multiple times is safe.

    Args:
        client: Authenticated Port API client.
        on_progress: Optional callback invoked as ``(step, item, detail)``
            for each resource created.

    Returns:
        A SeedResult summarising what was created.
    """
    progress = on_progress or _noop_progress
    result = SeedResult()

    # 1. Blueprints
    for bp in BLUEPRINTS:
        await client.upsert_blueprint(bp)
        progress("blueprints", bp["identifier"])
        result.blueprints_created += 1

    # 2. Scorecards
    for bp_id, sc in SCORECARDS:
        await client.upsert_scorecard(bp_id, sc)
        progress("scorecards", sc["identifier"])
        result.scorecards_created += 1

    # 3. Entities -- dependency order: teams, environments, microservices, deployments
    entity_groups: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("team", "teams", TEAMS),
        ("environment", "environments", ENVIRONMENTS),
        ("microservice", "microservices", MICROSERVICES),
        ("deployment", "deployments", _generate_deployments()),
    ]

    for bp_id, step_name, entities in entity_groups:
        for entity in entities:
            await client.upsert_entity(bp_id, entity)
            detail = _entity_detail(entity)
            progress(step_name, entity["identifier"], detail)
            result.entities_created += 1
        result.entity_breakdown[step_name] = len(entities)

    return result


def _entity_detail(entity: dict[str, Any]) -> str:
    """Build a detail string for progress reporting on microservice entities.

    Args:
        entity: Entity data dict.

    Returns:
        Detail string like ``"-> platform, [staging, production]"`` or empty.
    """
    relations = entity.get("relations", {})
    owned_by = relations.get("owned_by")
    deployed_to = relations.get("deployed_to")

    if owned_by and deployed_to:
        envs = deployed_to if isinstance(deployed_to, list) else [deployed_to]
        return f"-> {owned_by}, [{', '.join(envs)}]"
    return ""


async def cleanup_demo_data(
    client: PortClient,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Delete all seeded demo data in reverse dependency order.

    Silently skips resources that are already deleted (404).

    Args:
        client: Authenticated Port API client.
        on_progress: Optional callback invoked as ``(step, item, detail)``
            for each resource deleted.

    Returns:
        Total count of deleted resources.
    """
    progress = on_progress or _noop_progress
    deleted = 0

    # 1. Entities -- reverse order: deployments, microservices, environments, teams
    entity_groups: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("deployment", "deployments", _generate_deployments()),
        ("microservice", "microservices", MICROSERVICES),
        ("environment", "environments", ENVIRONMENTS),
        ("team", "teams", TEAMS),
    ]

    for bp_id, step_name, entities in entity_groups:
        count = 0
        for entity in entities:
            if await _safe_delete_entity(client, bp_id, entity["identifier"]):
                count += 1
                deleted += 1
        progress(step_name, str(count))

    # 2. Scorecards
    for bp_id, sc in SCORECARDS:
        if await _safe_delete_scorecard(client, bp_id, sc["identifier"]):
            deleted += 1
            progress("scorecards", sc["identifier"])

    # 3. Blueprints -- reverse order
    for bp in reversed(BLUEPRINTS):
        if await _safe_delete_blueprint(client, bp["identifier"]):
            deleted += 1
            progress("blueprints", bp["identifier"])

    return deleted


async def _safe_delete_entity(
    client: PortClient, blueprint_id: str, identifier: str
) -> bool:
    """Delete an entity, returning False on 404.

    Args:
        client: Authenticated Port API client.
        blueprint_id: Blueprint the entity belongs to.
        identifier: Entity identifier.

    Returns:
        True if deleted, False if not found.
    """
    try:
        await client.delete_entity(blueprint_id, identifier)
        return True
    except PortAPIError as exc:
        if exc.status_code == 404:
            return False
        raise


async def _safe_delete_scorecard(
    client: PortClient, blueprint_id: str, identifier: str
) -> bool:
    """Delete a scorecard, returning False on 404.

    Args:
        client: Authenticated Port API client.
        blueprint_id: Blueprint the scorecard belongs to.
        identifier: Scorecard identifier.

    Returns:
        True if deleted, False if not found.
    """
    try:
        await client.delete_scorecard(blueprint_id, identifier)
        return True
    except PortAPIError as exc:
        if exc.status_code == 404:
            return False
        raise


async def _safe_delete_blueprint(client: PortClient, identifier: str) -> bool:
    """Delete a blueprint, returning False on 404.

    Args:
        client: Authenticated Port API client.
        identifier: Blueprint identifier.

    Returns:
        True if deleted, False if not found.
    """
    try:
        await client.delete_blueprint(identifier)
        return True
    except PortAPIError as exc:
        if exc.status_code == 404:
            return False
        raise
