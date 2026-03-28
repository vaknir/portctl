# portctl

GitOps CLI for [Port.io](https://www.getport.io/) -- manage your developer portal configuration as versioned YAML in git.

`portctl` works like `kubectl` or `terraform` for your Port.io portal: pull live config to local YAML files, review changes with a diff, push updates back, and detect drift -- all from your terminal or CI pipeline.

## Features

- **Pull / Push workflow** -- export portal config (blueprints, scorecards, actions, pages) to YAML, edit locally, push back
- **Dry-run diffs** -- see exactly what will change before applying
- **Drift detection** -- audit live portal state against your last-applied snapshot
- **Validation pipeline** -- local schema checks plus optional remote API validation
- **Rollback** -- restore any previous configuration state
- **Multi-org support** -- manage multiple Port.io organizations from one config
- **Secure credentials** -- OS keychain first, env vars for CI, encrypted file fallback
- **Rich terminal UI** -- tables, trees, progress bars, syntax-highlighted YAML

## Quick Start

```bash
# Install
pip install portctl
# or
uv tool install portctl

# Initialize a new project
portctl init

# Authenticate
portctl auth login

# Pull portal config to local YAML files
portctl pull

# Edit YAML files in your editor, then preview changes
portctl diff

# Push changes to Port.io
portctl push
```

## Command Reference

### Setup

| Command | Description |
|---|---|
| `portctl init` | Initialize a new portctl project (interactive wizard) |
| `portctl auth login` | Authenticate with Port.io credentials |
| `portctl auth status` | Check authentication status |
| `portctl auth logout` | Clear stored credentials |
| `portctl org list` | List configured organizations |
| `portctl org add` | Add a new organization |
| `portctl org remove` | Remove an organization |

### Workflow

| Command | Description |
|---|---|
| `portctl pull` | Pull portal config from Port.io to local YAML |
| `portctl diff` | Show what would change (local vs remote) |
| `portctl push` | Push local YAML config to Port.io |
| `portctl validate` | Validate YAML syntax and schema |
| `portctl validate --remote` | Validate against the Port.io API |
| `portctl audit` | Detect configuration drift |
| `portctl rollback --to <event-id>` | Restore to a previous state |

### Utilities

| Command | Description |
|---|---|
| `portctl whoami` | Show current auth and org info |
| `portctl blueprint show <name>` | Interactive blueprint inspector |
| `portctl history` | View apply/export event log |
| `portctl seed` | Seed demo data for testing |

### Global Options

```
-V, --version   Show version and exit
-v, --verbose   Enable debug logging
--help          Show help for any command
```

## Configuration

portctl stores its configuration in `~/.portctl/`:

```
~/.portctl/
  config.yaml       # Organizations, default org, preferences
  state.yaml        # Last-applied snapshots per org per resource
  credentials       # Encrypted credentials (fallback)
```

### Config File

```yaml
# ~/.portctl/config.yaml
default_org: my-org
orgs:
  my-org:
    client_id: your-port-client-id
    # client_secret resolved via keyring, env var, or credentials file
```

### Credential Resolution

Credentials are resolved in this order:

1. **OS keychain** (via `keyring`) -- set by `portctl auth login`
2. **Environment variables** -- `PORT_CLIENT_ID` + `PORT_CLIENT_SECRET` (for CI/CD)
3. **Encrypted file** -- `~/.portctl/credentials` (headless Linux fallback)
4. **Config file** -- `~/.portctl/config.yaml` inline (not recommended)

### .portctlignore

Create a `.portctlignore` file in your project root to exclude resources from pull/push operations, using gitignore-style patterns.

## GitOps Workflow

The typical workflow for managing portal configuration with `portctl`:

```
1. portctl pull          # Export live config to YAML files
2. git checkout -b feat  # Branch for changes
3. (edit YAML files)     # Make changes in your editor
4. portctl validate      # Check syntax and schema locally
5. portctl diff          # Review what will change
6. git commit & push     # Version control your changes
7. portctl push          # Apply changes to Port.io (via CI or locally)
```

In CI, use environment variables for authentication:

```bash
export PORT_CLIENT_ID="..."
export PORT_CLIENT_SECRET="..."
portctl validate --remote && portctl push
```

## Development

Requires Python 3.11+.

```bash
# Clone and install
git clone https://github.com/vaknir/portctl.git
cd portctl
uv sync

# Run the CLI
uv run portctl --help

# Run tests
uv run pytest tests/unit/ -x --tb=short

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Type check
uv run mypy src/portctl/

# Full quality check
uv run ruff check src/ tests/ && uv run mypy src/portctl/ && uv run pytest tests/unit/ -x --tb=short
```

## Contributing

See [docs/contributing.md](docs/contributing.md) for development guidelines, code standards, and pull request process.

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
