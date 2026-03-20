# Architecture Design: whoami, .portctlignore, init

**Date**: 2026-03-20
**Status**: Proposed
**Author**: Architect Agent

---

## Architecture Overview

Three new features for portctl following the existing three-layer architecture (CLI -> Service -> Client). Feature 1 (whoami) is a read-only diagnostic command. Feature 2 (.portctlignore) is a cross-cutting filtering service consumed by exporter, planner, applier, and auditor. Feature 3 (init) is an interactive setup wizard that bootstraps config, runs export, and scaffolds templates.

All three features follow established patterns: typer commands in `cli/commands/`, stateless service functions, pydantic models for schemas, rich for output, custom exceptions, Google-style docstrings, strict type hints.

---

## Feature 1: `portctl whoami`

### Purpose

Sanity-check command that displays the current portctl identity and environment at a glance. Must degrade gracefully when config is missing or auth fails -- each field shows what it can, marks the rest as unknown.

### Data Flow

```
CLI (whoami.py)
  -> load_config() [may fail -> partial output]
  -> resolve_credentials() [may fail -> show "no credentials"]
  -> PortClient.get_me() [may fail -> show "unauthenticated"]
  -> env_detector (if exists) [may fail -> show "unknown"]
  -> gather_whoami_info() returns WhoamiInfo dataclass
  -> format as rich Panel or --json dict
```

### Files to Create

| File | Purpose |
|------|---------|
| `src/portctl/cli/commands/whoami.py` | CLI command, registered as top-level (not a subgroup) |
| `src/portctl/services/whoami.py` | Service that collects all identity info |
| `tests/unit/cli/test_whoami.py` | CLI output/exit code tests |
| `tests/unit/services/test_whoami.py` | Service logic tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/portctl/cli/app.py` | Register `whoami` command (top-level, not a typer group) |

### Key Classes and Functions

```python
# src/portctl/services/whoami.py

@dataclass
class WhoamiInfo:
    """Collected identity and environment information."""
    version: str                          # from constants.VERSION
    org_name: str | None                  # from config.default_org or --org
    org_role: str | None                  # from OrgConfig.role
    api_url: str | None                   # from OrgConfig.api_url
    user_email: str | None                # from /me endpoint
    user_name: str | None                 # from /me endpoint
    credential_source: str | None         # "keyring" | "env" | "config" | None
    config_path: Path | None              # path to config file if it exists
    state_path: Path | None               # path to state file if it exists
    is_ci: bool                           # True if CI env vars detected
    ci_provider: str | None               # "github-actions" | "gitlab-ci" | "jenkins" | etc
    authenticated: bool                   # True if /me succeeded

async def gather_whoami_info(
    org: str | None = None,
) -> WhoamiInfo:
    """Collect identity info with graceful degradation.

    Each step is wrapped in try/except so partial info is always returned.

    Args:
        org: Optional org alias override.

    Returns:
        WhoamiInfo with as many fields populated as possible.
    """

def detect_ci_environment() -> tuple[bool, str | None]:
    """Detect if running in CI and which provider.

    Checks: GITHUB_ACTIONS, GITLAB_CI, JENKINS_URL, CIRCLECI,
    BUILDKITE, TRAVIS, CI (generic).

    Returns:
        Tuple of (is_ci, provider_name).
    """

def detect_credential_source(org_name: str, config: PortctlConfig | None) -> str | None:
    """Determine which credential source would be used without fetching secrets.

    Checks env vars -> keyring -> config in order. Returns the name of the
    first source that has credentials, or None.

    Args:
        org_name: Organization alias.
        config: Loaded config, or None if unavailable.

    Returns:
        "env" | "keyring" | "config" | None
    """
```

```python
# src/portctl/cli/commands/whoami.py

@app.command()  # Note: this is a standalone command, not a group
def whoami(
    org: Optional[str] = typer.Option(None, "--org", help="Organization alias."),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON for CI."),
) -> None:
    """Show current identity, org, and environment."""
