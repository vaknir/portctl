"""Tests for whoami service -- identity and environment detection."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from portctl.models.config import OrgConfig, PortctlConfig

if TYPE_CHECKING:
    import pytest

KEYRING_MODULE = "portctl.services.whoami.keyring"


def _make_config(
    *,
    org_name: str = "prod",
    client_id: str = "cfg-id",
    client_secret: str = "cfg-secret",
    role: str = "production",
    api_url: str = "https://api.getport.io/v1",
) -> PortctlConfig:
    """Create a PortctlConfig with a single org for testing."""
    return PortctlConfig(
        default_org=org_name,
        orgs={
            org_name: OrgConfig(
                name="Production",
                client_id=client_id,
                client_secret=client_secret,
                role=role,
                api_url=api_url,
            ),
        },
    )


class TestDetectCiEnvironment:
    """Tests for detect_ci_environment function."""

    def test_detect_ci_github_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GITHUB_ACTIONS=true returns (True, 'github-actions')."""
        from portctl.services.whoami import detect_ci_environment

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("BUILDKITE", raising=False)
        monkeypatch.delenv("TRAVIS", raising=False)
        monkeypatch.delenv("CI", raising=False)

        is_ci, provider = detect_ci_environment()

        assert is_ci is True
        assert provider == "github-actions"

    def test_detect_ci_gitlab(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GITLAB_CI=true returns (True, 'gitlab-ci')."""
        from portctl.services.whoami import detect_ci_environment

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv("GITLAB_CI", "true")
        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("BUILDKITE", raising=False)
        monkeypatch.delenv("TRAVIS", raising=False)
        monkeypatch.delenv("CI", raising=False)

        is_ci, provider = detect_ci_environment()

        assert is_ci is True
        assert provider == "gitlab-ci"

    def test_detect_ci_jenkins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JENKINS_URL set returns (True, 'jenkins')."""
        from portctl.services.whoami import detect_ci_environment

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.setenv("JENKINS_URL", "https://jenkins.example.com")
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("BUILDKITE", raising=False)
        monkeypatch.delenv("TRAVIS", raising=False)
        monkeypatch.delenv("CI", raising=False)

        is_ci, provider = detect_ci_environment()

        assert is_ci is True
        assert provider == "jenkins"

    def test_detect_ci_generic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI=true with no specific provider returns (True, 'ci')."""
        from portctl.services.whoami import detect_ci_environment

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("BUILDKITE", raising=False)
        monkeypatch.delenv("TRAVIS", raising=False)
        monkeypatch.setenv("CI", "true")

        is_ci, provider = detect_ci_environment()

        assert is_ci is True
        assert provider == "ci"

    def test_detect_ci_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No CI env vars returns (False, None)."""
        from portctl.services.whoami import detect_ci_environment

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        monkeypatch.delenv("JENKINS_URL", raising=False)
        monkeypatch.delenv("CIRCLECI", raising=False)
        monkeypatch.delenv("BUILDKITE", raising=False)
        monkeypatch.delenv("TRAVIS", raising=False)
        monkeypatch.delenv("CI", raising=False)

        is_ci, provider = detect_ci_environment()

        assert is_ci is False
        assert provider is None


class TestDetectCredentialSource:
    """Tests for detect_credential_source function."""

    @patch(KEYRING_MODULE)
    def test_detect_credential_source_env(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns 'env' when PORT_CLIENT_ID and PORT_CLIENT_SECRET are set."""
        from portctl.services.whoami import detect_credential_source

        monkeypatch.setenv("PORT_CLIENT_ID", "env-id")
        monkeypatch.setenv("PORT_CLIENT_SECRET", "env-secret")

        config = _make_config()
        result = detect_credential_source("prod", config)

        assert result == "env"

    @patch(KEYRING_MODULE)
    def test_detect_credential_source_keyring(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns 'keyring' when credentials are in OS keyring."""
        from portctl.services.whoami import detect_credential_source

        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.side_effect = lambda service, _user: {
            "portctl:prod:client_id": "kr-id",
            "portctl:prod:client_secret": "kr-secret",
        }.get(service)

        config = _make_config()
        result = detect_credential_source("prod", config)

        assert result == "keyring"

    @patch(KEYRING_MODULE)
    def test_detect_credential_source_config(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns 'config' when credentials are in config file."""
        from portctl.services.whoami import detect_credential_source

        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.return_value = None

        config = _make_config(client_id="cfg-id", client_secret="cfg-secret")
        result = detect_credential_source("prod", config)

        assert result == "config"

    @patch(KEYRING_MODULE)
    def test_detect_credential_source_none(
        self,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns None when no credentials are found anywhere."""
        from portctl.services.whoami import detect_credential_source

        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.return_value = None

        config = PortctlConfig(default_org=None, orgs={})
        result = detect_credential_source("prod", config)

        assert result is None


class TestGatherWhoamiInfo:
    """Tests for gather_whoami_info function."""

    @patch(KEYRING_MODULE)
    @patch("portctl.services.whoami.load_config")
    @patch("portctl.services.whoami.detect_ci_environment")
    async def test_gather_whoami_info_full(
        self,
        mock_detect_ci: MagicMock,
        mock_load_config: MagicMock,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns complete WhoamiInfo when all config and auth are available."""
        from portctl.services.whoami import gather_whoami_info

        config = _make_config()
        mock_load_config.return_value = config
        mock_detect_ci.return_value = (False, None)
        monkeypatch.setenv("PORT_CLIENT_ID", "env-id")
        monkeypatch.setenv("PORT_CLIENT_SECRET", "env-secret")

        info = await gather_whoami_info(org="prod")

        assert info.org_name == "prod"
        assert info.org_role == "production"
        assert info.api_url == "https://api.getport.io/v1"
        assert info.credential_source == "env"
        assert info.authenticated is True
        assert info.is_ci is False
        assert info.ci_provider is None
        assert info.version is not None

    @patch(KEYRING_MODULE)
    @patch("portctl.services.whoami.load_config")
    @patch("portctl.services.whoami.detect_ci_environment")
    async def test_gather_whoami_info_no_config(
        self,
        mock_detect_ci: MagicMock,
        mock_load_config: MagicMock,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns partial WhoamiInfo when config file is missing."""
        from portctl.exceptions import ConfigError
        from portctl.services.whoami import gather_whoami_info

        mock_load_config.side_effect = ConfigError("Config file not found")
        mock_detect_ci.return_value = (False, None)
        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)

        info = await gather_whoami_info()

        assert info.org_name is None
        assert info.org_role is None
        assert info.authenticated is False
        assert info.version is not None

    @patch(KEYRING_MODULE)
    @patch("portctl.services.whoami.load_config")
    @patch("portctl.services.whoami.detect_ci_environment")
    async def test_gather_whoami_info_no_credentials(
        self,
        mock_detect_ci: MagicMock,
        mock_load_config: MagicMock,
        mock_keyring: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Returns WhoamiInfo with authenticated=False when no credentials found."""
        from portctl.services.whoami import gather_whoami_info

        config = _make_config()
        # Remove creds from config so detect_credential_source returns None
        config.orgs["prod"].client_id = ""
        config.orgs["prod"].client_secret = ""
        mock_load_config.return_value = config
        mock_detect_ci.return_value = (True, "github-actions")
        monkeypatch.delenv("PORT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PORT_CLIENT_SECRET", raising=False)
        mock_keyring.get_password.return_value = None

        info = await gather_whoami_info(org="prod")

        assert info.org_name == "prod"
        assert info.authenticated is False
        assert info.credential_source is None
        assert info.is_ci is True
        assert info.ci_provider == "github-actions"
