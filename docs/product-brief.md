# portctl — Product Brief v0.1

> Last updated: 2026-03-16
> Status: Draft — Ring-1 (MVP)
> Author: Product Manager

---

## Table of Contents

1. [Product Purpose and Vision](#1-product-purpose-and-vision)
2. [Target Users](#2-target-users)
3. [Core Value Proposition](#3-core-value-proposition)
4. [Success Metrics](#4-success-metrics)
5. [MVP Scope — Ring-1](#5-mvp-scope--ring-1)
6. [User Stories with Acceptance Criteria](#6-user-stories-with-acceptance-criteria)
7. [Non-functional Requirements](#7-non-functional-requirements)
8. [Definition of Done](#8-definition-of-done)
9. [Risk and Dependencies](#9-risk-and-dependencies)

---

## 1. Product Purpose and Vision

### What is portctl?

`portctl` is a GitOps CLI for [Port.io](https://getport.io) — the internal developer portal platform. It allows platform engineers and DevOps teams to manage their Port organization's configuration (blueprints, scorecards, actions, and entities) as code, stored in version control, and applied through a familiar plan/apply workflow.

Port.io is a powerful developer portal, but today its configuration lives almost entirely in the Port UI. There is no sanctioned way to:

- Track blueprint and scorecard changes in git
- Diff the desired state against what is live in Port
- Apply configuration changes safely, with a preview step
- Bootstrap a new Port org from a declarative config file
- Integrate Port configuration changes into a CI/CD pipeline

`portctl` fills this gap. It gives platform engineers a CLI that speaks Port's API, understands Port's data model, and applies GitOps discipline to the developer portal layer of an organization's infrastructure.

### Vision

> Every Port.io resource — blueprints, scorecards, actions, entities — should be expressible as a file in a git repository, reviewable as a pull request, and applicable through a repeatable CLI command.

The long-term vision is for `portctl` to be to Port.io what `kubectl` is to Kubernetes and what `terraform` is to cloud infrastructure: the authoritative CLI for managing a developer portal as code.

---

## 2. Target Users

### Primary Persona: Platform Engineer

- Works at a company that uses Port.io as its internal developer portal
- Manages blueprints, scorecards, and actions for 10–200+ developer teams
- Comfortable in the terminal; uses kubectl, terraform, or similar tools daily
- Frustrated by manual Port UI changes that are not tracked, reviewable, or reproducible
- Wants to include Port configuration in existing GitOps pipelines (GitHub Actions, ArgoCD, etc.)

**Workflow today:** Log in to Port UI, manually edit blueprints, lose track of what changed and when, struggle to replicate config across staging and production Port orgs.

**Workflow with portctl:** `portctl export` pulls current Port state into YAML files, engineer modifies files, `portctl plan` shows what will change, `portctl apply` pushes the changes via API. All changes live in git.

### Secondary Persona: DevOps / Infrastructure Engineer

- Sets up and maintains CI/CD pipelines
- Needs portctl to run headlessly with a service account token
- Wants a `--dry-run` / plan step in the pipeline before applying changes to production Port orgs

### Tertiary Persona: Port.io Solutions Engineer / Customer Success

- Onboards new customers onto Port.io
- Uses portctl to scaffold a standard starting configuration for a new org
- Needs `portctl export` to capture a customer's existing setup as a reproducible config artifact

---

## 3. Core Value Proposition

### The pitch: "kubectl for your developer portal"

| Without portctl | With portctl |
|---|---|
| Blueprint changes happen in the UI, undocumented | Blueprint changes are YAML files in git, reviewed in PRs |
| No way to diff desired vs. actual state | `portctl plan` shows an exact diff before any change |
| Copy-pasting config between staging and production orgs | `portctl apply --target-org prod` applies the same config |
| Onboarding a new Port org takes hours of clicking | `portctl apply` from a scaffold takes minutes |
| CI/CD pipelines cannot gate on Port config drift | `portctl plan --exit-code` returns non-zero on drift |

### Why now?

Port.io has reached sufficient maturity that enterprise customers are managing complex configurations with dozens of blueprints and scorecards. The lack of GitOps tooling is becoming a meaningful barrier to adoption for infrastructure-mature teams.

---

## 4. Success Metrics

### v0.1 (Ring-1 — MVP)

- A platform engineer can run `portctl export` on a real Port org and get valid YAML files representing all blueprints and scorecards
- A platform engineer can run `portctl plan` and see a human-readable diff of what would change
- A platform engineer can run `portctl apply` and have the changes reflected in Port within 5 seconds per resource
- Auth flow works: `portctl auth login` produces a stored credential; `portctl auth status` confirms validity
- Zero crashes on the happy path; all errors surface a clear message and non-zero exit code
- The tool installs via a single command (Homebrew or `go install`)

### v0.5

- At least 3 external platform engineers have used portctl in a real Port org and reported the plan/apply loop as "correct"
- CI mode works: portctl runs headlessly with a `PORTCTL_TOKEN` environment variable
- At least 1 customer has `portctl apply` running in a GitHub Actions pipeline
- Blueprint validation catches at least 80% of common schema errors before an API call is made

### v1.0

- portctl is the recommended configuration-as-code tool in Port.io's official documentation
- Supports full CRUD for blueprints, scorecards, actions, and pages
- A community registry of scaffold templates exists
- The plan output is stable enough to be used as a CI gate (non-zero exit code on drift)

---

## 5. MVP Scope — Ring-1

### IN scope for Ring-1

| # | Feature | Command |
|---|---|---|
| 1 | Project scaffold | `portctl init` |
| 2 | Config loader | Internal — reads YAML config from the working directory |
| 3 | Port API client | Internal — authenticated HTTP client wrapping Port REST API |
| 4 | Auth login / status | `portctl auth login`, `portctl auth status` |
| 5 | Org list | `portctl org list` |
| 6 | Export blueprints and scorecards | `portctl export` |
| 7 | Layer 1 validation | `portctl validate` — schema-level checks before any API call |
| 8 | Plan command | `portctl plan` — diff desired vs. live state |
| 9 | Apply command | `portctl apply` — push desired state to Port |
| 10 | Blueprint show | `portctl blueprint show <identifier>` |

### OUT of scope for Ring-1

- Actions management (create, update, delete Port actions)
- Pages management
- Entity management (software catalog items)
- Multi-org apply in a single command
- Rollback / undo
- Secrets or sensitive field handling
- State file (no local state cache — all reads go live to the API)
- Plugin or extension system
- Web dashboard or TUI
- Windows support (Ring-1 targets macOS and Linux only)
- Port webhooks configuration
- Team and permission management

---

## 6. User Stories with Acceptance Criteria

---

### US-001: Project Scaffold [P0, Size: S]

**As a** platform engineer setting up portctl for the first time,
**I want to** run a single command that creates a valid portctl project directory structure,
**so that** I have a known starting point with the correct file layout and a config file I can fill in.

**Acceptance Criteria:**

- `portctl init` creates a `portctl.yaml` config file in the current directory
- `portctl init` creates a `blueprints/` subdirectory and a `scorecards/` subdirectory
- `portctl init` is idempotent: running it a second time does not overwrite existing files; it prints a warning for each file that already exists
- `portctl init` accepts an optional `--org <org-id>` flag that pre-populates the org field in `portctl.yaml`
- Running `portctl init` in a non-empty directory does not delete any existing files
- The generated `portctl.yaml` contains inline comments explaining each field
- `portctl init` exits 0 on success

---

### US-002: Config Loader [P0, Size: S]

**As a** platform engineer,
**I want** portctl to automatically find and parse the `portctl.yaml` configuration file from the current directory or any parent directory,
**so that** I can run portctl commands from anywhere within my project tree without specifying a config path.

**Acceptance Criteria:**

- portctl searches for `portctl.yaml` starting from the current working directory, walking up to the filesystem root
- If no config file is found, portctl prints a clear error: "no portctl.yaml found in current directory or any parent" and exits non-zero
- Config file specifies at minimum: `org` (Port org ID) and `port_api_url` (defaults to `https://api.getport.io`)
- A `--config <path>` flag overrides the automatic search and uses the specified file
- If the config file is found but is invalid YAML, portctl prints a parse error with the line number and exits non-zero
- Environment variable `PORTCTL_CONFIG` overrides the automatic search (lower priority than `--config` flag)

---

### US-003: Port API Client [P0, Size: M]

**As a** portctl developer,
**I want** a well-encapsulated Port API client that handles authentication, base URL, retries, and error parsing,
**so that** all commands share a single, correct HTTP layer without duplication.

**Acceptance Criteria:**

- The client attaches the Bearer token to every request automatically
- The client respects the `port_api_url` from config (enables pointing at Port staging environments)
- On HTTP 401 or 403, the client returns a structured auth error and prints a human-readable message: "Authentication failed — run `portctl auth login`"
- On HTTP 429 (rate limit), the client retries with exponential backoff, up to 3 attempts, before returning an error
- On HTTP 5xx, the client retries once before returning the error
- All API errors include the Port API error body in the structured error returned to the caller
- The client is testable: it accepts an injectable HTTP transport so tests can mock the Port API without network calls
- The client never logs the Bearer token to stdout or any log file

---

### US-004: Auth Login / Status [P0, Size: S]

**As a** platform engineer,
**I want to** authenticate portctl against my Port organization using my Port credentials or a client secret,
**so that** all subsequent commands operate on my org without me re-entering credentials each time.

**Acceptance Criteria:**

- `portctl auth login` prompts for Port Client ID and Client Secret (input is masked)
- `portctl auth login` exchanges the credentials for a JWT via Port's OAuth2 client credentials flow
- On success, the token and expiry are stored in `~/.portctl/credentials` with file permissions `0600`
- `portctl auth login --client-id <id> --client-secret <secret>` accepts credentials as flags (for CI use; secret is never echoed to stdout)
- `portctl auth status` prints: org ID, token expiry timestamp, and "valid" or "expired" status
- `portctl auth status` exits non-zero if no credentials are stored or if the stored token is expired
- If `PORTCTL_TOKEN` environment variable is set, it takes precedence over stored credentials and no file I/O for auth is performed
- Credentials file is never included in git (portctl init adds `.portctl/` to `.gitignore`)

---

### US-005: Org List [P0, Size: XS]

**As a** platform engineer,
**I want to** see which Port organizations my credentials have access to,
**so that** I can confirm I am authenticated to the correct org before running plan or apply.

**Acceptance Criteria:**

- `portctl org list` prints a table with columns: Org ID, Org Name
- The org currently configured in `portctl.yaml` is marked with a `*` indicator
- If credentials are missing or expired, the command fails with a clear auth error and exits non-zero
- `portctl org list --output json` prints the list as a JSON array suitable for scripting
- Command completes in under 3 seconds on a standard internet connection

---

### US-006: Export Blueprints and Scorecards [P0, Size: M]

**As a** platform engineer,
**I want to** export all blueprints and scorecards from a live Port org into local YAML files,
**so that** I can put the current Port configuration under version control and use it as the starting point for future plan/apply cycles.

**Acceptance Criteria:**

- `portctl export` fetches all blueprints from the configured org via the Port API and writes one YAML file per blueprint to `blueprints/<identifier>.yaml`
- `portctl export` fetches all scorecards and writes one YAML file per scorecard to `scorecards/<identifier>.yaml`
- Exported YAML files are valid portctl resource files (can be immediately fed back to `portctl plan` without modification)
- `portctl export --blueprints-only` exports only blueprints; `--scorecards-only` exports only scorecards
- If a local file for a resource already exists, portctl prompts before overwriting; `--force` flag skips the prompt
- `portctl export` prints a summary line: "Exported N blueprints, M scorecards"
- Exported files use consistent YAML formatting (deterministic field ordering) so re-exporting the same org produces identical files
- Command exits non-zero if any API call fails; partial exports are reported with a warning listing which resources failed

---

### US-007: Layer 1 Validation [P0, Size: M]

**As a** platform engineer,
**I want** portctl to validate my local YAML files against the Port resource schema before making any API calls,
**so that** I catch structural and type errors locally, without consuming API rate limits or causing partial applies.

**Acceptance Criteria:**

- `portctl validate` reads all YAML files from `blueprints/` and `scorecards/` and validates them against the portctl schema
- Validation checks at minimum: required fields present, field types correct, identifier format valid (alphanumeric + hyphens, no spaces), relations reference identifiers that exist in the local blueprint set
- Each validation error is reported with: file path, line number (where determinable), field name, and human-readable error message
- `portctl validate` exits 0 if all files pass, exits non-zero if any file fails, with a summary count of errors
- `portctl validate` runs automatically as the first step of `portctl plan` and `portctl apply`; if validation fails, neither command proceeds
- A file with no `kind` field produces the error: "missing required field 'kind'"
- Unknown top-level fields produce a warning (not an error) to allow forward-compatibility

---

### US-008: Plan Command [P0, Size: L]

**As a** platform engineer,
**I want to** see a diff of what portctl would change in my Port org before any changes are made,
**so that** I can review the impact of my local config changes and catch mistakes before they affect live systems.

**Acceptance Criteria:**

- `portctl plan` reads all local YAML files, fetches the current state from the Port API, and prints a diff
- The plan output uses a +/- format: lines to be added are prefixed with `+` (green), lines to be removed prefixed with `-` (red), unchanged context lines shown without prefix
- Each changed resource is shown as a separate diff block with a header: `~ Blueprint: <identifier>` (modify), `+ Blueprint: <identifier>` (create), `- Blueprint: <identifier>` (delete)
- Resources present in Port but absent from local files are shown as deletions only if `--prune` flag is passed; otherwise they are shown as a warning: "N resources in Port not managed by portctl"
- `portctl plan` exits 0 if there are no changes, exits with code 2 if there are changes (suitable for CI gates)
- `portctl plan --output json` emits a machine-readable JSON plan object
- Plan runs validation (US-007) first; if validation fails, plan exits non-zero without fetching from API
- Plan completes in under 10 seconds for an org with up to 50 blueprints and 20 scorecards
- Plan never modifies any local file or any Port resource

---

### US-009: Apply Command [P0, Size: L]

**As a** platform engineer,
**I want to** apply my local portctl configuration to my Port org,
**so that** the live Port org reflects exactly what is defined in my YAML files.

**Acceptance Criteria:**

- `portctl apply` runs validation and plan internally; if the plan produces no changes, it prints "Nothing to apply" and exits 0
- Before making any API calls, `portctl apply` prints the plan output and prompts: "Apply these changes? [y/N]"; `--auto-approve` flag skips the prompt
- `portctl apply` creates resources that exist locally but not in Port
- `portctl apply` updates resources that differ between local state and Port
- `portctl apply` does NOT delete resources present in Port but absent locally, unless `--prune` flag is passed (with an additional confirmation prompt)
- Each resource operation is logged as it completes: `Applied blueprint <identifier> (created | updated)`
- If any individual resource operation fails, portctl continues applying remaining resources, then prints a summary of all failures and exits non-zero
- `portctl apply` prints a final summary: "Applied: N created, M updated, P deleted, Q failed"
- `portctl apply` is safe to run repeatedly — applying with no local changes produces no API calls after the plan step

---

### US-010: Blueprint Show [P1, Size: S]

**As a** platform engineer,
**I want to** inspect the current live definition of a specific blueprint in my Port org,
**so that** I can quickly check what a blueprint looks like in Port without opening the UI.

**Acceptance Criteria:**

- `portctl blueprint show <identifier>` fetches the blueprint with the given identifier from the Port API and prints it as formatted YAML
- If the identifier does not exist in Port, the command prints: "Blueprint '<identifier>' not found in org <org-id>" and exits non-zero
- `portctl blueprint show <identifier> --output json` prints the raw Port API JSON response
- The YAML output matches the format that portctl would accept as an input file (round-trip compatible)
- Command completes in under 3 seconds on a standard internet connection
- `portctl blueprint show` without an identifier prints usage help and exits non-zero

---

## 7. Non-functional Requirements

### Performance

- `portctl plan` completes in under 10 seconds for orgs with up to 50 blueprints and 20 scorecards
- `portctl apply` for a set of 10 resources completes in under 30 seconds
- All read-only commands (`show`, `list`, `status`) complete in under 3 seconds
- portctl startup time must not exceed 1 second

### Security

- The Bearer token is never written to stdout, log files, or shell history
- The credentials file (`~/.portctl/credentials`) must be created with permissions `0600` and portctl must refuse to use it if permissions are wider
- No credentials are stored in `portctl.yaml` or any project-level file
- `portctl.yaml` and all resource YAML files must be safe to commit to a public repository
- portctl must not make any network calls except to the configured `port_api_url`
- All HTTPS connections must verify TLS certificates; there is no `--insecure` flag in Ring-1

### UX Standards

- Every command that fails must exit non-zero
- Every error message must include: what went wrong, what the user can do about it
- `portctl --help` and `portctl <command> --help` must be available for all commands and subcommands
- Output intended for humans is written to stdout; progress/status messages are written to stderr, so piping works correctly
- Colors and emoji are used only when stdout is a TTY; piped/redirected output is always plain text
- `portctl version` prints the binary version, git commit SHA, and build date

### Compatibility

- Supports macOS (arm64 and amd64) and Linux (amd64 and arm64)
- Windows is out of scope for Ring-1
- Requires Python 3.11+ runtime
- Installable via pip: `pip install portctl`

---

## 8. Definition of Done

A story is done when ALL of the following are true:

1. **Acceptance criteria met** — every AC listed in the story passes
2. **Code passes checks** — `ruff check` and `mypy --strict` exit 0 with no warnings
3. **Unit tests pass** — all existing and new tests pass; new business logic has test coverage
4. **Integration test exists** — at least one test exercises the command end-to-end against a mocked Port API
5. **Error paths tested** — auth failure, API error, missing config, and invalid YAML are each covered by a test
6. **Help text written** — `portctl <command> --help` shows accurate, useful help
7. **No secrets in code** — no hardcoded tokens, client IDs, or org IDs in source or tests
8. **Tech lead reviewed** — code has been reviewed and approved by the tech lead agent
9. **Changelog entry** — a CHANGELOG entry is added under the upcoming version section
10. **Manual smoke test** — the engineer has run the command against a real (staging) Port org and it behaved correctly

---

## 9. Risk and Dependencies

### External Dependencies

| Dependency | Risk | Mitigation |
|---|---|---|
| Port REST API stability | Port may change API endpoints or response shapes between versions | Pin to a specific API version header; add integration tests against the real API in CI |
| Port OAuth2 token flow | The client credentials flow may change or be restricted | Document the exact flow; test token refresh path; support `PORTCTL_TOKEN` env var as an escape hatch |
| Port API rate limits | Aggressive use of `export` or `plan` on large orgs could hit rate limits | Implement exponential backoff (US-003 AC); add `--concurrency` flag in Ring-2 |

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Port API does not expose all blueprint fields needed for round-trip fidelity | Medium | High — export/apply cycle would silently lose fields | Validate round-trip completeness against a real Port org in Ring-1; document known field gaps |
| YAML serialization produces non-deterministic field ordering | Low | Medium — noisy diffs in plan output | Use a deterministic YAML serializer; enforce canonical field order in tests |
| Port API lacks a bulk update endpoint; N+1 API calls per apply | High | Medium — slow apply for large orgs | Parallelize apply calls in Ring-2; document expected apply time per resource in Ring-1 |
| Blueprint relation dependencies require apply ordering | Medium | High — applying a blueprint before its relation target exists will fail | Topological sort resources by dependency order before applying |

### Business Risks

| Risk | Mitigation |
|---|---|
| Port.io ships an official CLI that supersedes portctl | Monitor Port.io roadmap; position portctl as complementary or contribute upstream |
| Platform engineers distrust automated apply to production portals | Default to no `--prune`; require explicit `--auto-approve`; plan step is mandatory |
| YAML config drift between team members causes conflict | Recommend one `portctl.yaml` per org managed by a single CI pipeline |

### Domain Notes

- Port.io uses a **client credentials** OAuth2 flow (not authorization code). Tokens are short-lived JWTs.
- Port blueprints have **relations** that reference other blueprint identifiers. Apply order matters — a blueprint that is a relation target must be applied before the blueprint that references it.
- Port **scorecards** reference blueprint identifiers. A scorecard cannot be applied if its target blueprint does not exist in Port.
- Port API base URL is `https://api.getport.io/v1`. The `/v1` path prefix is part of all endpoints.
- Blueprint identifiers in Port are globally unique within an org, alphanumeric with hyphens, and case-sensitive.
- The Port API returns `404` (not `403`) for resources that exist but the caller does not have access to — treat 404 as "not found or not authorized."
- Port has a concept of **protected blueprints** that cannot be deleted via the API. `portctl apply --prune` must handle this gracefully.

---

*End of Product Brief v0.1*
