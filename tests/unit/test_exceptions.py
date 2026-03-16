"""Tests for portctl exception hierarchy."""

from __future__ import annotations

import pytest

from portctl.exceptions import (
    AuthError,
    ConfigError,
    LockError,
    PortAPIError,
    PortctlError,
    ValidationError,
)


class TestPortctlError:
    """Tests for the base PortctlError."""

    def test_is_exception(self) -> None:
        assert issubclass(PortctlError, Exception)

    def test_can_raise_and_catch(self) -> None:
        with pytest.raises(PortctlError, match="something went wrong"):
            raise PortctlError("something went wrong")


class TestPortAPIError:
    """Tests for PortAPIError with status_code and detail."""

    def test_inherits_from_portctl_error(self) -> None:
        assert issubclass(PortAPIError, PortctlError)

    def test_stores_status_code_and_detail(self) -> None:
        err = PortAPIError(status_code=404, detail="Blueprint not found")
        assert err.status_code == 404
        assert err.detail == "Blueprint not found"

    def test_optional_resource(self) -> None:
        err = PortAPIError(status_code=500, detail="Internal error", resource="blueprint/svc")
        assert err.resource == "blueprint/svc"

    def test_resource_defaults_to_none(self) -> None:
        err = PortAPIError(status_code=400, detail="Bad request")
        assert err.resource is None

    def test_str_includes_status_and_detail(self) -> None:
        err = PortAPIError(status_code=403, detail="Forbidden")
        assert "403" in str(err)
        assert "Forbidden" in str(err)

    def test_catchable_as_portctl_error(self) -> None:
        with pytest.raises(PortctlError):
            raise PortAPIError(status_code=500, detail="Server error")


class TestConfigError:
    """Tests for ConfigError."""

    def test_inherits_from_portctl_error(self) -> None:
        assert issubclass(ConfigError, PortctlError)

    def test_can_raise_with_message(self) -> None:
        with pytest.raises(ConfigError, match="config not found"):
            raise ConfigError("config not found")


class TestValidationError:
    """Tests for ValidationError with errors list."""

    def test_inherits_from_portctl_error(self) -> None:
        assert issubclass(ValidationError, PortctlError)

    def test_stores_errors_list(self) -> None:
        errors = ["missing field: title", "invalid type for: schema"]
        err = ValidationError(errors=errors)
        assert err.errors == errors

    def test_empty_errors_list(self) -> None:
        err = ValidationError(errors=[])
        assert err.errors == []

    def test_str_includes_error_count(self) -> None:
        err = ValidationError(errors=["err1", "err2"])
        err_str = str(err)
        assert "2" in err_str


class TestLockError:
    """Tests for LockError."""

    def test_inherits_from_portctl_error(self) -> None:
        assert issubclass(LockError, PortctlError)

    def test_can_raise_with_message(self) -> None:
        with pytest.raises(LockError, match="lock held by"):
            raise LockError("lock held by user@example.com")


class TestAuthError:
    """Tests for AuthError."""

    def test_inherits_from_portctl_error(self) -> None:
        assert issubclass(AuthError, PortctlError)

    def test_can_raise_with_message(self) -> None:
        with pytest.raises(AuthError, match="invalid credentials"):
            raise AuthError("invalid credentials")

    def test_catchable_as_portctl_error(self) -> None:
        with pytest.raises(PortctlError):
            raise AuthError("expired token")
