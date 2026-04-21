"""Entrypoint that launches Streamlit on the platform-assigned port."""
from __future__ import annotations

import os
import sys

from streamlit.web import cli as stcli

if __name__ == "__main__":
    port = os.environ.get("DATABRICKS_APP_PORT", "8000")
    sys.argv = [
        "streamlit", "run", "app/app.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
    ]
    sys.exit(stcli.main())
