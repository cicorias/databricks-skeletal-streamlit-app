-- =============================================================
-- 01_setup.sql — DDL template for the Sales Review POC
--
-- Placeholders:  __CATALOG__  __SCHEMA__
-- Execute via:   make sql-setup
--                python3 sql/apply.py --catalog dev --schema default --profile dev
-- =============================================================

-- ── 1. Volume (landing zone for parquet files) ───────────────
CREATE VOLUME IF NOT EXISTS __CATALOG__.__SCHEMA__.raw_data;

-- ── 2. Ingest parquet files into a Delta table ───────────────
CREATE OR REPLACE TABLE __CATALOG__.__SCHEMA__.sales_raw AS
SELECT * FROM read_files(
  '/Volumes/__CATALOG__/__SCHEMA__/raw_data/sales/',
  format => 'parquet'
);

-- ── 3. Materialized View — monthly summary ───────────────────
CREATE OR REPLACE MATERIALIZED VIEW __CATALOG__.__SCHEMA__.mv_monthly_summary AS
SELECT
    year,
    month,
    region,
    product,
    COUNT(*)                        AS order_count,
    SUM(revenue)                    AS total_revenue,
    AVG(revenue)                    AS avg_order_value,
    SUM(CASE WHEN status = 'completed' THEN revenue ELSE 0 END) AS completed_revenue,
    SUM(CASE WHEN status = 'refunded'  THEN revenue ELSE 0 END) AS refunded_revenue,
    COUNT(DISTINCT sales_rep)       AS active_reps
FROM __CATALOG__.__SCHEMA__.sales_raw
GROUP BY year, month, region, product;

-- ── 4. Materialized View — rep leaderboard ───────────────────
CREATE OR REPLACE MATERIALIZED VIEW __CATALOG__.__SCHEMA__.mv_rep_leaderboard AS
SELECT
    sales_rep,
    year,
    month,
    COUNT(*)        AS orders,
    SUM(revenue)    AS revenue,
    RANK() OVER (PARTITION BY year, month ORDER BY SUM(revenue) DESC) AS rank
FROM __CATALOG__.__SCHEMA__.sales_raw
WHERE status = 'completed'
GROUP BY sales_rep, year, month;

-- ── 5. Approval workflow tables ──────────────────────────────
CREATE TABLE IF NOT EXISTS __CATALOG__.__SCHEMA__.workflow (
    workflow_id   STRING NOT NULL,
    record_ref    STRING,
    current_step  INT,
    total_steps   INT,
    status        STRING,
    submitted_by  STRING,
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP
) USING DELTA
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true',
    'delta.feature.allowColumnDefaults' = 'supported'
);

CREATE TABLE IF NOT EXISTS __CATALOG__.__SCHEMA__.workflow_steps (
    workflow_id   STRING,
    step          INT,
    role          STRING,
    reviewer      STRING,
    status        STRING,
    comments      STRING,
    acted_at      TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS __CATALOG__.__SCHEMA__.workflow_config (
    workflow_type STRING,
    step          INT,
    role          STRING
) USING DELTA;

-- ── 6. Seed workflow_config (idempotent — skips if rows exist)
INSERT INTO __CATALOG__.__SCHEMA__.workflow_config
SELECT * FROM (VALUES
    ('monthly_report', 1, 'manager'),
    ('monthly_report', 2, 'finance'),
    ('monthly_report', 3, 'director')
) WHERE NOT EXISTS (SELECT 1 FROM __CATALOG__.__SCHEMA__.workflow_config LIMIT 1);

-- ── 7. Audit view ────────────────────────────────────────────
CREATE OR REPLACE VIEW __CATALOG__.__SCHEMA__.vw_workflow_audit AS
SELECT
    w.workflow_id,
    w.record_ref,
    w.status        AS workflow_status,
    w.submitted_by,
    w.created_at,
    ws.step,
    ws.role,
    ws.reviewer,
    ws.status       AS step_status,
    ws.comments,
    ws.acted_at
FROM __CATALOG__.__SCHEMA__.workflow w
JOIN __CATALOG__.__SCHEMA__.workflow_steps ws
  ON w.workflow_id = ws.workflow_id
ORDER BY w.created_at DESC, ws.step;
