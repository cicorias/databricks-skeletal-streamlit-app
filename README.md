# Databricks Sales Review POC

End-to-end proof of concept: parquet files in a Volume → materialized views → 
Serverless SQL Warehouse → Streamlit approval app.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            Unity Catalog (dev.default)                          │
│                                                                                 │
│  ┌──────────────────────────── BATCH ─────────────────────────────────────┐     │
│  │                                                                        │     │
│  │   /Volumes/dev/default/raw_data/sales/                                 │     │
│  │   ┌──────────┐ ┌──────────┐ ┌──────────┐                               │     │
│  │   │ 2024_01  │ │ 2024_02  │ │  . . .   │  ◄── parquet files land       │     │
│  │   │ .parquet │ │ .parquet │ │          │      (manual / ETL / trigger) │     │
│  │   └────┬─────┘ └────┬─────┘ └────┬─────┘                               │     │
│  │        └─────────────┼───────────┘                                     │     │
│  │                      ▼                                                 │     │
│  │        ┌─────────────────────────┐                                     │     │
│  │        │      sales_raw          │  Delta table                        │     │
│  │        │  read_files() / COPY    │  (ingested from volume)             │     │
│  │        └────────────┬────────────┘                                     │     │
│  │                     │                                                  │     │
│  │           REFRESH MATERIALIZED VIEW                                    │     │
│  │           (02_refresh_job.py — scheduled)                              │     │
│  │                     │                                                  │     │
│  │          ┌──────────┴──────────┐                                       │     │
│  │          ▼                     ▼                                       │     │
│  │  ┌──────────────────┐  ┌───────────────────┐                           │     │
│  │  │ mv_monthly_      │  │ mv_rep_           │  Materialized views       │     │
│  │  │ summary          │  │ leaderboard       │  (pre-aggregated)         │     │
│  │  └────────┬─────────┘  └────────┬──────────┘                           │     │
│  │           └──────────┬──────────┘                                      │     │
│  └──────────────────────┼─────────────────────────────────────────────────┘     │
│                         │                                                       │
│  ┌──────────────────────┼──── REAL-TIME (transactional) ──────────────────┐     │
│  │                      │                                                 │     │
│  │          ┌───────────┴──────────────┐   ┌────────────────────────┐     │     │
│  │          │  workflow       (Delta)  │   │  workflow_steps (Delta)│     │     │
│  │          │  CDF enabled for audit   │◄─►│  one row per step      │     │     │
│  │          └───────────┬──────────────┘   └───────────┬────────────┘     │     │
│  │                      └──────────┬───────────────────┘                  │     │
│  │                                 ▼                                      │     │
│  │                   ┌──────────────────────────┐                         │     │
│  │                   │  vw_workflow_audit (VIEW) │  live JOIN             │     │
│  │                   │  always current           │  (not materialized)    │     │
│  │                   └─────────────┬────────────┘                         │     │
│  └─────────────────────────────────┼──────────────────────────────────────┘     │
│                                    │                                            │
└────────────────────────────────────┼────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼─────────────────┐
                    │   Serverless SQL Warehouse       │
                    │   (Photon engine, pay-per-query) │
                    └────────────────┬─────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
   ┌───────────────────┐  ┌──────────────────┐  ┌───────────────────┐
   │   Dashboard       │  │   Review Queue   │  │   Audit Log       │
   │  reads MVs        │  │  reads + writes  │  │  reads live view  │
   │  (batch-fresh)    │  │  workflow Delta  │  │  (always current) │
   └───────────────────┘  └──────────────────┘  └───────────────────┘
              └──────────────────────┼──────────────────────┘
                                     │
                         Streamlit App (Databricks Apps)
