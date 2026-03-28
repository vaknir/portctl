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

SCORECARD_SECURITY: dict[str, Any] = {
    "identifier": "security",
    "title": "Security",
    "rules": [
        {
            "identifier": "has-on-call-contact",
            "title": "Has On-call Contact",
            "level": "Bronze",
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
            "identifier": "not-internal-tier",
            "title": "Not Internal Tier",
            "level": "Silver",
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
        {
            "identifier": "has-service-description",
            "title": "Has Service Description",
            "level": "Silver",
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
            "identifier": "is-critical-tier",
            "title": "Is Critical Tier",
            "level": "Gold",
            "query": {
                "combinator": "and",
                "conditions": [
                    {
                        "operator": "=",
                        "property": "tier",
                        "value": "critical",
                    }
                ],
            },
        },
    ],
}

SCORECARD_CODE_QUALITY: dict[str, Any] = {
    "identifier": "code-quality",
    "title": "Code Quality",
    "rules": [
        {
            "identifier": "has-repository",
            "title": "Has Repository",
            "level": "Bronze",
            "query": {
                "combinator": "and",
                "conditions": [
                    {
                        "operator": "isNotEmpty",
                        "property": "repository",
                    }
                ],
            },
        },
        {
            "identifier": "has-service-docs",
            "title": "Has Service Documentation",
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
            "identifier": "has-oncall-owner",
            "title": "Has On-call Owner",
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
            "identifier": "is-production-grade",
            "title": "Is Production Grade",
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
    ("microservice", SCORECARD_SECURITY),
    ("microservice", SCORECARD_CODE_QUALITY),
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


# ── GitHub integration entities ──────────────────────────────────────

GITHUB_ORGANIZATIONS: list[dict[str, Any]] = [
    {
        "identifier": "acme-corp",
        "title": "Acme Corp",
        "properties": {
            "login": "acme-corp",
            "id": 12345678,
            "nodeId": "MDEyOk9yZ2FuaXphdGlvbjEyMzQ1Njc4",
            "url": "https://github.com/acme-corp",
            "reposUrl": "https://api.github.com/orgs/acme-corp/repos",
            "eventsUrl": "https://api.github.com/orgs/acme-corp/events",
            "hooksUrl": "https://api.github.com/orgs/acme-corp/hooks",
            "issuesUrl": "https://api.github.com/orgs/acme-corp/issues",
            "membersUrl": "https://api.github.com/orgs/acme-corp/members{/member}",
            "publicMembersUrl": "https://api.github.com/orgs/acme-corp/public_members{/member}",
            "avatarUrl": "https://avatars.githubusercontent.com/u/12345678",
            "description": "Building the future of developer portals",
        },
        "relations": {},
    },
]

GITHUB_USERS: list[dict[str, Any]] = [
    {
        "identifier": "sarah-chen",
        "title": "Sarah Chen",
        "properties": {"email": "sarah.chen@acme-corp.dev"},
        "relations": {},
    },
    {
        "identifier": "alex-murphy",
        "title": "Alex Murphy",
        "properties": {"email": "alex.murphy@acme-corp.dev"},
        "relations": {},
    },
    {
        "identifier": "jordan-lee",
        "title": "Jordan Lee",
        "properties": {"email": "jordan.lee@acme-corp.dev"},
        "relations": {},
    },
    {
        "identifier": "priya-patel",
        "title": "Priya Patel",
        "properties": {"email": "priya.patel@acme-corp.dev"},
        "relations": {},
    },
    {
        "identifier": "marcus-johnson",
        "title": "Marcus Johnson",
        "properties": {"email": "marcus.johnson@acme-corp.dev"},
        "relations": {},
    },
]

GITHUB_TEAMS: list[dict[str, Any]] = [
    {
        "identifier": "core-platform",
        "title": "Core Platform",
        "properties": {
            "slug": "core-platform",
            "description": "Core infrastructure and platform services",
            "link": "https://github.com/orgs/acme-corp/teams/core-platform",
            "permission": "admin",
            "notification_setting": "notifications_enabled",
        },
        "relations": {
            "members": ["sarah-chen", "alex-murphy"],
        },
    },
    {
        "identifier": "backend-eng",
        "title": "Backend Engineering",
        "properties": {
            "slug": "backend-eng",
            "description": "Backend services and API development",
            "link": "https://github.com/orgs/acme-corp/teams/backend-eng",
            "permission": "push",
            "notification_setting": "notifications_enabled",
        },
        "relations": {
            "members": ["jordan-lee", "priya-patel", "marcus-johnson"],
        },
    },
    {
        "identifier": "frontend-eng",
        "title": "Frontend Engineering",
        "properties": {
            "slug": "frontend-eng",
            "description": "Frontend applications and UI components",
            "link": "https://github.com/orgs/acme-corp/teams/frontend-eng",
            "permission": "push",
            "notification_setting": "notifications_enabled",
        },
        "relations": {
            "members": ["alex-murphy", "jordan-lee"],
        },
    },
]

_REPO_DEFINITIONS: list[tuple[str, str, str, str, str, list[str]]] = [
    # (identifier, title, description, language, defaultBranch, teams)
    (
        "api-gateway-repo",
        "API Gateway",
        "Central API gateway with routing and rate limiting",
        "Go",
        "main",
        ["core-platform"],
    ),
    (
        "auth-service-repo",
        "Auth Service",
        "Authentication and authorization microservice",
        "Python",
        "main",
        ["backend-eng"],
    ),
    (
        "payment-service-repo",
        "Payment Service",
        "Payment processing and Stripe integration",
        "Java",
        "main",
        ["backend-eng"],
    ),
    (
        "notification-service-repo",
        "Notification Service",
        "Multi-channel notification delivery",
        "Python",
        "main",
        ["backend-eng"],
    ),
    (
        "user-service-repo",
        "User Service",
        "User profile and preferences management",
        "TypeScript",
        "main",
        ["backend-eng", "frontend-eng"],
    ),
    (
        "search-service-repo",
        "Search Service",
        "Full-text search powered by Elasticsearch",
        "Go",
        "main",
        ["core-platform"],
    ),
    (
        "analytics-service-repo",
        "Analytics Service",
        "Internal analytics and reporting pipeline",
        "Python",
        "develop",
        ["backend-eng"],
    ),
    (
        "billing-service-repo",
        "Billing Service",
        "Subscription management and invoicing",
        "Java",
        "main",
        ["backend-eng"],
    ),
]

_REPO_READMES: dict[str, str] = {
    "api-gateway-repo": (
        "# API Gateway\nHigh-performance gateway built with Go.\n"
        "Handles routing, rate limiting, and authentication."
    ),
    "auth-service-repo": (
        "# Auth Service\nOAuth2/OIDC provider for Acme platform.\n"
        "Supports SSO, MFA, and API key management."
    ),
    "payment-service-repo": (
        "# Payment Service\nStripe-based payment processing.\n"
        "PCI-DSS compliant with automatic retry logic."
    ),
    "notification-service-repo": (
        "# Notification Service\nSends email, SMS, and push notifications.\n"
        "Supports templating and delivery scheduling."
    ),
    "user-service-repo": (
        "# User Service\nManages user profiles and preferences.\nGraphQL and REST APIs available."
    ),
    "search-service-repo": (
        "# Search Service\nElasticsearch-backed search engine.\n"
        "Supports fuzzy matching and faceted search."
    ),
    "analytics-service-repo": (
        "# Analytics Service\nEvent ingestion and reporting pipeline.\n"
        "ClickHouse backend with real-time dashboards."
    ),
    "billing-service-repo": (
        "# Billing Service\nSubscription lifecycle and invoice generation.\n"
        "Integrates with Stripe and NetSuite."
    ),
}


def _generate_github_repositories() -> list[dict[str, Any]]:
    """Generate GitHub repository entities with realistic metadata.

    Returns:
        List of repository entity dicts.
    """
    now = datetime.now(tz=UTC)
    repos: list[dict[str, Any]] = []
    for idx, (ident, title, desc, lang, branch, teams) in enumerate(_REPO_DEFINITIONS):
        repos.append(
            {
                "identifier": ident,
                "title": title,
                "properties": {
                    "readme": _REPO_READMES[ident],
                    "url": f"https://github.com/acme-corp/{ident.replace('-repo', '')}",
                    "defaultBranch": branch,
                    "description": desc,
                    "visibility": "private",
                    "language": lang,
                    "last_push": (now - timedelta(hours=idx * 3 + 1)).isoformat(),
                    "require_code_owner_review": True,
                    "require_approval_count": 2 if lang in ("Java", "Go") else 1,
                },
                "relations": {
                    "githubTeams": teams,
                    "organization": "acme-corp",
                },
            }
        )
    return repos


def _generate_github_pull_requests() -> list[dict[str, Any]]:
    """Generate recent GitHub pull request entities.

    Returns:
        List of PR entity dicts with a mix of statuses.
    """
    now = datetime.now(tz=UTC)
    raw: list[tuple[str, str, str, str, str, str, int, int, str]] = [
        # (id, title, status, repo, creator, branch, hours_ago, pr_num, lead_time)
        (
            "pr-api-gw-142",
            "feat: add circuit breaker to upstream calls",
            "merged",
            "api-gateway-repo",
            "sarah-chen",
            "feat/circuit-breaker",
            4,
            142,
            "6.2",
        ),
        (
            "pr-auth-89",
            "fix: refresh token rotation race condition",
            "merged",
            "auth-service-repo",
            "jordan-lee",
            "fix/token-rotation",
            8,
            89,
            "3.5",
        ),
        (
            "pr-payment-67",
            "feat: add Apple Pay support",
            "open",
            "payment-service-repo",
            "priya-patel",
            "feat/apple-pay",
            2,
            67,
            "",
        ),
        (
            "pr-user-201",
            "refactor: migrate to Prisma ORM",
            "open",
            "user-service-repo",
            "marcus-johnson",
            "refactor/prisma-migration",
            12,
            201,
            "",
        ),
        (
            "pr-search-34",
            "fix: memory leak in query cache",
            "merged",
            "search-service-repo",
            "alex-murphy",
            "fix/query-cache-leak",
            24,
            34,
            "1.8",
        ),
        (
            "pr-billing-55",
            "chore: upgrade Stripe SDK to v15",
            "closed",
            "billing-service-repo",
            "priya-patel",
            "chore/stripe-v15",
            48,
            55,
            "",
        ),
    ]

    prs: list[dict[str, Any]] = []
    for ident, title, status, repo, creator, branch, hours_ago, pr_num, lead in raw:
        created_at = (now - timedelta(hours=hours_ago)).isoformat()
        props: dict[str, Any] = {
            "status": status,
            "createdAt": created_at,
            "updatedAt": (now - timedelta(hours=max(0, hours_ago - 1))).isoformat(),
            "link": f"https://github.com/acme-corp/{repo.replace('-repo', '')}/pull/{pr_num}",
            "prNumber": pr_num,
            "branch": branch,
        }
        if status == "merged":
            props["mergedAt"] = (now - timedelta(hours=max(0, hours_ago - 1))).isoformat()
            props["leadTimeHours"] = float(lead)
        if status in ("merged", "closed"):
            props["closedAt"] = (now - timedelta(hours=max(0, hours_ago - 1))).isoformat()

        prs.append(
            {
                "identifier": ident,
                "title": title,
                "properties": props,
                "relations": {
                    "repository": repo,
                    "git_hub_creator": creator,
                },
            }
        )
    return prs


# ── Jira integration entities ───────────────────────────────────────

JIRA_PROJECTS: list[dict[str, Any]] = [
    {
        "identifier": "PLAT",
        "title": "Platform",
        "properties": {
            "url": "https://acme-corp.atlassian.net/browse/PLAT",
        },
        "relations": {},
    },
    {
        "identifier": "BACK",
        "title": "Backend",
        "properties": {
            "url": "https://acme-corp.atlassian.net/browse/BACK",
        },
        "relations": {},
    },
]

JIRA_USERS: list[dict[str, Any]] = [
    {
        "identifier": "jira-sarah-chen",
        "title": "Sarah Chen",
        "properties": {
            "emailAddress": "sarah.chen@acme-corp.dev",
            "displayName": "Sarah Chen",
            "active": True,
            "accountType": "atlassian",
        },
        "relations": {},
    },
    {
        "identifier": "jira-jordan-lee",
        "title": "Jordan Lee",
        "properties": {
            "emailAddress": "jordan.lee@acme-corp.dev",
            "displayName": "Jordan Lee",
            "active": True,
            "accountType": "atlassian",
        },
        "relations": {},
    },
    {
        "identifier": "jira-priya-patel",
        "title": "Priya Patel",
        "properties": {
            "emailAddress": "priya.patel@acme-corp.dev",
            "displayName": "Priya Patel",
            "active": True,
            "accountType": "atlassian",
        },
        "relations": {},
    },
    {
        "identifier": "jira-marcus-johnson",
        "title": "Marcus Johnson",
        "properties": {
            "emailAddress": "marcus.johnson@acme-corp.dev",
            "displayName": "Marcus Johnson",
            "active": True,
            "accountType": "atlassian",
        },
        "relations": {},
    },
]


def _generate_jira_issues() -> list[dict[str, Any]]:
    """Generate Jira issue entities with realistic metadata.

    Returns:
        List of Jira issue entity dicts.
    """
    now = datetime.now(tz=UTC)
    raw: list[tuple[str, str, str, str, str, str, list[str], str, list[str], int, str]] = [
        # (id, title, status, type, project, reporter, components, priority, labels, days_ago, url)
        (
            "PLAT-101",
            "Circuit breaker timeout tuning",
            "Done",
            "Story",
            "PLAT",
            "jira-sarah-chen",
            ["api-gateway"],
            "High",
            ["reliability"],
            3,
            "https://acme-corp.atlassian.net/browse/PLAT-101",
        ),
        (
            "PLAT-102",
            "Elasticsearch cluster upgrade to 8.x",
            "In Progress",
            "Story",
            "PLAT",
            "jira-sarah-chen",
            ["search-service"],
            "Medium",
            ["infrastructure", "upgrade"],
            5,
            "https://acme-corp.atlassian.net/browse/PLAT-102",
        ),
        (
            "PLAT-103",
            "API gateway memory spike under load",
            "To Do",
            "Bug",
            "PLAT",
            "jira-jordan-lee",
            ["api-gateway"],
            "Critical",
            ["production", "performance"],
            1,
            "https://acme-corp.atlassian.net/browse/PLAT-103",
        ),
        (
            "BACK-201",
            "Add Apple Pay payment method",
            "In Progress",
            "Story",
            "BACK",
            "jira-priya-patel",
            ["payment-service"],
            "High",
            ["payments", "feature"],
            4,
            "https://acme-corp.atlassian.net/browse/BACK-201",
        ),
        (
            "BACK-202",
            "Refresh token rotation race condition",
            "Done",
            "Bug",
            "BACK",
            "jira-jordan-lee",
            ["auth-service"],
            "Critical",
            ["security", "auth"],
            2,
            "https://acme-corp.atlassian.net/browse/BACK-202",
        ),
        (
            "BACK-203",
            "Migrate user-service to Prisma ORM",
            "In Progress",
            "Task",
            "BACK",
            "jira-marcus-johnson",
            ["user-service"],
            "Medium",
            ["tech-debt", "migration"],
            7,
            "https://acme-corp.atlassian.net/browse/BACK-203",
        ),
        (
            "BACK-204",
            "Notification delivery retry logic",
            "In Review",
            "Story",
            "BACK",
            "jira-priya-patel",
            ["notification-service"],
            "Medium",
            ["reliability"],
            6,
            "https://acme-corp.atlassian.net/browse/BACK-204",
        ),
        (
            "BACK-205",
            "Stripe SDK v15 upgrade",
            "Done",
            "Task",
            "BACK",
            "jira-marcus-johnson",
            ["billing-service"],
            "Low",
            ["dependencies", "upgrade"],
            10,
            "https://acme-corp.atlassian.net/browse/BACK-205",
        ),
    ]

    issues: list[dict[str, Any]] = []
    for (
        ident,
        title,
        status,
        issue_type,
        project,
        reporter,
        components,
        priority,
        labels,
        days_ago,
        url,
    ) in raw:
        created = (now - timedelta(days=days_ago)).isoformat()
        updated = (now - timedelta(days=max(0, days_ago - 1))).isoformat()
        issues.append(
            {
                "identifier": ident,
                "title": title,
                "properties": {
                    "url": url,
                    "status": status,
                    "issueType": issue_type,
                    "components": components,
                    "creator": reporter.replace("jira-", "").replace("-", " ").title(),
                    "priority": priority,
                    "labels": labels,
                    "created": created,
                    "updated": updated,
                },
                "relations": {
                    "project": project,
                    "jira_user_reporter": reporter,
                },
            }
        )
    return issues


# ── Service / Workload / Group entities ─────────────────────────────

SERVICES: list[dict[str, Any]] = [
    {
        "identifier": f"{name}-svc",
        "title": title,
        "properties": {},
        "relations": {"repository": f"{name}-repo"},
    }
    for name, title in [
        ("api-gateway", "API Gateway"),
        ("auth-service", "Auth Service"),
        ("payment-service", "Payment Service"),
        ("notification-service", "Notification Service"),
        ("user-service", "User Service"),
        ("search-service", "Search Service"),
        ("analytics-service", "Analytics Service"),
        ("billing-service", "Billing Service"),
    ]
]

WORKLOADS: list[dict[str, Any]] = [
    {
        "identifier": "api-gateway-prod-wl",
        "title": "API Gateway (Production)",
        "properties": {"version": "2.4.1"},
        "relations": {"service": "api-gateway-svc", "environment": "production"},
    },
    {
        "identifier": "auth-service-prod-wl",
        "title": "Auth Service (Production)",
        "properties": {"version": "1.8.3"},
        "relations": {"service": "auth-service-svc", "environment": "production"},
    },
    {
        "identifier": "payment-service-prod-wl",
        "title": "Payment Service (Production)",
        "properties": {"version": "3.1.0"},
        "relations": {"service": "payment-service-svc", "environment": "production"},
    },
    {
        "identifier": "user-service-stg-wl",
        "title": "User Service (Staging)",
        "properties": {"version": "4.1.0-rc1"},
        "relations": {"service": "user-service-svc", "environment": "staging"},
    },
    {
        "identifier": "search-service-prod-wl",
        "title": "Search Service (Production)",
        "properties": {"version": "2.0.0"},
        "relations": {"service": "search-service-svc", "environment": "production"},
    },
    {
        "identifier": "analytics-service-dev-wl",
        "title": "Analytics Service (Development)",
        "properties": {"version": "0.9.0-alpha"},
        "relations": {"service": "analytics-service-svc", "environment": "development"},
    },
]

GROUPS: list[dict[str, Any]] = [
    {
        "identifier": "engineering",
        "title": "Engineering",
        "properties": {},
        "relations": {},
    },
    {
        "identifier": "product",
        "title": "Product",
        "properties": {},
        "relations": {},
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
        (
            "notification-prod",
            "Notification Prod",
            "notification-service",
            "production",
            "1.2.7",
            6,
        ),
        (
            "notification-stg",
            "Notification Staging",
            "notification-service",
            "staging",
            "1.3.0-rc1",
            7,
        ),
        ("user-service-prod", "User Service Prod", "user-service", "production", "4.0.2", 8),
        ("user-service-stg", "User Service Staging", "user-service", "staging", "4.1.0-rc1", 10),
        ("search-service-prod", "Search Prod", "search-service", "production", "2.0.0", 12),
        ("billing-service-prod", "Billing Prod", "billing-service", "production", "1.5.4", 14),
    ]

    shas = [
        "a1b2c3d",
        "e4f5g6h",
        "i7j8k9l",
        "m0n1o2p",
        "q3r4s5t",
        "u6v7w8x",
        "y9z0a1b",
        "c2d3e4f",
        "g5h6i7j",
        "k8l9m0n",
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
        progress("blueprints", bp["identifier"], "created")
        result.blueprints_created += 1

    # 2. Scorecards
    for bp_id, sc in SCORECARDS:
        await client.upsert_scorecard(bp_id, sc)
        progress("scorecards", sc["identifier"], "created")
        result.scorecards_created += 1

    # 3. Entities -- dependency order: independent first, then dependents
    entity_groups: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("group", "groups", GROUPS),
        ("team", "teams", TEAMS),
        ("environment", "environments", ENVIRONMENTS),
        ("githubOrganization", "github_organizations", GITHUB_ORGANIZATIONS),
        ("githubUser", "github_users", GITHUB_USERS),
        ("jiraProject", "jira_projects", JIRA_PROJECTS),
        ("jiraUser", "jira_users", JIRA_USERS),
        ("githubTeam", "github_teams", GITHUB_TEAMS),
        ("githubRepository", "github_repositories", _generate_github_repositories()),
        ("microservice", "microservices", MICROSERVICES),
        ("service", "services", SERVICES),
        ("githubPullRequest", "github_pull_requests", _generate_github_pull_requests()),
        ("jiraIssue", "jira_issues", _generate_jira_issues()),
        ("deployment", "deployments", _generate_deployments()),
        ("workload", "workloads", WORKLOADS),
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
        return f"-> {owned_by}, \\[{', '.join(envs)}]"
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

    # 1. Entities -- reverse dependency order
    entity_groups: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("workload", "workloads", WORKLOADS),
        ("deployment", "deployments", _generate_deployments()),
        ("jiraIssue", "jira_issues", _generate_jira_issues()),
        ("githubPullRequest", "github_pull_requests", _generate_github_pull_requests()),
        ("service", "services", SERVICES),
        ("microservice", "microservices", MICROSERVICES),
        ("githubRepository", "github_repositories", _generate_github_repositories()),
        ("githubTeam", "github_teams", GITHUB_TEAMS),
        ("jiraUser", "jira_users", JIRA_USERS),
        ("jiraProject", "jira_projects", JIRA_PROJECTS),
        ("githubUser", "github_users", GITHUB_USERS),
        ("githubOrganization", "github_organizations", GITHUB_ORGANIZATIONS),
        ("environment", "environments", ENVIRONMENTS),
        ("team", "teams", TEAMS),
        ("group", "groups", GROUPS),
    ]

    for bp_id, step_name, entities in entity_groups:
        count = 0
        for entity in entities:
            if await _safe_delete_entity(client, bp_id, entity["identifier"]):
                count += 1
                deleted += 1
        progress(step_name, str(count), "deleted")

    # 2. Scorecards
    for bp_id, sc in SCORECARDS:
        if await _safe_delete_scorecard(client, bp_id, sc["identifier"]):
            deleted += 1
            progress("scorecards", sc["identifier"], "deleted")

    # 3. Blueprints -- reverse order
    for bp in reversed(BLUEPRINTS):
        if await _safe_delete_blueprint(client, bp["identifier"]):
            deleted += 1
            progress("blueprints", bp["identifier"], "deleted")

    return deleted


async def _safe_delete_entity(client: PortClient, blueprint_id: str, identifier: str) -> bool:
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
        if exc.status_code in (404, 422):
            logger.debug("Skipping entity %s/%s: %s", blueprint_id, identifier, exc.detail)
            return False
        raise


async def _safe_delete_scorecard(client: PortClient, blueprint_id: str, identifier: str) -> bool:
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
        if exc.status_code in (404, 422):
            logger.debug("Skipping scorecard %s/%s: %s", blueprint_id, identifier, exc.detail)
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
        if exc.status_code in (404, 422):
            logger.debug("Skipping blueprint %s: %s", identifier, exc.detail)
            return False
        raise
