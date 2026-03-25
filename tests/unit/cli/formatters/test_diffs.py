"""Tests for plan/diff output formatting helpers."""

from __future__ import annotations

from typing import Any

from portctl.cli.formatters.diffs import _build_change_lines, _build_dict_sub_diff


class TestBuildDictSubDiff:
    """Tests for _build_dict_sub_diff field-level sub-diff."""

    def test_changed_field_shows_tilde_prefix(self) -> None:
        """A changed field shows ~ prefix with old -> new values."""
        old: dict[str, Any] = {"title": "Old Title", "level": "Bronze"}
        new: dict[str, Any] = {"title": "New Title", "level": "Bronze"}

        lines = _build_dict_sub_diff("rules[0]", old, new)

        change_lines = [(text, style) for text, style in lines if style == "yellow"]
        assert len(change_lines) == 1
        text, _ = change_lines[0]
        assert "~ title:" in text
        assert "Old Title" in text
        assert "New Title" in text

    def test_added_field_shows_plus_prefix(self) -> None:
        """An added field shows + prefix."""
        old: dict[str, Any] = {"title": "Rule"}
        new: dict[str, Any] = {"title": "Rule", "description": "A rule"}

        lines = _build_dict_sub_diff("rules[0]", old, new)

        added_lines = [(text, style) for text, style in lines if style == "green"]
        assert len(added_lines) == 1
        text, _ = added_lines[0]
        assert "+ description:" in text
        assert "A rule" in text

    def test_removed_field_shows_minus_prefix(self) -> None:
        """A removed field shows - prefix."""
        old: dict[str, Any] = {"title": "Rule", "deprecated": True}
        new: dict[str, Any] = {"title": "Rule"}

        lines = _build_dict_sub_diff("rules[0]", old, new)

        removed_lines = [(text, style) for text, style in lines if style == "red"]
        assert len(removed_lines) == 1
        text, _ = removed_lines[0]
        assert "- deprecated" in text

    def test_identical_dicts_return_empty_list(self) -> None:
        """Identical dicts return empty list (no real change)."""
        data: dict[str, Any] = {"title": "Rule", "level": "Gold"}

        lines = _build_dict_sub_diff("rules[0]", data, dict(data))

        assert lines == []

    def test_label_extracted_from_identifier(self) -> None:
        """Label is extracted from identifier field in the header."""
        old: dict[str, Any] = {"identifier": "my-rule", "title": "Old"}
        new: dict[str, Any] = {"identifier": "my-rule", "title": "New"}

        lines = _build_dict_sub_diff("rules[0]", old, new)

        header_text, header_style = lines[0]
        assert header_style == "bold"
        assert "my-rule" in header_text
        assert "rules[0]" in header_text

    def test_multiple_changes_in_one_dict(self) -> None:
        """Multiple changes in one dict are all captured."""
        old: dict[str, Any] = {"title": "Old", "level": "Bronze", "extra": "val"}
        new: dict[str, Any] = {"title": "New", "level": "Gold", "added": "field"}

        lines = _build_dict_sub_diff("rules[0]", old, new)

        yellow_lines = [t for t, s in lines if s == "yellow"]
        green_lines = [t for t, s in lines if s == "green"]
        red_lines = [t for t, s in lines if s == "red"]
        # title and level changed
        assert len(yellow_lines) == 2
        # 'added' is new
        assert len(green_lines) == 1
        # 'extra' was removed
        assert len(red_lines) == 1


class TestBuildChangeLinesWithDicts:
    """Tests for _build_change_lines when values_changed contains dict values."""

    def test_dict_values_use_sub_diff(self) -> None:
        """When old and new values are both dicts, _build_change_lines delegates to sub-diff."""
        diff: dict[str, Any] = {
            "values_changed": {
                "root['rules'][0]": {
                    "old_value": {
                        "identifier": "has-owner",
                        "title": "Has Owner",
                        "level": "Bronze",
                    },
                    "new_value": {
                        "identifier": "has-owner",
                        "title": "Has Owner",
                        "level": "Gold",
                    },
                },
            },
        }

        text = _build_change_lines(diff)
        rendered = text.plain

        # Should show the sub-diff detail, not the full dict blob
        assert "level:" in rendered
        assert "Bronze" in rendered
        assert "Gold" in rendered

    def test_scalar_values_shown_inline(self) -> None:
        """Scalar value changes are shown inline with arrow notation."""
        diff: dict[str, Any] = {
            "values_changed": {
                "root['title']": {
                    "old_value": "Old Title",
                    "new_value": "New Title",
                },
            },
        }

        text = _build_change_lines(diff)
        rendered = text.plain

        assert "title:" in rendered
        assert "Old Title" in rendered
        assert "New Title" in rendered
