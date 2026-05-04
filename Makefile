# ── Project tasks ─────────────────────────────────────────────
PROFILE     ?= dev
CATALOG     ?= dev
SCHEMA      ?= default
SILVER_VOL  ?= silver
APP_NAME    ?= streamlit-app
APP_PORT    ?= 8000
WAREHOUSE   ?= $(shell databricks warehouses list -p $(PROFILE) --output json \
                 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
DBSQL        = databricks experimental aitools tools query
C            = $(CATALOG).$(SCHEMA)

.PHONY: help install dev token gen-data env create-volume upload-data sql-setup deploy deploy-cli deploy-perms deploy-code stop delete-app clean-runtime clean-data clean-all

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install project dependencies into .venv
	uv sync

dev: ## Run Streamlit locally (reads .env via python-dotenv)
	uv run streamlit run app/app.py \
	  --server.port=$(APP_PORT) --server.address=0.0.0.0 --server.headless=true

dev-run: ## run with the true entry point app/run.py
	uv run python app/run.py

token: ## Print a fresh OAuth token for the dev profile
	@databricks auth token -p $(PROFILE) | python3 -c \
	  "import sys,json; print(json.load(sys.stdin)['access_token'])"

gen-data: ## Generate sample parquet files AND silver audit JSON files
	cd data && uv run python generate_parquet.py
	cd data && uv run python generate_silver.py

env: ## Generate .env from the dev Databricks profile
	@echo "DATABRICKS_HOST=$$(grep -A5 '^\[$(PROFILE)\]' ~/.databrickscfg \
	  | grep host | awk '{print $$NF}' | sed 's|https://||')" > .env
	@echo "DATABRICKS_TOKEN=$$(databricks auth token -p $(PROFILE) \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")" >> .env
	@echo "DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/$(WAREHOUSE)" >> .env
	@echo "DATABRICKS_CATALOG=$(CATALOG)" >> .env
	@echo "DATABRICKS_SCHEMA=$(SCHEMA)" >> .env
	@echo "SILVER_VOLUME_PATH=/Volumes/$(CATALOG)/$(SCHEMA)/$(SILVER_VOL)" >> .env
	@echo "✅ .env written (warehouse=$(WAREHOUSE))"

dev-fresh:  ## runs token env and dev in one command (for quick iteration)
	$(MAKE) token env dev


# ── Data pipeline ─────────────────────────────────────────────

create-volume: ## Create the Unity Catalog volumes (raw_data + silver)
	$(DBSQL) "CREATE VOLUME IF NOT EXISTS $(C).raw_data" -p $(PROFILE)
	$(DBSQL) "CREATE VOLUME IF NOT EXISTS $(C).$(SILVER_VOL)" -p $(PROFILE)
	@echo "✅ Volumes $(C).raw_data and $(C).$(SILVER_VOL) ready"

upload-data: create-volume ## Upload parquet + silver files to Databricks Volumes
	databricks fs cp data/parquet_output/ \
	  dbfs:/Volumes/$(CATALOG)/$(SCHEMA)/raw_data/sales/ \
	  --recursive --overwrite -p $(PROFILE)
	databricks fs cp data/silver_output/ \
	  dbfs:/Volumes/$(CATALOG)/$(SCHEMA)/$(SILVER_VOL)/ \
	  --recursive --overwrite -p $(PROFILE)

sql-setup: ## Create tables, materialized views, and audit view (from sql/01_setup.sql)
	python3 sql/apply.py --catalog $(CATALOG) --schema $(SCHEMA) --profile $(PROFILE)

refresh: ## Refresh materialized views (re-reads sales_raw)
	$(DBSQL) "REFRESH MATERIALIZED VIEW $(C).mv_monthly_summary" -p $(PROFILE)
	$(DBSQL) "REFRESH MATERIALIZED VIEW $(C).mv_rep_leaderboard" -p $(PROFILE)
	@echo "✅ Materialized views refreshed"

# ── Deploy ────────────────────────────────────────────────────
WS_USER      = $$(databricks current-user me -p $(PROFILE) --output json \
                 | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])")
WS_APP_PATH  = /Workspace/Users/$(WS_USER)/$(APP_NAME)

deploy: ## Deploy the Databricks App via DABs bundle
	@echo "── Deploying bundle (uploads code + warehouse resource) ──"
	databricks bundle deploy -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "── Registering UC table resources (not yet supported by bundles) ──"
	sed -e 's/__WAREHOUSE_ID__/$(WAREHOUSE)/g' \
	    -e 's/__CATALOG__/$(CATALOG)/g' \
	    -e 's/__SCHEMA__/$(SCHEMA)/g' \
	    -e 's/__SILVER_VOL__/$(SILVER_VOL)/g' \
	    meta/app-resources.json.tpl > /tmp/_app_resources.json
	databricks apps update $(APP_NAME) -p $(PROFILE) \
	  --json @/tmp/_app_resources.json
	rm -f /tmp/_app_resources.json
	@echo "── Starting app (applies config + restarts) ──"
	databricks bundle run streamlit_app -t dev -p $(PROFILE) --var="app_name=$(APP_NAME)"
	@echo "✅ App deployed and running"