```

### Integration Points

- `services/config.py::load_config()` -- wrapped in try/except, partial output on failure
- `services/auth.py::resolve_credentials()` -- only called if config loaded
- `client/port_client.py::PortClient.get_me()` -- only called if credentials resolved
- `constants.py::VERSION, CONFIG_FILE, STATE_FILE` -- always available

### Output Format

**Interactive (rich Panel):**
```
portctl whoami
+--------------------------+
| portctl v0.1.0           |
+--------------------------+
  Org:         my-org (production)
  API:         https://api.getport.io/v1
  User:        user@example.com
  Credentials: keyring
  Config:      ~/.portctl/config.yaml
  State:       ~/.portctl/state.yaml
  CI:          no
  Auth:        authenticated
```

**JSON (--json flag):**
```json
{
  "version": "0.1.0",
  "org": "my-org",
  "role": "production",
  "api_url": "https://api.getport.io/v1",
  "user": "user@example.com",
  "credential_source": "keyring",
  "authenticated": true,
  "ci": false
}
```

### Test Strategy

- **Unit (service):** Test `gather_whoami_info` with mocked config/auth/client. Test each degradation path: no config, no credentials, auth failure. Test `detect_ci_environment` with various env var combos. Test `detect_credential_source` for each source.
- **Unit (CLI):** Test `--json` output is valid JSON. Test exit code 0 even with partial info. Test `--org` override.
- Mock boundaries: mock `load_config`, `resolve_credentials`, `PortClient.get_me`.

### Complexity: S (mid-dev)

---

## Feature 2: `.portctlignore`

### Purpose

Glob-based ignore file that excludes resources from export, plan, apply, and audit. Follows `.gitignore` conventions: comments with `#`, negation with `!`, glob patterns, blank lines ignored. Matches against resource type/identifier paths like `blueprints/_ocean_*`.

### Data Flow

```
Service (exporter/planner/applier/auditor)
  -> load_ignore_patterns(config_dir)  # reads .portctlignore from project root
  -> returns IgnoreFilter instance
  -> filter.is_ignored("blueprints", "_ocean_kafka_consumer") -> True
  -> filter.is_ignored("scorecards", "my_scorecard") -> False
```

### Files to Create

| File | Purpose |
|------|---------|
| `src/portctl/services/ignore.py` | Parse .portctlignore, match resources against patterns |
| `tests/unit/services/test_ignore.py` | Pattern parsing, matching, negation, edge cases |
| `tests/fixtures/.portctlignore.sample` | Sample ignore file for tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/portctl/services/exporter.py` | Filter exported resources through IgnoreFilter |
| `src/portctl/services/planner.py` | Filter local + remote resources through IgnoreFilter |
| `src/portctl/services/applier.py` | Filter plan changes through IgnoreFilter |
| `src/portctl/constants.py` | Add `IGNORE_FILE = ".portctlignore"` |

### Key Classes and Functions

```python
# src/portctl/services/ignore.py

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class IgnoreRule:
    """A single parsed ignore rule."""
    pattern: str            # the glob pattern
    negated: bool = False   # True if prefixed with !
    resource_type: str | None = None  # "blueprints", "scorecards", etc. or None for all

@dataclass
class IgnoreFilter:
    """Compiled set of ignore rules. Immutable after creation."""
    rules: list[IgnoreRule] = field(default_factory=list)

    def is_ignored(self, resource_type: str, identifier: str) -> bool:
        """Check if a resource should be ignored.

        Evaluates rules in order. Last matching rule wins (like .gitignore).
        A negation rule un-ignores a previously matched resource.

        Matching is done against "{resource_type}/{identifier}" paths,
        e.g. "blueprints/_ocean_kafka_consumer".

        Args:
            resource_type: "blueprints", "scorecards", "actions", "pages".
            identifier: Resource identifier string.

        Returns:
            True if the resource should be excluded.
        """

    def filter_identifiers(
        self, resource_type: str, identifiers: list[str]
    ) -> list[str]:
        """Return only non-ignored identifiers from the list.

        Args:
            resource_type: Resource type string.
            identifiers: List of identifiers to filter.

        Returns:
            Filtered list with ignored identifiers removed.
        """

