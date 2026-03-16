# Contributing to portctl

## Architecture Overview

portctl follows a strict three-layer architecture. Every feature touches all three layers, and each has clear responsibilities.

```
CLI Layer (typer commands)
    |
    v
Service Layer (business logic)
    |
    v
Client Layer (Port API wrapper)
```

### CLI Layer (`src/portctl/cli/`)

**Responsibility**: Parse arguments, call a service, format and print output.

- One file per command group (e.g., `commands/plan.py`, `commands/apply.py`)
- Each file defines a `typer.Typer()` instance registered on the main app
- Catches `PortctlError` subtypes and prints user-friendly messages
- Uses rich for all output (tables, trees, panels, progress bars)
- Contains zero business logic

```python
# src/portctl/cli/commands/plan.py
import typer
from rich.console import Console

from portctl.services.planner import plan_org
from portctl.services.config import load_config
from portctl.exceptions import PortctlError

app = typer.Typer()
console = Console()


@app.command()
def plan(
    org: str = typer.Argument(help="Organization alias to plan against"),
    resource: str | None = typer.Option(None, "--resource", "-r", help="Limit to resource type"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full diff detail"),
) -> None:
    """Dry-run diff: compare local YAML against live Port config."""
    try:
        config = load_config()
        result = plan_org(config=config, org_alias=org, resource_filter=resource)
        # format and print result using rich
        _render_plan(result, verbose=verbose)
    except PortctlError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
```

### Service Layer (`src/portctl/services/`)

**Responsibility**: All business logic. Validation, diffing, environment detection, state management.

- Functions receive dependencies as arguments (config, client) -- no global state
- Return typed result objects, never print anything
- Raise specific `PortctlError` subtypes on failure
- Never import httpx or rich

```python
# src/portctl/services/planner.py
from portctl.client.port_client import PortClient
from portctl.models.config import OrgConfig
from portctl.services.exporter import fetch_remote_resources
from portctl.services.differ import compute_diff

async def plan_org(
    config: OrgConfig,
    org_alias: str,
    resource_filter: str | None = None,
) -> PlanResult:
    """Compare local YAML against live Port config and return a diff."""
    async with PortClient(config.get_org(org_alias)) as client:
        remote = await fetch_remote_resources(client, resource_filter)
    local = load_local_resources(config.yaml_dir, resource_filter)
    diff = compute_diff(local=local, remote=remote)
    return PlanResult(changes=diff.changes, breaking=diff.breaking)
```

### Client Layer (`src/portctl/client/`)

**Responsibility**: HTTP communication with Port API. Token management, retries, response parsing.

- Single `PortClient` class wrapping `httpx.AsyncClient`
- Automatic JWT refresh on 401
- Exponential backoff retry for 429, 5xx
- All responses parsed into pydantic models before returning
- Never contains business logic

```python
# src/portctl/client/port_client.py
from portctl.client.models import BlueprintResponse

class PortClient:
    async def get_blueprint(self, identifier: str) -> BlueprintResponse:
        response = await self._request("GET", f"/blueprints/{identifier}")
        return BlueprintResponse.model_validate(response.json())
```

## How to Add a New Command

1. **Create the command file** at `src/portctl/cli/commands/<name>.py`
2. **Create or extend a service** at `src/portctl/services/<name>.py`
3. **Register the command** in `src/portctl/cli/app.py`
4. **Add tests** for both the service logic and the CLI output
5. **Add client methods** if new Port API endpoints are needed

Example: adding `portctl prune <org>`:

```python
# 1. src/portctl/cli/commands/prune.py
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def prune(
    org: str = typer.Argument(help="Organization alias"),
    stale: bool = typer.Option(False, "--stale", help="Only prune stale entities"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Show what would be deleted"),
) -> None:
    """Delete ghost entities whose source no longer exists."""
    ...

# 2. src/portctl/services/pruner.py
async def find_stale_entities(...) -> list[StaleEntity]: ...
async def delete_entities(...) -> PruneResult: ...

# 3. src/portctl/cli/app.py
from portctl.cli.commands import prune
app.add_typer(prune.app, name="prune")
```

## How to Add a New Port Resource Type

Port resources (blueprints, scorecards, actions, pages) each follow the same pattern:

1. **Define the YAML schema** as a pydantic model in `src/portctl/models/<resource>.py`
2. **Add client methods** for CRUD operations in `src/portctl/client/port_client.py`
3. **Add API response models** in `src/portctl/client/models.py`
4. **Register in the exporter** so `portctl export` pulls it
5. **Register in the planner/applier** so `plan` and `apply` handle it
6. **Add Layer 1 validation rules** in `src/portctl/validation/layer1.py`
7. **Add Layer 2 validation rules** (if any) in `src/portctl/validation/layer2.py`
8. **Add test fixtures** in `tests/fixtures/`

### Pydantic Model Example

