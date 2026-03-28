"""Tests for config loader service."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from portctl.exceptions import ConfigError
from portctl.services.config import ensure_org, get_org, load_config, resolve_env_vars

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def valid_config_yaml() -> dict[str, object]:
    """Return a valid config dict for serialization to YAML."""
    return {
        "default_org": "prod",
        "orgs": {
            "prod": {
                "name": "Production",
                "client_id": "prod-id-123",
                "client_secret": "prod-secret-456",
                "role": "production",
                "api_url": "https://api.getport.io/v1",
            },
            "dev": {
                "name": "Development",
                "client_id": "dev-id-789",
                "client_secret": "dev-secret-012",
                "role": "development",
            },
        },
    }


@pytest.fixture()
def config_file(tmp_path: Path, valid_config_yaml: dict[str, object]) -> Path:
    """Write a valid config YAML file and return its path."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(valid_config_yaml))
    return path


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_valid(self, config_file: Path) -> None:
        """Loads and parses a valid config file."""
        config = load_config(path=config_file)
        assert config.default_org == "prod"
        assert "prod" in config.orgs
        assert "dev" in config.orgs
        assert config.orgs["prod"].name == "Production"
        assert config.orgs["prod"].client_id == "prod-id-123"
        assert config.orgs["prod"].role == "production"
        assert config.orgs["dev"].role == "development"

    def test_load_config_missing_file(self, tmp_path: Path) -> None:
        """Raises ConfigError when the config file does not exist."""
        missing = tmp_path / "nonexistent.yaml"
        with pytest.raises(ConfigError, match="not found"):
            load_config(path=missing)

    def test_load_config_invalid_yaml(self, tmp_path: Path) -> None:
        """Raises ConfigError for unparseable YAML."""
        bad_file = tmp_path / "config.yaml"
        bad_file.write_text("{ invalid yaml: [unterminated")
        with pytest.raises(ConfigError, match="[Pp]arse|[Ii]nvalid YAML"):
            load_config(path=bad_file)

    def test_load_config_missing_required_fields(self, tmp_path: Path) -> None:
        """Raises ConfigError when required fields are missing from config."""
        incomplete = tmp_path / "config.yaml"
        incomplete.write_text(yaml.dump({"default_org": "prod"}))
        with pytest.raises(ConfigError, match="[Vv]alidation|[Ii]nvalid"):
            load_config(path=incomplete)

    def test_load_config_with_env_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Resolves ${VAR} patterns in string values during load."""
        monkeypatch.setenv("PORT_CLIENT_ID", "env-id-resolved")
        monkeypatch.setenv("PORT_CLIENT_SECRET", "env-secret-resolved")
        config_data = {
            "default_org": "prod",
            "orgs": {
                "prod": {
                    "name": "Production",
                    "client_id": "${PORT_CLIENT_ID}",
                    "client_secret": "${PORT_CLIENT_SECRET}",
                    "role": "production",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))
        config = load_config(path=path)
        assert config.orgs["prod"].client_id == "env-id-resolved"
        assert config.orgs["prod"].client_secret == "env-secret-resolved"

    def test_load_config_default_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Uses ~/.portctl/config.yaml when no path given."""
        config_dir = tmp_path / ".portctl"
        config_dir.mkdir()
        config_path = config_dir / "config.yaml"
        config_data = {
            "orgs": {
                "dev": {
                    "name": "Dev",
                    "client_id": "id",
                    "client_secret": "secret",
                },
            },
        }
        config_path.write_text(yaml.dump(config_data))
        monkeypatch.setattr("portctl.services.config.CONFIG_FILE", config_path)
        config = load_config()
        assert "dev" in config.orgs


