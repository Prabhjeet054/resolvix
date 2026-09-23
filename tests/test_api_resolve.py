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
