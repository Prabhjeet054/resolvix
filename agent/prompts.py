"""Strict, grounded prompts for classification, RAG synthesis, and translation."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are Resolvix AI, a tier-3 enterprise IT support resolution agent. "
    "You provide fact-grounded, clear troubleshooting steps based strictly on "
    "historical resolved tickets. If context lacks the answer, acknowledge it "
    "and suggest escalation. Never invent ticket IDs, refunds, or system state "
    "that is not present in the provided evidence."
)

CLASSIFICATION_PROMPT = """Classify the support issue below.

Return ONLY valid JSON (no markdown fences) with this schema:
{{"category":"TECH|BILLING|ACCOUNT|SECURITY|GENERAL","priority":"LOW|MEDIUM|HIGH|CRITICAL","reasoning":"brief explanation"}}

Category guidance:
- TECH: crashes, performance, bugs, integrations
- BILLING: charges, invoices, subscriptions, refunds
- ACCOUNT: profile, permissions, settings
- SECURITY: login, password, MFA, unauthorized access
- GENERAL: how-to / informational

Issue:
{query}
"""

RAG_SYNTHESIS_PROMPT = """Synthesize a clear, step-by-step troubleshooting resolution for the current customer issue.

Rules:
1. Ground every step in the historical tickets / resolutions below.
2. Cite ticket IDs inline like [Ticket 103] when you reuse a resolution idea.
3. If evidence is weak, say so and recommend escalation.
4. Prefer a short checklist (3–7 steps). Use Markdown.
5. Do not invent facts not present in the evidence.

Current issue:
{query}

Detected language: {language_name} ({language_code})
Predicted category: {category}
Predicted priority: {priority}

Historical evidence (top similar resolved tickets):
{evidence}
"""

TRANSLATION_PROMPT = """Translate the technical resolution below into {language_name} ({language_code}).

Keep code, shell commands, URLs, product names, error codes, and ticket IDs unchanged.
Preserve Markdown structure (headings, numbered lists).

Resolution to translate:
{resolution}
"""

REFINE_PROMPT = """You are continuing an existing support conversation (Refine & Clarify).

The customer follow-up may ask to simplify, adapt to another OS/environment, or clarify steps.
Answer the follow-up using:
1) The conversation so far (already in chat messages)
2) The historical ticket evidence below
3) The original issue context

Rules:
- Stay grounded in the evidence; do not invent new ticket facts.
- If adapting steps (e.g. macOS vs Windows), clearly note assumptions.
- Keep a short Markdown checklist.
- Cite ticket IDs when reusing historical resolutions.

Original issue:
{original_query}

Follow-up:
{follow_up}

Historical evidence (retrieved tickets):
{evidence}
"""


def format_evidence(similar_tickets: list[dict]) -> str:
    """Render top matched tickets into a compact evidence block for the LLM."""
    if not similar_tickets:
        return "(no similar resolved tickets found)"

    blocks: list[str] = []
    for i, ticket in enumerate(similar_tickets, start=1):
        pct = ticket.get("similarity_pct")
        if pct is None:
            score = float(ticket.get("similarity_score") or 0.0)
            pct = round(score * 100.0, 1)
        blocks.append(
            "\n".join(
                [
                    f"[{i}] Ticket {ticket.get('ticket_id')} "
                    f"| lang={ticket.get('language_code')} "
                    f"| category={ticket.get('category_name')} "
                    f"| priority={ticket.get('priority')} "
                    f"| similarity={pct}%",
                    f"Description: {ticket.get('description')}",
                    f"Resolution: {ticket.get('resolution') or '(none)'}",
                ]
            )
        )
    return "\n\n".join(blocks)
