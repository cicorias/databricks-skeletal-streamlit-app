"""SPA static-file serving with safe fallback semantics.

Order of resolution (registered AFTER all /api blueprints):
  1. If the requested path matches a real file under STATIC_DIR → serve it.
  2. Else if the path looks like an asset (has a file extension) → 404.
     This avoids masking broken JS/CSS chunk URLs as `index.html`.
  3. Else → return `index.html` for client-side routing.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Blueprint, abort, send_from_directory

logger = logging.getLogger(__name__)

# .../flaskapp/backend/flask_backend/static_serve.py
#                       ^                         ^
# parents[1] = .../flaskapp/backend
# parents[2] = .../flaskapp
_PACKAGE_DIR = Path(__file__).resolve().parent
_FLASKAPP_ROOT = _PACKAGE_DIR.parents[1]
_DEFAULT_STATIC_DIR = _FLASKAPP_ROOT / "frontend" / "dist"

STATIC_DIR = Path(os.environ.get("STATIC_DIR", str(_DEFAULT_STATIC_DIR))).resolve()

bp = Blueprint("spa", __name__)


def _has_extension(path: str) -> bool:
    last_segment = path.rsplit("/", 1)[-1]
    return "." in last_segment


@bp.get("/")
@bp.get("/<path:requested>")
def spa(requested: str = ""):
    # Never let the SPA catch-all swallow unknown /api/* paths — the JSON
    # error handler (registered in app.py) needs to return JSON 404s for those.
    if requested.startswith("api/") or requested == "api":
        abort(404)

    if not STATIC_DIR.exists():
        logger.warning(
            "Static dir %s does not exist; build the frontend with `npm run build`.",
            STATIC_DIR,
        )
        abort(503, "Frontend bundle is not built yet.")

    if requested:
        candidate = (STATIC_DIR / requested).resolve()
        try:
            candidate.relative_to(STATIC_DIR)
        except ValueError:
            abort(404)
        if candidate.is_file():
            return send_from_directory(STATIC_DIR, requested)
        if _has_extension(requested):
            abort(404)

    return send_from_directory(STATIC_DIR, "index.html")
