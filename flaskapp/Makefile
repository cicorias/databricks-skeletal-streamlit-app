# ── flaskapp/Makefile ─────────────────────────────────────────
PROFILE   ?= dev
APP_NAME  ?= sales-dashboard-flask
APP_PORT  ?= 8000
VITE_PORT ?= 5173

# Unity Catalog target — must match flaskapp/app.yaml DATABRICKS_CATALOG/SCHEMA.
CATALOG   ?= dev
SCHEMA    ?= default

# Warehouse ID is the SAME value the bundle uses (resolved from
# databricks.local.yml's `warehouse_id` variable). Lazy-evaluated so the
# `databricks bundle validate` shell-out doesn't run on `make help` etc.
WAREHOUSE  = $(shell databricks bundle validate -t dev -p $(PROFILE) \
              --var="app_name=$(APP_NAME)" --output json 2>/dev/null \
              | python3 -c "import sys,json; \
print(json.load(sys.stdin)['variables']['warehouse_id']['value'])")

.PHONY: help install install-py install-node lock dev-backend dev-frontend dev-frontend-remote \
        build-frontend test typecheck token validate deploy deploy-perms run stop clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Install ────────────────────────────────────────────────────
install: install-py install-node ## Install Python (uv) + Node deps

install-py: ## Install Python deps via uv (creates .venv)
	uv sync

install-node: ## Install npm deps at the flaskapp/ root
	npm install

lock: ## Regenerate uv.lock (run after editing pyproject.toml)
	uv lock

# ── Local dev ──────────────────────────────────────────────────
dev-backend: ## Run Flask locally on :8000 (loads .env). Mode 1 + 2 backend.
	PYTHONPATH=backend FLASK_ENV=development FLASK_PORT=$(APP_PORT) \
	  uv run python backend/run.py

dev-frontend: ## Run Vite locally on :5173, proxy /api → http://localhost:8000 (Mode 1)
	npm run dev -- --port $(VITE_PORT)

dev-frontend-remote: ## Run Vite locally on :5173, proxy /api → deployed app (Mode 2). Requires DATABRICKS_TOKEN.
	@if [ -z "$$DATABRICKS_TOKEN" ]; then \
	  echo "DATABRICKS_TOKEN is not set."; \
	  echo "  Run: export DATABRICKS_TOKEN=\$$(make token)"; \
	  exit 1; \
	fi
	@if [ -z "$$VITE_REMOTE_BACKEND_URL" ]; then \
	  echo "VITE_REMOTE_BACKEND_URL is not set."; \
	  echo "  Get the URL with: databricks apps get $(APP_NAME) -p $(PROFILE) --output json | jq -r .url"; \
	  exit 1; \
	fi
	npm run dev:remote -- --port $(VITE_PORT)

# ── Build & test ───────────────────────────────────────────────
build-frontend: ## Build the React app to frontend/dist (used for `npm run preview`; Databricks rebuilds on deploy)
	npm run build

typecheck: ## Run TypeScript type-check only
	npm run typecheck

test: ## Run backend pytest suite
	uv run pytest -v

# ── Auth helpers ───────────────────────────────────────────────
token: ## Print a fresh OAuth bearer token from the dev profile
	@databricks auth token -p $(PROFILE) | python3 -c \
	  "import sys,json; print(json.load(sys.stdin)['access_token'])"

# ── Bundle / deploy ────────────────────────────────────────────
validate: ## Validate the DABs bundle
	databricks bundle validate -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"

deploy: ## Deploy via DABs (uploads source + applies app config + registers UC resources)
	@echo "── Validating bundle ──"
	databricks bundle validate -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Deploying bundle ──"
	databricks bundle deploy -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Registering UC resources (sql-warehouse + UC tables) ──"
	@if [ -z "$(WAREHOUSE)" ]; then \
	  echo "❌ Could not resolve warehouse_id from bundle. Set warehouse_id in databricks.local.yml."; \
	  exit 1; \
	fi
	@echo "    warehouse=$(WAREHOUSE)  catalog=$(CATALOG)  schema=$(SCHEMA)"
	@sed -e 's/__WAREHOUSE_ID__/$(WAREHOUSE)/g' \
	    -e 's/__CATALOG__/$(CATALOG)/g' \
	    -e 's/__SCHEMA__/$(SCHEMA)/g' \
	    meta/app-resources.json.tpl > /tmp/_flaskapp_resources.json
	databricks apps update $(APP_NAME) -p $(PROFILE) \
	  --json @/tmp/_flaskapp_resources.json
	@rm -f /tmp/_flaskapp_resources.json
	@echo "── Starting app (applies config + restarts) ──"
	databricks bundle run sales_dashboard_flask -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Verifying registered resources ──"
	@databricks apps get $(APP_NAME) -p $(PROFILE) --output json \
	  | python3 -c "import sys,json; \
app=json.load(sys.stdin); \
names={r['name'] for r in (app.get('resources') or [])}; \
required={'sql-warehouse','mv-monthly-summary','mv-rep-leaderboard'}; \
missing=required-names; \
sys.exit(f'❌ Missing app resources after deploy: {sorted(missing)}') if missing else print(f'✅ Resources present: {sorted(names)}')"
	@echo "✅ App deployed and running"

run: ## Re-run the deployed app (applies app.yaml changes)
	databricks bundle run sales_dashboard_flask -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"

stop: ## Stop the deployed app (keeps definition; saves compute)
	databricks apps stop $(APP_NAME) -p $(PROFILE)

deploy-perms: ## Emit SQL grants for the app SP (fallback when auto-grant doesn't trigger). Set SP=<guid>.
ifndef SP
	$(error SP is required — get it from: databricks apps get $(APP_NAME) -p $(PROFILE) --output json | jq -r .service_principal_client_id)
endif
	@echo "-- ============================================================"
	@echo "-- UC grants for Databricks App service principal"
	@echo "-- App:       $(APP_NAME)"
	@echo "-- Principal: $(SP)"
	@echo "-- Catalog:   $(CATALOG)"
	@echo "-- Schema:    $(CATALOG).$(SCHEMA)"
	@echo "-- Run these as a catalog/workspace admin if 'make deploy' didn't"
	@echo "-- auto-grant (see Databricks Apps UC privilege requirements)."
	@echo "-- ============================================================"
	@echo ""
	@echo "GRANT USE CATALOG ON CATALOG \`$(CATALOG)\` TO \`$(SP)\`;"
	@echo "GRANT USE SCHEMA  ON SCHEMA  \`$(CATALOG)\`.\`$(SCHEMA)\` TO \`$(SP)\`;"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`mv_monthly_summary\` TO \`$(SP)\`;"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`mv_rep_leaderboard\` TO \`$(SP)\`;"

# ── Cleanup ────────────────────────────────────────────────────
clean: ## Remove local build artifacts
	rm -rf frontend/dist node_modules .venv .pytest_cache .ruff_cache
	find backend -name __pycache__ -type d -exec rm -rf {} +
	@echo "✅ Cleaned"
