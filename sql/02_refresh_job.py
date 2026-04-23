"""
02_refresh_job.py
-----------------
Attach this as a Databricks Workflow Job task (Python).
Schedule it to run whenever new parquet files land in the Volume
(e.g. nightly, or triggered by a file arrival event).

It refreshes both materialized views so the Streamlit app
always reads pre-aggregated, fast data via Photon.

Configure CATALOG and SCHEMA via Databricks job parameters or
widget defaults below.
"""
from databricks.sdk.runtime import spark   # available in Databricks runtime

try:
    CATALOG = dbutils.widgets.get("catalog")  # noqa: F821
except Exception:
    CATALOG = "dev"

try:
    SCHEMA = dbutils.widgets.get("schema")  # noqa: F821
except Exception:
    SCHEMA = "default"

MVS = [
    "mv_monthly_summary",
    "mv_rep_leaderboard",
]

for mv in MVS:
    full_name = f"{CATALOG}.{SCHEMA}.{mv}"
    print(f"Refreshing {full_name} ...")
    spark.sql(f"REFRESH MATERIALIZED VIEW {full_name}")
    print(f"  ✓ Done")

print("\nAll materialized views refreshed.")