```python
# src/portctl/models/scorecard.py
from pydantic import BaseModel, Field, model_validator

class ScorecardCondition(BaseModel):
    property: str = Field(description="Property identifier to evaluate")
    operator: str = Field(description="Comparison operator (=, !=, >=, isNotEmpty, etc.)")
    value: str | int | float | bool | list[str] | None = Field(
        default=None,
        description="Value to compare against (not required for isNotEmpty/isEmpty)",
    )

class ScorecardRule(BaseModel):
    identifier: str = Field(description="Unique rule identifier")
    title: str = Field(description="Human-readable rule title")
    level: str = Field(description="Level this rule belongs to (must match a level identifier)")
    query: ScorecardQuery = Field(description="Query conditions for this rule")

class ScorecardLevel(BaseModel):
    identifier: str = Field(description="Unique level identifier")
    title: str = Field(description="Human-readable level title")
    color: str = Field(description="Display color (red, orange, yellow, green)")

class Scorecard(BaseModel):
    identifier: str = Field(description="Unique scorecard identifier")
    title: str = Field(description="Human-readable scorecard title")
    blueprint: str = Field(description="Blueprint this scorecard applies to")
    levels: list[ScorecardLevel] = Field(description="Ordered list of levels (highest first)")
    rules: list[ScorecardRule] = Field(description="Scorecard rules")

    @model_validator(mode="after")
    def validate_rule_levels(self) -> "Scorecard":
        """Every rule.level must reference a defined level identifier."""
        level_ids = {level.identifier for level in self.levels}
        for rule in self.rules:
            if rule.level not in level_ids:
                raise ValueError(
                    f"Rule '{rule.identifier}' references level '{rule.level}' "
                    f"but defined levels are: {', '.join(sorted(level_ids))}"
                )
        return self
```

## Error Handling Patterns

### Service Layer: Raise Specific Exceptions

```python
from portctl.exceptions import ConfigError, ValidationError, PortAPIError

def load_config() -> Config:
    path = Path.home() / ".portctl" / "config.yaml"
    if not path.exists():
        raise ConfigError(
            f"Config file not found at {path}. Run 'portctl org add' to create one."
        )
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    return Config.model_validate(data)
```

### CLI Layer: Catch and Format

```python
@app.command()
def export(org: str = typer.Argument(...)) -> None:
    try:
        result = run_export(org)
        console.print(f"[green]Exported {result.file_count} files[/green]")
    except AuthError as e:
        console.print(f"[red]Authentication failed:[/red] {e}")
        console.print("[dim]Run 'portctl auth login' to re-authenticate[/dim]")
        raise typer.Exit(code=3)
    except ConfigError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(code=1)
    except PortAPIError as e:
        console.print(f"[red]Port API error ({e.status_code}):[/red] {e.detail}")
        raise typer.Exit(code=1)
```

### Validation: Collect All Errors

Never fail on the first error. Collect all issues and report them together:

```python
from portctl.validation.errors import ValidationIssue, ValidationResult

def validate_layer1(resources: list[Resource]) -> ValidationResult:
    issues: list[ValidationIssue] = []

    for resource in resources:
        issues.extend(_check_schema(resource))
        issues.extend(_check_references(resource))
        issues.extend(_check_enums(resource))

    return ValidationResult(
        passed=len([i for i in issues if i.severity == "error"]) == 0,
        issues=issues,
    )
```

## Rich Output Patterns

### Tables

```python
from rich.table import Table
from rich.console import Console

console = Console()

def render_org_list(orgs: list[OrgInfo]) -> None:
    table = Table(title="Configured Organizations")
    table.add_column("Alias", style="cyan")
    table.add_column("Role", style="magenta")
    table.add_column("Last Apply", style="green")
    table.add_column("Status")

    for org in orgs:
        status = "[green]synced[/green]" if org.synced else "[yellow]drifted[/yellow]"
        table.add_row(org.alias, org.role, org.last_apply or "never", status)

    console.print(table)
```

### Plan Diff Output

```python
from rich.console import Console
from rich.text import Text

console = Console()

def render_plan(result: PlanResult) -> None:
    for change in result.changes:
        if change.action == "create":
            console.print(f"  [green]+[/green] {change.resource_type}/{change.identifier}")
        elif change.action == "update":
            console.print(f"  [yellow]~[/yellow] {change.resource_type}/{change.identifier}")
            for field, diff in change.field_diffs.items():
                console.print(f"      {field}: [red]{diff.old}[/red] -> [green]{diff.new}[/green]")
        elif change.action == "delete":
            console.print(f"  [red]-[/red] {change.resource_type}/{change.identifier}")

    if result.breaking:
        console.print("\n[red bold]Breaking changes detected:[/red bold]")
        for b in result.breaking:
            console.print(f"  [red]![/red] {b.description}")
```

### Progress Bars

