"""Unit tests for hybrid vector + keyword retrieval."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np

from embeddings.hybrid import (
    extract_technical_terms,
    merge_hybrid_results,
)
from embeddings.similarity_search import (
    build_oracle_hybrid_sql,
    find_similar_tickets,
)


def test_extract_error_codes_ticket_ids_products():
    terms = extract_technical_terms(
        'Getting HTTP 429 from Salesforce sync on ticket #153 — also ORA-12541'
    )
    assert "HTTP429" in terms["error_codes"] or any(
        "429" in c for c in terms["error_codes"]
    )
    assert any("ORA" in c for c in terms["error_codes"])
    assert 153 in terms["ticket_ids"]
    assert any(p.lower() == "salesforce" for p in terms["products"])
    assert terms["has_keywords"] is True


def test_merge_prefers_exact_ticket_and_hybrid():
    vector = [
        {
            "ticket_id": 10,
            "similarity_score": 0.91,
            "similarity_pct": 91.0,
            "similarity_distance": 0.09,
            "description": "vector only",
            "source_mode": "ORACLE_23AI",
        },
        {
            "ticket_id": 20,
            "similarity_score": 0.70,
            "similarity_pct": 70.0,
            "similarity_distance": 0.30,
            "description": "will become hybrid",
            "source_mode": "ORACLE_23AI",
        },
    ]
    keyword = [
        {
            "ticket_id": 20,
            "similarity_score": 0.75,
            "keyword_hits": ["HTTP 429"],
            "exact_ticket": False,
            "source_mode": "ORACLE_KEYWORD",
        },
        {
            "ticket_id": 99,
            "similarity_score": 0.5,
            "keyword_hits": ["ticket:99"],
            "exact_ticket": True,
            "source_mode": "ORACLE_KEYWORD",
            "description": "exact ticket id",
        },
    ]
    merged = merge_hybrid_results(vector, keyword, top_n=3)
    assert merged[0]["ticket_id"] == 99
    assert merged[0]["exact_ticket"] is True
    hybrid = next(m for m in merged if m["ticket_id"] == 20)
    assert hybrid["match_type"] == "hybrid"
    assert "HTTP 429" in hybrid["keyword_hits"]
    assert hybrid["similarity_score"] > 0.70


def test_build_oracle_hybrid_sql_includes_both_branches():
    sql = build_oracle_hybrid_sql(
        query_text="HTTP 429 rate limit on API",
        category_filter="Technical",
    )
    assert "VECTOR_DISTANCE" in sql
    assert "LIKE" in sql
    assert "HTTP" in sql.upper() or "429" in sql


def test_find_similar_tickets_hybrid_in_memory():
    fake = np.zeros(384, dtype=np.float32)
    fake[0] = 1.0
    records = (
        {
            "ticket_id": 201,
            "description": "Generic login trouble",
            "language_code": "en",
            "category_name": "Login",
            "resolution": "reset",
            "priority": "HIGH",
            "ticket_status": "RESOLVED",
        },
        {
            "ticket_id": 202,
            "description": "Our team is receiving HTTP 429 Too Many Requests errors",
            "language_code": "en",
            "category_name": "Technical",
            "resolution": "backoff",
            "priority": "HIGH",
            "ticket_status": "RESOLVED",
        },
    )
    # Orthogonal / aligned embeddings: 202 aligns with query
    matrix = np.zeros((2, 384), dtype=np.float32)
    matrix[0, 1] = 1.0
    matrix[1, 0] = 1.0

    with patch(
        "embeddings.similarity_search._load_seed_corpus",
        return_value=(records, matrix),
    ), patch("embeddings.similarity_search.is_db_available", return_value=False):
        results = find_similar_tickets(
            fake,
            top_n=2,
            prefer_oracle=False,
            apply_feedback=False,
            query_text="API returns HTTP 429 when syncing",
        )

    assert results
    assert any(
        r["ticket_id"] == 202
        and r.get("match_type") in {"hybrid", "keyword"}
        and any("429" in str(h) for h in (r.get("keyword_hits") or []))
        for r in results
    )
