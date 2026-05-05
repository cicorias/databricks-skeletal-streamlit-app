# Sales Dashboard — Flask + React on Databricks Apps

A separate sub-project (sibling to the Streamlit app at `../app/`) that serves the
**read-only Sales Dashboard** as a single-page React app backed by a Flask JSON API.

The app reads from the same materialized views the Streamlit app uses
(`dev.default.mv_monthly_summary`, `dev.default.mv_rep_leaderboard`) — set those
up first via the root project's `make sql-setup`, `make gen-data`, and
`make upload-data` targets.

## Architecture

```
Browser ── /api/* ──────► Flask (gunicorn, workers=2)
                          │  • SP auth via auto-injected env vars
                          │  • databricks-sql-connector → SQL warehouse
                          ▼
Browser ── / + assets ──► Flask SPA fallback → frontend/dist/index.html
```

In production a **single** Flask process serves both the React static bundle
and the `/api/*` JSON endpoints — required because Databricks Apps exposes only
one port (`DATABRICKS_APP_PORT`).

In local dev the two sides run as separate processes — Vite serves React with
HMR on `:5173`, Flask serves `/api/*` on `:8000`, and Vite proxies `/api/*` to
Flask.

## Three run modes

| Mode | Frontend | Backend | When to use |
|------|----------|---------|-------------|
| **1. Local + Local** | `npm run dev` (Vite :5173) | `make dev-backend` (Flask :8000) | Day-to-day development |
| **2. Local + Remote** | `make dev-frontend-remote` | Deployed Databricks App | Verifying frontend changes against real workspace data |
| **3. Production** | Served by Flask static fallback | Same Flask process | Real users on the deployed app |

## Prerequisites

- `mise` toolchain active (gives Python 3.12, `uv`, `databricks` CLI)
- Node.js 20+ (`node -v`)
- The root repo's data setup completed:
  ```bash
  cd ..
  make gen-data upload-data sql-setup
  ```
- Azure CLI logged in: `az account show`
- Databricks profile `dev` configured in `~/.databrickscfg` with `auth_type = databricks-cli`

## Initial setup

```bash
cd flaskapp

# 1) Install Python and Node deps. uv generates .venv automatically.
make install

# 2) Generate uv.lock (required so Databricks Apps installs via uv with Python 3.12).
make lock

# 3) Copy local config templates and fill in values.
cp .env.sample .env                                  # backend secrets / warehouse id
cp databricks.local.yml.sample databricks.local.yml  # workspace host + warehouse id
cp frontend/.env.sample frontend/.env                # only needed for Mode 2
```

Edit `.env`:
- `DATABRICKS_HOST` — workspace hostname without `https://`
- `DATABRICKS_WAREHOUSE_ID` — `databricks warehouses list -p dev | head`
- Either `DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` (SP auth), or `DATABRICKS_TOKEN` (bearer fallback)

Edit `databricks.local.yml`:
- `workspace.host` — full `https://adb-...` URL
- `variables.warehouse_id.default` — same warehouse id

## Mode 1 — Local frontend + Local backend

```bash
# Terminal 1
make dev-backend

# Terminal 2
make dev-frontend
```

Open http://localhost:5173. Vite proxies `/api/*` → Flask on `:8000`.

Smoke check Flask alone:
```bash
curl http://localhost:8000/api/health
# {"mode":"local","ok":true}
```

## Mode 2 — Local frontend + Remote (deployed) backend

First deploy the app (see "Deploy" below), then:

```bash
# Get the app URL and a bearer token.
export VITE_REMOTE_BACKEND_URL=$(databricks apps get sales-dashboard-flask -p dev --output json | jq -r .url)
export DATABRICKS_TOKEN=$(make token)

# Sanity check the bearer auth — must return JSON, not HTML.
curl -H "Authorization: Bearer $DATABRICKS_TOKEN" "$VITE_REMOTE_BACKEND_URL/api/health"
# {"mode":"databricks-apps","ok":true}

# Run Vite with the remote proxy.
make dev-frontend-remote
```

Open http://localhost:5173 — the page now renders against your live workspace data.

