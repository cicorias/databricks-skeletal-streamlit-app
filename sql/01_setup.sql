-- =============================================================
-- 01_setup.sql  —  Run in Databricks SQL Editor or a Notebook
-- Replace: my_catalog, my_schema with your actual names
-- =============================================================

-- ── 1. Catalog & Schema ──────────────────────────────────────
CREATE CATALOG IF NOT EXISTS my_catalog;
CREATE SCHEMA  IF NOT EXISTS my_catalog.my_schema;

-- ── 2. Volume (where parquet files live) ─────────────────────
CREATE VOLUME IF NOT EXISTS my_catalog.my_schema.raw_data;
-- Upload parquet_output/*.parquet to:
--   /Volumes/my_catalog/my_schema/raw_data/sales/

-- ── 3. External table over all parquet files in the volume ───
CREATE TABLE IF NOT EXISTS my_catalog.my_schema.sales_raw
USING PARQUET
OPTIONS (path '/Volumes/my_catalog/my_schema/raw_data/sales/')
-- Databricks infers schema automatically from the parquet files
;

-- Verify raw load
SELECT COUNT(*), MIN(order_date), MAX(order_date)
FROM my_catalog.my_schema.sales_raw;

-- ── 4. Materialized View — monthly summary ───────────────────
-- Refreshed on a schedule (see 02_refresh_job.py)
-- Photon on the Serverless Warehouse resolves this instantly
CREATE MATERIALIZED VIEW IF NOT EXISTS my_catalog.my_schema.mv_monthly_summary
AS
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
FROM my_catalog.my_schema.sales_raw
GROUP BY year, month, region, product;

-- ── 5. Materialized View — rep leaderboard ───────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS my_catalog.my_schema.mv_rep_leaderboard
AS
SELECT
    sales_rep,
    year,
    month,
    COUNT(*)        AS orders,
    SUM(revenue)    AS revenue,
    RANK() OVER (PARTITION BY year, month ORDER BY SUM(revenue) DESC) AS rank
FROM my_catalog.my_schema.sales_raw
WHERE status = 'completed'
GROUP BY sales_rep, year, month;

-- ── 6. Approval workflow tables ──────────────────────────────
CREATE TABLE IF NOT EXISTS my_catalog.my_schema.workflow (
    workflow_id   STRING  NOT NULL,
    record_ref    STRING,          -- e.g. "2024-03 / North"
    current_step  INT     DEFAULT 1,
    total_steps   INT     DEFAULT 3,
    status        STRING  DEFAULT 'pending',   -- pending|in_review|approved|rejected
    submitted_by  STRING,
    created_at    TIMESTAMP DEFAULT current_timestamp(),
    updated_at    TIMESTAMP DEFAULT current_timestamp()
) USING DELTA TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS my_catalog.my_schema.workflow_steps (
    workflow_id   STRING,
    step          INT,
    role          STRING,      -- manager|finance|director
    reviewer      STRING,
    status        STRING DEFAULT 'pending',
    comments      STRING,
    acted_at      TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS my_catalog.my_schema.workflow_config (
    workflow_type STRING,
    step          INT,
    role          STRING
) USING DELTA;

INSERT INTO my_catalog.my_schema.workflow_config VALUES
    ('monthly_report', 1, 'manager'),
    ('monthly_report', 2, 'finance'),
    ('monthly_report', 3, 'director');

-- ── 7. Audit view ─────────────────────────────────────────────
CREATE OR REPLACE VIEW my_catalog.my_schema.vw_workflow_audit AS
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
FROM my_catalog.my_schema.workflow w
JOIN my_catalog.my_schema.workflow_steps ws
  ON w.workflow_id = ws.workflow_id
ORDER BY w.created_at DESC, ws.step;
