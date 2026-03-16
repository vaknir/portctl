"""Config file schema (pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from portctl.constants import DEFAULT_API_URL


class OrgConfig(BaseModel):
    """Configuration for a single Port organization."""

    name: str = Field(description="Organization display name")
    client_id: str = Field(description="Port API client ID")
    client_secret: str = Field(description="Port API client secret")
    role: Literal["production", "mirror", "development"] = Field(
        default="development", description="Organization role"
    )
    api_url: str = Field(default=DEFAULT_API_URL, description="Port API base URL")


class PortctlConfig(BaseModel):
    """Root configuration file schema."""

    default_org: str | None = Field(
        default=None, description="Default organization alias"
    )
    orgs: dict[str, OrgConfig] = Field(
        description="Organization configurations keyed by alias"
    )
