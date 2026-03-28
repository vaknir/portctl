"""Tests for Blueprint pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from portctl.models.blueprint import (
    Blueprint,
    BlueprintProperty,
    BlueprintRelation,
)


class TestBlueprintProperty:
    """Tests for BlueprintProperty model."""

    def test_minimal_property(self) -> None:
        """Only type is required."""
        prop = BlueprintProperty(type="string")
        assert prop.type == "string"
        assert prop.title is None
        assert prop.description is None
        assert prop.required is False

    def test_full_property(self) -> None:
        """All fields can be set."""
        prop = BlueprintProperty(
            type="string",
            title="Service Name",
            description="Name of the service",
            required=True,
            default="unnamed",
            enum=["a", "b"],
            format="url",
        )
        assert prop.title == "Service Name"
        assert prop.required is True
        assert prop.default == "unnamed"
        assert prop.enum == ["a", "b"]
        assert prop.format == "url"

    def test_missing_type_rejected(self) -> None:
        """type is required."""
        with pytest.raises(ValidationError):
            BlueprintProperty()  # type: ignore[call-arg]


class TestBlueprintRelation:
    """Tests for BlueprintRelation model."""

    def test_minimal_relation(self) -> None:
        """Only target is required."""
        rel = BlueprintRelation(target="environment")
        assert rel.target == "environment"
        assert rel.many is False
        assert rel.required is False
        assert rel.title is None

    def test_full_relation(self) -> None:
        """All fields can be set."""
        rel = BlueprintRelation(
            target="environment",
            title="Runs In",
            many=True,
            required=True,
        )
        assert rel.title == "Runs In"
        assert rel.many is True
        assert rel.required is True

    def test_missing_target_rejected(self) -> None:
        """target is required."""
        with pytest.raises(ValidationError):
            BlueprintRelation()  # type: ignore[call-arg]


class TestBlueprint:
    """Tests for Blueprint model."""

    def test_minimal_blueprint(self) -> None:
        """identifier and title are required, others default."""
        bp = Blueprint(identifier="service", title="Service")
        assert bp.identifier == "service"
        assert bp.title == "Service"
        assert bp.icon is None
        assert bp.description is None
        assert bp.properties == {}
        assert bp.relations == {}

    def test_full_blueprint(self) -> None:
        """All fields populated."""
        bp = Blueprint(
            identifier="service",
            title="Service",
            icon="Microservice",
            description="A microservice",
            properties={
                "language": BlueprintProperty(type="string", title="Language"),
            },
            relations={
                "environment": BlueprintRelation(target="environment", many=True),
            },
        )
        assert bp.icon == "Microservice"
        assert "language" in bp.properties
        assert bp.properties["language"].type == "string"
        assert "environment" in bp.relations
        assert bp.relations["environment"].many is True

    def test_missing_identifier_rejected(self) -> None:
        """identifier is required."""
        with pytest.raises(ValidationError):
            Blueprint(title="Service")  # type: ignore[call-arg]

    def test_missing_title_rejected(self) -> None:
        """title is required."""
        with pytest.raises(ValidationError):
            Blueprint(identifier="service")  # type: ignore[call-arg]

    def test_blueprint_from_api_response(self) -> None:
        """Blueprint model can be constructed from a typical API response dict."""
        api_data = {
            "identifier": "service",
            "title": "Service",
            "icon": "Microservice",
            "description": "A service blueprint",
            "schema": {
                "properties": {
                    "language": {"type": "string", "title": "Language"},
                    "version": {"type": "string", "required": True},
                },
                "required": ["version"],
            },
            "relations": {
                "environment": {
                    "target": "environment",
                    "title": "Environment",
                    "many": True,
                    "required": False,
                },
            },
        }
        # The exporter maps API format -> model format
        # Here we test that the model accepts the mapped data
        properties = {}
        schema = api_data.get("schema", {})
        required_props = schema.get("required", [])
        for name, prop_data in schema.get("properties", {}).items():
            prop_data_copy = dict(prop_data)
            if name in required_props:
                prop_data_copy["required"] = True
            properties[name] = BlueprintProperty(**prop_data_copy)

        bp = Blueprint(
            identifier=api_data["identifier"],
            title=api_data["title"],
            icon=api_data.get("icon"),
            description=api_data.get("description"),
            properties=properties,
            relations={k: BlueprintRelation(**v) for k, v in api_data.get("relations", {}).items()},
        )
        assert bp.identifier == "service"
        assert bp.properties["version"].required is True
        assert bp.relations["environment"].many is True
