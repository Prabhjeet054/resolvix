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
