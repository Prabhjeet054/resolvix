"""Resolvix local LLM agent package (Ollama-backed)."""

from agent.escalation import EscalationDecision, evaluate_escalation, recommend_routing
from agent.resolver import AgentResult, TicketResolverAgent

__all__ = [
    "AgentResult",
    "EscalationDecision",
    "TicketResolverAgent",
    "evaluate_escalation",
    "recommend_routing",
]
