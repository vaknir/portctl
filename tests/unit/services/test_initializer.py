"""Tests for the project initializer service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from portctl.exceptions import ConfigError
from portctl.services.initializer import (
    InitOptions,
    InitResult,
    generate_ci_workflow,
    generate_ignore_file,
    init_project,
    scaffold_templates,
    write_config_file,
    write_project_state,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestWriteConfigFile:
    """Tests for write_config_file."""

    def test_write_config_file(self, tmp_path: Path) -> None:
        """Creates a valid YAML config file with the org entry."""
        config_dir = tmp_path / ".portctl"
        config_dir.mkdir()
        path = write_config_file(config_dir, "my-org", "https://api.getport.io/v1")

        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert data["default_org"] == "my-org"
        assert "my-org" in data["orgs"]
        assert data["orgs"]["my-org"]["name"] == "my-org"
        assert data["orgs"]["my-org"]["api_url"] == "https://api.getport.io/v1"

    def test_write_config_file_no_credentials(self, tmp_path: Path) -> None:
        """Config file does not contain any inline secrets."""
        config_dir = tmp_path / ".portctl"
        config_dir.mkdir()
        path = write_config_file(config_dir, "my-org", "https://api.getport.io/v1")

        raw = path.read_text()
        data = yaml.safe_load(raw)
        org = data["orgs"]["my-org"]
        # Credentials should use env var placeholders, not real values
        assert org["client_id"] == "${PORT_CLIENT_ID}"
        assert org["client_secret"] == "${PORT_CLIENT_SECRET}"

    def test_write_config_file_creates_directory(self, tmp_path: Path) -> None:
        """Creates the config directory if it does not exist."""
        config_dir = tmp_path / ".portctl"
        # Do NOT create config_dir -- the function should create it
        path = write_config_file(config_dir, "my-org", "https://api.getport.io/v1")
        assert path.exists()
        assert config_dir.exists()


class TestWriteProjectState:
    """Tests for write_project_state."""

    def test_write_project_state(self, tmp_path: Path) -> None:
        """Creates .portctl-state.yaml with valid initial structure."""
        path = write_project_state(tmp_path)

        assert path.exists()
        assert path.name == ".portctl-state.yaml"
        data = yaml.safe_load(path.read_text())
        assert data is not None
        assert "version" in data
        assert "resources" in data


class TestScaffoldTemplates:
    """Tests for scaffold_templates."""

    def test_scaffold_templates(self, tmp_path: Path) -> None:
        """Creates expected template files with valid YAML."""
        created = scaffold_templates(tmp_path)

        assert len(created) > 0
        for rel_path in created:
            full_path = tmp_path / rel_path
            assert full_path.exists(), f"Expected file not created: {rel_path}"
            # All template files should be valid YAML
            data = yaml.safe_load(full_path.read_text())
            assert isinstance(data, dict), f"Template is not a YAML mapping: {rel_path}"

    def test_scaffold_templates_creates_directories(self, tmp_path: Path) -> None:
        """Creates blueprints/ and scorecards/ subdirectories."""
        scaffold_templates(tmp_path)

        assert (tmp_path / "blueprints").is_dir()
        assert (tmp_path / "scorecards").is_dir()

    def test_scaffold_templates_expected_files(self, tmp_path: Path) -> None:
        """Scaffolds the specific expected template files."""
        created = scaffold_templates(tmp_path)

        # Should have 3 blueprints and 1 scorecard
        bp_files = [f for f in created if f.startswith("blueprints/")]
        sc_files = [f for f in created if f.startswith("scorecards/")]
        assert len(bp_files) == 3
        assert len(sc_files) == 1


class TestGenerateCiWorkflow:
    """Tests for generate_ci_workflow."""

    def test_generate_ci_workflow_github(self, tmp_path: Path) -> None:
        """Creates .github/workflows/portctl.yml for GitHub."""
        path = generate_ci_workflow(tmp_path, "my-org", provider="github")

        assert path.exists()
        assert path == tmp_path / ".github" / "workflows" / "portctl.yml"

    def test_generate_ci_workflow_has_org_name(self, tmp_path: Path) -> None:
        """Workflow file contains the org name in commands."""
        path = generate_ci_workflow(tmp_path, "acme-prod", provider="github")

        content = path.read_text()
        assert "acme-prod" in content

    def test_generate_ci_workflow_valid_yaml(self, tmp_path: Path) -> None:
        """Generated workflow file is valid YAML."""
        path = generate_ci_workflow(tmp_path, "my-org", provider="github")

        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict)
        assert "jobs" in data


class TestGenerateIgnoreFile:
    """Tests for generate_ignore_file."""

    def test_generate_ignore_file(self, tmp_path: Path) -> None:
        """Creates .portctlignore with default ignore rules."""
        path = generate_ignore_file(tmp_path)

        assert path.exists()
        assert path.name == ".portctlignore"
        content = path.read_text()
        assert "blueprints/_*" in content
        assert "blueprints/$*" in content


class TestInitProject:
    """Tests for init_project (async orchestrator)."""

    @pytest.mark.asyncio()
    async def test_init_project_fresh_mode(self, tmp_path: Path) -> None:
        """Fresh mode scaffolds templates without running export."""
        config_dir = tmp_path / "config"
        options = InitOptions(
            org_name="my-org",
            mode="fresh",
            project_dir=tmp_path,
            config_dir=config_dir,
        )

        result = await init_project(options)

        assert isinstance(result, InitResult)
        assert result.config_path.exists()
        assert result.state_path.exists()
        assert result.exported_resources == 0
        assert len(result.scaffolded_templates) > 0
        assert len(result.files_created) > 0

    @pytest.mark.asyncio()
    async def test_init_project_existing_mode(self, tmp_path: Path) -> None:
        """Existing mode runs export (mocked) instead of scaffolding templates."""
        config_dir = tmp_path / "config"
        options = InitOptions(
            org_name="my-org",
            mode="existing",
            client_id="test-id",
            client_secret="test-secret",
            project_dir=tmp_path,
            config_dir=config_dir,
        )

        mock_export = AsyncMock(return_value={"blueprints": 3, "scorecards": 2})

        # Build a mock that works as: async with PortClient(...) as client
        mock_client_instance = AsyncMock()
        mock_client_ctx = MagicMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls = MagicMock(return_value=mock_client_ctx)

        with (
            patch("portctl.services.exporter.export_all", mock_export),
            patch("portctl.client.port_client.PortClient", mock_client_cls),
        ):
            result = await init_project(options)

        assert result.exported_resources == 5  # 3 + 2
        assert result.scaffolded_templates == []
        mock_export.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_init_project_refuses_existing_config(self, tmp_path: Path) -> None:
        """Raises ConfigError if config file already exists."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text("existing: true")

        options = InitOptions(
            org_name="my-org",
            mode="fresh",
            project_dir=tmp_path,
            config_dir=config_dir,
        )

        with pytest.raises(ConfigError, match="already exists"):
            await init_project(options)

    @pytest.mark.asyncio()
    async def test_init_project_no_ci(self, tmp_path: Path) -> None:
        """When generate_ci is False, no CI workflow is created."""
        config_dir = tmp_path / "config"
        options = InitOptions(
            org_name="my-org",
            mode="fresh",
            project_dir=tmp_path,
            config_dir=config_dir,
            generate_ci=False,
        )

        result = await init_project(options)

        assert result.ci_workflow_path is None

    @pytest.mark.asyncio()
    async def test_init_project_no_ignore(self, tmp_path: Path) -> None:
        """When generate_ignore is False, no .portctlignore is created."""
        config_dir = tmp_path / "config"
        options = InitOptions(
            org_name="my-org",
            mode="fresh",
            project_dir=tmp_path,
            config_dir=config_dir,
            generate_ignore=False,
        )

        result = await init_project(options)

        assert result.ignore_path is None
