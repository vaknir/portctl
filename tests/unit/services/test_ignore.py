"""Tests for .portctlignore service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from portctl.services.ignore import IgnoreFilter, IgnoreRule, load_ignore_filter, parse_ignore_file

if TYPE_CHECKING:
    from pathlib import Path


class TestParseIgnoreFile:
    """Tests for parse_ignore_file function."""

    def test_parse_empty_file(self) -> None:
        """Empty string returns no rules."""
        rules = parse_ignore_file("")
        assert rules == []

    def test_parse_comments_and_blanks(self) -> None:
        """Comments and blank lines are skipped."""
        content = """
# This is a comment
   # Indented comment


# Another comment
"""
        rules = parse_ignore_file(content)
        assert rules == []

    def test_parse_simple_patterns(self) -> None:
        """Pattern with slash is parsed with resource_type."""
        rules = parse_ignore_file("blueprints/_*")
        assert len(rules) == 1
        assert rules[0].pattern == "_*"
        assert rules[0].resource_type == "blueprints"
        assert rules[0].negated is False

    def test_parse_unslashed_pattern(self) -> None:
        """Pattern without slash has no resource_type (matches any)."""
        rules = parse_ignore_file("test_*")
        assert len(rules) == 1
        assert rules[0].pattern == "test_*"
        assert rules[0].resource_type is None
        assert rules[0].negated is False

    def test_parse_negation(self) -> None:
        """Pattern prefixed with ! sets negated=True."""
        rules = parse_ignore_file("!blueprints/_ocean_kafka")
        assert len(rules) == 1
        assert rules[0].pattern == "_ocean_kafka"
        assert rules[0].resource_type == "blueprints"
        assert rules[0].negated is True

    def test_parse_negation_unslashed(self) -> None:
        """Negated pattern without slash has no resource_type."""
        rules = parse_ignore_file("!keep_me")
        assert len(rules) == 1
        assert rules[0].pattern == "keep_me"
        assert rules[0].resource_type is None
        assert rules[0].negated is True

    def test_parse_multiple_rules(self) -> None:
        """Multiple rules are parsed in order."""
        content = """\
