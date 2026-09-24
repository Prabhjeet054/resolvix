"""End-to-end regression tests for the agentic RAG pipeline (offline-safe)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agent.prompts import format_evidence
from agent.resolver import (
    TicketResolverAgent,
    _extractive_resolution,
    _heuristic_classification,
    _parse_classification,
)
from analytics.clustering import cluster_recent_embeddings
from embeddings.similarity_search import build_oracle_hybrid_sql, build_oracle_sql, find_similar_in_memory


def test_parse_classification_json():
    raw = '{"category":"SECURITY","priority":"HIGH","reasoning":"login issue"}'
    cat, pri, reason = _parse_classification(raw)
    assert cat == "SECURITY"
    assert pri == "HIGH"
    assert "login" in reason


def test_parse_classification_fenced():
    raw = '```json\n{"category":"BILLING","priority":"CRITICAL","reasoning":"refund"}\n```'
    cat, pri, _ = _parse_classification(raw)
    assert cat == "BILLING"
    assert pri == "CRITICAL"


def test_heuristic_classification_login():
    cat, pri, _ = _heuristic_classification("password reset link expired")
    assert cat == "SECURITY"
    assert pri == "HIGH"


def test_build_oracle_sql_includes_vector_distance():
    sql = build_oracle_sql("Login", "HIGH")
    assert "VECTOR_DISTANCE" in sql
    assert "COSINE" in sql
    assert "category_filter" in sql
    assert "priority_filter" in sql


def test_build_oracle_hybrid_sql_documents_keyword_branch():
    sql = build_oracle_hybrid_sql("ORA-12541 on ticket #109")
    assert "VECTOR_DISTANCE" in sql
    assert "Hybrid search" in sql
    assert "ticket:109" in sql or "109" in sql


def test_find_similar_in_memory_returns_scores():
    # Deterministic unit vector query against corpus (may be slow on first model load)
    rng = np.random.default_rng(0)
    fake = rng.normal(size=384).astype(np.float32)
    fake /= np.linalg.norm(fake)
    with patch(
        "embeddings.similarity_search._load_seed_corpus"
    ) as mock_corpus:
        records = (
            {
                "ticket_id": 101,
                "description": "password reset failed",
                "language_code": "en",
                "category_name": "Login",
                "resolution": "reset tokens",
                "priority": "HIGH",
                "ticket_status": "RESOLVED",
            },
        )
        matrix = fake.reshape(1, -1)
        mock_corpus.return_value = (records, matrix)
        results = find_similar_in_memory(fake, top_n=1, category_filter="Login")
    assert len(results) == 1
    assert results[0]["source_mode"] == "IN_MEMORY"
    assert results[0]["similarity_score"] == pytest.approx(1.0, abs=1e-5)


def test_extractive_resolution_cites_tickets():
    tickets = [
        {
            "ticket_id": 103,
            "category_name": "Login",
            "priority": "HIGH",
            "similarity_pct": 88.5,
            "resolution": "Issued fresh reset email",
        }
    ]
    text = _extractive_resolution("reset password", tickets)
    assert "Ticket 103" in text
    assert "Issued fresh reset email" in text


def test_format_evidence():
    block = format_evidence(
        [
            {
                "ticket_id": 1,
                "language_code": "en",
                "category_name": "Billing",
                "priority": "HIGH",
                "similarity_pct": 90.0,
                "description": "double charge",
                "resolution": "refunded",
            }
        ]
    )
    assert "Ticket 1" in block
    assert "refunded" in block


def test_clustering_alerts_on_dense_group():
    # Five near-identical vectors should trigger an alert
    base = np.ones(8, dtype=np.float32)
    noise = np.eye(8, dtype=np.float32) * 0.01
    embeddings = np.stack([base + noise[i % 8] for i in range(5)])
    alerts = cluster_recent_embeddings(
        ticket_ids=[1, 2, 3, 4, 5],
        embeddings=embeddings,
        similarity_threshold=0.88,
        min_cluster_size=5,
        method="greedy",
    )
    assert len(alerts) == 1
    assert alerts[0].size == 5


def test_dbscan_clustering_dense_group():
    base = np.ones(16, dtype=np.float32)
    embeddings = np.stack([base + (i * 0.001) for i in range(5)])
    alerts = cluster_recent_embeddings(
        ticket_ids=[11, 12, 13, 14, 15],
        embeddings=embeddings,
        similarity_threshold=0.88,
        min_cluster_size=5,
        method="dbscan",
    )
    assert len(alerts) >= 1
    assert alerts[0].size >= 5


def test_hourly_burst_detection():
    from datetime import datetime, timedelta, timezone

    from analytics.clustering import detect_hourly_bursts

    base = np.ones(8, dtype=np.float32)
    embeddings = np.stack([base for _ in range(5)])
    now = datetime.now(timezone.utc)
    created = [now - timedelta(minutes=i * 5) for i in range(5)]
    alerts = detect_hourly_bursts(
        ticket_ids=[1, 2, 3, 4, 5],
        embeddings=embeddings,
        created_at=created,
        similarity_threshold=0.88,
        min_cluster_size=5,
    )
    assert len(alerts) == 1
    assert "Emerging Major Incident Alert" in alerts[0].message


def test_agent_resolve_offline_pipeline():
    """Full resolve path with Oracle + Ollama mocked offline."""
    fake_vec = np.zeros(384, dtype=np.float32)
    fake_vec[0] = 1.0

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False
    mock_llm.model = "llama3.2:3b"

    similar = [
        {
            "ticket_id": 109,
            "description": "app crash splash",
            "resolution": "roll back build",
            "language_code": "en",
            "category_name": "Technical",
            "priority": "HIGH",
            "similarity_score": 0.91,
            "similarity_distance": 0.09,
            "similarity_pct": 91.0,
            "source_mode": "IN_MEMORY",
        }
    ]

    with patch("agent.resolver.generate_embedding", return_value=fake_vec), patch(
        "agent.resolver.find_similar_tickets", return_value=similar
    ), patch("agent.resolver.detect_language", return_value="en"):
        agent = TicketResolverAgent(llm=mock_llm)
        result = agent.resolve("mobile app crashes on splash screen")

    assert result.search_backend == "IN_MEMORY"
    assert result.llm_available is False
    assert result.classified_category in {"TECH", "SECURITY", "GENERAL", "BILLING", "ACCOUNT"}
    assert "Ticket 109" in result.synthesized_resolution or "roll back" in result.synthesized_resolution
    assert len(result.trace_steps) >= 4
    assert "VECTOR_DISTANCE" in result.live_sql
    # High similarity should not force escalation unless CRITICAL
    assert result.confidence >= 0.9
    assert result.escalation_required is False


def test_agent_escalation_on_low_confidence():
    fake_vec = np.zeros(384, dtype=np.float32)
    fake_vec[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    similar = [
        {
            "ticket_id": 1,
            "description": "weather is nice",
            "resolution": "n/a",
            "language_code": "en",
            "category_name": "General",
            "priority": "LOW",
            "similarity_score": 0.2,
            "similarity_distance": 0.8,
            "similarity_pct": 20.0,
            "source_mode": "IN_MEMORY",
        }
    ]

    with patch("agent.resolver.generate_embedding", return_value=fake_vec), patch(
        "agent.resolver.find_similar_tickets", return_value=similar
    ), patch("agent.resolver.detect_language", return_value="en"):
        result = TicketResolverAgent(llm=mock_llm).resolve("completely unrelated query xyz")

    assert result.escalation_required is True
    assert result.escalation_hint is not None
    assert result.escalation is not None
    assert result.escalation["ESCALATION_REQUIRED"] is True
    assert result.escalation["on_call_specialist"]
    assert result.escalation["department"]


def test_evaluate_escalation_critical_priority():
    from agent.escalation import evaluate_escalation

    decision = evaluate_escalation(
        top_similarity=0.95,
        priority="CRITICAL",
        category="SECURITY",
    )
    assert decision.ESCALATION_REQUIRED is True
    assert "CRITICAL" in "".join(decision.reasons)
    assert decision.tier == "Tier-3"
    assert "Jordan Blake" in (decision.on_call_specialist or "")
    assert decision.threshold == 0.65


def test_evaluate_escalation_high_confidence_no_page():
    from agent.escalation import evaluate_escalation

    decision = evaluate_escalation(
        top_similarity=0.91,
        priority="HIGH",
        category="TECH",
    )
    assert decision.ESCALATION_REQUIRED is False
    assert decision.on_call_specialist is None
    assert decision.threshold == 0.65


def test_agent_refine_reuses_prior_tickets_no_fresh_search():
    fake_vec = np.zeros(384, dtype=np.float32)
    fake_vec[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    prior = [
        {
            "ticket_id": 42,
            "description": "password reset expired",
            "resolution": "reissue reset link",
            "language_code": "en",
            "category_name": "Login",
            "priority": "HIGH",
            "similarity_score": 0.93,
            "similarity_distance": 0.07,
            "similarity_pct": 93.0,
            "source_mode": "IN_MEMORY",
        }
    ]

    with patch("agent.resolver.generate_embedding", return_value=fake_vec) as emb, patch(
        "agent.resolver.find_similar_tickets"
    ) as find_sim, patch("agent.resolver.detect_language", return_value="en"):
        result = TicketResolverAgent(llm=mock_llm).resolve(
            "Can you simplify this for a non-technical user?",
            chat_history=[
                {"role": "user", "content": "Unable to reset my password"},
                {"role": "assistant", "content": "1. Open reset link\n2. Set new password"},
            ],
            prior_tickets=prior,
            original_query="Unable to reset my password",
        )

    find_sim.assert_not_called()
    emb.assert_called()  # still embeds original issue for confidence path
    assert result.refine_mode is True
    assert result.reused_prior_tickets is True
    assert result.original_query == "Unable to reset my password"
    assert [t["ticket_id"] for t in result.similar_tickets] == [42]
    assert "Ticket 42" in result.synthesized_resolution or "reissue" in result.synthesized_resolution
    assert "Refine & Clarify" in result.live_sql
