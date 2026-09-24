"""Tests for thumbs feedback persistence and retrieval suppression."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from feedback.store import (
    apply_feedback_to_matches,
    list_flagged_resolutions,
    record_feedback,
    should_suppress_ticket,
    _load,
)


client = TestClient(app)


def test_record_downvote_flags_and_suppresses_weak_match(tmp_path: Path):
    store = tmp_path / "feedback_store.json"
    result = record_feedback(
        "down",
        query="password reset broken",
        resolution="try again later",
        similar_ticket_ids=[109, 110],
        category="SECURITY",
        priority="HIGH",
        source="test",
        store_path=store,
    )
    assert result["recorded"] is True
    assert result["flagged"] is not None
    assert result["flagged"]["status"] == "open"
    assert 109 in result["suppressed_ticket_ids"]

    data = _load(store)
    assert data["ticket_votes"]["109"]["down"] == 1
    assert len(list_flagged_resolutions(store_path=store)) == 1

    # Weak downvoted match is dropped; strong match is kept but flagged.
    filtered = apply_feedback_to_matches(
        [
            {
                "ticket_id": 109,
                "similarity_score": 0.70,
                "description": "weak",
            },
            {
                "ticket_id": 200,
                "similarity_score": 0.95,
                "description": "strong clean",
            },
            {
                "ticket_id": 110,
                "similarity_score": 0.92,
                "description": "strong but downvoted",
            },
        ],
        store_path=store,
    )
    ids = [m["ticket_id"] for m in filtered]
    assert 109 not in ids
    assert 200 in ids
    assert 110 in ids
    flagged = next(m for m in filtered if m["ticket_id"] == 110)
    assert flagged.get("feedback_flagged") is True


def test_upvote_offsets_suppression(tmp_path: Path):
    store = tmp_path / "feedback_store.json"
    record_feedback(
        "down",
        query="q",
        similar_ticket_ids=[42],
        store_path=store,
    )
    record_feedback(
        "up",
        query="q",
        similar_ticket_ids=[42],
        store_path=store,
    )
    data = _load(store)
    assert should_suppress_ticket(data, 42, 0.5) is False


def test_feedback_api_endpoints(tmp_path: Path, monkeypatch):
    store = tmp_path / "api_feedback.json"
    monkeypatch.setattr("feedback.store.DEFAULT_STORE_PATH", store)

    resp = client.post(
        "/api/v1/feedback",
        json={
            "vote": "down",
            "query": "app crash on launch",
            "resolution": "reinstall the app",
            "similar_ticket_ids": [150, 151],
            "source": "test",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recorded"] is True
    assert body["vote"] == "down"
    assert body["flagged"]["status"] == "open"

    review = client.get("/api/v1/feedback/review")
    assert review.status_code == 200
    payload = review.json()
    assert payload["stats"]["down"] >= 1
    assert len(payload["flagged"]) >= 1
