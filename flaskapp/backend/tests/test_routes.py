"""Smoke tests for Flask routes — db.query_rows is mocked to avoid hitting Databricks."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask_backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_local(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["mode"] == "local"


@patch("flask_backend.routes.dashboard.query_rows")
def test_filters(mock_q, client):
    mock_q.side_effect = [
        [{"year": 2024}, {"year": 2023}],
        [{"region": "EMEA"}, {"region": "APAC"}],
        [{"product": "Widget"}, {"product": "Gadget"}],
    ]
    res = client.get("/api/dashboard/filters")
    assert res.status_code == 200
    body = res.get_json()
    assert body["years"] == [2024, 2023]
    assert body["regions"] == ["EMEA", "APAC"]
    assert body["products"] == ["Widget", "Gadget"]
    assert mock_q.call_count == 3


@patch("flask_backend.routes.dashboard.query_rows")
def test_kpis(mock_q, client):
    mock_q.return_value = [
        {"revenue": 1234.5, "orders": 7, "completed": 1000.0, "refunded": 234.5}
    ]
    res = client.post(
        "/api/dashboard/kpis",
        json={"year": 2024, "regions": ["EMEA"], "products": ["Widget"]},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body == {
        "revenue": 1234.5,
        "orders": 7,
        "completed": 1000.0,
        "refunded": 234.5,
    }


@patch("flask_backend.routes.dashboard.query_rows")
def test_kpis_validation_missing_year(mock_q, client):
    res = client.post("/api/dashboard/kpis", json={"regions": ["EMEA"], "products": ["W"]})
    assert res.status_code == 400
    mock_q.assert_not_called()


@patch("flask_backend.routes.dashboard.query_rows")
def test_kpis_validation_empty_regions(mock_q, client):
    res = client.post(
        "/api/dashboard/kpis",
        json={"year": 2024, "regions": [], "products": ["W"]},
    )
    assert res.status_code == 400
    mock_q.assert_not_called()


@patch("flask_backend.routes.dashboard.query_rows")
def test_monthly(mock_q, client):
    mock_q.return_value = [
        {"month": 1, "revenue": 100.0, "orders": 5},
        {"month": 2, "revenue": 200.0, "orders": 10},
    ]
    res = client.post(
        "/api/dashboard/monthly",
        json={"year": 2024, "regions": ["EMEA"], "products": ["Widget"]},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["points"] == [
        {"month": 1, "revenue": 100.0, "orders": 5},
        {"month": 2, "revenue": 200.0, "orders": 10},
    ]


@patch("flask_backend.routes.dashboard.query_rows")
def test_region_product(mock_q, client):
    mock_q.return_value = [
        {"region": "EMEA", "product": "Widget", "revenue": 500.0},
        {"region": "APAC", "product": "Gadget", "revenue": 750.0},
    ]
    res = client.post(
        "/api/dashboard/region-product",
        json={"year": 2024, "regions": ["EMEA", "APAC"], "products": ["Widget", "Gadget"]},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["rows"]) == 2
    assert body["rows"][0]["region"] == "EMEA"


@patch("flask_backend.routes.dashboard.query_rows")
def test_leaderboard(mock_q, client):
    mock_q.return_value = [
        {"rank": 1, "sales_rep": "Alice", "orders": 10, "revenue": 1000.0},
        {"rank": 2, "sales_rep": "Bob", "orders": 8, "revenue": 800.0},
    ]
    res = client.post("/api/dashboard/leaderboard", json={"year": 2024, "month": 3})
    assert res.status_code == 200
    body = res.get_json()
    assert body["rows"][0]["sales_rep"] == "Alice"
    assert body["rows"][1]["rank"] == 2


def test_leaderboard_invalid_month(client):
    res = client.post("/api/dashboard/leaderboard", json={"year": 2024, "month": 13})
    assert res.status_code == 400


def test_spa_responds_to_root(client):
    """The SPA catch-all returns 200 (with built dist) or 503 (without). Either is fine."""
    res = client.get("/")
    assert res.status_code in (200, 503)


def test_api_404_returns_json(client):
    """Unknown /api/* paths return JSON, not the SPA fallback HTML."""
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.is_json
    body = res.get_json()
    assert "error" in body
