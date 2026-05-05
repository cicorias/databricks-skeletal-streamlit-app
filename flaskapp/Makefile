# ── flaskapp/Makefile ─────────────────────────────────────────
PROFILE   ?= dev
APP_NAME  ?= sales-dashboard-flask
APP_PORT  ?= 8000
VITE_PORT ?= 5173

.PHONY: help install install-py install-node lock dev-backend dev-frontend dev-frontend-remote \
        build-frontend test typecheck token validate deploy run stop clean

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

deploy: ## Deploy via DABs (uploads source + applies app config)
	@echo "── Validating bundle ──"
	databricks bundle validate -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Deploying bundle ──"
	databricks bundle deploy -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Starting app (applies config + restarts) ──"
	databricks bundle run sales_dashboard_flask -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "✅ App deployed and running"

run: ## Re-run the deployed app (applies app.yaml changes)
	databricks bundle run sales_dashboard_flask -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"

stop: ## Stop the deployed app (keeps definition; saves compute)
	databricks apps stop $(APP_NAME) -p $(PROFILE)

# ── Cleanup ────────────────────────────────────────────────────
clean: ## Remove local build artifacts
	rm -rf frontend/dist node_modules .venv .pytest_cache .ruff_cache
	find backend -name __pycache__ -type d -exec rm -rf {} +
	@echo "✅ Cleaned"