def parse_ignore_file(content: str) -> list[IgnoreRule]:
    """Parse .portctlignore file content into rules.

    Syntax:
    - Blank lines are ignored
    - Lines starting with # are comments
    - Lines starting with ! are negation (un-ignore)
    - Patterns containing / are matched as "{type}/{identifier}" paths
    - Patterns without / are matched against identifier only (any type)
    - Standard glob syntax: *, ?, [seq], [!seq]

    Examples:
        blueprints/_ocean_*       # ignore all ocean blueprints
        scorecards/legacy_*       # ignore legacy scorecards
        _internal_*               # ignore across all resource types
        !blueprints/_ocean_kafka  # but keep this specific one

    Args:
        content: Raw file content.

    Returns:
        Ordered list of IgnoreRule instances.
    """

def load_ignore_filter(project_dir: Path) -> IgnoreFilter:
    """Load .portctlignore from the project directory.

    If the file does not exist, returns an empty IgnoreFilter (nothing ignored).

    Args:
        project_dir: Project root directory.

    Returns:
        Compiled IgnoreFilter instance.
    """
```

### Integration Points

Each consuming service loads the filter once and applies it during resource enumeration.

**exporter.py -- `export_blueprints` and `export_scorecards`:**
```python
# At the top of export_all():
ignore = load_ignore_filter(output_dir)

# In the loop over raw_blueprints:
if ignore.is_ignored("blueprints", identifier):
    logger.debug("Ignored blueprint: %s", identifier)
    continue
```

**planner.py -- `plan_org`:**
```python
# After loading local + remote:
ignore = load_ignore_filter(config_dir)

# Filter local_blueprints and remote_blueprints dicts before diffing:
local_blueprints = {
    k: v for k, v in local_blueprints.items()
    if not ignore.is_ignored("blueprints", k)
}
remote_blueprints = {
    k: v for k, v in remote_blueprints.items()
    if not ignore.is_ignored("blueprints", k)
}
# Same for scorecards
```

**applier.py -- `apply_org`:**
```python
# Filter plan.changes before applying:
ignore = load_ignore_filter(config_dir)
filtered_changes = [
    c for c in plan.changes
    if not ignore.is_ignored(c.resource_type + "s", c.identifier)
]
```

### .portctlignore File Format

```
# Ignore all Ocean integration blueprints
blueprints/_ocean_*

# Ignore all internal scorecards
scorecards/_*

# But keep this specific one
!scorecards/_critical_metrics

# Ignore any resource with "test" prefix (any type)
test_*

# Ignore specific blueprint
blueprints/deprecated_service
```

### Design Decisions

- **Decision**: Use `fnmatch` from stdlib for glob matching, not `pathspec` or `gitignore-parser`.
  **Why**: fnmatch covers the needed patterns (*, ?, [seq]). We don't need full gitignore semantics like directory-only rules or `**` recursion. Avoids a new dependency.
  **Reversible**: Yes -- the IgnoreFilter interface is stable; we can swap the matching engine later.

- **Decision**: Match against `"{resource_type}/{identifier}"` virtual paths, not filesystem paths.
  **Why**: Resources are identified by type+identifier, not file paths. This is more intuitive for users who think in Port terms.
  **Reversible**: Yes.

- **Decision**: Last-rule-wins semantics (like .gitignore).
  **Why**: Familiar to developers. Negation rules only make sense with ordered evaluation.
  **Reversible**: No -- changing evaluation order would be a breaking behavioral change.

### Test Strategy

- **Unit (ignore.py):** Test `parse_ignore_file` with comments, blank lines, negation, slashed/unslashed patterns. Test `IgnoreFilter.is_ignored` for exact match, glob match, negation override, no-match passthrough. Test `load_ignore_filter` with missing file (returns empty). Test `filter_identifiers` convenience method.
- **Unit (exporter/planner/applier):** Test that ignored resources are excluded from export summary, plan changes, and apply operations. Use fixtures with a `.portctlignore` file.
- No integration tests needed -- this is purely local logic.

### Complexity: M (senior-dev)

The cross-cutting nature (4 services) and the need to get matching semantics exactly right justify a senior.

---

## Feature 3: `portctl init`

### Purpose

Interactive project setup wizard. Two paths: (A) connect to an existing Port org and export its config, or (B) start fresh with scaffolded templates. Creates config file, state file, optionally generates CI workflow, and scaffolds commented template YAMLs. Supports `--non-interactive` for CI bootstrapping.

### Data Flow

```
CLI (init.py)
  -> detect existing config (abort if .portctl already initialized)
  -> prompt: existing org or fresh start?
  -> Path A (existing org):
       -> prompt for org name, client_id, client_secret
       -> verify_token() to validate credentials
       -> write config.yaml
       -> store_credentials() in keyring
       -> run export_all() to pull live config
  -> Path B (fresh start):
       -> prompt for org name
       -> scaffold template YAMLs from bundled templates
  -> optionally generate .github/workflows/portctl.yml
  -> write .portctl-state.yaml (empty initial state)
  -> write .portctlignore with sensible defaults
  -> print summary