# Ignore all internal blueprints
blueprints/_*
# But keep kafka
!blueprints/_ocean_kafka
# Ignore test scorecards
scorecards/test_*
"""
        rules = parse_ignore_file(content)
        assert len(rules) == 3
        assert rules[0] == IgnoreRule(pattern="_*", resource_type="blueprints")
        assert rules[1] == IgnoreRule(
            pattern="_ocean_kafka", resource_type="blueprints", negated=True
        )
        assert rules[2] == IgnoreRule(pattern="test_*", resource_type="scorecards")

    def test_parse_strips_whitespace(self) -> None:
        """Leading/trailing whitespace on lines is stripped."""
        rules = parse_ignore_file("  blueprints/_*  ")
        assert len(rules) == 1
        assert rules[0].pattern == "_*"
        assert rules[0].resource_type == "blueprints"


class TestIgnoreFilterIsIgnored:
    """Tests for IgnoreFilter.is_ignored method."""

    def test_is_ignored_basic_match(self) -> None:
        """Glob pattern matches expected identifiers."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_ocean_*", resource_type="blueprints")]
        )
        assert ignore.is_ignored("blueprints", "_ocean_kafka") is True
        assert ignore.is_ignored("blueprints", "_ocean_pagerduty") is True

    def test_is_ignored_no_match(self) -> None:
        """Non-matching pattern returns False."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_ocean_*", resource_type="blueprints")]
        )
        assert ignore.is_ignored("blueprints", "service") is False

    def test_is_ignored_type_mismatch(self) -> None:
        """Pattern with resource_type does not match other types."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_ocean_*", resource_type="blueprints")]
        )
        assert ignore.is_ignored("scorecards", "_ocean_kafka") is False

    def test_is_ignored_negation_overrides(self) -> None:
        """Negation rule un-ignores a previously matched resource."""
        ignore = IgnoreFilter(
            rules=[
                IgnoreRule(pattern="_ocean_*", resource_type="blueprints"),
                IgnoreRule(
                    pattern="_ocean_kafka", resource_type="blueprints", negated=True
                ),
            ]
        )
        assert ignore.is_ignored("blueprints", "_ocean_kafka") is False
        assert ignore.is_ignored("blueprints", "_ocean_pagerduty") is True

    def test_is_ignored_last_rule_wins(self) -> None:
        """Later rules override earlier ones (like .gitignore)."""
        ignore = IgnoreFilter(
            rules=[
                IgnoreRule(pattern="_ocean_*", resource_type="blueprints"),
                IgnoreRule(
                    pattern="_ocean_kafka", resource_type="blueprints", negated=True
                ),
                # Re-ignore kafka specifically
                IgnoreRule(pattern="_ocean_kafka", resource_type="blueprints"),
            ]
        )
        assert ignore.is_ignored("blueprints", "_ocean_kafka") is True

    def test_is_ignored_unslashed_matches_any_type(self) -> None:
        """Pattern without resource_type matches across all types."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_internal_*", resource_type=None)]
        )
        assert ignore.is_ignored("blueprints", "_internal_system") is True
        assert ignore.is_ignored("scorecards", "_internal_metrics") is True
        assert ignore.is_ignored("actions", "_internal_hook") is True

    def test_is_ignored_empty_rules(self) -> None:
        """Empty filter never ignores anything."""
        ignore = IgnoreFilter(rules=[])
        assert ignore.is_ignored("blueprints", "service") is False

    def test_is_ignored_question_mark_glob(self) -> None:
        """? glob matches single character."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="svc-?", resource_type="blueprints")]
        )
        assert ignore.is_ignored("blueprints", "svc-a") is True
        assert ignore.is_ignored("blueprints", "svc-ab") is False

    def test_is_ignored_bracket_glob(self) -> None:
        """[seq] glob matches character set."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="env-[123]", resource_type="blueprints")]
        )
        assert ignore.is_ignored("blueprints", "env-1") is True
        assert ignore.is_ignored("blueprints", "env-4") is False


class TestIgnoreFilterFilterIdentifiers:
    """Tests for IgnoreFilter.filter_identifiers method."""

    def test_filter_identifiers(self) -> None:
        """Returns only non-ignored identifiers."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_ocean_*", resource_type="blueprints")]
        )
        identifiers = ["service", "_ocean_kafka", "environment", "_ocean_pagerduty"]
        result = ignore.filter_identifiers("blueprints", identifiers)
        assert result == ["service", "environment"]

    def test_filter_identifiers_empty_input(self) -> None:
        """Empty input returns empty list."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_*", resource_type="blueprints")]
        )
        assert ignore.filter_identifiers("blueprints", []) == []

    def test_filter_identifiers_nothing_ignored(self) -> None:
        """When nothing matches, all identifiers are returned."""
        ignore = IgnoreFilter(
            rules=[IgnoreRule(pattern="_ocean_*", resource_type="blueprints")]
        )
        identifiers = ["service", "environment"]
        assert ignore.filter_identifiers("blueprints", identifiers) == identifiers


class TestLoadIgnoreFilter:
    """Tests for load_ignore_filter function."""

    def test_load_ignore_filter_missing_file(self, tmp_path: Path) -> None:
        """Returns empty filter when .portctlignore does not exist."""
        ignore = load_ignore_filter(tmp_path)
        assert ignore.rules == []

    def test_load_ignore_filter_existing_file(self, tmp_path: Path) -> None:
        """Reads and parses .portctlignore file."""
        ignore_file = tmp_path / ".portctlignore"
        ignore_file.write_text(
            "# Ignore ocean blueprints\nblueprints/_ocean_*\n!blueprints/_ocean_kafka\n"
        )
        ignore = load_ignore_filter(tmp_path)
        assert len(ignore.rules) == 2
        assert ignore.is_ignored("blueprints", "_ocean_pagerduty") is True
        assert ignore.is_ignored("blueprints", "_ocean_kafka") is False

    def test_load_ignore_filter_empty_file(self, tmp_path: Path) -> None:
        """Empty file returns empty filter."""
        ignore_file = tmp_path / ".portctlignore"
        ignore_file.write_text("")
        ignore = load_ignore_filter(tmp_path)
        assert ignore.rules == []