```

### Why each piece

| Component | Why |
|---|---|
| **Volume** | Managed, governed storage in Unity Catalog |
| **External table** | No data copy — reads parquet in place |
| **Materialized view** | Pre-aggregated; app reads tiny result not raw rows |
| **Serverless SQL Warehouse** | ~2s cold start, Photon engine, pay-per-query |
| **Delta for workflow state** | ACID writes, full history, CDF for audit |
| **Streamlit on Databricks Apps** | Runs inside your workspace, uses same auth |

### Data flow — batch vs real-time

There are two independent data paths through the system (shown in the
diagram above). Sales analytics data moves through a **batch** pipeline
on a schedule. Workflow state is **transactional** — written and read in
real time by the Streamlit app.

#### Layer-by-layer update mechanics

| Layer | Medallion | Type | How it updates | Freshness |
|-------|-----------|------|----------------|-----------|
| **Volume** (`raw_data/sales/`) | 🥉 Bronze | Storage | New parquet files are dropped (manually, by an ETL job, or a file-arrival trigger) | Whenever files land |
| **`sales_raw`** (Delta table) | 🥈 Silver | Ingestion | Initial load: `CREATE TABLE … AS SELECT * FROM read_files(…)`. Incremental: use `COPY INTO` or Auto Loader to pick up new files without re-scanning old ones | Depends on ingestion cadence |
| **`mv_monthly_summary`** | 🥇 Gold | Batch aggregation | `REFRESH MATERIALIZED VIEW` — re-reads `sales_raw` and rebuilds the pre-aggregated result set. Triggered by the scheduled job (`02_refresh_job.py`) | Stale until next refresh |
| **`mv_rep_leaderboard`** | 🥇 Gold | Batch aggregation | Same — refreshed in the same scheduled job | Stale until next refresh |
| **`workflow`** | 🥈 Silver | Transactional | `INSERT` on submit, `UPDATE` on approve/reject — executed by `app/workflow.py` through the SQL Warehouse | Immediate (ACID) |
| **`workflow_steps`** | 🥈 Silver | Transactional | `INSERT` per step on submit, `UPDATE` when a reviewer acts | Immediate (ACID) |
| **`vw_workflow_audit`** | 🥇 Gold | Live view | Regular SQL `VIEW` (not materialized) — re-evaluated on every query by joining `workflow` ⟕ `workflow_steps` | Always current |

#### What is *not* real-time

The Dashboard page shows data that is only as fresh as the **last
materialized view refresh**. If new parquet files arrive at 10 AM
and the refresh job runs at 6 AM daily, the dashboard will not show
that data until the next 6 AM run (or until someone triggers a manual
`REFRESH MATERIALIZED VIEW`).

#### What *is* real-time

Everything on the Review Queue and Audit Log pages. When a reviewer
approves a record, the Delta table is updated immediately and the
next page load reflects the change — no pipeline or refresh needed.

---

## Setup — step by step

### 1. Generate sample parquet files (local)

```bash
cd data/
uv run python generate_parquet.py
# Creates parquet_output/sales_2024_01.parquet … sales_2025_12.parquet
```

### 2. Upload to Databricks Volume

```bash
# Create the volume (first time only)
databricks experimental aitools tools query \
  "CREATE VOLUME IF NOT EXISTS dev.default.raw_data" -p dev

# Upload parquet files
databricks fs cp data/parquet_output/ \
  dbfs:/Volumes/dev/default/raw_data/sales/ --recursive --overwrite -p dev
```

### 3. Run SQL setup

Create the table, materialized views, workflow tables, and audit view.
Adjust `dev.default` if using a different catalog/schema.

> **Note on `databricks experimental aitools tools query`:** This is a
> convenience wrapper around the stable
> [SQL Statement Execution API](https://docs.databricks.com/api/workspace/statementexecution/executestatement)
> (`POST /api/2.0/sql/statements`). It auto-discovers the warehouse
> and formats output. If the experimental command is removed in a
> future CLI release, replace with
> `databricks api post /api/2.0/sql/statements --json '{"warehouse_id":"<id>","statement":"...","wait_timeout":"30s"}'`.

```bash
# External table over the parquet files
databricks experimental aitools tools query "
  CREATE OR REPLACE TABLE dev.default.sales_raw AS
  SELECT * FROM read_files('/Volumes/dev/default/raw_data/sales/', format => 'parquet')
