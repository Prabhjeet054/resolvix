"""TicketResolverAgent — orchestrates embed → retrieve → classify → RAG → localize."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.escalation import evaluate_escalation
from agent.llm_client import OllamaClient
from agent.prompts import (
    CLASSIFICATION_PROMPT,
    RAG_SYNTHESIS_PROMPT,
    REFINE_PROMPT,
    SYSTEM_PROMPT,
    TRANSLATION_PROMPT,
    format_evidence,
)
from embeddings.generate import generate_embedding
from embeddings.languages import detect_language, get_language_name
from embeddings.similarity_search import build_oracle_hybrid_sql, find_similar_tickets
from privacy.redact import (
    merge_counts,
    redact_chat_history,
    redact_pii,
    redact_tickets,
)


@dataclass
class AgentResult:
    """Structured output of a full Resolvix agent run."""

    query: str
    detected_language_code: str
    detected_language_name: str
    classified_category: str
    classified_priority: str
    similar_tickets: list[dict]
    synthesized_resolution: str
    localized_resolution: str | None
    search_backend: str  # ORACLE_23AI | IN_MEMORY
    confidence: float
    escalation_required: bool
    escalation_hint: str | None
    live_sql: str
    trace_steps: list[dict] = field(default_factory=list)
    llm_available: bool = False
    classification_reasoning: str = ""
    escalation: dict | None = None  # full HITL EscalationDecision payload
    refine_mode: bool = False
    reused_prior_tickets: bool = False
    original_query: str | None = None
    pii_redacted: bool = False
    pii_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _parse_classification(raw: str) -> tuple[str, str, str]:
    """Extract category/priority/reasoning from LLM JSON (tolerant of fences)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Attempt to locate first JSON object
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return "GENERAL", "MEDIUM", "fallback: unparseable LLM classification"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return "GENERAL", "MEDIUM", "fallback: unparseable LLM classification"

    category = str(data.get("category", "GENERAL")).upper()
    priority = str(data.get("priority", "MEDIUM")).upper()
    reasoning = str(data.get("reasoning", "")).strip()

    if category not in {"TECH", "BILLING", "ACCOUNT", "SECURITY", "GENERAL"}:
        category = "GENERAL"
    if priority not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
        priority = "MEDIUM"
    return category, priority, reasoning


def _heuristic_classification(query: str) -> tuple[str, str, str]:
    """Offline fallback when Ollama is unavailable."""
    q = query.lower()
    if any(k in q for k in ("password", "login", "mfa", "otp", "2fa", "token", "sso")):
        return "SECURITY", "HIGH", "heuristic: auth/login keywords"
    if any(k in q for k in ("bill", "invoice", "charge", "refund", "upi", "payment", "subscription")):
        return "BILLING", "HIGH", "heuristic: billing keywords"
    if any(k in q for k in ("crash", "error", "bug", "slow", "latency", "timeout", "app")):
        return "TECH", "MEDIUM", "heuristic: technical keywords"
    if any(k in q for k in ("account", "profile", "permission", "access")):
        return "ACCOUNT", "MEDIUM", "heuristic: account keywords"
    return "GENERAL", "MEDIUM", "heuristic: default"


def _extractive_resolution(query: str, tickets: list[dict]) -> str:
    """Deterministic RAG-style summary when the LLM is offline."""
    if not tickets:
        return (
            "### Suggested next steps\n"
            "1. No similar resolved tickets were found in the knowledge base.\n"
            "2. Gather reproduction steps, error codes, and affected environment.\n"
            "3. Escalate to the on-call tier-2 specialist for this category.\n"
        )

    lines = [
        "### Suggested resolution (evidence-based, LLM offline)",
        f"_Query:_ {query.strip()}",
        "",
        "Based on the closest historical tickets:",
    ]
    for t in tickets:
        pct = t.get("similarity_pct")
        if pct is None:
            pct = round(float(t.get("similarity_score") or 0) * 100.0, 1)
        lines.append(
            f"- **[Ticket {t.get('ticket_id')}]** ({pct}% similar, "
            f"{t.get('category_name')}/{t.get('priority')}): "
            f"{t.get('resolution') or 'No resolution text stored.'}"
        )
    lines.extend(
        [
            "",
            "### Recommended checklist",
            "1. Confirm the symptom matches the cited ticket(s).",
            "2. Apply the most relevant historical resolution steps above.",
            "3. Verify with the customer and close or escalate if unresolved.",
        ]
    )
    return "\n".join(lines)


def _department_for_category(category: str) -> str:
    """Backward-compatible department label helper."""
    from agent.escalation import recommend_routing

    route = recommend_routing(category)
    return f"{route['tier']} {route['department']}"


