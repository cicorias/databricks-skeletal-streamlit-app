"""Local development entry point.

Run from flaskapp/ root:

    cd flaskapp
    PYTHONPATH=backend uv run python backend/run.py

Or via the Makefile:  make dev-backend
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend/ is importable when run as a script (e.g. `python backend/run.py`).
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

try:
    from dotenv import load_dotenv

    # .env lives at flaskapp/.env (one level above backend/).
    load_dotenv(_BACKEND_DIR.parent / ".env")
except ImportError:
    pass

from flask_backend.app import create_app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "8000"))
    create_app().run(host="0.0.0.0", port=port, debug=True, use_reloader=True)
