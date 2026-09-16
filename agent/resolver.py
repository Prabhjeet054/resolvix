"""TicketResolverAgent — orchestrates embed → retrieve → classify → RAG → localize."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.llm_client import OllamaClient
from agent.prompts import (
    CLASSIFICATION_PROMPT,
    RAG_SYNTHESIS_PROMPT,
    SYSTEM_PROMPT,
    TRANSLATION_PROMPT,
    format_evidence,
)
from embeddings.generate import generate_embedding
from embeddings.languages import detect_language, get_language_name
from embeddings.similarity_search import build_oracle_sql, find_similar_tickets


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
    mapping = {
        "TECH": "Tier-2 Application Reliability / Platform Engineering",
        "BILLING": "Tier-2 Revenue Operations / Billing Ops",
        "ACCOUNT": "Tier-2 Identity & Access / Account Ops",
        "SECURITY": "Tier-3 Security Operations / IAM On-Call",
        "GENERAL": "Tier-1 Support Lead",
    }
    return mapping.get(category, "Tier-1 Support Lead")


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
    ) -> AgentResult:
        """Run the full pipeline and return a structured AgentResult."""
        trace: list[dict] = []
        clean_query = (query or "").strip()
        if not clean_query:
            raise ValueError("query must be a non-empty string")

        # Language detection
        t0 = _now_ms()
        lang_code = (language_override or detect_language(clean_query)).lower()
        lang_name = get_language_name(lang_code)
        trace.append(
            {
                "step": "language_detection",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"{lang_name} ({lang_code})",
            }
        )

        # Embedding
        t0 = _now_ms()
        embedding = generate_embedding(clean_query)
        trace.append(
            {
                "step": "embedding",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"dim={embedding.shape[0]} model=paraphrase-multilingual-MiniLM-L12-v2",
            }
        )

        # Dual-mode retrieval
        t0 = _now_ms()
        similar = find_similar_tickets(
            embedding,
            top_n=top_n,
            category_filter=category_filter,
            priority_filter=priority_filter,
        )
        backend = similar[0]["source_mode"] if similar else (
            "ORACLE_23AI" if False else "IN_MEMORY"
        )
        # Prefer explicit tag even when empty: probe via first successful path
        if similar:
            backend = str(similar[0].get("source_mode", "IN_MEMORY"))
        else:
            from db.connection import is_db_available

            backend = "ORACLE_23AI" if is_db_available() else "IN_MEMORY"

        live_sql = build_oracle_sql(category_filter, priority_filter)
        trace.append(
            {
                "step": "retrieval",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"backend={backend}, matches={len(similar)}",
            }
        )

        llm_ok = self.llm.is_available()

        # Classification
        t0 = _now_ms()
        if llm_ok:
            try:
                raw = self.llm.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": CLASSIFICATION_PROMPT.format(query=clean_query),
                        },
                    ],
                    temperature=0.1,
                )
                category, priority, reasoning = _parse_classification(raw)
                class_detail = "ollama"
            except Exception as exc:
                category, priority, reasoning = _heuristic_classification(clean_query)
                class_detail = f"heuristic after LLM error: {exc}"
        else:
            category, priority, reasoning = _heuristic_classification(clean_query)
            class_detail = "heuristic (ollama offline)"
        trace.append(
            {
                "step": "classification",
                "duration_ms": round(_now_ms() - t0, 1),
                "details": f"{category}/{priority} via {class_detail}",
            }
        )

        # RAG synthesis
        t0 = _now_ms()
        evidence = format_evidence(similar)
        if llm_ok:
            try:
                messages: list[dict[str, str]] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                ]
                if chat_history:
                    messages.extend(chat_history[-6:])
                messages.append(
                    {
                        "role": "user",
                        "content": RAG_SYNTHESIS_PROMPT.format(
                            query=clean_query,
                            language_name=lang_name,
                            language_code=lang_code,
                            category=category,
                            priority=priority,
                            evidence=evidence,
                        ),
                    }
                )
                synthesized = self.llm.chat(messages, temperature=0.3)
                synth_detail = "ollama grounded RAG"
            except Exception as exc:
                synthesized = _extractive_resolution(clean_query, similar)
                synth_detail = f"extractive after LLM error: {exc}"
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

        # Confidence & escalation (HITL)
        top_score = 0.0
        if similar:
            top_score = float(similar[0].get("similarity_score") or 0.0)
        confidence = max(0.0, min(1.0, top_score))
        escalation_required = confidence < 0.65 or priority == "CRITICAL"
        escalation_hint = None
        if escalation_required:
            escalation_hint = (
                f"ESCALATION_REQUIRED → route to {_department_for_category(category)} "
                f"(top similarity {confidence * 100:.1f}%, priority={priority})"
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
        )
