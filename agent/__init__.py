"""Resolvix local LLM agent package (Ollama-backed)."""

from agent.escalation import EscalationDecision, evaluate_escalation, recommend_routing
from agent.groundedness import GroundednessCheck, check_groundedness
from agent.resolver import AgentResult, TicketResolverAgent

__all__ = [
    "AgentResult",
    "EscalationDecision",
    "GroundednessCheck",
    "TicketResolverAgent",
    "check_groundedness",
    "evaluate_escalation",
    "recommend_routing",
]
