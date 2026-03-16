"""Tests for Scorecard pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from portctl.models.scorecard import (
    Query,
    QueryCondition,
    Scorecard,
    ScorecardLevel,
    ScorecardRule,
)


class TestScorecardLevel:
    """Tests for ScorecardLevel model."""

    def test_valid_level(self) -> None:
        """All required fields provided."""
        level = ScorecardLevel(identifier="gold", title="Gold", color="gold")
        assert level.identifier == "gold"
        assert level.title == "Gold"
        assert level.color == "gold"

    def test_missing_identifier_rejected(self) -> None:
        """identifier is required."""
        with pytest.raises(ValidationError):
            ScorecardLevel(title="Gold", color="gold")  # type: ignore[call-arg]

    def test_missing_color_rejected(self) -> None:
        """color is required."""
        with pytest.raises(ValidationError):
            ScorecardLevel(identifier="gold", title="Gold")  # type: ignore[call-arg]


class TestQueryCondition:
    """Tests for QueryCondition model."""

    def test_minimal_condition(self) -> None:
        """Only operator is required."""
        cond = QueryCondition(operator="isNotEmpty")
        assert cond.operator == "isNotEmpty"
        assert cond.property is None
        assert cond.value is None

    def test_full_condition(self) -> None:
        """All fields set."""
        cond = QueryCondition(property="language", operator="=", value="python")
        assert cond.property == "language"
        assert cond.value == "python"


class TestQuery:
    """Tests for Query model."""

    def test_defaults(self) -> None:
        """Defaults to 'and' combinator with empty conditions."""
        q = Query()
        assert q.combinator == "and"
        assert q.conditions == []

    def test_or_combinator(self) -> None:
        """Accepts 'or' combinator."""
        q = Query(combinator="or")
        assert q.combinator == "or"

    def test_invalid_combinator_rejected(self) -> None:
        """Rejects invalid combinator values."""
        with pytest.raises(ValidationError):
            Query(combinator="xor")  # type: ignore[arg-type]

    def test_with_conditions(self) -> None:
        """Accepts a list of conditions."""
        q = Query(
            combinator="and",
            conditions=[
                QueryCondition(property="language", operator="=", value="python"),
                QueryCondition(property="coverage", operator=">", value=80),
            ],
        )
        assert len(q.conditions) == 2


class TestScorecardRule:
    """Tests for ScorecardRule model."""

    def test_valid_rule(self) -> None:
        """All required fields provided."""
        rule = ScorecardRule(
            identifier="has-readme",
            title="Has README",
            level="bronze",
            query=Query(
                conditions=[QueryCondition(property="readme", operator="isNotEmpty")]
            ),
        )
        assert rule.identifier == "has-readme"
        assert rule.level == "bronze"
        assert len(rule.query.conditions) == 1

    def test_missing_query_rejected(self) -> None:
        """query is required."""
        with pytest.raises(ValidationError):
            ScorecardRule(
                identifier="r1",
                title="Rule 1",
                level="bronze",
            )  # type: ignore[call-arg]


class TestScorecard:
    """Tests for Scorecard model."""

    def test_minimal_scorecard(self) -> None:
        """identifier, title, blueprint are required; rest defaults."""
        sc = Scorecard(
            identifier="production-readiness",
            title="Production Readiness",
            blueprint="service",
        )
        assert sc.identifier == "production-readiness"
        assert sc.blueprint == "service"
        assert sc.levels == []
        assert sc.rules == []

    def test_full_scorecard(self) -> None:
        """All fields populated."""
        sc = Scorecard(
            identifier="production-readiness",
            title="Production Readiness",
            blueprint="service",
            levels=[
                ScorecardLevel(identifier="bronze", title="Bronze", color="orange"),
                ScorecardLevel(identifier="gold", title="Gold", color="gold"),
            ],
            rules=[
                ScorecardRule(
                    identifier="has-readme",
                    title="Has README",
                    level="bronze",
                    query=Query(
                        conditions=[
                            QueryCondition(property="readme", operator="isNotEmpty"),
                        ]
                    ),
                ),
            ],
        )
        assert len(sc.levels) == 2
        assert len(sc.rules) == 1

    def test_missing_blueprint_rejected(self) -> None:
        """blueprint is required."""
        with pytest.raises(ValidationError):
            Scorecard(
                identifier="sc1",
                title="Scorecard 1",
            )  # type: ignore[call-arg]

    def test_scorecard_from_api_response(self) -> None:
        """Scorecard model can be constructed from a typical API response dict."""
        api_data = {
            "identifier": "production-readiness",
            "title": "Production Readiness",
            "blueprint": "service",
            "levels": [
                {"identifier": "bronze", "title": "Bronze", "color": "orange"},
                {"identifier": "gold", "title": "Gold", "color": "gold"},
            ],
            "rules": [
                {
                    "identifier": "has-readme",
                    "title": "Has README",
                    "level": "bronze",
                    "query": {
                        "combinator": "and",
                        "conditions": [
                            {"property": "readme", "operator": "isNotEmpty"},
                        ],
                    },
                },
            ],
        }
        sc = Scorecard(**api_data)
        assert sc.identifier == "production-readiness"
        assert len(sc.levels) == 2
        assert sc.rules[0].query.conditions[0].operator == "isNotEmpty"
