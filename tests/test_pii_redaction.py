"""Tests for PII redaction before embed / LLM / storage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from api.main import app
from agent.resolver import TicketResolverAgent
from privacy.redact import redact_pii, redact_text


client = TestClient(app)


def test_redact_email_phone_account_id():
    text = (
        "Contact jane.doe@example.com or +1 (555) 123-4567 about "
        "account ID ACC-998877 please."
    )
    result = redact_pii(text)
    assert result.redacted is True
    assert "[EMAIL]" in result.text
    assert "[PHONE]" in result.text
    assert "[ACCOUNT_ID]" in result.text
    assert "jane.doe@example.com" not in result.text
    assert "555" not in result.text or "[PHONE]" in result.text
    assert "ACC-998877" not in result.text
    assert result.counts.get("email") == 1
    assert result.counts.get("phone", 0) >= 1
    assert result.counts.get("account_id") == 1


def test_redact_leaves_normal_support_text():
    text = "Unable to reset my password — the reset link expires immediately."
    result = redact_pii(text)
    assert result.redacted is False
    assert result.text == text


def test_agent_redacts_query_before_embed_and_llm():
    fake = np.zeros(384, dtype=np.float32)
    fake[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False
    similar = [
        {
            "ticket_id": 1,
            "description": "login issue",
            "resolution": "reset",
            "language_code": "en",
            "category_name": "Login",
            "priority": "HIGH",
            "similarity_score": 0.9,
            "similarity_distance": 0.1,
            "similarity_pct": 90.0,
            "source_mode": "IN_MEMORY",
        }
    ]

    dirty = "Help me at person@company.com phone 555-987-6543 acct:CUST-42"
    with patch("agent.resolver.generate_embedding", return_value=fake) as emb, patch(
        "agent.resolver.find_similar_tickets", return_value=similar
    ), patch("agent.resolver.detect_language", return_value="en"):
        result = TicketResolverAgent(llm=mock_llm).resolve(dirty)

    embedded_text = emb.call_args.args[0]
    assert "person@company.com" not in embedded_text
    assert "[EMAIL]" in embedded_text or "EMAIL" in embedded_text
    assert result.pii_redacted is True
    assert "person@company.com" not in result.query
    assert "[EMAIL]" in result.query


def test_api_resolve_returns_pii_flags():
    fake = np.zeros(384, dtype=np.float32)
    fake[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False
    similar = [
        {
            "ticket_id": 9,
            "description": "x",
            "resolution": "y",
            "language_code": "en",
            "category_name": "General",
            "priority": "LOW",
            "similarity_score": 0.5,
            "similarity_distance": 0.5,
            "similarity_pct": 50.0,
            "source_mode": "IN_MEMORY",
        }
    ]
    with patch("agent.resolver.generate_embedding", return_value=fake), patch(
        "agent.resolver.find_similar_tickets", return_value=similar
    ), patch("agent.resolver.detect_language", return_value="en"), patch(
        "agent.resolver.OllamaClient", return_value=mock_llm
    ):
        resp = client.post(
            "/api/v1/resolve",
            json={"query": "Email me at a@b.co about account id ACC-1A2B"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pii_redacted"] is True
    assert body["pii_counts"].get("email", 0) >= 1
    assert "[EMAIL]" in body["query"]


def test_redact_text_helper():
    assert redact_text("user@example.com") == "[EMAIL]"
