# ── Project tasks ─────────────────────────────────────────────
PROFILE     ?= dev
CATALOG     ?= dev
SCHEMA      ?= default
APP_PORT    ?= 8000
WAREHOUSE   ?= $(shell databricks warehouses list -p $(PROFILE) --output json \
                 | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
DBSQL        = databricks experimental aitools tools query
C            = $(CATALOG).$(SCHEMA)

.PHONY: help install dev token gen-data env create-volume upload-data sql-setup deploy stop delete-app clean-runtime clean-data clean-all

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install project dependencies into .venv
	uv sync

dev: ## Run Streamlit locally (reads .env via python-dotenv)
	uv run streamlit run app/app.py \
	  --server.port=$(APP_PORT) --server.address=0.0.0.0 --server.headless=true

token: ## Print a fresh OAuth token for the dev profile
	@databricks auth token -p $(PROFILE) | python3 -c \
	  "import sys,json; print(json.load(sys.stdin)['access_token'])"

gen-data: ## Generate sample parquet files in data/parquet_output/
	cd data && uv run python generate_parquet.py

env: ## Generate .env from the dev Databricks profile
	@echo "DATABRICKS_HOST=$$(grep -A5 '^\[$(PROFILE)\]' ~/.databrickscfg \
	  | grep host | awk '{print $$NF}' | sed 's|https://||')" > .env
	@echo "DATABRICKS_TOKEN=$$(databricks auth token -p $(PROFILE) \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")" >> .env
	@echo "DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/$(WAREHOUSE)" >> .env
	@echo "DATABRICKS_CATALOG=$(CATALOG)" >> .env
	@echo "DATABRICKS_SCHEMA=$(SCHEMA)" >> .env
	@echo "✅ .env written (warehouse=$(WAREHOUSE))"

# ── Data pipeline ─────────────────────────────────────────────

create-volume: ## Create the Unity Catalog volume for parquet files
	$(DBSQL) "CREATE VOLUME IF NOT EXISTS $(C).raw_data" -p $(PROFILE)
	@echo "✅ Volume $(C).raw_data ready"

upload-data: create-volume ## Upload parquet files to the Databricks Volume
	databricks fs cp data/parquet_output/ \
	  dbfs:/Volumes/$(CATALOG)/$(SCHEMA)/raw_data/sales/ \
	  --recursive --overwrite -p $(PROFILE)