```

### Files to Create

| File | Purpose |
|------|---------|
| `src/portctl/cli/commands/init.py` | CLI command with interactive prompts |
| `src/portctl/services/initializer.py` | Init logic: config generation, template scaffolding, CI workflow |
| `src/portctl/services/templates/` | Directory for bundled template files |
| `src/portctl/services/templates/blueprint_service.yaml` | Template: microservice blueprint |
| `src/portctl/services/templates/blueprint_environment.yaml` | Template: environment blueprint |
| `src/portctl/services/templates/blueprint_team.yaml` | Template: team blueprint |
| `src/portctl/services/templates/scorecard_production_readiness.yaml` | Template: production readiness scorecard |
| `src/portctl/services/templates/portctlignore.default` | Default .portctlignore content |
| `src/portctl/services/templates/github_workflow.yaml` | GitHub Actions workflow template |
| `tests/unit/cli/test_init.py` | CLI prompt flow tests |
| `tests/unit/services/test_initializer.py` | Service logic tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/portctl/cli/app.py` | Register `init` command (top-level) |
| `src/portctl/constants.py` | Add `PORTCTL_STATE_FILE = ".portctl-state.yaml"`, `IGNORE_FILE = ".portctlignore"` (if not already added by Feature 2) |
| `pyproject.toml` | Add `package-data` for templates directory if using `importlib.resources` |

### Key Classes and Functions

```python
# src/portctl/services/initializer.py

from dataclasses import dataclass
from pathlib import Path

@dataclass
class InitOptions:
    """Options collected from interactive prompts or CLI flags."""
    org_name: str
    mode: Literal["existing", "fresh"]
    client_id: str | None = None       # only for "existing" mode
    client_secret: str | None = None   # only for "existing" mode
    api_url: str = DEFAULT_API_URL
    generate_ci: bool = True
    ci_provider: Literal["github", "gitlab"] = "github"
    generate_ignore: bool = True
    project_dir: Path = Path(".")

@dataclass
class InitResult:
    """Summary of what init created."""
    config_path: Path
    state_path: Path
    ignore_path: Path | None
    ci_workflow_path: Path | None
    exported_blueprints: int      # 0 for fresh mode
    exported_scorecards: int      # 0 for fresh mode
    scaffolded_templates: list[str]  # empty for existing mode
    files_created: list[Path]     # all files created for summary display

def write_config_file(
    project_dir: Path,
    org_name: str,
    api_url: str,
) -> Path:
    """Write ~/.portctl/config.yaml with the org entry.

    Does NOT include credentials -- those go to keyring.

    Args:
        project_dir: Project root (unused, config goes to ~/.portctl/).
        org_name: Organization alias.
        api_url: Port API base URL.

    Returns:
        Path to the written config file.
    """

def write_project_state(project_dir: Path) -> Path:
    """Write .portctl-state.yaml with empty initial state.

    Args:
        project_dir: Project root directory.

    Returns:
        Path to the written state file.
    """

def scaffold_templates(project_dir: Path) -> list[str]:
    """Copy commented template YAMLs into project directory.

    Creates:
    - blueprints/service.yaml
    - blueprints/environment.yaml
    - blueprints/team.yaml
    - scorecards/production_readiness.yaml

    Each file has comments explaining every field.

    Args:
        project_dir: Project root directory.

    Returns:
        List of relative paths to scaffolded files.
    """

def generate_ci_workflow(
    project_dir: Path,
    org_name: str,
    provider: Literal["github", "gitlab"] = "github",
) -> Path:
    """Generate CI workflow file for portctl plan/apply.

    GitHub: .github/workflows/portctl.yml
    GitLab: .gitlab-ci.yml (future)

    The workflow:
    - On PR: runs `portctl validate` and `portctl plan`
    - On merge to main: runs `portctl apply`
    - Uses PORT_CLIENT_ID and PORT_CLIENT_SECRET from secrets

    Args:
        project_dir: Project root directory.
        org_name: Org alias for the workflow.
        provider: CI provider.

    Returns:
        Path to the generated workflow file.
    """

def generate_ignore_file(project_dir: Path) -> Path:
    """Generate default .portctlignore file.

    Default ignores:
    - blueprints/_*  (internal blueprints)
    - blueprints/$*  (system blueprints)

    Args:
        project_dir: Project root directory.

    Returns:
        Path to the generated ignore file.
    """

async def init_project(options: InitOptions) -> InitResult:
    """Execute the full init workflow.

    Args:
        options: Collected init options.

    Returns:
        InitResult summarizing what was created.

    Raises:
        ConfigError: If config already exists and --force not set.
        AuthError: If credential verification fails (existing mode).
    """
```

