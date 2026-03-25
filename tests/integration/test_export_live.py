"""Integration tests for the export service against the live Port.io API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ruamel.yaml import YAML

from portctl.services.exporter import export_blueprints

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient

pytestmark = pytest.mark.integration


class TestExportBlueprints:
    """Verify export_blueprints writes YAML files from live data."""

    async def test_export_blueprints_creates_files(
        self, port_client: PortClient, tmp_path: Path
    ) -> None:
        """Exported blueprint identifiers should each have a corresponding YAML file."""
        exported = await export_blueprints(port_client, tmp_path)

        # The org may have zero user blueprints -- that's OK, but we still
        # verify the contract: every returned identifier has a file on disk.
        for identifier in exported:
            yaml_path = tmp_path / "blueprints" / f"{identifier}.yaml"
            assert yaml_path.exists(), f"Expected YAML file for blueprint '{identifier}'"

    async def test_export_blueprints_returns_list(
        self, port_client: PortClient, tmp_path: Path
    ) -> None:
        """export_blueprints should return a list of strings."""
        exported = await export_blueprints(port_client, tmp_path)

        assert isinstance(exported, list)
        for item in exported:
            assert isinstance(item, str)

    async def test_export_skips_internal_blueprints(
        self, port_client: PortClient, tmp_path: Path
    ) -> None:
        """Exported identifiers must not start with _ or $."""
        exported = await export_blueprints(port_client, tmp_path)

        for identifier in exported:
            assert not identifier.startswith("_"), (
                f"Internal blueprint exported: {identifier}"
            )
            assert not identifier.startswith("$"), (
                f"System blueprint exported: {identifier}"
            )


class TestExportRoundtripStructure:
    """Verify the YAML files produced by export have the expected structure."""

    async def test_blueprint_yaml_has_required_keys(
        self, port_client: PortClient, tmp_path: Path
    ) -> None:
        """Each exported YAML should contain at least 'identifier' and 'title'."""
        exported = await export_blueprints(port_client, tmp_path)
        if not exported:
            pytest.skip("No user blueprints in this Port org -- nothing to validate")

        yml = YAML()
        for identifier in exported:
            yaml_path = tmp_path / "blueprints" / f"{identifier}.yaml"
            with yaml_path.open(encoding="utf-8") as fh:
                data = yml.load(fh)

            assert isinstance(data, dict), f"Expected dict in {yaml_path}"
            assert "identifier" in data, f"Missing 'identifier' in {yaml_path}"
            assert "title" in data, f"Missing 'title' in {yaml_path}"
            assert data["identifier"] == identifier

    async def test_blueprint_yaml_is_valid_yaml(
        self, port_client: PortClient, tmp_path: Path
    ) -> None:
        """Every exported file should be parseable YAML."""
        exported = await export_blueprints(port_client, tmp_path)
        if not exported:
            pytest.skip("No user blueprints in this Port org -- nothing to validate")

        yml = YAML()
        for identifier in exported:
            yaml_path = tmp_path / "blueprints" / f"{identifier}.yaml"
            with yaml_path.open(encoding="utf-8") as fh:
                data = yml.load(fh)
            assert data is not None, f"Empty YAML in {yaml_path}"
