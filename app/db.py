"""
db.py — SQL helpers with explicit auth: OBO for reads, SP for writes.

Connection strategy:
  - SP connection: cached with @st.cache_resource (long-lived, shared).
  - User connection: created per-call using the OBO token from headers.
    Not cached because the token can go stale (Streamlit WebSocket issue).
"""
from __future__ import annotations

import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
import streamlit as st
from databricks import sql

try:
    from app.auth import AuthError, get_sp_config, get_user_token, is_databricks_app
except ImportError:
    from auth import AuthError, get_sp_config, get_user_token, is_databricks_app

logger = logging.getLogger(__name__)

CATALOG = os.environ.get("DATABRICKS_CATALOG", "my_catalog")
SCHEMA_ = os.environ.get("DATABRICKS_SCHEMA", "my_schema")

# Table names — injected via valueFrom on Databricks Apps, defaults for local dev.
T_MV_MONTHLY = os.environ.get("TABLE_MV_MONTHLY_SUMMARY", f"{CATALOG}.{SCHEMA_}.mv_monthly_summary")
T_MV_LEADER = os.environ.get("TABLE_MV_REP_LEADERBOARD", f"{CATALOG}.{SCHEMA_}.mv_rep_leaderboard")
T_WORKFLOW = os.environ.get("TABLE_WORKFLOW", f"{CATALOG}.{SCHEMA_}.workflow")
T_WORKFLOW_STEPS = os.environ.get("TABLE_WORKFLOW_STEPS", f"{CATALOG}.{SCHEMA_}.workflow_steps")
T_WORKFLOW_CONFIG = os.environ.get("TABLE_WORKFLOW_CONFIG", f"{CATALOG}.{SCHEMA_}.workflow_config")
T_WORKFLOW_AUDIT = os.environ.get("TABLE_WORKFLOW_AUDIT", f"{CATALOG}.{SCHEMA_}.vw_workflow_audit")


def _resolve_http_path() -> str:
    """Build the SQL warehouse HTTP path.

    On Databricks Apps, DATABRICKS_WAREHOUSE_ID is injected via valueFrom.
    Locally, DATABRICKS_HTTP_PATH is set in .env by 'make env'.
    """
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if warehouse_id:
        return f"/sql/1.0/warehouses/{warehouse_id}"
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if http_path:
        return http_path
    raise AuthError(
        "Neither DATABRICKS_WAREHOUSE_ID nor DATABRICKS_HTTP_PATH is set. "
        "Check app.yaml (for Databricks Apps) or .env (for local dev)."
    )


def _resolve_host() -> str:
    """Return the workspace hostname."""
    host = os.environ.get("DATABRICKS_HOST")
    if host:
        return host.replace("https://", "")
    if is_databricks_app():
        cfg = get_sp_config()
        return cfg.host.replace("https://", "")
    raise AuthError("DATABRICKS_HOST is not set.")


# ── SP connection (cached, shared across all users) ──────────────
@st.cache_resource
def _get_sp_connection():
    """Return a long-lived connection using Service Principal credentials."""
    cfg = get_sp_config()
    host = cfg.host.replace("https://", "") if cfg.host else _resolve_host()
    return sql.connect(
        server_hostname=host,
        http_path=_resolve_http_path(),
        credentials_provider=lambda: cfg.authenticate,
        catalog=CATALOG,
        schema=SCHEMA_,
    )


# ── User OBO connection (per-call, not cached) ──────────────────
def _get_user_connection():
    """Return a connection using the end-user's OBO access token."""
    return sql.connect(
        server_hostname=_resolve_host(),
        http_path=_resolve_http_path(),
        access_token=get_user_token(),
        catalog=CATALOG,
        schema=SCHEMA_,
    )


# ── Public API ───────────────────────────────────────────────────
def query_df(sql_text: str, params: list | None = None) -> pd.DataFrame:
    """Run a read query using the Service Principal connection.

    Uses the SP's cached connection for all reads. When OBO user_api_scopes
    are configured on the app (scope: "sql"), callers can switch to
    query_df_as_user() for user-scoped ACL enforcement.
    """
    conn = _get_sp_connection()
    with conn.cursor() as cur:
        cur.execute(sql_text, params or [])
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=columns)


def query_df_as_user(sql_text: str, params: list | None = None) -> pd.DataFrame:
    """Run a read query on behalf of the end-user (OBO).

    Requires the app to have user_api_scopes: ["sql"] configured.
    Uses the user's forwarded access token so warehouse ACLs
    are evaluated against the real user identity.
    """
    with _get_user_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params or [])
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description]
    return pd.DataFrame(rows, columns=columns)


def execute_as_sp(sql_text: str, params: list | None = None) -> None:
    """Run a DML statement using the Service Principal.

    Use for shared-state writes (workflow inserts/updates) where
    the SP owns the tables.  Caller is responsible for recording
    the real user identity in the row data for audit purposes.
    """
    conn = _get_sp_connection()
    with conn.cursor() as cur:
        cur.execute(sql_text, params or [])