class TestResolveEnvVars:
    """Tests for resolve_env_vars function."""

    def test_resolve_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replaces ${VAR} with the environment variable value."""
        monkeypatch.setenv("MY_VAR", "hello")
        assert resolve_env_vars("${MY_VAR}") == "hello"

    def test_resolve_env_vars_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ConfigError for unset environment variables."""
        monkeypatch.delenv("UNSET_VAR_XYZ", raising=False)
        with pytest.raises(ConfigError, match="UNSET_VAR_XYZ"):
            resolve_env_vars("${UNSET_VAR_XYZ}")

    def test_resolve_env_vars_no_vars(self) -> None:
        """Returns the string unchanged when it has no ${} patterns."""
        assert resolve_env_vars("plain string") == "plain string"

    def test_resolve_env_vars_multiple(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handles multiple ${VAR} patterns in a single string."""
        monkeypatch.setenv("HOST", "localhost")
        monkeypatch.setenv("PORT", "8080")
        result = resolve_env_vars("http://${HOST}:${PORT}/api")
        assert result == "http://localhost:8080/api"

    def test_resolve_env_vars_embedded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Handles ${VAR} embedded in surrounding text."""
        monkeypatch.setenv("TOKEN", "abc123")
        result = resolve_env_vars("Bearer ${TOKEN}")
        assert result == "Bearer abc123"


class TestGetOrg:
    """Tests for get_org function."""

    def test_get_org_by_name(self, config_file: Path) -> None:
        """Returns the named org configuration."""
        config = load_config(path=config_file)
        org = get_org(config, name="dev")
        assert org.name == "Development"
        assert org.client_id == "dev-id-789"

    def test_get_org_default(self, config_file: Path) -> None:
        """Returns the default org when no name is given."""
        config = load_config(path=config_file)
        org = get_org(config)
        assert org.name == "Production"

    def test_get_org_not_found(self, config_file: Path) -> None:
        """Raises ConfigError when the named org does not exist."""
        config = load_config(path=config_file)
        with pytest.raises(ConfigError, match="nonexistent"):
            get_org(config, name="nonexistent")

    def test_get_org_no_default(self, tmp_path: Path) -> None:
        """Raises ConfigError when no default is set and no name is given."""
        config_data = {
            "orgs": {
                "dev": {
                    "name": "Dev",
                    "client_id": "id",
                    "client_secret": "secret",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))
        config = load_config(path=path)
        with pytest.raises(ConfigError, match="[Nn]o default"):
            get_org(config)


class TestEnsureOrg:
    """Tests for ensure_org function."""

    def test_ensure_org_does_not_overwrite_existing_default(self, tmp_path: Path) -> None:
        """Does not overwrite existing default_org when set_default is False."""
        config_data = {
            "default_org": "prod",
            "orgs": {
                "prod": {
                    "name": "Production",
                    "client_id": "prod-id",
                    "client_secret": "prod-secret",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))

        config = ensure_org("staging", path=path)

        assert config.default_org == "prod"
        assert "staging" in config.orgs
        assert config.orgs["staging"].name == "staging"

    def test_ensure_org_sets_default_when_none(self, tmp_path: Path) -> None:
        """Sets the new org as default when no default_org is set."""
        config_data = {
            "orgs": {
                "dev": {
                    "name": "Development",
                    "client_id": "dev-id",
                    "client_secret": "dev-secret",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))

        config = ensure_org("prod", path=path)

        assert config.default_org == "prod"
        assert "prod" in config.orgs

    def test_ensure_org_set_default_flag_overrides(self, tmp_path: Path) -> None:
        """Overrides existing default_org when set_default=True."""
        config_data = {
            "default_org": "prod",
            "orgs": {
                "prod": {
                    "name": "Production",
                    "client_id": "prod-id",
                    "client_secret": "prod-secret",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))

        config = ensure_org("staging", set_default=True, path=path)

        assert config.default_org == "staging"
        assert "staging" in config.orgs
        assert "prod" in config.orgs

    def test_ensure_org_adds_new_org(self, tmp_path: Path) -> None:
        """Adds a new org to an existing config."""
        config_data = {
            "default_org": "prod",
            "orgs": {
                "prod": {
                    "name": "Production",
                    "client_id": "prod-id",
                    "client_secret": "prod-secret",
                },
            },
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config_data))

        config = ensure_org(
            "new-org",
            client_id="new-id",
            client_secret="new-secret",
            path=path,
        )

        assert "new-org" in config.orgs
        assert config.orgs["new-org"].client_id == "new-id"
        assert config.orgs["new-org"].client_secret == "new-secret"

    def test_ensure_org_creates_config_if_missing(self, tmp_path: Path) -> None:
        """Creates a new config file if it does not exist."""
        path = tmp_path / "missing.yaml"
        assert not path.exists()

        config = ensure_org(
            "fresh",
            client_id="fresh-id",
            client_secret="fresh-secret",
            path=path,
        )

        assert path.exists()
        assert config.default_org == "fresh"
        assert "fresh" in config.orgs
        assert config.orgs["fresh"].client_id == "fresh-id"

        # Verify file was actually saved by reloading it
        reloaded = load_config(path=path)
        assert reloaded.default_org == "fresh"
        assert reloaded.orgs["fresh"].client_id == "fresh-id"
