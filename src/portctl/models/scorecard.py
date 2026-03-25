"""Scorecard YAML schema (pydantic)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScorecardLevel(BaseModel):
    """Schema for a scorecard level (e.g. Bronze, Silver, Gold)."""

    identifier: str = Field(default="", description="Unique level identifier")
    title: str = Field(description="Display title")
    color: str = Field(description="Color for the level indicator")


class QueryCondition(BaseModel):
    """Schema for a single query condition in a scorecard rule."""

    property: str | None = Field(default=None, description="Property to evaluate")
    operator: str = Field(description="Comparison operator (=, !=, >, <, contains, etc.)")
    value: Any = Field(default=None, description="Value to compare against")  # noqa: ANN401


class Query(BaseModel):
    """Schema for a query combining multiple conditions."""

    combinator: Literal["and", "or"] = Field(
        default="and", description="Logical combinator for conditions"
    )
    conditions: list[QueryCondition] = Field(
        default_factory=list, description="List of conditions to evaluate"
    )


class ScorecardRule(BaseModel):
    """Schema for a single scorecard rule."""

    identifier: str = Field(description="Unique rule identifier")
    title: str = Field(description="Display title")
    level: str = Field(description="Level identifier this rule contributes to")
    query: Query = Field(description="Query that defines the rule condition")


class Scorecard(BaseModel):
    """Schema for a Port.io scorecard YAML file."""

    identifier: str = Field(description="Unique scorecard identifier")
    title: str = Field(description="Display title")
    blueprint: str = Field(description="Blueprint identifier this scorecard belongs to")
    levels: list[ScorecardLevel] = Field(
        default_factory=list, description="Scorecard levels from lowest to highest"
    )
    rules: list[ScorecardRule] = Field(
        default_factory=list, description="Rules that define how entities are scored"
    )
