"""Page YAML schema (pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Page(BaseModel):
    """Schema for a Port.io page YAML file.

    Pages define portal UI layouts with widgets. Widget configurations are
    deeply nested and vary by type, so they are kept as flexible dicts.
    """

    identifier: str = Field(description="Unique page identifier")
    title: str = Field(description="Display title")
    type: str | None = Field(
        default=None, description="Page type (blueprint-entities, dashboard, etc.)"
    )
    icon: str | None = Field(default=None, description="Page icon name")
    description: str | None = Field(default=None, description="Human-readable description")
    widgets: list[dict[str, Any]] = Field(  # noqa: ANN401
        default_factory=list, description="Widget configurations for the page layout"
    )
    locked: bool = Field(default=False, description="Whether the page is locked from editing")
    parent: str | None = Field(default=None, description="Parent page identifier for nested pages")
