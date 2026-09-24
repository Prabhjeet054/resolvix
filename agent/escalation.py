"""Human-in-the-loop smart escalation (roadmap Feature C).

Flags ``ESCALATION_REQUIRED = TRUE`` when the top similarity match is below
65% **or** classified priority is CRITICAL, and recommends the tier-2/3
department plus an on-call specialist for the category.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SIMILARITY_ESCALATION_THRESHOLD = 0.65

# Department + primary on-call specialist by agent category classification
ESCALATION_ROUTING: dict[str, dict[str, str]] = {
    "TECH": {
        "tier": "Tier-2",
        "department": "Application Reliability / Platform Engineering",
        "on_call_specialist": "Priya Nair (SRE On-Call)",
        "queue": "platform-sre-p1",
    },
    "BILLING": {
        "tier": "Tier-2",
        "department": "Revenue Operations / Billing Ops",
        "on_call_specialist": "Marcus Chen (Billing Ops Lead)",
        "queue": "billing-ops-escalations",
    },
    "ACCOUNT": {
        "tier": "Tier-2",
        "department": "Identity & Access / Account Ops",
        "on_call_specialist": "Aisha Rahman (IAM Specialist)",
        "queue": "iam-account-ops",
    },
    "SECURITY": {
        "tier": "Tier-3",
        "department": "Security Operations / IAM On-Call",
        "on_call_specialist": "Jordan Blake (SecOps Pager)",
        "queue": "secops-critical",
    },
    "GENERAL": {
        "tier": "Tier-1",
        "department": "Support Lead / Floor Supervisor",
        "on_call_specialist": "Sam Ortiz (Support Floor Lead)",
        "queue": "tier1-supervisor",
    },
}


@dataclass
class EscalationDecision:
    """Structured HITL escalation recommendation."""

    ESCALATION_REQUIRED: bool
    reasons: list[str]
    top_similarity: float
    priority: str
    category: str
    tier: str | None
    department: str | None
    on_call_specialist: str | None
    queue: str | None
    summary: str
    threshold: float = SIMILARITY_ESCALATION_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recommend_routing(category: str) -> dict[str, str]:
    """Return tier / department / specialist routing for a category."""
    key = (category or "GENERAL").upper()
    return dict(ESCALATION_ROUTING.get(key, ESCALATION_ROUTING["GENERAL"]))


def evaluate_escalation(
    top_similarity: float,
    priority: str,
    category: str,
    threshold: float = SIMILARITY_ESCALATION_THRESHOLD,
) -> EscalationDecision:
    """Decide whether human escalation is required and whom to page.

    Rules:
      - ESCALATION_REQUIRED = TRUE if top similarity < threshold (default 65%)
      - ESCALATION_REQUIRED = TRUE if priority == CRITICAL
    """
    priority_u = (priority or "MEDIUM").upper()
    category_u = (category or "GENERAL").upper()
    sim = max(0.0, min(1.0, float(top_similarity or 0.0)))

    reasons: list[str] = []
    if sim < threshold:
        reasons.append(
            f"top similarity {sim * 100:.1f}% < {threshold * 100:.0f}% confidence floor"
        )
    if priority_u == "CRITICAL":
        reasons.append("classified priority is CRITICAL")

    required = len(reasons) > 0
    routing = recommend_routing(category_u) if required else {
        "tier": None,
        "department": None,
        "on_call_specialist": None,
        "queue": None,
    }

    if required:
        summary = (
            f"ESCALATION_REQUIRED = TRUE → {routing['tier']} "
            f"{routing['department']} · On-call: {routing['on_call_specialist']} "
            f"(queue: {routing['queue']}) · reasons: {'; '.join(reasons)}"
        )
    else:
        summary = (
            f"ESCALATION_REQUIRED = FALSE "
            f"(top similarity {sim * 100:.1f}% ≥ {threshold * 100:.0f}%, "
            f"priority={priority_u})"
        )

    return EscalationDecision(
        ESCALATION_REQUIRED=required,
        reasons=reasons,
        top_similarity=sim,
        priority=priority_u,
        category=category_u,
        tier=routing.get("tier"),
        department=routing.get("department"),
        on_call_specialist=routing.get("on_call_specialist"),
        queue=routing.get("queue"),
        summary=summary,
        threshold=float(threshold),
    )