" -p dev

# Materialized view — monthly summary
databricks experimental aitools tools query "
  CREATE OR REPLACE MATERIALIZED VIEW dev.default.mv_monthly_summary AS
  SELECT
      year, month, region, product,
      COUNT(*)                        AS order_count,
      SUM(revenue)                    AS total_revenue,
      AVG(revenue)                    AS avg_order_value,
      SUM(CASE WHEN status = 'completed' THEN revenue ELSE 0 END) AS completed_revenue,
      SUM(CASE WHEN status = 'refunded'  THEN revenue ELSE 0 END) AS refunded_revenue,
      COUNT(DISTINCT sales_rep)       AS active_reps
  FROM dev.default.sales_raw
  GROUP BY year, month, region, product
" -p dev

# Materialized view — rep leaderboard
databricks experimental aitools tools query "
  CREATE OR REPLACE MATERIALIZED VIEW dev.default.mv_rep_leaderboard AS
  SELECT
      sales_rep, year, month,
      COUNT(*)     AS orders,
      SUM(revenue) AS revenue,
      RANK() OVER (PARTITION BY year, month ORDER BY SUM(revenue) DESC) AS rank
  FROM dev.default.sales_raw
  WHERE status = 'completed'
  GROUP BY sales_rep, year, month
" -p dev

# Workflow tables
databricks experimental aitools tools query "
  CREATE TABLE IF NOT EXISTS dev.default.workflow (
      workflow_id STRING NOT NULL, record_ref STRING,
      current_step INT, total_steps INT, status STRING,
      submitted_by STRING, created_at TIMESTAMP, updated_at TIMESTAMP
  ) USING DELTA
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true',
                 'delta.feature.allowColumnDefaults' = 'supported')
" -p dev

databricks experimental aitools tools query "
  CREATE TABLE IF NOT EXISTS dev.default.workflow_steps (
      workflow_id STRING, step INT, role STRING, reviewer STRING,
      status STRING, comments STRING, acted_at TIMESTAMP
  ) USING DELTA
" -p dev

databricks experimental aitools tools query "
  CREATE TABLE IF NOT EXISTS dev.default.workflow_config (
      workflow_type STRING, step INT, role STRING
  ) USING DELTA
" -p dev

databricks experimental aitools tools query "
  INSERT INTO dev.default.workflow_config VALUES
      ('monthly_report', 1, 'manager'),
      ('monthly_report', 2, 'finance'),
      ('monthly_report', 3, 'director')
" -p dev

# Audit view
databricks experimental aitools tools query "
  CREATE OR REPLACE VIEW dev.default.vw_workflow_audit AS
  SELECT w.workflow_id, w.record_ref, w.status AS workflow_status,
         w.submitted_by, w.created_at, ws.step, ws.role, ws.reviewer,
         ws.status AS step_status, ws.comments, ws.acted_at
  FROM dev.default.workflow w
  JOIN dev.default.workflow_steps ws ON w.workflow_id = ws.workflow_id
  ORDER BY w.created_at DESC, ws.step
" -p dev
```

### 4. Create a Serverless SQL Warehouse

Databricks UI → **SQL Warehouses → Create**
- Type: **Serverless**
- Size: Small (fine for a POC)
- Auto-stop: 10 min
- Copy the **HTTP Path** (looks like `/sql/1.0/warehouses/abc123`)

### 5. Deploy the Streamlit app

#### a. Create the app (first time only)

```bash
databricks apps create streamlit-app -p dev --no-wait
```

#### b. Configure `app.yaml`

Edit `app.yaml` at the repo root with your SQL Warehouse HTTP path,
catalog, and schema. `DATABRICKS_HOST` and `DATABRICKS_TOKEN` are
injected automatically by the Databricks Apps platform.

```yaml
command:
  - "streamlit"
  - "run"
  - "app/app.py"
  - "--server.port=8000"
  - "--server.address=0.0.0.0"

