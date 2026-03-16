"""Pydantic models for Port API responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PortAPIResponse(BaseModel):
    """Base response from Port API."""

    ok: bool = Field(description="Whether the API call succeeded")


class BlueprintResponse(PortAPIResponse):
    """Response for a single blueprint."""

    blueprint: dict[str, Any] = Field(description="Blueprint data")


class BlueprintsResponse(PortAPIResponse):
    """Response for listing blueprints."""

    blueprints: list[dict[str, Any]] = Field(description="List of blueprints")


class ScorecardResponse(PortAPIResponse):
    """Response for a single scorecard."""

    scorecard: dict[str, Any] = Field(description="Scorecard data")


class ScorecardsResponse(PortAPIResponse):
    """Response for listing scorecards."""

    scorecards: list[dict[str, Any]] = Field(description="List of scorecards")


class ActionResponse(PortAPIResponse):
    """Response for a single action."""

    action: dict[str, Any] = Field(description="Action data")


class ActionsResponse(PortAPIResponse):
    """Response for listing actions."""

    actions: list[dict[str, Any]] = Field(description="List of actions")


class PageResponse(PortAPIResponse):
    """Response for a single page."""

    page: dict[str, Any] = Field(description="Page data")


class PagesResponse(PortAPIResponse):
    """Response for listing pages."""

    pages: list[dict[str, Any]] = Field(description="List of pages")


class EntitiesResponse(PortAPIResponse):
    """Response for listing entities."""

    entities: list[dict[str, Any]] = Field(description="List of entities")


class IntegrationsResponse(PortAPIResponse):
    """Response for listing integrations."""

    integrations: list[dict[str, Any]] = Field(description="List of integrations")


class IntegrationLogsResponse(PortAPIResponse):
    """Response for listing integration logs."""

    logs: list[dict[str, Any]] = Field(description="List of log entries")


class UserResponse(PortAPIResponse):
    """Response for current user info."""

    user: dict[str, Any] = Field(description="User data")
