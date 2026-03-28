"""Export logic: API -> YAML files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from portctl.models.action import Action
from portctl.models.blueprint import (
    Blueprint,
    BlueprintCalculationProperty,
    BlueprintMirrorProperty,
    BlueprintProperty,
    BlueprintRelation,
)
from portctl.models.page import Page
from portctl.models.scorecard import Scorecard
from portctl.services.ignore import IgnoreFilter, load_ignore_filter

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of an export operation with counts and identifiers.

    Attributes:
        blueprint_ids: List of exported blueprint identifiers.
        scorecard_ids: List of exported scorecard identifiers.
    """

    blueprint_ids: list[str] = field(default_factory=list)
    scorecard_ids: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)
    page_ids: list[str] = field(default_factory=list)

    @property
    def blueprint_count(self) -> int:
        """Number of exported blueprints."""
        return len(self.blueprint_ids)

    @property
    def scorecard_count(self) -> int:
        """Number of exported scorecards."""
        return len(self.scorecard_ids)

    @property
    def action_count(self) -> int:
        """Number of exported actions."""
        return len(self.action_ids)

    @property
    def page_count(self) -> int:
        """Number of exported pages."""
        return len(self.page_ids)

    def to_summary(self) -> dict[str, int]:
        """Return a summary dict for backward compatibility.

        Returns:
            Dict with resource counts.
        """
        return {
            "blueprints": self.blueprint_count,
            "scorecards": self.scorecard_count,
            "actions": self.action_count,
            "pages": self.page_count,
        }


# Prefixes that indicate internal/system blueprints
_INTERNAL_PREFIXES = ("_", "$")


def _is_internal(identifier: str) -> bool:
    """Check if a blueprint identifier is internal/system-generated.

    Args:
        identifier: Blueprint identifier string.

    Returns:
        True if the blueprint should be skipped during export.
    """
    return any(identifier.startswith(prefix) for prefix in _INTERNAL_PREFIXES)


def _map_blueprint(api_data: dict[str, Any]) -> Blueprint:
    """Map a Port API blueprint response to the Blueprint model.

    The API returns properties inside a ``schema`` key with a separate
    ``required`` list. This function normalises that into per-property
    ``required`` flags on the model.

    Args:
        api_data: Raw blueprint dict from the Port API.

    Returns:
        A validated Blueprint model instance.
    """
    schema = api_data.get("schema", {})
    required_props: list[str] = schema.get("required", [])

    properties: dict[str, BlueprintProperty] = {}
    for name, prop_data in schema.get("properties", {}).items():
        mapped = dict(prop_data)
        if name in required_props:
            mapped["required"] = True
        properties[name] = BlueprintProperty(**mapped)

    relations: dict[str, BlueprintRelation] = {}
    for name, rel_data in api_data.get("relations", {}).items():
        relations[name] = BlueprintRelation(**rel_data)

    mirror_properties: dict[str, BlueprintMirrorProperty] = {}
    for name, mp_data in api_data.get("mirrorProperties", {}).items():
        mirror_properties[name] = BlueprintMirrorProperty(**mp_data)

    calculation_properties: dict[str, BlueprintCalculationProperty] = {}
    for name, cp_data in api_data.get("calculationProperties", {}).items():
        calculation_properties[name] = BlueprintCalculationProperty(**cp_data)

    return Blueprint(
        identifier=api_data["identifier"],
        title=api_data["title"],
        icon=api_data.get("icon"),
        description=api_data.get("description"),
        properties=properties,
        relations=relations,
        mirror_properties=mirror_properties,
        calculation_properties=calculation_properties,
    )


def _map_scorecard(api_data: dict[str, Any]) -> Scorecard:
    """Map a Port API scorecard response to the Scorecard model.

    Args:
        api_data: Raw scorecard dict from the Port API.

    Returns:
        A validated Scorecard model instance.
    """
    return Scorecard(**api_data)


def _map_action(api_data: dict[str, Any]) -> Action:
    """Map a Port API action response to the Action model.

    Args:
        api_data: Raw action dict from the Port API.

    Returns:
        A validated Action model instance.
    """
    return Action(
        identifier=api_data["identifier"],
        title=api_data.get("title", ""),
        blueprint=api_data.get("blueprint", ""),
        trigger=api_data.get("trigger", {}),
        invocation_method=api_data.get("invocationMethod"),
        user_properties=api_data.get("userInputs", {}).get("properties", {}),
        description=api_data.get("description"),
        required_approval=api_data.get("requiredApproval", False),
    )


