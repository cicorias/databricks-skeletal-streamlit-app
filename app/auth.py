"""
auth.py — Authentication helpers for Databricks Apps (OBO + Service Principal).

When running on Databricks Apps:
  - SP auth is auto-configured via injected env vars (DATABRICKS_CLIENT_ID/SECRET).
  - User identity comes from X-Forwarded-Email / X-Forwarded-Access-Token headers.

When running locally:
  - Falls back to DATABRICKS_TOKEN env var and a configurable default email.
"""
from __future__ import annotations

import logging
import os

import streamlit as st
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
    DATABRICKS_CLIENT_ID, and DATABRICKS_CLIENT_SECRET.
    Locally it picks up whatever is configured in the environment or
    ~/.databrickscfg.
    """
    return Config()


def get_user_email() -> str:
    """Return the authenticated user's email address.

    On Databricks Apps this is injected by the reverse proxy.
    Locally it falls back to DATABRICKS_USER_EMAIL or a default.

    Raises:
        AuthError: If running on Databricks Apps and the header is missing.
    """
    if is_databricks_app():
        email = st.context.headers.get("X-Forwarded-Email")
        if not email:
            raise AuthError(
                "X-Forwarded-Email header missing — the Databricks Apps "
                "reverse proxy should inject this. Try refreshing the page."
            )
        return email
    return os.environ.get("DATABRICKS_USER_EMAIL", "local-dev@localhost")


def get_user_token() -> str:
    """Return the end-user's OBO access token for SQL warehouse queries.

    On Databricks Apps this comes from the X-Forwarded-Access-Token header.
    Locally it falls back to the DATABRICKS_TOKEN env var.

    Raises:
        AuthError: If running on Databricks Apps and the header is missing,
            or if running locally with no DATABRICKS_TOKEN set.
    """
    if is_databricks_app():
        token = st.context.headers.get("X-Forwarded-Access-Token")
        if not token:
            raise AuthError(
                "X-Forwarded-Access-Token header missing. "
                "Your session may have expired — please reload the page."
            )
        return token

    token = os.environ.get("DATABRICKS_TOKEN")
    if not token:
        raise AuthError(
            "DATABRICKS_TOKEN env var is not set. "
            "Run 'make env' to generate a .env file for local development."
        )
    return token
