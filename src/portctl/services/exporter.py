"""Export logic: API -> YAML files."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from portctl.models.blueprint import (
    Blueprint,
    BlueprintCalculationProperty,
    BlueprintMirrorProperty,
    BlueprintProperty,
    BlueprintRelation,
)
from portctl.models.scorecard import Scorecard
from portctl.services.ignore import IgnoreFilter, load_ignore_filter

if TYPE_CHECKING:
    from pathlib import Path

    from portctl.client.port_client import PortClient

logger = logging.getLogger(__name__)

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


async def export_all(
    client: PortClient,
    output_dir: Path,
    resource: str | None = None,
) -> dict[str, int]:
    """Orchestrate export of blueprints and scorecards.

    Args:
        client: Authenticated Port API client.
        output_dir: Root directory for exported files.
        resource: Optional filter -- ``"blueprints"`` or ``"scorecards"``
            to export only that resource type. Exports all when ``None``.

    Returns:
        Summary dict with counts, e.g. ``{"blueprints": 3, "scorecards": 5}``.
    """
    ignore = load_ignore_filter(output_dir)
    blueprint_ids: list[str] = []
    blueprint_count = 0
    scorecard_count = 0

    if resource is None or resource == "blueprints":
        blueprint_ids = await export_blueprints(client, output_dir, ignore=ignore)
        blueprint_count = len(blueprint_ids)

    if resource is None or resource == "scorecards":
        # If we haven't fetched blueprint ids yet, do so for scorecard lookup
        if not blueprint_ids and resource == "scorecards":
            raw_blueprints = await client.get_blueprints()
            blueprint_ids = [
                bp["identifier"]
                for bp in raw_blueprints
                if not _is_internal(bp.get("identifier", ""))
            ]
        scorecard_ids = await export_scorecards(
            client, blueprint_ids, output_dir, ignore=ignore
        )
        scorecard_count = len(scorecard_ids)

    return {"blueprints": blueprint_count, "scorecards": scorecard_count}