deploy-cli: ## Deploy the Databricks App via plain CLI (no DABs/Terraform)
	$(eval _WS_USER := $(shell databricks current-user me -p $(PROFILE) --output json \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])"))
	$(eval _APP_PATH := /Workspace/Users/$(_WS_USER)/$(APP_NAME))
	@echo "── Staging app source files ──"
	$(eval _STAGE := $(shell mktemp -d))
	cp app.yaml $(_STAGE)/
	rsync -a --exclude='__pycache__' app/ $(_STAGE)/app/
	@echo "── Uploading to $(_APP_PATH) ──"
	databricks workspace import-dir $(_STAGE) $(_APP_PATH) \
	  --overwrite -p $(PROFILE)
	rm -rf $(_STAGE)
	@echo "── Creating app (skipped if it already exists) ──"
	@databricks apps get $(APP_NAME) -p $(PROFILE) >/dev/null 2>&1 \
	  && echo "  app already exists — skipping create" \
	  || databricks apps create $(APP_NAME) \
	       --description "Sales Review Portal — Streamlit on Databricks Apps" \
	       --no-compute -p $(PROFILE)
	@echo "── Registering resources (warehouse + UC tables) ──"
	sed -e 's/__WAREHOUSE_ID__/$(WAREHOUSE)/g' \
	    -e 's/__CATALOG__/$(CATALOG)/g' \
	    -e 's/__SCHEMA__/$(SCHEMA)/g' \
	    -e 's/__SILVER_VOL__/$(SILVER_VOL)/g' \
	    meta/app-resources.json.tpl > /tmp/_app_resources.json
	databricks apps update $(APP_NAME) -p $(PROFILE) \
	  --json @/tmp/_app_resources.json
	rm -f /tmp/_app_resources.json
	@echo "── Deploying and starting app ──"
	databricks apps deploy $(APP_NAME) \
	  --source-code-path $(_APP_PATH) -p $(PROFILE)
	@echo "✅ App deployed and running (CLI path)"

deploy-perms: ## Emit SQL grants for the app service principal (SP=<guid>)
ifndef SP
	$(error SP is required — set the app service principal ID, e.g. make deploy-perms SP=56add8ed-...)
