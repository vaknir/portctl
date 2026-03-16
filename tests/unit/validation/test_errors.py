"""Tests for validation error types."""

from __future__ import annotations

from portctl.validation.errors import ValidationIssue, ValidationResult


class TestValidationResult:
    """Tests for ValidationResult error collection."""

    def test_validation_result_has_errors(self) -> None:
        result = ValidationResult()
        assert result.has_errors is False

        result.add_error("file.yaml", "missing field")
        assert result.has_errors is True

    def test_validation_result_error_count(self) -> None:
        result = ValidationResult()
        assert result.error_count == 0

        result.add_error("a.yaml", "err1")
        result.add_error("b.yaml", "err2")
        result.add_warning("c.yaml", "warn1")
        assert result.error_count == 2

    def test_add_error_and_warning(self) -> None:
        result = ValidationResult()
        result.add_error("file.yaml", "bad field", line=5, suggestion="use 'title'")
        result.add_warning("file.yaml", "deprecated key", line=10)

        assert len(result.issues) == 2

        error = result.issues[0]
        assert isinstance(error, ValidationIssue)
        assert error.file_path == "file.yaml"
        assert error.line == 5
        assert error.message == "bad field"
        assert error.severity == "error"
        assert error.suggestion == "use 'title'"

        warning = result.issues[1]
        assert warning.severity == "warning"
        assert warning.line == 10
        assert warning.suggestion is None