```python
from rich.progress import Progress

async def export_all(client: PortClient) -> ExportResult:
    resource_types = ["blueprints", "scorecards", "actions", "pages"]

    with Progress() as progress:
        task = progress.add_task("Exporting...", total=len(resource_types))
        for rtype in resource_types:
            progress.update(task, description=f"Exporting {rtype}...")
            await export_resource_type(client, rtype)
            progress.advance(task)
```

### Validation Output

```python
def render_validation(result: ValidationResult) -> None:
    for check in result.checks:
        if check.passed:
            console.print(f"[green]  check[/green]  {check.name:<25} {check.summary}")
        else:
            console.print(f"[red]  cross[/red]  {check.name:<25} {check.error_count} errors")
            for issue in check.issues:
                console.print(f"        [dim]{issue.file}:{issue.line}[/dim]")
                console.print(f"        {issue.message}")
                if issue.suggestion:
                    console.print(f"        [blue]-> {issue.suggestion}[/blue]")
    console.print()
    if result.passed:
        console.print("[green]All checks passed[/green]")
    else:
        console.print(f"[red]{result.error_count} errors -- fix before applying[/red]")
```

## Writing Tests

### Unit Test Example (Service Layer)

```python
# tests/unit/services/test_validator.py
import pytest
from portctl.validation.layer1 import validate_layer1
from tests.fixtures.factories import make_scorecard, make_blueprint

class TestScorecardValidation:
    def test_valid_scorecard_passes(self):
        blueprint = make_blueprint(identifier="service", properties=["coverage_pct"])
        scorecard = make_scorecard(
            blueprint="service",
            rules=[{"identifier": "cov", "level": "basic", "property": "coverage_pct"}],
        )
        result = validate_layer1([blueprint, scorecard])
        assert result.passed

    def test_missing_property_reference(self):
        blueprint = make_blueprint(identifier="service", properties=["test_coverage"])
        scorecard = make_scorecard(
            blueprint="service",
            rules=[{"identifier": "cov", "level": "basic", "property": "coverage_pct"}],
        )
        result = validate_layer1([blueprint, scorecard])
        assert not result.passed
        assert any("coverage_pct" in str(i.message) for i in result.issues)

    def test_invalid_rule_level_reference(self):
        scorecard = make_scorecard(
            levels=["gold", "silver"],
            rules=[{"identifier": "r1", "level": "platinum", "property": "x"}],
        )
        result = validate_layer1([scorecard])
        assert not result.passed
        assert any("platinum" in str(i.message) for i in result.issues)
```

### Async Test Example (Client Layer)

```python
# tests/unit/client/test_port_client.py
import pytest
import httpx
from pytest_httpx import HTTPXMock
from portctl.client.port_client import PortClient

@pytest.mark.asyncio
async def test_get_blueprint_returns_model(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.getport.io/v1/blueprints/service",
        json={"ok": True, "blueprint": {"identifier": "service", "title": "Service"}},
    )
    async with PortClient(base_url="https://api.getport.io/v1", token="test") as client:
        result = await client.get_blueprint("service")
    assert result.identifier == "service"

@pytest.mark.asyncio
async def test_get_blueprint_404_raises(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=404, json={"ok": False, "message": "not found"})
    async with PortClient(base_url="https://api.getport.io/v1", token="test") as client:
        with pytest.raises(PortAPIError) as exc_info:
            await client.get_blueprint("nonexistent")
    assert exc_info.value.status_code == 404
```

### Pydantic Model Test

```python
# tests/unit/models/test_scorecard.py
import pytest
from pydantic import ValidationError
from portctl.models.scorecard import Scorecard

def test_scorecard_rejects_invalid_rule_level():
    with pytest.raises(ValidationError, match="platinum"):
        Scorecard(
            identifier="test",
            title="Test",
            blueprint="service",
            levels=[{"identifier": "gold", "title": "Gold", "color": "yellow"}],
            rules=[{"identifier": "r1", "title": "R1", "level": "platinum", "query": {...}}],
        )
```

### Test Fixtures

Place reusable fixtures in `tests/fixtures/`:

```python
# tests/fixtures/factories.py
from portctl.models.blueprint import Blueprint
from portctl.models.scorecard import Scorecard

def make_blueprint(
    identifier: str = "service",
    properties: list[str] | None = None,
) -> Blueprint:
    props = {p: {"type": "string"} for p in (properties or [])}
    return Blueprint(identifier=identifier, title=identifier.title(), properties=props)

def make_scorecard(
    identifier: str = "test_scorecard",
    blueprint: str = "service",
    levels: list[str] | None = None,
    rules: list[dict] | None = None,
) -> Scorecard:
    level_objs = [
        {"identifier": l, "title": l.title(), "color": "green"}
        for l in (levels or ["basic"])
    ]
    rule_objs = rules or []
    return Scorecard(
        identifier=identifier,
        title="Test",
        blueprint=blueprint,
        levels=level_objs,
        rules=rule_objs,
    )
```
