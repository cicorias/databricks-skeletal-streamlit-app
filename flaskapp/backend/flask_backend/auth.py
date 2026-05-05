"""Authentication helpers for the Flask backend.

When running on Databricks Apps:
  - SP auth is auto-configured via injected env vars (DATABRICKS_HOST,
    DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET).
  - User identity (if needed for OBO) comes from the X-Forwarded-* headers
    set by the Databricks Apps reverse proxy.

When running locally (FLASK_ENV=development):
  - Either SP creds are provided via .env, OR a DATABRICKS_TOKEN is provided
    as an OAuth bearer fallback (easier for quick start).
"""
from __future__ import annotations

import logging
import os

from databricks.sdk.core import Config

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when required authentication context is missing."""


def is_databricks_app() -> bool:
    """Return True when running inside the Databricks Apps platform."""
    return bool(os.environ.get("DATABRICKS_APP_NAME"))


def get_sp_config() -> Config:
    """Return a Databricks SDK Config using Service Principal credentials.

    On Databricks Apps the platform auto-injects DATABRICKS_HOST,
    DATABRICKS_CLIENT_ID, and DATABRICKS_CLIENT_SECRET. Locally the
    Config picks up whatever is in the environment (set via .env).
    """
    return Config()


def get_user_token_from_request(request) -> str | None:
    """Return the end-user's OBO access token, if present.

    Reads X-Forwarded-Access-Token from the active Flask request.
    Returns None if the header is missing (e.g., local dev or SP-only paths).
    """
    return request.headers.get("X-Forwarded-Access-Token")


def get_user_email_from_request(request) -> str | None:
    """Return the authenticated user's email, if present."""
    return request.headers.get("X-Forwarded-Email")
