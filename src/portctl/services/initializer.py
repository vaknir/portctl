"""Init logic: config generation, template scaffolding, CI workflow."""

from __future__ import annotations

import importlib.resources
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from portctl.constants import DEFAULT_API_URL
from portctl.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Template files bundled with the package, keyed by destination relative path.
_BLUEPRINT_TEMPLATES: dict[str, str] = {
    "blueprints/service.yaml": "blueprint_service.yaml",
    "blueprints/environment.yaml": "blueprint_environment.yaml",
    "blueprints/team.yaml": "blueprint_team.yaml",
}

_SCORECARD_TEMPLATES: dict[str, str] = {
    "scorecards/production_readiness.yaml": "scorecard_production_readiness.yaml",
}

_ALL_TEMPLATES: dict[str, str] = {**_BLUEPRINT_TEMPLATES, **_SCORECARD_TEMPLATES}


@dataclass
class InitOptions:
    """Options for the init workflow."""

    org_name: str
    mode: Literal["existing", "fresh"]
    org_id: str = ""
    client_id: str | None = None
    client_secret: str | None = None
    api_url: str = DEFAULT_API_URL
    generate_ci: bool = True
    ci_provider: Literal["github", "gitlab"] = "github"
    generate_ignore: bool = True
    project_dir: Path = field(default_factory=lambda: Path("."))
    config_dir: Path = field(default_factory=lambda: Path.home() / ".portctl")


@dataclass
class InitResult:
    """Result of the init workflow."""

    config_path: Path
    state_path: Path
    ignore_path: Path | None
    ci_workflow_path: Path | None
    exported_resources: int  # 0 for fresh mode
    scaffolded_templates: list[str]  # empty for existing mode
    files_created: list[Path]


def _templates_package() -> importlib.resources.abc.Traversable:
    """Return a Traversable pointing to the bundled templates directory.

    Returns:
        A Traversable for the ``portctl.services.templates`` data directory.
    """
    return importlib.resources.files("portctl.services") / "templates"


