"""Action YAML schema (pydantic)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Action(BaseModel):
    """Schema for a Port.io action YAML file.

    Actions define self-service operations that users can trigger on entities.
    The trigger and invocation_method structures are complex and vary by type,
    so they are kept as flexible dicts.
    """

    identifier: str = Field(description="Unique action identifier")
    title: str = Field(description="Display title")
    blueprint: str = Field(description="Blueprint identifier this action belongs to")
    trigger: dict[str, Any] = Field(  # noqa: ANN401
        default_factory=dict, description="Trigger configuration (manual, automation, etc.)"
    )
    invocation_method: dict[str, Any] | None = Field(  # noqa: ANN401
        default=None, description="How the action is executed (webhook, GitHub, etc.)"
    )
    user_properties: dict[str, Any] = Field(  # noqa: ANN401
        default_factory=dict, description="User input properties for the action form"
    )
    description: str | None = Field(default=None, description="Human-readable description")
    required_approval: bool = Field(
        default=False, description="Whether the action requires approval before execution"
    )