endif
	@echo "-- ============================================================"
	@echo "-- Unity Catalog grants for Databricks App service principal"
	@echo "-- App:       $(APP_NAME)"
	@echo "-- Principal: $(SP)"
	@echo "-- Catalog:   $(CATALOG)"
	@echo "-- Schema:    $(CATALOG).$(SCHEMA)"
	@echo "-- Warehouse: $(WAREHOUSE)"
	@echo "-- Generated: $$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	@echo "-- Run these statements as a catalog/workspace admin."
	@echo "-- ============================================================"
	@echo ""
	@echo "-- 1. Catalog + schema access"
	@echo "GRANT USE CATALOG ON CATALOG \`$(CATALOG)\` TO \`$(SP)\`;"
	@echo "GRANT USE SCHEMA  ON SCHEMA  \`$(CATALOG)\`.\`$(SCHEMA)\` TO \`$(SP)\`;"
	@echo ""
	@echo "-- 2. Read-only tables / views"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`mv_monthly_summary\`  TO \`$(SP)\`;"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`mv_rep_leaderboard\`  TO \`$(SP)\`;"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`workflow_config\`     TO \`$(SP)\`;"
	@echo "GRANT SELECT ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`vw_workflow_audit\`   TO \`$(SP)\`;"
	@echo ""
	@echo "-- 3. Read-write tables (SELECT + MODIFY)"
	@echo "GRANT SELECT, MODIFY ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`workflow\`       TO \`$(SP)\`;"
	@echo "GRANT SELECT, MODIFY ON TABLE \`$(CATALOG)\`.\`$(SCHEMA)\`.\`workflow_steps\` TO \`$(SP)\`;"
	@echo ""
	@echo "-- 4. Volume access (silver pipeline data)"
	@echo "GRANT WRITE VOLUME ON VOLUME \`$(CATALOG)\`.\`$(SCHEMA)\`.\`$(SILVER_VOL)\` TO \`$(SP)\`;"
	@echo ""
	@echo "-- 5. SQL Warehouse access (run via CLI or Warehouse Permissions UI)"
	@echo "-- databricks api post /api/2.0/permissions/sql/warehouses/$(WAREHOUSE) \\"
	@echo "--   -p $(PROFILE) --json '{\"access_control_list\":[{\"service_principal_name\":\"$(SP)\",\"permission_level\":\"CAN_USE\"}]}'"

deploy-code: ## Upload code + create/deploy app (no resource registration)
	$(eval _WS_USER := $(shell databricks current-user me -p $(PROFILE) --output json \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])"))
	$(eval _APP_PATH := /Workspace/Users/$(_WS_USER)/$(APP_NAME))
	@echo "── Staging app source files ──"
	$(eval _STAGE := $(shell mktemp -d))
	cp app.yaml $(_STAGE)/
	rsync -a --exclude='__pycache__' app/ $(_STAGE)/app/
	@echo "── Uploading to $(_APP_PATH) ──"
	databricks workspace import-dir $(_STAGE) $(_APP_PATH) \
	  --overwrite -p $(PROFILE)
	rm -rf $(_STAGE)
	@echo "── Creating app (skipped if it already exists) ──"
	@databricks apps get $(APP_NAME) -p $(PROFILE) >/dev/null 2>&1 \
	  && echo "  app already exists — skipping create" \
	  || databricks apps create $(APP_NAME) \
	       --description "Sales Review Portal — Streamlit on Databricks Apps" \
	       --no-compute -p $(PROFILE)
	@echo "── Starting app (must be running before deploy) ──"
	@databricks apps start $(APP_NAME) -p $(PROFILE) >/dev/null 2>&1 || true
	@echo "── Deploying app ──"
	databricks apps deploy $(APP_NAME) \
	  --source-code-path $(_APP_PATH) -p $(PROFILE)
	@echo "✅ App deployed (code only — resources managed separately via deploy-perms)"

stop: ## Stop the Databricks App (keeps app definition, saves compute cost)
	databricks apps stop $(APP_NAME) -p $(PROFILE)

delete-app: ## Delete the Databricks App entirely (removes service principal too)
	databricks apps delete $(APP_NAME) -p $(PROFILE)

# ── Cleanup tiers ────────────────────────────────────────────

clean-runtime: ## Tier 1: delete workflow submissions (keep tables + seed data)
	$(DBSQL) "DELETE FROM $(C).workflow_steps" -p $(PROFILE)
	$(DBSQL) "DELETE FROM $(C).workflow" -p $(PROFILE)
	@echo "✅ Tier 1: runtime data cleared"

clean-data: ## Tier 2: drop all tables/views/files (keep volume + app)
	$(DBSQL) "DROP VIEW IF EXISTS $(C).vw_workflow_audit" -p $(PROFILE)
	$(DBSQL) "DROP MATERIALIZED VIEW IF EXISTS $(C).mv_monthly_summary" -p $(PROFILE)
	$(DBSQL) "DROP MATERIALIZED VIEW IF EXISTS $(C).mv_rep_leaderboard" -p $(PROFILE)
	$(DBSQL) "DROP TABLE IF EXISTS $(C).workflow_steps" -p $(PROFILE)
	$(DBSQL) "DROP TABLE IF EXISTS $(C).workflow" -p $(PROFILE)
	$(DBSQL) "DROP TABLE IF EXISTS $(C).workflow_config" -p $(PROFILE)
	$(DBSQL) "DROP TABLE IF EXISTS $(C).sales_raw" -p $(PROFILE)
	databricks fs rm dbfs:/Volumes/$(CATALOG)/$(SCHEMA)/raw_data/sales/ --recursive -p $(PROFILE) || true
	databricks fs rm dbfs:/Volumes/$(CATALOG)/$(SCHEMA)/$(SILVER_VOL)/ --recursive -p $(PROFILE) || true
	@echo "✅ Tier 2: all data dropped — re-run 'make upload-data sql-setup' to rebuild"

clean-all: clean-data ## Tier 3: full teardown (app + volume + workspace files)
	databricks apps delete $(APP_NAME) -p $(PROFILE) || true
	$(DBSQL) "DROP VOLUME IF EXISTS $(C).raw_data" -p $(PROFILE) || true
	$(DBSQL) "DROP VOLUME IF EXISTS $(C).$(SILVER_VOL)" -p $(PROFILE) || true
	$(eval WS_PATH := $(shell databricks current-user me -p $(PROFILE) --output json \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])"))
	databricks workspace delete \
	  "/Workspace/Users/$(WS_PATH)/$(APP_NAME)" \
	  --recursive -p $(PROFILE) || true
	@echo "✅ Tier 3: full teardown complete"