```python
# src/portctl/cli/commands/init.py

app = typer.Typer()

@app.command(name="run")
def init_run(
    org: Optional[str] = typer.Option(None, "--org", help="Organization alias."),
    mode: Optional[str] = typer.Option(
        None, "--mode", help="'existing' or 'fresh'. Interactive if omitted."
    ),
    client_id: Optional[str] = typer.Option(None, "--client-id", help="Port client ID."),
    client_secret: Optional[str] = typer.Option(
        None, "--client-secret", help="Port client secret."
    ),
    no_ci: bool = typer.Option(False, "--no-ci", help="Skip CI workflow generation."),
    no_ignore: bool = typer.Option(False, "--no-ignore", help="Skip .portctlignore generation."),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Non-interactive mode for CI. Requires --org and --mode."
    ),
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory."),
) -> None:
    """Initialize a new portctl project."""
```

### Template Content (Example: blueprint_service.yaml)

```yaml
# Service Blueprint - represents a microservice in your catalog
# Customize the properties and relations to match your architecture
#
# Docs: https://docs.getport.io/build-your-software-catalog/customize-integrations/configure-data-model/
identifier: service
title: Service
icon: Microservice
description: A microservice in the software catalog
properties:
  # Add your service properties here. Common examples:
  language:
    type: string
    title: Language
    description: Primary programming language
    enum:
      - Python
      - TypeScript
      - Go
      - Java
      - Rust
  repository:
    type: string
    title: Repository
    description: Git repository URL
    format: url
  tier:
    type: string
    title: Service Tier
    description: Criticality tier
    enum:
      - Tier 1 - Critical
      - Tier 2 - Important
      - Tier 3 - Standard
      - Tier 4 - Internal
relations:
  # environment:
  #   target: environment
  #   title: Deployed To
  #   many: true
  # team:
  #   target: team
  #   title: Owned By
```

### CI Workflow Template (GitHub Actions)

```yaml
name: portctl
on:
  pull_request:
    paths:
      - 'blueprints/**'
      - 'scorecards/**'
      - 'actions/**'
      - 'pages/**'
  push:
    branches: [main]
    paths:
      - 'blueprints/**'
      - 'scorecards/**'
      - 'actions/**'
      - 'pages/**'

jobs:
  validate-and-plan:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv tool install portctl
      - run: portctl validate
      - run: portctl plan run ${ORG_NAME} --json
        env:
          PORT_CLIENT_ID: ${{ secrets.PORT_CLIENT_ID }}
          PORT_CLIENT_SECRET: ${{ secrets.PORT_CLIENT_SECRET }}

  apply:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv tool install portctl
      - run: portctl apply run ${ORG_NAME} --yes
        env:
          PORT_CLIENT_ID: ${{ secrets.PORT_CLIENT_ID }}
          PORT_CLIENT_SECRET: ${{ secrets.PORT_CLIENT_SECRET }}
```

