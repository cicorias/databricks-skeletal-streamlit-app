"""SQL warehouse helpers using Service Principal authentication.

Connection strategy:
  * One per-worker, lazily-initialised connection.
  * Created INSIDE each gunicorn worker (not at import time) so we never
    fork a process with live connector state. Run gunicorn WITHOUT --preload.
  * Reconnect on transport-level failures (warehouses go idle and drop
    long-lived sockets).
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

from databricks import sql
from databricks.sql.exc import OperationalError

from flask_backend.auth import AuthError, get_sp_config

logger = logging.getLogger(__name__)

# Catalog / schema — match the existing Streamlit app defaults.
CATALOG = os.environ.get("DATABRICKS_CATALOG", "dev")
SCHEMA = os.environ.get("DATABRICKS_SCHEMA", "default")

# Table FQNs (allow override via env, otherwise compute from CATALOG/SCHEMA).
T_MV_MONTHLY = os.environ.get(
    "TABLE_MV_MONTHLY_SUMMARY", f"{CATALOG}.{SCHEMA}.mv_monthly_summary"
)
T_MV_LEADER = os.environ.get(
    "TABLE_MV_REP_LEADERBOARD", f"{CATALOG}.{SCHEMA}.mv_rep_leaderboard"
)

_conn = None
_conn_lock = threading.Lock()


def _resolve_http_path() -> str:
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if warehouse_id:
        return f"/sql/1.0/warehouses/{warehouse_id}"
    http_path = os.environ.get("DATABRICKS_HTTP_PATH")
    if http_path:
        return http_path
    raise AuthError(
        "Neither DATABRICKS_WAREHOUSE_ID nor DATABRICKS_HTTP_PATH is set. "
        "On Databricks Apps this comes from app.yaml `valueFrom: sql-warehouse`. "
        "Locally, set it in flaskapp/.env."
    )


def _resolve_host(cfg) -> str:
    host = os.environ.get("DATABRICKS_HOST") or cfg.host
    if not host:
        raise AuthError("DATABRICKS_HOST is not set.")
    return host.replace("https://", "").rstrip("/")


def _open_connection():
    """Open a fresh SP-authenticated SQL connection."""
    cfg = get_sp_config()
    host = _resolve_host(cfg)
    http_path = _resolve_http_path()

    # Quick-start fallback: if the user provided DATABRICKS_TOKEN but no SP
    # creds, use the bearer token instead of an SDK credentials provider.
    token = os.environ.get("DATABRICKS_TOKEN")
    has_sp = os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get(
        "DATABRICKS_CLIENT_SECRET"
    )
    if token and not has_sp:
        logger.info("Opening SQL connection using DATABRICKS_TOKEN (bearer fallback)")
        return sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
            catalog=CATALOG,
            schema=SCHEMA,
        )

    logger.info("Opening SQL connection using Service Principal credentials")
    return sql.connect(
        server_hostname=host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
        catalog=CATALOG,
        schema=SCHEMA,
    )


def _get_connection():
    """Return the per-worker connection, opening it on first use."""
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                _conn = _open_connection()
    return _conn


def _reset_connection():
    global _conn
    with _conn_lock:
        try:
            if _conn is not None:
                _conn.close()
        except Exception:  # noqa: BLE001
            logger.debug("Error closing stale connection", exc_info=True)
        _conn = None


def query_rows(sql_text: str, params: list | None = None) -> list[dict[str, Any]]:
    """Run a read-only query and return rows as a list of dicts.

    Retries once on OperationalError (transient warehouse disconnect).
    """
    for attempt in (1, 2):
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute(sql_text, params or [])
                rows = cur.fetchall()
                columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]
        except OperationalError as e:
            logger.warning("SQL connection failed (attempt %d): %s", attempt, e)
            _reset_connection()
            if attempt == 2:
                raise
    return []  # unreachable
