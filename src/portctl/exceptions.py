"""Custom exception hierarchy for portctl."""

from __future__ import annotations


class PortctlError(Exception):
    """Base exception for all portctl errors."""


class PortAPIError(PortctlError):
    """Port API returned an error (4xx/5xx)."""

    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        resource: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.resource = resource
        super().__init__(f"Port API error {status_code}: {detail}")


class ConfigError(PortctlError):
    """Configuration file is missing, malformed, or invalid."""


class ValidationError(PortctlError):
    """YAML validation failed (Layer 1 or Layer 2)."""

    def __init__(self, *, errors: list[str]) -> None:
        self.errors = errors
        count = len(errors)
        super().__init__(f"Validation failed with {count} error(s)")


class LockError(PortctlError):
    """Lock acquisition or release failed."""


class AuthError(PortctlError):
    """Authentication failed -- bad credentials or expired token."""