### Design Decisions

- **Decision**: Templates are bundled as package data files, loaded via `importlib.resources`.
  **Why**: Keeps templates versionable with the CLI. No network dependency. `importlib.resources` is the stdlib way to access package data in Python 3.9+.
  **Reversible**: Yes.

- **Decision**: Config file goes to `~/.portctl/config.yaml` (global), project state goes to `.portctl-state.yaml` (project-local).
  **Why**: Config contains credentials/org mapping (user-level concern). Project state tracks what was last applied (project-level concern, committed to git). This matches the existing `CONFIG_FILE` and `STATE_FILE` constants.
  **Reversible**: No -- changing file locations is a breaking change.

- **Decision**: `init` detects existing config and refuses to overwrite without `--force`.
  **Why**: Prevents accidental data loss. Standard CLI safety pattern.
  **Reversible**: Yes.

- **Decision**: Fresh mode scaffolds 3 blueprint templates + 1 scorecard template.
  **Why**: Service, Environment, Team are the most common Port catalog blueprints. Production Readiness is the most common scorecard. Enough to demonstrate the pattern without overwhelming.
  **Reversible**: Yes -- we can add more templates later.

### Integration Points

- `services/config.py::load_config()` -- check for existing config to avoid overwrite
- `services/auth.py::store_credentials()` -- store creds after verification in existing mode
- `services/auth.py::verify_token()` -- validate credentials before storing
- `services/exporter.py::export_all()` -- run full export in existing mode
- `services/ignore.py::load_ignore_filter()` -- init generates default .portctlignore (ties into Feature 2)
- `constants.py` -- file path constants

### Test Strategy

- **Unit (service):** Test `write_config_file` creates valid YAML parseable by `load_config`. Test `scaffold_templates` creates expected files with valid YAML content. Test `generate_ci_workflow` creates valid YAML. Test `init_project` in both modes with mocked PortClient. Test abort-on-existing-config behavior.
- **Unit (CLI):** Test `--non-interactive` requires `--org` and `--mode` (exit code 1 if missing). Test `--no-ci` skips workflow generation. Test interactive prompts using `typer.testing.CliRunner` with input injection.
- Mock boundaries: mock `verify_token`, `store_credentials`, `export_all`, `PortClient`.
- Use `tmp_path` fixture for all file operations.

### Complexity: M (senior-dev)

Multiple file generation, interactive prompts, two code paths, ties into auth and export.

---

## Implementation Order

1. **Feature 2: .portctlignore** (no dependencies, other features benefit from it)
2. **Feature 1: whoami** (standalone, quick win)
3. **Feature 3: init** (depends on Feature 2 for default ignore file generation)

## Cross-Cutting Observations

- The `_is_internal()` function and `_load_local_blueprints()` / `_load_local_scorecards()` are duplicated between `exporter.py`, `planner.py`, and `applier.py`. Feature 2 is a natural place to consolidate: the IgnoreFilter subsumes `_is_internal()` via default ignore rules (`blueprints/_*`, `blueprints/$*`). Consider extracting `_load_local_blueprints` and `_load_local_scorecards` into a shared `services/loader.py` module during the Feature 2 implementation. This is optional refactoring, not a requirement.

- All three features add top-level commands to `app.py`. `whoami` and `init` are registered differently from existing commands -- they are standalone commands, not `add_typer` groups. Use `@app.command()` directly on the main app or use a single-command typer with `invoke_without_command=True`.

## Summary Table

| Feature | Files New | Files Modified | Complexity | Agent |
|---------|-----------|----------------|------------|-------|
| whoami | 4 | 1 | S | mid-dev |
| .portctlignore | 3 | 4 | M | senior-dev |
| init | 11 | 3 | M | senior-dev |
