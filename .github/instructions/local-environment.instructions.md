---
applyTo: '**'
description: 'Local shell environment: Azure, Databricks CLI, mise toolchain, and auth conventions'
---

# Local Shell Environment

This session has authenticated access to Azure and Azure Databricks. Follow
these conventions when running CLI commands or writing automation that targets
the cloud.

## Toolchain (mise)

Tools are managed by [mise](https://mise.jdx.dev/). The project `mise.toml`
pins Python 3.12; the user-level `~/.config/mise/config.toml` provides
additional tools. Key tools available:

| Tool | Version | Notes |
|------|---------|-------|
| `databricks` | 0.296.0 | Databricks CLI, installed via `mise` as `databricks-cli` |
| `python` | 3.12 | Project default (pinned in `mise.toml`) |
| `az` | (system) | Azure CLI — already authenticated |
| `azd` | 1.23.15 | Azure Developer CLI |
| `uv` | (system) | Python package manager — **always** use instead of `pip` |

Do **not** install tools with `apt`, `brew`, or manual downloads when mise
already provides them.

## Authentication

### Azure CLI (`az`)

* The Azure CLI is already authenticated (`az account show` works).
* Use `az` for any Azure resource operations (Key Vault, Storage, RBAC, etc.).

### Databricks CLI — Always Use Azure CLI Auth

The Databricks CLI **must** authenticate via the Azure CLI token. Never use
PATs, OAuth M2M tokens, or `databricks auth login` interactively.

**How it works:** The `~/.databrickscfg` profiles set `auth_type = databricks-cli`,
which delegates to the Azure CLI token automatically when `az` is logged in.

**Available profiles** (defined in `~/.databrickscfg`):

| Profile | Use |
|---------|-----|
| `dev` | Development workspace (default) |
| `mcaps01` | Same workspace, alternate profile name |

Workspace host URLs are resolved from `~/.databrickscfg` at runtime — never hardcode them in scripts, instructions, or config files. To discover the current host, read it from the profile:

```bash
databricks -p dev auth env | grep DATABRICKS_HOST
```

**Usage patterns:**

```bash
# Explicit profile (preferred)
databricks -p dev workspace list /
databricks -p dev jobs list

# Or set env var for a session
export DATABRICKS_CONFIG_PROFILE=dev
databricks workspace list /
```

**Do NOT:**
- Use `databricks auth login` or `databricks configure --token`
- Store or reference personal access tokens (PATs)
- Hardcode workspace URLs — use the profile name

### Environment Variables

When running Databricks CLI commands or deploying bundles, prefer setting
the profile via `DATABRICKS_CONFIG_PROFILE` rather than repeating `-p` on
every command:

```bash
export DATABRICKS_CONFIG_PROFILE=dev
databricks bundle validate
databricks bundle deploy -t dev
```

## Databricks Compute — Serverless Default

**Serverless compute is the default.** When creating or configuring:

* **Jobs / Workflows** — do not specify a cluster; they run on serverless by default
* **Notebooks** — attach to serverless compute unless a specific runtime is required
* **DABs job definitions** — omit `existing_cluster_id` and `new_cluster` blocks to use serverless; only add cluster config when serverless is insufficient (e.g., init scripts, custom libs, GPU)
* **SQL Warehouses** — use serverless SQL warehouses

If a task explicitly requires a classic or job cluster (init scripts, custom
Docker, GPU), document the reason in a code comment.

### Serverless Python Version Constraint

Databricks serverless compute uses **environment versions** to determine the
Python runtime. The project requires Python 3.12 (per `databricks/.python-version`).

| Environment Version | Python | Databricks Connect | Use |
|---------------------|--------|-------------------|-----|
| 1 | 3.10.12 | 14.3 | ❌ Too old |
| 2 | 3.11.10 | 15.4 | ❌ Too old |
| **3** | **3.12.3** | **16.4** | ✅ Minimum supported |
| **4** | **3.12.3** | **17.3** | ✅ Recommended |
| **5** | **3.12.3** | **18** | ✅ Latest |

**Always specify `client: "3"` or higher** in environment specs for serverless
jobs to get Python 3.12. Example for job submission:

```json
"environments": [{
  "environment_key": "default",
  "spec": {
    "client": "3",
    "dependencies": ["<wheel-path>"]
  }
}]
```

* `pyproject.toml` sets `requires-python = ">=3.12"` — matching `databricks/.python-version`
* `ruff` is configured with `target-version = "py310"` for broad lint compatibility,
  but the code targets 3.12 features
* Use `from __future__ import annotations` in all modules for forward-compatible
  type hints

### Wheel Packaging with uv

The `ap_je_flow` package is built as a wheel and installed on serverless
compute via the DABs `artifacts` section:

```yaml
# databricks/databricks.yml
artifacts:
  ap_je_flow_whl:
    type: whl
    path: ./src
    build: "uv build --wheel --out-dir dist"
```

* **Always use `uv build`** to build the wheel — never `pip wheel` or raw
  `python setup.py bdist_wheel`
* The wheel is uploaded automatically by `databricks bundle deploy`
* Serverless jobs reference the wheel via an `environment_key` with the
  wheel path in `spec.dependencies`
* No `setup.py` is needed — `uv` uses `pyproject.toml` directly

## Databricks Asset Bundles (DABs)

Bundle operations should always specify the target:

```bash
# Validate
databricks bundle validate -t dev

# Deploy
databricks bundle deploy -t dev

# Run a specific job
databricks bundle run -t dev <job-name>
```

Bundle config lives in `databricks/databricks.yml`. See
[databricks-notebooks.instructions.md](.github/instructions/databricks-notebooks.instructions.md)
for notebook and job conventions, environment promotion strategy, and variable
definitions per target.

## Quick Reference

```bash
# Check Azure auth
az account show

# Check Databricks CLI auth
databricks -p dev auth env

# List workspace contents
databricks -p dev workspace list /Repos

# Validate bundle
cd databricks && databricks bundle validate -t dev

# Deploy bundle
cd databricks && databricks bundle deploy -t dev

# Run tests locally
cd databricks && uv run pytest tests/unit -v

# Lint
cd databricks && uv run ruff check src notebooks
```

## Stage Completion Criteria

A pipeline stage (phase) is **not done** until it has been:

1. **Unit tested locally** — `make test` passes with all new and existing tests green
2. **Linted locally** — `make lint` passes clean
3. **Deployed to Azure Databricks** — bundle deployed via `databricks bundle deploy -t dev`
4. **Executed in the cloud** — the notebook or job has been run on the Azure Databricks workspace and completed with **zero errors**
5. **Output verified** — intermediate results reviewed (row counts, balances, checkpoint values) and confirmed correct

Only after all five criteria are met should a stage be marked as ✅ DONE in the plan checklist. Local-only validation is insufficient — cloud execution is the definitive proof of correctness.
