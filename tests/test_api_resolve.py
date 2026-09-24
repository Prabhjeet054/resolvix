"""API webhook tests for Feature D (FastAPI /api/v1/resolve)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_resolve_schema():
    resp = client.get("/api/v1/resolve/schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint"] == "POST /api/v1/resolve"
    assert "resolution" in body["returns"]
    assert "similar_ticket_ids" in body["returns"]


def test_resolve_webhook_returns_resolution_and_ticket_ids():
    fake = np.zeros(384, dtype=np.float32)
    fake[0] = 1.0
    similar = [
        {
            "ticket_id": 42,
            "description": "password reset",
            "resolution": "reissue link",
            "language_code": "en",
            "category_name": "Login",
            "priority": "HIGH",
            "similarity_score": 0.91,
            "similarity_distance": 0.09,
            "similarity_pct": 91.0,
            "source_mode": "IN_MEMORY",
        }
    ]
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    with patch("agent.resolver.generate_embedding", return_value=fake), patch(
        "agent.resolver.find_similar_tickets", return_value=similar
    ), patch("agent.resolver.detect_language", return_value="en"), patch(
        "agent.resolver.OllamaClient", return_value=mock_llm
    ):
        resp = client.post(
            "/api/v1/resolve",
            json={
                "query": "Unable to reset my password",
                "customer_id": "zendesk-123",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "resolution" in data and data["resolution"]
    assert data["similar_ticket_ids"] == [42]
    assert data["customer_id"] == "zendesk-123"
    assert data["category"]
    assert data["priority"]


def test_resolve_rejects_empty_query():
    resp = client.post("/api/v1/resolve", json={"query": ""})
    assert resp.status_code == 422


def test_system_status_endpoint():
    with patch("api.main.is_db_available", return_value=False), patch(
        "api.main.OllamaClient"
    ) as mock_cls:
        mock = MagicMock()
        mock.is_available.return_value = False
        mock.list_models.return_value = []
        mock_cls.return_value = mock
        resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "oracle_ok" in body
    assert "ollama_ok" in body
    assert "models" in body
    assert body["oracle_ok"] is False


def test_file_ticket_offline_message():
    with patch("api.main.is_db_available", return_value=False):
        resp = client.post(
            "/api/v1/tickets",
            json={
                "description": "Cannot login",
                "category": "SECURITY",
                "priority": "HIGH",
                "language_code": "en",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filed"] is False
    assert body["ticket_id"] is None
    assert "offline" in body["message"].lower()


def test_frontend_index_served():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert b"Resolvix" in resp.content
    assert b"Emerging Incidents" in resp.content
    assert b"incident-clusters" in resp.content


def test_incidents_last_24h_includes_ticket_links():
    fake_report = {
        "status": "ok",
        "tickets_analyzed": 12,
        "method": "dbscan",
        "similarity_threshold": 0.88,
        "min_cluster_size": 5,
        "alerts": [
            {
                "cluster_id": 0,
                "ticket_ids": [101, 102, 103, 104, 105],
                "size": 5,
                "avg_similarity": 0.93,
                "message": "Emerging Major Incident Alert: 5 tickets",
                "method": "dbscan",
                "window_hours": None,
                "sample_descriptions": ["password reset failed"],
            }
        ],
        "hourly_burst_alerts": [],
        "message": "Analyzed 12 tickets; 1 cluster alert(s), 0 hourly burst alert(s).",
    }
    with patch("analytics.clustering.analyze_last_24h", return_value=fake_report):
        resp = client.get(
            "/api/v1/incidents/last-24h",
            params={"method": "dbscan", "hours": 24},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tickets_analyzed"] == 12
    assert body["hours"] == 24
    assert body["alerts"][0]["ticket_links"] == [
        {"ticket_id": 101, "href": "#ticket-101"},
        {"ticket_id": 102, "href": "#ticket-102"},
        {"ticket_id": 103, "href": "#ticket-103"},
        {"ticket_id": 104, "href": "#ticket-104"},
        {"ticket_id": 105, "href": "#ticket-105"},
    ]
