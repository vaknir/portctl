"""Blueprint YAML schema (pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BlueprintProperty(BaseModel):
    """Schema for a single blueprint property."""

    type: str = Field(description="Property type (string, number, boolean, array, object)")
    title: str | None = Field(default=None, description="Display title for the property")
    description: str | None = Field(default=None, description="Human-readable description")
    required: bool = Field(default=False, description="Whether the property is required")
    default: Any = Field(default=None, description="Default value for the property")  # noqa: ANN401
    enum: list[str] | None = Field(default=None, description="Allowed values for the property")
    format: str | None = Field(default=None, description="Value format (url, email, etc.)")
    spec: str | None = Field(default=None, description="Spec type for the property")
    icon: str | None = Field(default=None, description="Icon for the property")


class BlueprintMirrorProperty(BaseModel):
    """Schema for a mirror property that reflects a related entity's property."""

    title: str | None = Field(default=None, description="Display title")
    path: str = Field(description="Path to the mirrored property (e.g. relation.property)")


class BlueprintCalculationProperty(BaseModel):
    """Schema for a calculation property using aggregation functions."""

    title: str | None = Field(default=None, description="Display title")
    calculation: str = Field(description="Calculation type (count, average, etc.)")
    type: str = Field(description="Result type")
    colors: dict[str, str] | None = Field(
        default=None, description="Color mapping for values"
    )


class BlueprintRelation(BaseModel):
    """Schema for a relation between two blueprints."""

    target: str = Field(description="Target blueprint identifier")
    title: str | None = Field(default=None, description="Display title for the relation")
    many: bool = Field(default=False, description="Whether this is a many-relation")
    required: bool = Field(default=False, description="Whether the relation is required")


class Blueprint(BaseModel):
    """Schema for a Port.io blueprint YAML file."""

    identifier: str = Field(description="Unique blueprint identifier")
    title: str = Field(description="Display title")
    icon: str | None = Field(default=None, description="Blueprint icon name")
    description: str | None = Field(default=None, description="Human-readable description")
    properties: dict[str, BlueprintProperty] = Field(
        default_factory=dict, description="Blueprint properties keyed by name"
    )
    mirror_properties: dict[str, BlueprintMirrorProperty] = Field(
        default_factory=dict, description="Mirror properties keyed by name"
    )
    calculation_properties: dict[str, BlueprintCalculationProperty] = Field(
        default_factory=dict, description="Calculation properties keyed by name"
    )
    relations: dict[str, BlueprintRelation] = Field(
        default_factory=dict, description="Relations keyed by name"
    )