env:
  - name: DATABRICKS_HTTP_PATH
    value: "/sql/1.0/warehouses/<your_warehouse_id>"
  - name: DATABRICKS_CATALOG
    value: "dev"
  - name: DATABRICKS_SCHEMA
    value: "default"
```

#### c. Upload source code and deploy

```bash
# Upload the project to the workspace source code path
databricks workspace import-dir . \
  /Workspace/Users/<your_user>/streamlit-app \
  --overwrite -p dev

# Deploy (creates a new snapshot deployment)
databricks apps deploy streamlit-app \
  --source-code-path /Workspace/Users/<your_user>/streamlit-app \
  -p dev
```

The deploy command will wait until the app is running. Once complete,
the app URL is shown in the output (also visible via `databricks apps get streamlit-app -p dev`).

### 6. Run locally (optional)

Run the Streamlit app on your machine while it queries the Databricks
SQL Warehouse in the cloud. Requires steps 1–4 to be complete.

#### Quick start (Makefile)

```bash
make install      # install deps into .venv
make env          # generate .env from your Databricks CLI profile
make dev          # start Streamlit on http://localhost:8000
```

Run `make help` for the full list of targets. The `PROFILE`, `CATALOG`,
`SCHEMA`, and `APP_PORT` variables are configurable:

```bash
make env PROFILE=mcaps01 CATALOG=prod SCHEMA=analytics
make dev APP_PORT=9000
```

#### Manual steps (if not using Make)

The app uses `python-dotenv` to load a `.env` file when running
locally. On Databricks Apps the platform injects `DATABRICKS_HOST`
and `DATABRICKS_TOKEN` automatically and there is no `.env` — the
`dotenv` import is wrapped in a `try/except` so the app works in
both environments without changes.

```bash
# Install dependencies (once)
uv sync

# Discover your SQL Warehouse ID
databricks warehouses list -p dev

