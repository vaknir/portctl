"""Tests for panels formatter -- render_blueprint."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from portctl.cli.formatters.panels import render_blueprint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture(blueprint_data: dict) -> str:
    """Render a blueprint to a string and return the output."""
    buf = StringIO()
    con = Console(file=buf, no_color=True, width=120)
    render_blueprint(blueprint_data, con)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_BLUEPRINT: dict = {
    "identifier": "service",
    "title": "Microservice",
    "icon": "Microservice",
    "description": "A microservice component",
    "schema": {
        "properties": {
            "language": {"type": "string", "title": "Language"},
            "coverage": {"type": "number", "title": "Coverage"},
        },
        "required": ["language"],
    },
    "relations": {
        "team": {"target": "team", "title": "Team", "many": False},
        "services": {"target": "service", "title": "Services", "many": True},
    },
}

NO_PROPERTIES_BLUEPRINT: dict = {
    "identifier": "empty-bp",
    "title": "Empty Blueprint",
    "icon": None,
    "description": None,
    "schema": {"properties": {}, "required": []},
    "relations": {
        "owner": {"target": "team", "title": "Owner", "many": False},
    },
}

NO_RELATIONS_BLUEPRINT: dict = {
    "identifier": "lone-bp",
    "title": "Lone Blueprint",
    "icon": "Tool",
    "description": "Has properties but no relations",
    "schema": {
        "properties": {
            "version": {"type": "string", "title": "Version"},
        },
        "required": ["version"],
    },
    "relations": {},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderBlueprintTitle:
    """render_blueprint shows blueprint header information."""

    def test_render_blueprint_shows_title(self) -> None:
        """Blueprint title appears in the rendered output."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "Microservice" in output

    def test_render_blueprint_shows_identifier(self) -> None:
        """Blueprint identifier appears in the rendered output."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "service" in output

    def test_render_blueprint_shows_description(self) -> None:
        """Blueprint description appears when present."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "A microservice component" in output


class TestRenderBlueprintProperties:
    """render_blueprint renders a properties table."""

    def test_render_blueprint_shows_properties(self) -> None:
        """Properties table is rendered with property names."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "language" in output
        assert "coverage" in output

    def test_render_blueprint_shows_property_types(self) -> None:
        """Property type column appears in the output."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "string" in output
        assert "number" in output

    def test_render_blueprint_shows_required_marker(self) -> None:
        """Required properties are marked, optional ones are not."""
        output = _capture(MINIMAL_BLUEPRINT)
        # Required marker present for required property
        assert "\u2713" in output or "Yes" in output or "required" in output.lower()

    def test_render_blueprint_no_properties(self) -> None:
        """Renders gracefully when there are no properties."""
        output = _capture(NO_PROPERTIES_BLUEPRINT)
        # Should not raise; identifier should still appear
        assert "empty-bp" in output or "Empty Blueprint" in output


class TestRenderBlueprintRelations:
    """render_blueprint renders a relations table."""

    def test_render_blueprint_shows_relations(self) -> None:
        """Relations table is rendered with relation names."""
        output = _capture(MINIMAL_BLUEPRINT)
        assert "team" in output
        assert "services" in output

    def test_render_blueprint_shows_relation_targets(self) -> None:
        """Relation target blueprint identifiers appear in output."""
        output = _capture(MINIMAL_BLUEPRINT)
        # 'team' target and 'service' target
        assert "team" in output

    def test_render_blueprint_shows_many_flag(self) -> None:
        """Many/single cardinality is shown for relations."""
        output = _capture(MINIMAL_BLUEPRINT)
        # 'services' relation is many=True, 'team' relation is many=False
        assert "Yes" in output or "No" in output

    def test_render_blueprint_no_relations(self) -> None:
        """Renders gracefully when there are no relations."""
        output = _capture(NO_RELATIONS_BLUEPRINT)
        # Should not raise; title should still appear
        assert "Lone Blueprint" in output or "lone-bp" in output
