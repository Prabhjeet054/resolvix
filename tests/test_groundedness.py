"""Tests for agent groundedness self-check (citation audit → escalate)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from agent.escalation import evaluate_escalation
from agent.groundedness import check_groundedness, heuristic_groundedness
from agent.resolver import TicketResolverAgent


TICKETS = [
    {
        "ticket_id": 103,
        "description": "password reset failed",
        "resolution": "reissue reset link",
        "language_code": "en",
        "category_name": "Login",
        "priority": "HIGH",
        "similarity_score": 0.92,
        "similarity_pct": 92.0,
        "source_mode": "IN_MEMORY",
    }
]


def test_heuristic_pass_when_every_step_cites():
    resolution = (
        "### Checklist\n"
        "1. Open the reset page [Ticket 103].\n"
        "2. Request a new link from [Ticket 103].\n"
        "3. Confirm login works (see [Ticket 103]).\n"
    )
    check = heuristic_groundedness(resolution, TICKETS)
    assert check.every_step_cited is True
    assert check.escalate is False
    assert check.score == 1.0
    assert check.cited_ticket_ids == [103]


def test_heuristic_fail_when_step_missing_citation():
    resolution = (
        "1. Open the reset page [Ticket 103].\n"
        "2. Clear browser cookies somehow.\n"
        "3. Retry login using [Ticket 103].\n"
    )
    check = heuristic_groundedness(resolution, TICKETS)
    assert check.every_step_cited is False
    assert check.escalate is True
    assert check.score < 1.0
    assert any("cookies" in s.lower() for s in check.ungrounded_steps)


def test_heuristic_fail_on_invented_ticket_id():
    resolution = (
        "1. Apply hotfix from [Ticket 999].\n"
        "2. Restart the service [Ticket 999].\n"
    )
    check = heuristic_groundedness(resolution, TICKETS)
    assert check.escalate is True
    assert 999 in check.invented_ticket_ids


def test_heuristic_na_without_retrieved_tickets():
    check = heuristic_groundedness("1. Gather logs.\n2. Escalate.", [])
    assert check.escalate is False
    assert check.score == 1.0
    assert "N/A" in check.summary


def test_llm_self_check_used_when_available():
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    mock_llm.chat.return_value = (
        '{"every_step_cited":false,"score":0.5,"step_count":2,'
        '"cited_step_count":1,"ungrounded_steps":["guess the password"],'
        '"cited_ticket_ids":[103],"invented_ticket_ids":[],'
        '"reasoning":"step 2 invents advice"}'
    )
    check = check_groundedness(
        "1. Use [Ticket 103].\n2. guess the password",
        TICKETS,
        llm=mock_llm,
    )
    assert check.method == "llm"
    assert check.escalate is True
    assert check.score == 0.5
    mock_llm.chat.assert_called_once()


def test_evaluate_escalation_on_groundedness_fail():
    decision = evaluate_escalation(
        top_similarity=0.95,
        priority="HIGH",
        category="TECH",
        groundedness_ok=False,
        groundedness_score=0.5,
        groundedness_detail="Groundedness FAIL — 1/2 steps lack citations",
    )
    assert decision.ESCALATION_REQUIRED is True
    assert any("Groundedness" in r or "groundedness" in r for r in decision.reasons)
    assert decision.on_call_specialist


def test_agent_escalates_when_ungrounded_llm_resolution():
    fake_vec = np.zeros(384, dtype=np.float32)
    fake_vec[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = True
    # classify → RAG → groundedness (fail) → optional translation skipped
    mock_llm.chat.side_effect = [
        '{"category":"TECH","priority":"MEDIUM","reasoning":"crash"}',
        (
            "1. Restart the laptop.\n"
            "2. Reinstall the OS from scratch.\n"
            "3. Buy a new device.\n"
        ),
        (
            '{"every_step_cited":false,"score":0.0,"step_count":3,'
            '"cited_step_count":0,"ungrounded_steps":["Restart the laptop"],'
            '"cited_ticket_ids":[],"invented_ticket_ids":[],'
            '"reasoning":"no citations"}'
        ),
    ]

    with patch("agent.resolver.generate_embedding", return_value=fake_vec), patch(
        "agent.resolver.find_similar_tickets", return_value=TICKETS
    ), patch("agent.resolver.detect_language", return_value="en"):
        result = TicketResolverAgent(llm=mock_llm).resolve("app crashes on launch")

    assert result.escalation_required is True
    assert result.groundedness is not None
    assert result.groundedness["escalate"] is True
    assert result.groundedness_score is not None
    assert result.groundedness_score < 1.0
    assert any(
        step["step"] == "groundedness_self_check" for step in result.trace_steps
    )


def test_offline_extractive_passes_groundedness():
    fake_vec = np.zeros(384, dtype=np.float32)
    fake_vec[0] = 1.0
    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    with patch("agent.resolver.generate_embedding", return_value=fake_vec), patch(
        "agent.resolver.find_similar_tickets", return_value=TICKETS
    ), patch("agent.resolver.detect_language", return_value="en"):
        result = TicketResolverAgent(llm=mock_llm).resolve("password reset failed")

    assert result.groundedness is not None
    assert result.groundedness["escalate"] is False
    assert result.groundedness_score == 1.0
    assert result.escalation_required is False
