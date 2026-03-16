# portctl - GitOps CLI for Port.io

## Project Overview

portctl is a GitOps CLI that manages Port.io portal configuration (blueprints, scorecards, actions, pages) as versioned YAML files in git. Think `kubectl` or `terraform` for your developer portal: `export` pulls live config, `plan` shows a dry-run diff, `apply` pushes changes, `audit` detects UI drift.

**Tech stack**: Python 3.11+, typer, rich, httpx (async), pydantic v2, deepdiff, keyring, cryptography

**Architecture**: Three-layer separation:
- **CLI layer** (typer commands) -- argument parsing, output formatting, user interaction
- **Service layer** -- business logic, validation pipeline, diffing, environment detection
- **Client layer** -- Port API wrapper, auth token management, HTTP calls

## Repository Structure

```
portctl/
  src/
    portctl/
      __init__.py
      __main__.py              # python -m portctl entry point
      cli/
        __init__.py
        app.py                 # typer app factory, top-level group
        commands/
          auth.py              # login, status, logout
          org.py               # org add, list, remove
          export.py            # export <org>
          plan.py              # plan <org>
          apply.py             # apply <org>
          diff.py              # diff <org1> <org2>
          promote.py           # promote <from> <to>
          audit.py             # audit <org>
          validate.py          # validate
          blueprint.py         # blueprint show <name>
          history.py           # history <org>
          rollback.py          # rollback <org>
          lock.py              # lock, unlock, lock status
          entity.py            # entity get, search, watch
          status.py            # integration health dashboard
          logs.py              # tail integration/action logs
          migrate.py           # migrate, migrate-from-terraform
          seed.py              # seed <org>
          graph.py             # graph <org>
          prune.py             # prune <org>
          query.py             # query --blueprint --jq
          test_rule.py         # test-rule
        formatters/
          __init__.py
          tables.py            # rich table builders
          trees.py             # rich tree builders (graph, blueprint show)
          diffs.py             # plan/diff output formatting
          panels.py            # status panels, entity detail views
      services/
        __init__.py
        auth.py                # credential resolution (keyring -> env -> file -> config)
        config.py              # config loader (~/.portctl/config.yaml)
        state.py               # state tracker (~/.portctl/state.yaml)
        exporter.py            # export logic: API -> YAML files
        planner.py             # plan logic: diff local YAML vs live API
        applier.py             # apply logic: push local YAML -> API
        differ.py              # cross-org diff
        promoter.py            # cross-org promote
        auditor.py             # drift detection (live vs last-applied snapshot)
        validator.py           # validation pipeline orchestrator
        env_detector.py        # automatic environment detection (prod/staging/dev)
        lock_manager.py        # distributed locking via Port entities
        snapshot.py            # snapshot storage for rollback
      client/
        __init__.py
        port_client.py         # httpx async client wrapper for Port API
        auth.py                # JWT token fetch + auto-refresh
        models.py              # pydantic models for API responses
        endpoints.py           # endpoint URL constants
      models/
        __init__.py
        blueprint.py           # Blueprint YAML schema (pydantic)
        scorecard.py           # Scorecard YAML schema (pydantic)
        action.py              # Action YAML schema (pydantic)
        page.py                # Page YAML schema (pydantic)
        config.py              # Config file schema
        state.py               # State file schema
        lock.py                # Lock entity schema
        common.py              # shared types (Query, Condition, etc.)
      validation/
        __init__.py
        pipeline.py            # orchestrates Layer 1 + Layer 2
        layer1.py              # local checks: YAML syntax, schema, refs, enums
        layer2.py              # remote checks: API-backed validation
        errors.py              # validation error collection + formatting
      exceptions.py            # custom exception hierarchy
      constants.py             # magic strings, defaults, version
  tests/
    unit/
      cli/                     # CLI argument/output tests
      services/                # service layer tests
      client/                  # client layer tests (mocked HTTP)
      models/                  # pydantic model tests
      validation/              # validation pipeline tests
    integration/               # tests hitting Port API (VCR cassettes)
      cassettes/               # recorded API responses
    fixtures/                  # shared YAML fixtures, factory helpers
    conftest.py
  docs/
    contributing.md
  pyproject.toml
  uv.lock
  .python-version
  .ruff.toml
  .gitignore
```

## Development Setup

```bash
# requires python 3.11+
python --version

# install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# create venv and install deps
uv sync

# install pre-commit hooks
uv run pre-commit install

# run the CLI
uv run portctl --help
# or
uv run python -m portctl --help
```

## Running Tests

```bash
# all tests
uv run pytest

# unit tests only
uv run pytest tests/unit/ -x --tb=short

# integration tests (requires PORT_CLIENT_ID and PORT_CLIENT_SECRET)
uv run pytest tests/integration/ -x --tb=short

# with coverage
uv run pytest --cov=src/portctl --cov-report=term-missing

# single file
uv run pytest tests/unit/services/test_validator.py -v
```

## Linting and Formatting

```bash
# lint
uv run ruff check src/ tests/

# format
uv run ruff format src/ tests/

# type check
uv run mypy src/portctl/
```

## Code Standards

### Python Style
- **ruff** for linting and formatting (config in `.ruff.toml` or `pyproject.toml`)
- **Strict type hints everywhere** -- no `Any` unless interfacing with untyped externals
- **mypy strict mode** -- `--strict` flag in CI
- Line length: 100
- Docstrings: Google style, required on all public functions and classes