class TicketResolverAgent:
    """Master orchestrator for multilingual agentic RAG resolution."""

    def __init__(self, llm: OllamaClient | None = None, model: str | None = None) -> None:
        self.llm = llm or OllamaClient(model=model)

    def resolve(
        self,
        query: str,
        top_n: int = 3,
        category_filter: str | None = None,
        priority_filter: str | None = None,
        language_override: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
        prior_tickets: list[dict] | None = None,
        original_query: str | None = None,
    ) -> AgentResult:
        """Run the full pipeline and return a structured AgentResult.

        When ``chat_history`` / ``prior_tickets`` are provided, runs in
        Refine & Clarify mode: prior retrieved tickets stay as evidence and
        the follow-up is answered with conversation context via Ollama.
        """
        trace: list[dict] = []
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("query must be a non-empty string")

        # PII redaction before embed / LLM (emails, phones, account IDs).
        query_redaction = redact_pii(clean_query)
        clean_query = query_redaction.text.strip() or clean_query
        pii_totals = dict(query_redaction.counts)

        history_in = list(chat_history or [])
        history_in, hist_counts = redact_chat_history(history_in)
        pii_totals = merge_counts(pii_totals, hist_counts)

        tickets_in = list(prior_tickets or [])
        tickets_in, ticket_counts = redact_tickets(tickets_in)
        pii_totals = merge_counts(pii_totals, ticket_counts)

        orig_raw = (original_query or "").strip()
        if orig_raw:
            orig_redaction = redact_pii(orig_raw)
            original_query = orig_redaction.text.strip() or orig_raw
            pii_totals = merge_counts(pii_totals, orig_redaction.counts)

        chat_history = history_in or None
        prior_tickets = tickets_in or None

        refine_mode = bool(chat_history) or bool(prior_tickets)
        base_issue = (original_query or clean_query).strip()

        trace.append(
            {
                "step": "pii_redaction",
                "duration_ms": 0.0,
                "details": (
                    f"redacted={bool(pii_totals)} counts={pii_totals or '{}'}"
                ),
            }
        )

        # Language detection (prefer original issue language in refine mode)
        t0 = _now_ms()
        detect_text = base_issue if refine_mode else clean_query
        lang_code = (language_override or detect_language(detect_text)).lower()
        lang_name = get_language_name(lang_code)
        trace.append(
            {
                "step": "language_detection",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"{lang_name} ({lang_code})"
                + (" [refine]" if refine_mode else ""),
            }
        )

        # Embedding + retrieval (reuse prior tickets on follow-up when available)
        t0 = _now_ms()
        reused_prior = False
        if refine_mode and prior_tickets:
            # Keep the same evidence set for Refine & Clarify follow-ups.
            similar = [dict(t) for t in prior_tickets if isinstance(t, dict)]
            if top_n >= 1:
                similar = similar[:top_n]
            embedding = generate_embedding(base_issue)
            reused_prior = True
            retrieval_detail = f"reused prior tickets ({len(similar)}) [refine]"
        elif refine_mode:
            # Follow-up without explicit tickets: re-retrieve on the original issue,
            # not the short follow-up phrase ("simplify for non-tech").
            embedding = generate_embedding(base_issue)
            similar = find_similar_tickets(
                embedding,
                top_n=top_n,
                category_filter=category_filter,
                priority_filter=priority_filter,
                query_text=base_issue,
            )
            retrieval_detail = (
                f"refine re-retrieve on original issue matches={len(similar)}"
            )
        else:
            embedding = generate_embedding(clean_query)
            similar = find_similar_tickets(
                embedding,
                top_n=top_n,
                category_filter=category_filter,
                priority_filter=priority_filter,
                query_text=clean_query,
            )
            flagged_n = sum(1 for t in similar if t.get("feedback_flagged"))
            hybrid_n = sum(
                1 for t in similar if t.get("match_type") in {"hybrid", "keyword"}
            )
            retrieval_detail = (
                f"fresh hybrid search matches={len(similar)}"
                + (f", keyword/hybrid={hybrid_n}" if hybrid_n else "")
                + (f", feedback_flagged={flagged_n}" if flagged_n else "")
            )
        trace.append(
            {
                "step": "embedding",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"dim={embedding.shape[0]} model=paraphrase-multilingual-MiniLM-L12-v2",
            }
        )

        if similar:
            backend = str(similar[0].get("source_mode", "IN_MEMORY"))
        else:
            from db.connection import is_db_available

            backend = "ORACLE_23AI" if is_db_available() else "IN_MEMORY"

        live_sql = build_oracle_hybrid_sql(
            query_text=base_issue if refine_mode else clean_query,
            category_filter=category_filter,
            priority_filter=priority_filter,
        )
        if refine_mode:
            live_sql = (
                "-- Refine & Clarify: evidence reused from prior resolve "
                f"({len(similar)} ticket(s)); follow-up does not re-rank search.\n"
                if reused_prior
                else "-- Refine & Clarify: re-retrieved using original issue text.\n"
            ) + live_sql
        t_retrieve = _now_ms()
        trace.append(
            {
                "step": "retrieval",
                "duration_ms": round(t_retrieve - t0, 1),
                "details": f"backend={backend}, {retrieval_detail}",
            }
        )

        llm_ok = self.llm.is_available()

        # Classification (keep prior classification signal from base issue in refine)
        t0 = _now_ms()
        classify_text = base_issue if refine_mode else clean_query
        if llm_ok:
            try:
                raw = self.llm.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": CLASSIFICATION_PROMPT.format(query=classify_text),
                        },
                    ],
                    temperature=0.1,
                )
                category, priority, reasoning = _parse_classification(raw)
                class_detail = "ollama"
            except Exception as exc:
                category, priority, reasoning = _heuristic_classification(classify_text)
                class_detail = f"heuristic after LLM error: {exc}"
        else:
            category, priority, reasoning = _heuristic_classification(classify_text)
            class_detail = "heuristic (ollama offline)"
        trace.append(
            {
                "step": "classification",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"{category}/{priority} via {class_detail}",
            }
        )

        # RAG synthesis / refine
        t0 = _now_ms()
        evidence = format_evidence(similar)
        if llm_ok:
            try:
                messages: list[dict[str, str]] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                ]
                if chat_history:
                    messages.extend(chat_history[-8:])
                if refine_mode:
                    user_content = REFINE_PROMPT.format(
                        original_query=base_issue,
                        follow_up=clean_query,
                        evidence=evidence,
                    )
                else:
                    user_content = RAG_SYNTHESIS_PROMPT.format(
                        query=clean_query,
                        language_name=lang_name,
                        language_code=lang_code,
                        category=category,
                        priority=priority,
                        evidence=evidence,
                    )
                messages.append({"role": "user", "content": user_content})
                synthesized = self.llm.chat(messages, temperature=0.3)
                synth_detail = (
                    "ollama refine+clarify" if refine_mode else "ollama grounded RAG"
                )
            except Exception as exc:
                synthesized = _extractive_resolution(clean_query, similar)
                synth_detail = f"extractive after LLM error: {exc}"
        else:
            if refine_mode:
                synthesized = (
                    f"### Refined answer (LLM offline)\n"
                    f"_Follow-up:_ {clean_query}\n\n"
                    + _extractive_resolution(base_issue, similar)
                )
                synth_detail = "extractive refine (ollama offline)"
            else:
                synthesized = _extractive_resolution(clean_query, similar)
                synth_detail = "extractive (ollama offline)"
        trace.append(
            {
                "step": "rag_synthesis",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": synth_detail,
            }
        )

        # Localization
        localized: str | None = None
        t0 = _now_ms()
        if lang_code != "en" and llm_ok:
            try:
                localized = self.llm.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": TRANSLATION_PROMPT.format(
                                language_name=lang_name,
                                language_code=lang_code,
                                resolution=synthesized,
                            ),
                        },
                    ],
                    temperature=0.2,
                )
                loc_detail = f"translated to {lang_name}"
            except Exception as exc:
                loc_detail = f"translation skipped: {exc}"
        else:
            loc_detail = "skipped (English or LLM offline)"
        trace.append(
            {
                "step": "localization",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": loc_detail,
            }
        )

        # Confidence & HITL escalation (Feature C)
        top_score = 0.0
        if similar:
            top_score = float(similar[0].get("similarity_score") or 0.0)
        confidence = max(0.0, min(1.0, top_score))
        decision = evaluate_escalation(
            top_similarity=confidence,
            priority=priority,
            category=category,
        )
        escalation_required = decision.ESCALATION_REQUIRED
        escalation_hint = decision.summary if escalation_required else None
        trace.append(
            {
                "step": "hitl_escalation",
                "duration_ms": 0.0,
                "details": decision.summary,
            }
        )

        return AgentResult(
            query=clean_query,
            detected_language_code=lang_code,
            detected_language_name=lang_name,
            classified_category=category,
            classified_priority=priority,
            similar_tickets=similar,
            synthesized_resolution=synthesized,
            localized_resolution=localized,
            search_backend=backend,
            confidence=confidence,
            escalation_required=escalation_required,
            escalation_hint=escalation_hint,
            live_sql=live_sql,
            trace_steps=trace,
            llm_available=llm_ok,
            classification_reasoning=reasoning,
            escalation=decision.to_dict(),
            refine_mode=refine_mode,
            reused_prior_tickets=reused_prior,
            original_query=base_issue if refine_mode else clean_query,
            pii_redacted=bool(pii_totals),
            pii_counts=pii_totals,
        )