def _map_page(api_data: dict[str, Any]) -> Page:
    """Map a Port API page response to the Page model.

    Args:
        api_data: Raw page dict from the Port API.

    Returns:
        A validated Page model instance.
    """
    return Page(
        identifier=api_data["identifier"],
        title=api_data.get("title", ""),
        type=api_data.get("type"),
        icon=api_data.get("icon"),
        description=api_data.get("description"),
        widgets=api_data.get("widgets", []),
        locked=api_data.get("locked", False),
        parent=api_data.get("parent"),
    )


def _write_yaml(data: dict[str, Any], path: Path) -> None:
    """Write a dictionary to a YAML file using ruamel.yaml.

    Args:
        data: Dictionary to serialise.
        path: File path to write to.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    yml = YAML()
    yml.default_flow_style = False
    yml.width = 120
    with path.open("w", encoding="utf-8") as fh:
        yml.dump(data, fh)


async def export_blueprints(
    client: PortClient,
    output_dir: Path,
    ignore: IgnoreFilter | None = None,
) -> list[str]:
    """Export all non-internal blueprints to YAML files.

    Fetches blueprints from the Port API, filters out internal ones (identifiers
    starting with ``_`` or ``$``) and any matched by the ignore filter, maps them
    to the Blueprint model, and writes each as a YAML file under
    ``output_dir/blueprints/<identifier>.yaml``.

    Args:
        client: Authenticated Port API client.
        output_dir: Root directory for exported files.
        ignore: Optional ignore filter. Loaded from output_dir if not provided.

    Returns:
        List of exported blueprint identifiers.
    """
    if ignore is None:
        ignore = load_ignore_filter(output_dir)

    raw_blueprints = await client.get_blueprints()
    exported: list[str] = []

    for raw in raw_blueprints:
        identifier = raw.get("identifier", "")
        if _is_internal(identifier):
            logger.debug("Skipping internal blueprint: %s", identifier)
            continue

        if ignore.is_ignored("blueprints", identifier):
            logger.debug("Skipping ignored blueprint: %s", identifier)
            continue

        blueprint = _map_blueprint(raw)
        data = blueprint.model_dump(exclude_none=True)
        yaml_path = output_dir / "blueprints" / f"{identifier}.yaml"
        _write_yaml(data, yaml_path)
        exported.append(identifier)
        logger.info("Exported blueprint: %s", identifier)

    return exported


async def export_scorecards(
    client: PortClient,
    blueprints: list[str],
    output_dir: Path,
    ignore: IgnoreFilter | None = None,
) -> list[str]:
    """Export scorecards for the given blueprints to YAML files.

    For each blueprint identifier, fetches its scorecards from the Port API,
    filters out any matched by the ignore filter, maps them to the Scorecard
    model, and writes each as a YAML file under
    ``output_dir/scorecards/<identifier>.yaml``.

    Args:
        client: Authenticated Port API client.
        blueprints: List of blueprint identifiers to fetch scorecards for.
        output_dir: Root directory for exported files.
        ignore: Optional ignore filter. Loaded from output_dir if not provided.

    Returns:
        List of exported scorecard identifiers.
    """
    if ignore is None:
        ignore = load_ignore_filter(output_dir)

    exported: list[str] = []

    for blueprint_id in blueprints:
        raw_scorecards = await client.get_scorecards(blueprint_id)
        for raw in raw_scorecards:
            scorecard = _map_scorecard(raw)
            if ignore.is_ignored("scorecards", scorecard.identifier):
                logger.debug("Skipping ignored scorecard: %s", scorecard.identifier)
                continue
            data = scorecard.model_dump(exclude_none=True)
            yaml_path = output_dir / "scorecards" / f"{scorecard.identifier}.yaml"
            _write_yaml(data, yaml_path)
            exported.append(scorecard.identifier)
            logger.info("Exported scorecard: %s", scorecard.identifier)

    return exported


async def export_actions(
    client: PortClient,
    output_dir: Path,
    ignore: IgnoreFilter | None = None,
) -> list[str]:
    """Export all actions to YAML files.

    Fetches actions from the Port API, filters out any matched by the ignore
    filter, maps them to the Action model, and writes each as a YAML file
    under ``output_dir/actions/<identifier>.yaml``.

    Args:
        client: Authenticated Port API client.
        output_dir: Root directory for exported files.
        ignore: Optional ignore filter. Loaded from output_dir if not provided.

    Returns:
        List of exported action identifiers.
    """
    if ignore is None:
        ignore = load_ignore_filter(output_dir)

    exported: list[str] = []

    raw_actions = await client.get_actions()
    for raw in raw_actions:
        action = _map_action(raw)
        if _is_internal(action.identifier):
            logger.debug("Skipping internal action: %s", action.identifier)
            continue
        if ignore.is_ignored("actions", action.identifier):
            logger.debug("Skipping ignored action: %s", action.identifier)
            continue
        data = action.model_dump(exclude_none=True)
        yaml_path = output_dir / "actions" / f"{action.identifier}.yaml"
        _write_yaml(data, yaml_path)
        exported.append(action.identifier)
        logger.info("Exported action: %s", action.identifier)

    return exported


async def export_pages(
    client: PortClient,
    output_dir: Path,
    ignore: IgnoreFilter | None = None,
) -> list[str]:
    """Export all pages to YAML files.

    Fetches pages from the Port API, filters out any matched by the ignore
    filter, maps them to the Page model, and writes each as a YAML file
    under ``output_dir/pages/<identifier>.yaml``.

    Args:
        client: Authenticated Port API client.
        output_dir: Root directory for exported files.
        ignore: Optional ignore filter. Loaded from output_dir if not provided.

    Returns:
        List of exported page identifiers.
    """
    if ignore is None:
        ignore = load_ignore_filter(output_dir)

    raw_pages = await client.get_pages()
    exported: list[str] = []

    for raw in raw_pages:
        identifier = raw.get("identifier", "")
        if _is_internal(identifier):
            logger.debug("Skipping internal page: %s", identifier)
            continue
        if ignore.is_ignored("pages", identifier):
            logger.debug("Skipping ignored page: %s", identifier)
            continue

        page = _map_page(raw)
        data = page.model_dump(exclude_none=True)
        yaml_path = output_dir / "pages" / f"{identifier}.yaml"
        _write_yaml(data, yaml_path)
        exported.append(identifier)
        logger.info("Exported page: %s", identifier)

    return exported


async def export_all(
    client: PortClient,
    output_dir: Path,
    resource: str | None = None,
) -> ExportResult:
    """Orchestrate export of all resource types.

    Args:
        client: Authenticated Port API client.
        output_dir: Root directory for exported files.
        resource: Optional filter -- ``"blueprints"``, ``"scorecards"``,
            ``"actions"``, or ``"pages"`` to export only that resource type.
            Exports all when ``None``.

    Returns:
        An ExportResult with exported resource identifiers and counts.
    """
    ignore = load_ignore_filter(output_dir)
    blueprint_ids: list[str] = []
    exported_blueprint_ids: list[str] = []
    exported_scorecard_ids: list[str] = []
    exported_action_ids: list[str] = []
    exported_page_ids: list[str] = []

    if resource is None or resource == "blueprints":
        blueprint_ids = await export_blueprints(client, output_dir, ignore=ignore)
        exported_blueprint_ids = blueprint_ids

    # Scorecards and actions both need blueprint IDs for lookup
    needs_blueprint_ids = resource in ("scorecards", "actions")
    if needs_blueprint_ids and not blueprint_ids:
        raw_blueprints = await client.get_blueprints()
        blueprint_ids = [
            bp["identifier"] for bp in raw_blueprints if not _is_internal(bp.get("identifier", ""))
        ]

    if resource is None or resource == "scorecards":
        exported_scorecard_ids = await export_scorecards(
            client, blueprint_ids, output_dir, ignore=ignore
        )

    if resource is None or resource == "actions":
        exported_action_ids = await export_actions(client, output_dir, ignore=ignore)

    if resource is None or resource == "pages":
        exported_page_ids = await export_pages(client, output_dir, ignore=ignore)

    return ExportResult(
        blueprint_ids=exported_blueprint_ids,
        scorecard_ids=exported_scorecard_ids,
        action_ids=exported_action_ids,
        page_ids=exported_page_ids,
    )