### Pydantic v2 Models
- All Port API responses map to pydantic models in `src/portctl/client/models.py`
- All YAML schemas map to pydantic models in `src/portctl/models/`
- Use `model_validator` for cross-field validation
- Use `Field(description=...)` on every field
- Config file and state file schemas are also pydantic models

### httpx Async Client
- All Port API calls go through `PortClient` in `src/portctl/client/port_client.py`
- Never call httpx directly from services or CLI
- Use `httpx.AsyncClient` with connection pooling
- Token refresh handled transparently in the client
- Retry with exponential backoff for transient failures (429, 500, 502, 503, 504)
- Timeout defaults: 30s connect, 60s read

### Error Handling
Custom exception hierarchy in `src/portctl/exceptions.py`:
```python
class PortctlError(Exception):
    """Base exception for all portctl errors."""

class PortAPIError(PortctlError):
    """Port API returned an error (4xx/5xx)."""
    status_code: int
    detail: str

class ConfigError(PortctlError):
    """Configuration file is missing, malformed, or invalid."""

class ValidationError(PortctlError):
    """YAML validation failed (Layer 1 or Layer 2)."""
    errors: list[ValidationIssue]

class LockError(PortctlError):
    """Lock acquisition or release failed."""

class AuthError(PortctlError):
    """Authentication failed -- bad credentials or expired token."""
```

Rules:
- CLI commands catch `PortctlError` subtypes and print user-friendly messages via rich
- Services raise specific exceptions, never generic `Exception` or `ValueError`
- Never silently swallow exceptions
- Include actionable context in error messages ("did you mean X?")

### Rich Console Output
- Use `rich.console.Console` for all output (never bare `print()`)
- Tables for list/tabular data (`rich.table.Table`)
- Tree for hierarchical data (`rich.tree.Tree`)
- Progress bars for multi-step operations (`rich.progress`)
- Status spinners for API calls (`rich.status`)
- Panel for detailed entity/blueprint views (`rich.panel`)
- Syntax highlighting for YAML/JSON output (`rich.syntax`)
- Colors: green for success, red for errors, yellow for warnings, blue for info

### Typer Command Patterns
- One file per command group in `src/portctl/cli/commands/`
- Each file creates a `typer.Typer()` instance added to the main app
- Use `typer.Option()` and `typer.Argument()` with help text on every parameter
- Use callbacks for shared options (--org, --format, --verbose)
- Exit codes: 0 success, 1 general error, 2 validation error, 3 auth error

## Testing Standards

- **pytest** with **pytest-asyncio** for async tests
- Test directory structure mirrors `src/portctl/`
- **Unit tests**: all business logic in `services/`, `validation/`, `models/`
- **Integration tests**: API client with VCR-recorded responses (pytest-recording or vcrpy)
- Minimum coverage target: 80% on service and validation layers
- Test naming: `test_<function>_<scenario>` (e.g., `test_validate_missing_blueprint_reference`)
- Use factories/fixtures for test data, not inline YAML strings
- Mock boundaries: mock the client layer in service tests, mock httpx in client tests
- Never mock pydantic validation -- test with real models

## Architecture Principles

1. **CLI is thin**: commands parse args, call a service, format output. No business logic in CLI layer.
2. **Services are stateless functions**: receive dependencies as arguments, return results. No global state.
3. **Client is the only HTTP boundary**: all Port API calls go through `PortClient`. Services never import httpx.
4. **Config is read-only after load**: loaded once at startup, passed down. Never mutated.
5. **Validation is a pipeline**: Layer 1 (local, instant) then Layer 2 (remote, API-backed). All errors collected before reporting.
6. **State tracking**: `~/.portctl/state.yaml` tracks last-applied snapshots per org per resource.
7. **Credentials via keyring**: OS keychain first, then env vars, then encrypted file, then config file (last resort). Never store secrets in plain config.
8. **Environment detection**: automatic via confidence scoring (org name, entity count, blueprint complexity, integrations, CI actor ratio). Defaults to production if uncertain.

## Credential Resolution Order

1. OS keychain (via `keyring`) -- set by `portctl auth login`
2. `PORT_CLIENT_ID` + `PORT_CLIENT_SECRET` environment variables -- for CI/CD
3. Fernet-encrypted file at `~/.portctl/credentials` -- headless Linux fallback
4. `~/.portctl/config.yaml` inline credentials -- last resort, not recommended

## Git Conventions

- **Conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- **Branch naming**: `feature/VAK-XXX-short-description`, `fix/VAK-XXX-short-description`
- **PR descriptions**: summary of changes, test plan, breaking change notes
- Squash merge to main

## Common Commands Quick Reference

```bash
# development
uv sync                                      # install/update deps
uv run portctl --help                        # run CLI
uv run pytest tests/unit/ -x --tb=short      # run unit tests
uv run ruff check src/ tests/                # lint
uv run ruff format src/ tests/               # format
uv run mypy src/portctl/                     # type check

# full quality check
uv run ruff check src/ tests/ && uv run mypy src/portctl/ && uv run pytest tests/unit/ -x --tb=short
```

## Port API Basics

- Base URL: `https://api.getport.io/v1`
- Auth: POST `/auth/access_token` with `client_id` + `client_secret` -> JWT
- Blueprints: GET/POST/PUT/DELETE `/blueprints/{identifier}`
- Scorecards: GET/POST/PUT/DELETE `/blueprints/{blueprint}/scorecards/{identifier}`
- Actions: GET/POST/PUT/DELETE `/blueprints/{blueprint}/actions/{identifier}`
- Pages: GET/POST/PUT/DELETE `/pages/{identifier}`
- All responses follow `{ "ok": true, "blueprint": {...} }` pattern