sql-setup: ## Create tables, materialized views, and audit view
	@echo "── Creating sales_raw table ──"
	$(DBSQL) "CREATE OR REPLACE TABLE $(C).sales_raw AS \
	  SELECT * FROM read_files('/Volumes/$(CATALOG)/$(SCHEMA)/raw_data/sales/', format => 'parquet')" -p $(PROFILE)
	@echo "── Creating mv_monthly_summary ──"
	$(DBSQL) "CREATE OR REPLACE MATERIALIZED VIEW $(C).mv_monthly_summary AS \
	  SELECT year, month, region, product, \
	    COUNT(*) AS order_count, \
	    SUM(revenue) AS total_revenue, \
	    AVG(revenue) AS avg_order_value, \
	    SUM(CASE WHEN status = 'completed' THEN revenue ELSE 0 END) AS completed_revenue, \
	    SUM(CASE WHEN status = 'refunded'  THEN revenue ELSE 0 END) AS refunded_revenue, \
	    COUNT(DISTINCT sales_rep) AS active_reps \
	  FROM $(C).sales_raw \
	  GROUP BY year, month, region, product" -p $(PROFILE)
	@echo "── Creating mv_rep_leaderboard ──"
	$(DBSQL) "CREATE OR REPLACE MATERIALIZED VIEW $(C).mv_rep_leaderboard AS \
	  SELECT sales_rep, year, month, \
	    COUNT(*) AS orders, \
	    SUM(revenue) AS revenue, \
	    RANK() OVER (PARTITION BY year, month ORDER BY SUM(revenue) DESC) AS rank \
	  FROM $(C).sales_raw \
	  WHERE status = 'completed' \
	  GROUP BY sales_rep, year, month" -p $(PROFILE)
	@echo "── Creating workflow tables ──"
	$(DBSQL) "CREATE TABLE IF NOT EXISTS $(C).workflow ( \
	    workflow_id STRING NOT NULL, record_ref STRING, \
	    current_step INT, total_steps INT, status STRING, \
	    submitted_by STRING, created_at TIMESTAMP, updated_at TIMESTAMP \
	  ) USING DELTA \
	  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true', \
	                 'delta.feature.allowColumnDefaults' = 'supported')" -p $(PROFILE)
	$(DBSQL) "CREATE TABLE IF NOT EXISTS $(C).workflow_steps ( \
	    workflow_id STRING, step INT, role STRING, reviewer STRING, \
	    status STRING, comments STRING, acted_at TIMESTAMP \
	  ) USING DELTA" -p $(PROFILE)
	$(DBSQL) "CREATE TABLE IF NOT EXISTS $(C).workflow_config ( \
	    workflow_type STRING, step INT, role STRING \
	  ) USING DELTA" -p $(PROFILE)
	@echo "── Seeding workflow_config ──"
	$(DBSQL) "INSERT INTO $(C).workflow_config \
	  SELECT * FROM (VALUES \
	    ('monthly_report', 1, 'manager'), \
	    ('monthly_report', 2, 'finance'), \
	    ('monthly_report', 3, 'director') \
	  ) WHERE NOT EXISTS (SELECT 1 FROM $(C).workflow_config LIMIT 1)" -p $(PROFILE)
	@echo "── Creating vw_workflow_audit ──"
	$(DBSQL) "CREATE OR REPLACE VIEW $(C).vw_workflow_audit AS \
	  SELECT w.workflow_id, w.record_ref, w.status AS workflow_status, \
	    w.submitted_by, w.created_at, ws.step, ws.role, ws.reviewer, \
	    ws.status AS step_status, ws.comments, ws.acted_at \
	  FROM $(C).workflow w \
	  JOIN $(C).workflow_steps ws ON w.workflow_id = ws.workflow_id \
	  ORDER BY w.created_at DESC, ws.step" -p $(PROFILE)
	@echo "✅ SQL setup complete"

# ── Deploy ────────────────────────────────────────────────────
WS_USER      = $$(databricks current-user me -p $(PROFILE) --output json \
                 | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])")
WS_APP_PATH  = /Workspace/Users/$(WS_USER)/streamlit-app

deploy: ## Deploy the Databricks App via DABs bundle
	@echo "── Deploying bundle (uploads code + warehouse resource) ──"
	databricks bundle deploy -t dev -p $(PROFILE)
	@echo "── Registering UC table resources (not yet supported by bundles) ──"
	sed -e 's/__WAREHOUSE_ID__/$(WAREHOUSE)/g' \
	    -e 's/__CATALOG__/$(CATALOG)/g' \
	    -e 's/__SCHEMA__/$(SCHEMA)/g' \
	    meta/app-resources.json.tpl > /tmp/_app_resources.json
	databricks apps update streamlit-app -p $(PROFILE) \
	  --json @/tmp/_app_resources.json
	rm -f /tmp/_app_resources.json
	@echo "── Starting app (applies config + restarts) ──"
	databricks bundle run streamlit_app -t dev -p $(PROFILE)
	@echo "✅ App deployed and running"

stop: ## Stop the Databricks App (keeps app definition, saves compute cost)
	databricks apps stop streamlit-app -p $(PROFILE)

delete-app: ## Delete the Databricks App entirely (removes service principal too)
	databricks apps delete streamlit-app -p $(PROFILE)

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
	@echo "✅ Tier 2: all data dropped — re-run 'make upload-data sql-setup' to rebuild"

clean-all: clean-data ## Tier 3: full teardown (app + volume + workspace files)
	databricks apps delete streamlit-app -p $(PROFILE) || true
	$(DBSQL) "DROP VOLUME IF EXISTS $(C).raw_data" -p $(PROFILE) || true
	$(eval WS_PATH := $(shell databricks current-user me -p $(PROFILE) --output json \
	  | python3 -c "import sys,json; print(json.load(sys.stdin)['userName'])"))
	databricks workspace delete \
	  "/Workspace/Users/$(WS_PATH)/streamlit-app" \
	  --recursive -p $(PROFILE) || true
	@echo "✅ Tier 3: full teardown complete"