> **Tip:** OAuth tokens from `databricks auth token` expire (~1 hour). If you
> see a `Backend returned HTML instead of JSON` banner, refresh the token:
> `export DATABRICKS_TOKEN=$(make token)` and reload the page.

## Mode 3 — Deploy & run on Databricks Apps

```bash
make deploy
```

This runs `bundle validate → bundle deploy → bundle run`:

1. `bundle deploy` uploads everything in `flaskapp/` (excluding `node_modules/`,
   `.venv/`, `frontend/dist/`, etc.).
2. The Databricks Apps build phase:
   - Detects `pyproject.toml` + `uv.lock` → runs `uv sync` (Python 3.12)
   - Detects `package.json` → runs `npm install` then `npm run build`
3. `bundle run sales_dashboard_flask` applies `app.yaml` and starts gunicorn.

Find the URL after deploy:

```bash
databricks apps get sales-dashboard-flask -p dev --output json | jq -r .url
```

Other helpful targets:

```bash
make stop          # stop the app (saves compute), keeps the definition
make run           # apply app.yaml changes without re-uploading source
make validate      # validate the bundle without deploying
```

## Project layout

```
flaskapp/
├── pyproject.toml           # Python deps (uv) — used both locally and on Databricks Apps
├── uv.lock                  # generated; required for the platform to use uv
├── package.json             # Node deps + build script — Databricks Apps runs `npm install` + `npm run build`
├── app.yaml                 # gunicorn command + env injection (sql-warehouse via valueFrom)
├── databricks.yml           # DABs sub-bundle (separate from the root Streamlit bundle)
├── databricks.local.yml.sample
├── .env.sample              # backend dev secrets template
├── Makefile
├── backend/
│   ├── flask_backend/       # the Python package; gunicorn loads flask_backend.app:app
│   │   ├── app.py           # create_app() + module-level `app`
│   │   ├── auth.py          # SP Config helper
│   │   ├── db.py            # SQL warehouse query helper (lazy per-worker connection)
│   │   ├── routes/
│   │   │   ├── health.py
│   │   │   └── dashboard.py # all /api/dashboard/* endpoints
│   │   └── static_serve.py  # SPA fallback (file-exists then index.html)
│   ├── tests/test_routes.py # pytest smoke tests (db is mocked)
│   └── run.py               # local dev entry: `python backend/run.py`
└── frontend/                # Vite project root (uses flaskapp/package.json)
    ├── vite.config.ts       # proxy switches between local/remote backend
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api.ts           # typed fetch wrappers
        ├── types.ts
        └── components/
            ├── Filters.tsx
            ├── KpiCards.tsx
            ├── MonthlyChart.tsx       (Recharts)
            ├── RegionProductPivot.tsx
            └── Leaderboard.tsx
```

## Tests

```bash
make test           # backend pytest (mocks db.query_rows)
make typecheck      # frontend tsc --noEmit
```

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Frontend bundle is not built yet.` (503) | `frontend/dist/` missing locally — run `make build-frontend`. Doesn't affect production (Databricks rebuilds on deploy). |
| Charts empty, no error | The materialized views in `dev.default` are empty. Run the root project's `make gen-data upload-data sql-setup`. |
| `Backend returned HTML instead of JSON` (Mode 2) | Bearer token expired. `export DATABRICKS_TOKEN=$(make token)` and reload. |
| `PERMISSION_DENIED` on warehouse query | The app's service principal needs `CAN_USE` on the warehouse + `SELECT` on the materialized views. Bundle deploy auto-grants `CAN_USE`; SQL grants must be applied manually (see root project's `make deploy-perms`). |
| `502 Bad Gateway` after deploy | gunicorn binding wrong port/host. Check `app.yaml` uses `0.0.0.0:${DATABRICKS_APP_PORT}`. |

## Why a separate bundle?

Keeping `flaskapp/databricks.yml` independent from the root project's
`databricks.yml` lets you deploy and version the two apps independently:

```bash
# Deploy only the Streamlit app
cd ..        && make deploy

# Deploy only the Flask app
cd flaskapp  && make deploy
```