def write_config_file(config_dir: Path, org_name: str, api_url: str, *, org_id: str = "") -> Path:
    """Write ~/.portctl/config.yaml with the org entry. No credentials inline.

    Args:
        config_dir: Directory for the config file (e.g. ``~/.portctl``).
        org_name: Organization alias.
        api_url: Port API base URL.
        org_id: Port organization ID.

    Returns:
        Path to the created config file.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"

    org_entry: dict[str, str] = {
        "name": org_name,
        "api_url": api_url,
    }
    if org_id:
        org_entry["org_id"] = org_id

    config_data = {
        "default_org": org_name,
        "orgs": {
            org_name: org_entry,
        },
    }

    config_path.write_text(yaml.dump(config_data, default_flow_style=False, sort_keys=False))
    logger.info("Created config file: %s", config_path)
    return config_path


def _write_or_update_config(
    config_dir: Path, org_name: str, api_url: str, *, org_id: str = ""
) -> Path:
    """Write or update ~/.portctl/config.yaml, preserving existing orgs.

    If the config file exists, the new org is added (or updated if same alias).
    If it doesn't exist, a fresh config is created.

    Args:
        config_dir: Directory for the config file.
        org_name: Organization alias.
        api_url: Port API base URL.
        org_id: Port organization ID.

    Returns:
        Path to the config file.
    """
    config_path = config_dir / "config.yaml"

    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        orgs = raw.get("orgs", {})

        org_entry: dict[str, str] = {
            "name": org_name,
            "api_url": api_url,
        }
        if org_id:
            org_entry["org_id"] = org_id

        orgs[org_name] = org_entry

        raw["orgs"] = orgs
        if raw.get("default_org") is None:
            raw["default_org"] = org_name

        config_dir.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8"
        )
        logger.info("Updated config file: %s", config_path)
        return config_path

    return write_config_file(config_dir, org_name, api_url, org_id=org_id)


def write_project_state(project_dir: Path) -> Path:
    """Write .portctl-state.yaml with empty initial state.

    Args:
        project_dir: Root project directory.

    Returns:
        Path to the created state file.
    """
    state_path = project_dir / ".portctl-state.yaml"
    state_data = {
        "version": "1",
        "resources": {},
    }
    state_path.write_text(yaml.dump(state_data, default_flow_style=False, sort_keys=False))
    logger.info("Created project state: %s", state_path)
    return state_path


def scaffold_templates(project_dir: Path) -> list[str]:
    """Copy template YAMLs into the project directory.

    Creates ``blueprints/`` and ``scorecards/`` subdirectories and copies
    bundled template files into them.

    Args:
        project_dir: Root project directory.

    Returns:
        List of relative paths created (e.g. ``["blueprints/service.yaml"]``).
    """
    templates_root = _templates_package()
    created: list[str] = []

    for dest_rel, template_name in _ALL_TEMPLATES.items():
        dest_path = project_dir / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        template_file = templates_root / template_name
        dest_path.write_text(template_file.read_text(encoding="utf-8"))
        created.append(dest_rel)
        logger.info("Scaffolded: %s", dest_rel)

    return created


def generate_ci_workflow(
    project_dir: Path,
    org_name: str,
    provider: str = "github",
) -> Path:
    """Generate a CI workflow file for the given provider.

    Currently supports GitHub Actions. The generated workflow runs
    ``portctl validate`` and ``portctl plan`` on PRs, and
    ``portctl push`` on pushes to main.

    Args:
        project_dir: Root project directory.
        org_name: Organization alias to use in CI commands.
        provider: CI provider (currently only ``"github"``).

    Returns:
        Path to the created workflow file.
    """
    if provider == "github":
        workflow_dir = project_dir / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflow_dir / "portctl.yml"

        templates_root = _templates_package()
        template_content = (templates_root / "github_workflow.yaml").read_text(encoding="utf-8")
        workflow_content = template_content.replace("{org_name}", org_name)

        workflow_path.write_text(workflow_content)
        logger.info("Created CI workflow: %s", workflow_path)
        return workflow_path

    msg = f"Unsupported CI provider: {provider}"
    raise ConfigError(msg)


def generate_ignore_file(project_dir: Path) -> Path:
    """Generate a default .portctlignore file.

    Args:
        project_dir: Root project directory.

    Returns:
        Path to the created ignore file.
    """
    ignore_path = project_dir / ".portctlignore"
    templates_root = _templates_package()
    template_content = (templates_root / "portctlignore.default").read_text(encoding="utf-8")
    ignore_path.write_text(template_content)
    logger.info("Created ignore file: %s", ignore_path)
    return ignore_path


async def init_project(options: InitOptions) -> InitResult:
    """Execute the full init workflow.

    For ``fresh`` mode: generates config, state, templates, and optionally
    CI workflow and ignore file.

    For ``existing`` mode: generates config and state, then runs export
    to pull live resources from the Port API.

    Args:
        options: Init workflow configuration.

    Returns:
        An InitResult describing all created files and actions taken.

    Raises:
        ConfigError: If a config file already exists at the target location.
    """
    files_created: list[Path] = []

    # Write or update config (adds new org, preserves existing orgs)
    cfg_path = _write_or_update_config(
        options.config_dir, options.org_name, options.api_url, org_id=options.org_id
    )
    files_created.append(cfg_path)

    # Write project state
    state_path = write_project_state(options.project_dir)
    files_created.append(state_path)

    # Optional: ignore file
    ignore_path: Path | None = None
    if options.generate_ignore:
        ignore_path = generate_ignore_file(options.project_dir)
        files_created.append(ignore_path)

    # Optional: CI workflow
    ci_path: Path | None = None
    if options.generate_ci:
        ci_path = generate_ci_workflow(
            options.project_dir, options.org_name, provider=options.ci_provider
        )
        files_created.append(ci_path)

    # Mode-specific logic
    exported_resources = 0
    scaffolded_templates: list[str] = []

    if options.mode == "fresh":
        scaffolded_templates = scaffold_templates(options.project_dir)
        for rel in scaffolded_templates:
            files_created.append(options.project_dir / rel)

    elif options.mode == "existing":
        # Lazy imports to avoid circular deps and heavy imports at module level
        from portctl.client.port_client import PortClient
        from portctl.services.exporter import export_all

        if options.client_id is None or options.client_secret is None:
            raise ConfigError(
                "Credentials (--client-id and --client-secret) are required for 'existing' mode."
            )

        async with PortClient(
            client_id=options.client_id,
            client_secret=options.client_secret,
            api_base=options.api_url,
        ) as client:
            summary = await export_all(client, options.project_dir)

        exported_resources = sum(summary.values())

    return InitResult(
        config_path=cfg_path,
        state_path=state_path,
        ignore_path=ignore_path,
        ci_workflow_path=ci_path,
        exported_resources=exported_resources,
        scaffolded_templates=scaffolded_templates,
        files_created=files_created,
    )
