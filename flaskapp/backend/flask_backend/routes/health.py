"""Health-check endpoint."""
from __future__ import annotations

from flask import Blueprint, jsonify

from flask_backend.auth import is_databricks_app

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "mode": "databricks-apps" if is_databricks_app() else "local",
        }
    )
