"""Dashboard API endpoints — read-only port of the Streamlit dashboard.

All endpoints query the SQL warehouse using the app's Service Principal
credentials. No user-scoped (OBO) reads here; this matches the simpler
'SP-only' auth model the user selected at scaffold time.

Endpoints:
  GET  /api/dashboard/filters          — distinct year/region/product values
  POST /api/dashboard/kpis             — KPIs for a (year, regions, products) selection
  POST /api/dashboard/monthly          — monthly revenue + orders for a selection
  POST /api/dashboard/region-product   — revenue pivot by region × product
  POST /api/dashboard/leaderboard      — rep leaderboard for (year, month)
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from flask_backend.db import T_MV_LEADER, T_MV_MONTHLY, query_rows

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n) if n else "NULL"


def _validate_selection(payload: dict) -> tuple[int, list[str], list[str]]:
    """Extract and validate (year, regions, products) from a JSON request body.

    Aborts with 400 on missing/invalid fields. Region/product names are passed
    as parameters to the SQL driver, but we still bound list size to keep
    queries reasonable.
    """
    if not isinstance(payload, dict):
        abort(400, "Request body must be a JSON object.")
    try:
        year = int(payload["year"])
    except (KeyError, TypeError, ValueError):
        abort(400, "Field 'year' is required and must be an integer.")
    regions = payload.get("regions") or []
    products = payload.get("products") or []
    if not isinstance(regions, list) or not isinstance(products, list):
        abort(400, "Fields 'regions' and 'products' must be arrays of strings.")
    if not regions or not products:
        abort(400, "Select at least one region and one product.")
    if len(regions) > 100 or len(products) > 100:
        abort(400, "Too many regions or products selected.")
    if not all(isinstance(x, str) for x in regions + products):
        abort(400, "All region/product values must be strings.")
    return year, regions, products


@bp.get("/filters")
def filters():
    years = [
        r["year"]
        for r in query_rows(f"SELECT DISTINCT year FROM {T_MV_MONTHLY} ORDER BY year DESC")
    ]
    regions = [
        r["region"]
        for r in query_rows(f"SELECT DISTINCT region FROM {T_MV_MONTHLY} ORDER BY region")
    ]
    products = [
        r["product"]
        for r in query_rows(f"SELECT DISTINCT product FROM {T_MV_MONTHLY} ORDER BY product")
    ]
    return jsonify({"years": years, "regions": regions, "products": products})


@bp.post("/kpis")
def kpis():
    year, regions, products = _validate_selection(request.get_json(silent=True) or {})
    sql = f"""
        SELECT
            COALESCE(SUM(total_revenue), 0)     AS revenue,
            COALESCE(SUM(order_count), 0)       AS orders,
            COALESCE(SUM(completed_revenue), 0) AS completed,
            COALESCE(SUM(refunded_revenue), 0)  AS refunded
        FROM {T_MV_MONTHLY}
        WHERE year = ?
          AND region IN ({_placeholders(len(regions))})
          AND product IN ({_placeholders(len(products))})
    """
    row = query_rows(sql, [year, *regions, *products])
    if not row:
        return jsonify({"revenue": 0, "orders": 0, "completed": 0, "refunded": 0})
    r = row[0]
    return jsonify(
        {
            "revenue": float(r["revenue"] or 0),
            "orders": int(r["orders"] or 0),
            "completed": float(r["completed"] or 0),
            "refunded": float(r["refunded"] or 0),
        }
    )


@bp.post("/monthly")
def monthly():
    year, regions, products = _validate_selection(request.get_json(silent=True) or {})
    sql = f"""
        SELECT month,
               COALESCE(SUM(total_revenue), 0) AS revenue,
               COALESCE(SUM(order_count), 0)   AS orders
        FROM {T_MV_MONTHLY}
        WHERE year = ?
          AND region IN ({_placeholders(len(regions))})
          AND product IN ({_placeholders(len(products))})
        GROUP BY month
        ORDER BY month
    """
    rows = query_rows(sql, [year, *regions, *products])
    points = [
        {
            "month": int(r["month"]),
            "revenue": float(r["revenue"] or 0),
            "orders": int(r["orders"] or 0),
        }
        for r in rows
    ]
    return jsonify({"points": points})


@bp.post("/region-product")
def region_product():
    year, regions, products = _validate_selection(request.get_json(silent=True) or {})
    sql = f"""
        SELECT region, product,
               COALESCE(SUM(total_revenue), 0) AS revenue
        FROM {T_MV_MONTHLY}
        WHERE year = ?
          AND region IN ({_placeholders(len(regions))})
          AND product IN ({_placeholders(len(products))})
        GROUP BY region, product
        ORDER BY region, product
    """
    rows = query_rows(sql, [year, *regions, *products])
    return jsonify(
        {
            "rows": [
                {
                    "region": r["region"],
                    "product": r["product"],
                    "revenue": float(r["revenue"] or 0),
                }
                for r in rows
            ]
        }
    )


@bp.post("/leaderboard")
def leaderboard():
    payload = request.get_json(silent=True) or {}
    try:
        year = int(payload["year"])
        month = int(payload["month"])
    except (KeyError, TypeError, ValueError):
        abort(400, "Fields 'year' and 'month' are required integers.")
    if not (1 <= month <= 12):
        abort(400, "Field 'month' must be between 1 and 12.")
    sql = f"""
        SELECT rank, sales_rep, orders, revenue
        FROM {T_MV_LEADER}
        WHERE year = ? AND month = ?
        ORDER BY rank
    """
    rows = query_rows(sql, [year, month])
    return jsonify(
        {
            "rows": [
                {
                    "rank": int(r["rank"]),
                    "sales_rep": r["sales_rep"],
                    "orders": int(r["orders"] or 0),
                    "revenue": float(r["revenue"] or 0),
                }
                for r in rows
            ]
        }
    )