# Generate .env (host, token, warehouse auto-detected from CLI profile)
cat > .env << EOF
DATABRICKS_HOST=$(grep -A5 '^\[dev\]' ~/.databrickscfg | grep host | awk '{print $NF}' | sed 's|https://||')
DATABRICKS_TOKEN=$(databricks auth token -p dev | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<your_warehouse_id>
DATABRICKS_CATALOG=dev
DATABRICKS_SCHEMA=default
EOF

# Start Streamlit (dotenv loads .env automatically)
uv run streamlit run app/app.py \
  --server.port=8000 --server.address=0.0.0.0 --server.headless=true
```

Open http://localhost:8000 in your browser.

> **Why dotenv over `source .env`?** &ensp;`python-dotenv` loads the
> file directly into `os.environ` at Python startup — no shell wrapper,
> no `source` step to forget, and the same `.env` format works with
> Docker, CI runners, and IDE launch configs. On Databricks Apps the
> import is skipped gracefully (the platform injects env vars), so
> there is zero runtime cost in production.

> **`.env` is git-ignored.** It contains a short-lived OAuth token
> (~1 hour). Run `make env` to refresh it.

#### Makefile reference

All variables are configurable: `PROFILE`, `CATALOG`, `SCHEMA`, `SILVER_VOL`,
`APP_NAME`, `APP_PORT`. Example: `make env PROFILE=mcaps01 CATALOG=prod`.

| Target | What it does |
|--------|-------------|
| **Local development** | |
| `make install` | `uv sync` — install deps into `.venv` |
| `make dev` | Start Streamlit locally on `APP_PORT` (reads `.env` via dotenv) |
| `make dev-run` | Start via the production entry point (`app/run.py`) |
| `make dev-fresh` | Refresh token, regenerate `.env`, and start Streamlit in one command |
| `make env` | Generate `.env` from your Databricks CLI profile (auto-detects warehouse) |
| `make token` | Print a fresh OAuth token |
| **Data pipeline** | |
| `make gen-data` | Regenerate sample parquet files **and** silver audit JSON files |
| `make create-volume` | Create the Unity Catalog volumes (`raw_data` + `silver`) |
| `make upload-data` | Upload parquet + silver files to the volumes (creates volumes first) |
| `make sql-setup` | Create tables, MVs, workflow tables, seed data, and audit view |
| `make refresh` | Refresh materialized views (re-reads `sales_raw`) |
| **Deploy** | |
| `make deploy` | Deploy the Databricks App via DABs bundle (recommended) |
| `make deploy-cli` | Deploy via plain CLI — no DABs/Terraform required |
| `make deploy-code` | Upload code + create/deploy app (no resource registration) |
| `make deploy-perms SP=<guid>` | Emit SQL grants for the app service principal |
| `make stop` | Stop the Databricks App (keeps definition, saves compute) |
| `make delete-app` | Delete the Databricks App entirely (removes service principal too) |
| **Cleanup** | |
| `make clean-runtime` | **Tier 1** — delete workflow submissions (keep tables + seed data) |
| `make clean-data` | **Tier 2** — drop all tables/views/files (keep volume + app) |
| `make clean-all` | **Tier 3** — full teardown (app + volume + workspace files) |

The full setup from scratch is:

```bash
make install gen-data upload-data sql-setup env dev
```

### 7. Schedule the refresh job

- Go to **Workflows → Create Job**
- Task type: **Python script**
- File: `sql/02_refresh_job.py`
- Cluster: any small job cluster
- Schedule: `0 6 * * *` (daily at 6am, or on file arrival trigger)

---

## App pages

### 📈 Dashboard
- Year / region / product filters
- KPI cards (revenue, orders, completed, refunded)
- Monthly bar charts
- Region × product pivot table
- Rep leaderboard by month
- Submit a month for approval

### 📋 Review Queue
- Role-based: each reviewer only sees items at their step
- Step trail badges (⏳ pending / ✅ approved / ❌ rejected)
- Inline data preview from the materialized view
- Approve / Reject with comments
- Three-step flow: Manager → Finance → Director

### 📜 Audit Log
- Full history of every workflow action
- Filterable by status

### 📁 Pipeline Lineage
- Browse pipeline audit artifacts stored in Unity Catalog Volumes
- Hierarchical drill-down: **Reporting Period → Business Code → Job Run**
- Renders `sales-check.json` as a styled dashboard with status banner,
  section summary cards, and a tick-and-tie checks table
- Raw JSON expandable for full detail

See [Pipeline Lineage](#pipeline-lineage) below for how it works.

### 🔍 Session Debug
- Inspect environment variables, request headers, and decoded JWT tokens
- View current user SCIM profile and group membership
- Decode both user OBO and service principal tokens
- Useful for troubleshooting auth and role claims

---

## Demo walkthrough

A guided script to show the full submit → approve → audit flow.
Best run against a clean environment (`make clean-runtime` first).

### Act 1 — Explore the dashboard (any role)

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 1 | Name: `alice@company.com`, Role: **submitter** | Select **📈 Dashboard** |
| 2 | | Pick **Year = 2024**, leave all regions and products selected |
| 3 | | Scroll through KPI cards, monthly revenue/orders charts, and the region × product pivot |
| 4 | | Drag the **Rep Leaderboard** month slider to see rankings change |

### Act 2 — Submit a month for approval

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 5 | Role: **submitter** (keep) | Scroll to **Submit Month for Approval** |
| 6 | | Select month **2024-03** from the dropdown |
| 7 | | Click **📤 Submit for Review** |
| 8 | | Note the Workflow ID in the green success banner |

### Act 3 — Manager approval (step 1 of 3)

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 9 | Name: `bob@company.com`, Role: **manager** | Select **📋 Review Queue** |
| 10 | | The 2024-03 submission appears with step trail: ⏳ Manager · ⏳ Finance · ⏳ Director |
| 11 | | Review the inline data preview (region × product breakdown) |
| 12 | | Type a comment: `"Numbers look good"` |
| 13 | | Click **✅ Approve** |
| 14 | | Queue refreshes — item is gone (moved to Finance) |

### Act 4 — Finance approval (step 2 of 3)

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 15 | Name: `carol@company.com`, Role: **finance** | Stay on **📋 Review Queue** |
| 16 | | The item now shows: ✅ Manager · ⏳ Finance · ⏳ Director |
| 17 | | Comment: `"Revenue reconciled"`, click **✅ Approve** |

### Act 5 — Director final approval (step 3 of 3)

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 18 | Name: `dave@company.com`, Role: **director** | Stay on **📋 Review Queue** |
| 19 | | Step trail: ✅ Manager · ✅ Finance · ⏳ Director |
| 20 | | Comment: `"Approved for close"`, click **✅ Approve** |
| 21 | | Queue is now empty — workflow is fully approved |

### Act 6 — View the audit trail

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 22 | Any name/role | Select **📜 Audit Log** |
| 23 | | Full history visible: submitted → manager approved → finance approved → director approved |
| 24 | | Filter by status to show only `approved` |

### Act 7 — Rejection flow (optional)

| Step | Sidebar setting | Action |
|------|----------------|--------|
| 25 | Role: **submitter** | Submit another month (e.g. **2024-06**) on the Dashboard |
| 26 | Role: **manager** | Go to Review Queue, click **❌ Reject** with comment `"Missing Q2 adjustments"` |
| 27 | Any role | Check Audit Log — the rejection shows with the manager's comment |

> **Tip:** Run `make clean-runtime` between demo runs to clear all
> workflow data and start fresh.

---

## Pipeline Lineage

The **📁 Pipeline Lineage** page provides a read-only viewer for pipeline
audit artifacts (`sales-check.json`) stored in a Unity Catalog Volume.
It lets reviewers inspect the data-quality checks that ran during each
pipeline execution — without leaving the Streamlit app.

### How it works

1. **Silver Volume layout** — Each pipeline run writes a JSON audit file
   into a structured folder hierarchy inside the `silver` Volume:

   ```
   /Volumes/<catalog>/<schema>/silver/
   └── YYYY-MM/                    ← reporting period
       └── <BUSINESS_CODE>/        ← e.g. UNIT001, UNIT002
           └── job_MMDDYY_HHMMSS/ ← unique job run folder
               └── sales-check.json
   ```

2. **Hierarchical drill-down** — The app lists available folders at each
   level using the Databricks SDK `files.list_directory_contents()` API:
   - **Reporting Period** picker (year + month)
   - **Business Code** picker (sub-folders under the period)
   - **Job Run ID** picker (sub-folders under the business code)

3. **Audit JSON rendering** — Once a run is selected, the app reads
   `sales-check.json` and renders it as:
   - A **status banner** (PASS / WARN / FAIL) with pass/fail counts
   - **Section summary cards** for Source, OOB Check, Working Tab,
     Load Tab, and Upload Tab — showing row counts, sums, and balances
   - A **Tick & Tie table** listing each cross-check with a ✅/❌ result
   - An expandable **Raw JSON** view for full detail

4. **Caching** — Folder listings and file contents are cached in Streamlit
   session state. Click **🔄 Refresh listings** to clear the cache and
   re-fetch from the Volume.

### What the audit checks verify

The `sales-check.json` file tracks data lineage across pipeline stages:

| Check | What it validates |
|-------|-------------------|
| **Source → Working** | Row counts and signed sums carry forward correctly |
| **OOB (Out-of-Balance)** | Net imbalance is within tolerance; paired entries balance |
| **Working Tab** | Upper (accrued) + Lower (recognized) revenue nets to $0 |
| **Load Tab** | Credit and debit adjustment absolute sums match |
| **Upload Tab** | Header + line rows tally; credits = debits (entry balanced) |
| **Row lineage** | End-to-end row count: source → working → load → upload |

### Generating sample data

```bash
make gen-data       # creates data/silver_output/ with 24 months × 10 units
make upload-data    # uploads to /Volumes/<catalog>/<schema>/silver/
```

---

## Query performance

All app queries hit the **materialized views**, not the raw parquet.
The MVs contain pre-aggregated rows so queries like:

```sql
SELECT region, SUM(total_revenue)
FROM mv_monthly_summary
WHERE year = 2024
GROUP BY region
```

...complete in **under 1 second** on a Serverless Small warehouse,
even with millions of raw rows.

Raw parquet is only ever scanned when the refresh job runs.

---

## File layout

```
├── Makefile                     # make install / dev / env / deploy / …
├── app.yaml                     # Databricks App config (entry point + env vars)
├── databricks.yml               # DABs bundle definition
├── databricks.local.yml         # Local overrides (git-ignored)
├── pyproject.toml               # Python project + dependency manifest (uv)
├── meta/
│   └── app-resources.json.tpl   # Template for Databricks App resource registration
├── data/
│   ├── generate_parquet.py      # Generate sample sales parquet files
│   └── generate_silver.py       # Generate sample pipeline audit JSON files
├── sql/
│   ├── 01_setup.sql             # DDL template (__CATALOG__/__SCHEMA__ placeholders)
│   ├── 02_refresh_job.py        # Scheduled job to refresh MVs
│   └── apply.py                 # Execute SQL template via Databricks CLI
└── app/
    ├── __init__.py              # Makes app/ a Python package
    ├── app.py                   # Streamlit entry point (all pages)
    ├── auth.py                  # OBO + Service Principal auth helpers
    ├── db.py                    # SQL Warehouse connector (SP + user connections)
    ├── run.py                   # Production entry point (Databricks Apps port)
    ├── workflow.py              # Submit / approve / reject logic
    └── requirements.txt
```

---

## Databricks artifacts

Every resource created in the workspace, grouped by lifecycle. Use
this as a checklist for auditing what exists and what to tear down.

### Inventory

| Artifact | Kind | Lifecycle | Created by | Notes |
|----------|------|-----------|-----------|-------|
| `dev.default` | Catalog / Schema | Infrastructure | `01_setup.sql` / step 3 | Assumed to exist; not created by this project |
| `dev.default.raw_data` | Volume | Infrastructure | step 2 | Landing zone for parquet files |
| `dev.default.sales_raw` | Delta table | Data (rebuildable) | step 3 | Ingested from volume via `read_files()` |
| `dev.default.mv_monthly_summary` | Materialized view | Data (rebuildable) | step 3 | Pre-aggregated; refreshed by scheduled job |
| `dev.default.mv_rep_leaderboard` | Materialized view | Data (rebuildable) | step 3 | Pre-aggregated; refreshed by scheduled job |
| `dev.default.workflow_config` | Delta table | Seed data | step 3 | 3 rows defining the approval steps — static after setup |
| `dev.default.workflow` | Delta table | Runtime data | Streamlit app | Rows created on every "Submit for Review" |
| `dev.default.workflow_steps` | Delta table | Runtime data | Streamlit app | Rows created/updated on every submit/approve/reject |
| `dev.default.vw_workflow_audit` | SQL view | Data (rebuildable) | step 3 | Live JOIN over workflow tables — no stored data |
| Serverless SQL Warehouse | Compute | Infrastructure | Manual / UI | Pay-per-query; auto-stops after idle timeout |
| `streamlit-app` | Databricks App | Infrastructure | step 5 | Includes auto-created service principal + OAuth app |
| Workspace source code | Files | Deployment artifact | `make deploy` / step 5c | Snapshot copied to `/Workspace/Users/<user>/streamlit-app` |
| Volume files (`raw_data/sales/*.parquet`) | Parquet files | Data (rebuildable) | `make upload-data` / step 2 | 24 monthly files; can be regenerated with `make gen-data` |

### Lifecycle categories

**Infrastructure** — created once, lives for the duration of the
project. Tearing these down removes the ability to run the app.

**Seed data** — loaded once at setup. Static configuration that
doesn't change during normal operation (`workflow_config`).

**Data (rebuildable)** — can be dropped and recreated from the
pipeline at any time. No user state is lost.

**Runtime data** — created by the app during normal use. Contains
user-generated workflow submissions, approvals, and rejections.
**Dropping these loses user work.**

**Deployment artifact** — workspace files uploaded during deploy.
Recreated on every `make deploy`.

---

## Cleanup

Cleanup scripts segmented by lifecycle. Run only the tier you need.

### Tier 1 — Reset runtime data (keep everything, clear user activity)

Deletes all workflow submissions, approvals, and audit history.
Leaves tables, views, MVs, and seed data intact.

```bash
# Truncate runtime tables (keeps schema, drops all rows)
databricks experimental aitools tools query \
  "DELETE FROM dev.default.workflow_steps" -p dev
databricks experimental aitools tools query \
  "DELETE FROM dev.default.workflow" -p dev

echo "✅ Tier 1: runtime data cleared"
```

### Tier 2 — Reset all data (keep infrastructure, rebuild from scratch)

Drops all tables and views, but keeps the volume, warehouse, and app.
Re-run step 3 (SQL setup) and `make upload-data` to rebuild.

```bash
# Drop views first (depends on tables)
databricks experimental aitools tools query \
  "DROP VIEW IF EXISTS dev.default.vw_workflow_audit" -p dev

# Drop materialized views
databricks experimental aitools tools query \
  "DROP MATERIALIZED VIEW IF EXISTS dev.default.mv_monthly_summary" -p dev
databricks experimental aitools tools query \
  "DROP MATERIALIZED VIEW IF EXISTS dev.default.mv_rep_leaderboard" -p dev

# Drop tables
databricks experimental aitools tools query \
  "DROP TABLE IF EXISTS dev.default.workflow_steps" -p dev
databricks experimental aitools tools query \
  "DROP TABLE IF EXISTS dev.default.workflow" -p dev
databricks experimental aitools tools query \
  "DROP TABLE IF EXISTS dev.default.workflow_config" -p dev
databricks experimental aitools tools query \
  "DROP TABLE IF EXISTS dev.default.sales_raw" -p dev

# Remove parquet files from the volume
databricks fs rm dbfs:/Volumes/dev/default/raw_data/sales/ --recursive -p dev

echo "✅ Tier 2: all data dropped — re-run steps 2–3 to rebuild"
```

### Tier 3 — Full teardown (remove everything from the workspace)

Destroys the app, volume, workspace source code, and all data.
Only the catalog/schema and SQL warehouse survive (assumed shared).

```bash
# ── Tier 2 first ──
# (run all commands from Tier 2 above)

# ── Then destroy infrastructure ──

# Delete the Databricks App (also removes its service principal)
databricks apps delete streamlit-app -p dev

# Drop the volume
databricks experimental aitools tools query \
  "DROP VOLUME IF EXISTS dev.default.raw_data" -p dev

# Remove workspace source code
databricks workspace delete \
  /Workspace/Users/$(databricks current-user me -p dev --output json \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])")/streamlit-app \
  --recursive -p dev

echo "✅ Tier 3: full teardown complete"
```
