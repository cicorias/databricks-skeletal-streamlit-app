# ── appkitapp/Makefile ────────────────────────────────────────
PROFILE  ?= dev
APP_NAME ?= sales-appkit

.PHONY: help install dev build lint lint-fix format typecheck test test-e2e \
        token validate deploy run stop clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Install ────────────────────────────────────────────────────
install: ## Install npm dependencies
	npm install

# ── Local dev ──────────────────────────────────────────────────
dev: ## Run local dev server (Vite + Express, hot-reload)
	npm run dev

build: ## Build client + server for production
	npm run build

# ── Quality ────────────────────────────────────────────────────
lint: ## Run ESLint
	npm run lint

lint-fix: ## Run ESLint with auto-fix
	npm run lint:fix

format: ## Check formatting with Prettier
	npm run format

typecheck: ## Run TypeScript type-check
	npm run typecheck

test: ## Run Vitest + smoke tests
	npm test

test-e2e: ## Run Playwright end-to-end tests
	npm run test:e2e

# ── Auth helpers ───────────────────────────────────────────────
token: ## Print a fresh OAuth bearer token from the dev profile
	@databricks auth token -p $(PROFILE) | python3 -c \
	  "import sys,json; print(json.load(sys.stdin)['access_token'])"

# ── Bundle / deploy ────────────────────────────────────────────
validate: ## Validate the DABs bundle
	databricks bundle validate -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"

deploy: ## Deploy via DABs (validate + deploy + run)
	@echo "── Validating bundle ──"
	databricks bundle validate -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Deploying bundle ──"
	databricks bundle deploy -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Starting app ──"
	databricks bundle run sales_appkit -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "✅ App deployed and running"

run: ## Re-run the deployed app (applies app.yaml changes)
	databricks bundle run sales_appkit -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"

stop: ## Stop the deployed app (keeps definition; saves compute)
	databricks apps stop $(APP_NAME) -p $(PROFILE)

# ── Cleanup ────────────────────────────────────────────────────
clean: ## Remove local build artifacts
	rm -rf node_modules dist client/dist build .smoke-test test-results playwright-report
	@echo "✅ Cleaned"
