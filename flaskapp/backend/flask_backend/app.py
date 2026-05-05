"""Flask app factory.

Register order is critical for the SPA fallback:
  1. /api/* blueprints registered FIRST.
  2. SPA catch-all blueprint registered LAST.

In production (Databricks Apps), gunicorn loads `flask_backend.app:app`
where `app` is the module-level instance built by `create_app()`.
"""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    # Tighter JSON error responses for /api consumers.
    @app.errorhandler(HTTPException)
    def _json_http_error(e: HTTPException):  # noqa: ARG001
        from flask import request as _r  # local to avoid cycles
        if _r.path.startswith("/api/"):
            response = jsonify({"error": e.name, "message": e.description})
            response.status_code = e.code or 500
            return response
        return e

    # Optional CORS — dev-only convenience for local frontend → local backend.
    if os.environ.get("FLASK_ENV") == "development":
        try:
            from flask_cors import CORS

            CORS(app, resources={r"/api/*": {"origins": "*"}})
            logger.info("CORS enabled for /api/* (FLASK_ENV=development)")
        except ImportError:
            logger.warning("flask-cors not installed; skipping CORS middleware")

    # ── /api blueprints first ──────────────────────────────────
    from flask_backend.routes.dashboard import bp as dashboard_bp
    from flask_backend.routes.health import bp as health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(dashboard_bp)

    # ── SPA fallback last ──────────────────────────────────────
    from flask_backend.static_serve import bp as spa_bp

    app.register_blueprint(spa_bp)

    return app


# Module-level instance for gunicorn (`flask_backend.app:app`).
app = create_app()
