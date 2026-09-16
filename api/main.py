"""
Lightweight FastAPI webhook scaffold for Slack / Zendesk / Jira integrations.

Run: uvicorn api.main:app --reload --port 8080
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.resolver import TicketResolverAgent

app = FastAPI(
    title="Resolvix Resolve API",
    version="0.1.0",
    description="POST /api/v1/resolve — multilingual agentic RAG resolution webhook",
)


class ResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Customer issue text")
    customer_id: str | None = Field(default=None, description="External CRM customer id")
    top_n: int = Field(default=3, ge=1, le=10)


class ResolveResponse(BaseModel):
    resolution: str
    localized_resolution: str | None
    category: str
    priority: str
    language_code: str
    search_backend: str
    similar_ticket_ids: list[int]
    confidence: float
    escalation_required: bool
    escalation: dict[str, Any] | None = None
    customer_id: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/resolve", response_model=ResolveResponse)
def resolve_ticket(payload: ResolveRequest) -> ResolveResponse:
    """Resolve a support query and return structured agent output."""
    try:
        agent = TicketResolverAgent()
        result = agent.resolve(payload.query, top_n=payload.top_n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"resolve failed: {exc}") from exc

    return ResolveResponse(
        resolution=result.synthesized_resolution,
        localized_resolution=result.localized_resolution,
        category=result.classified_category,
        priority=result.classified_priority,
        language_code=result.detected_language_code,
        search_backend=result.search_backend,
        similar_ticket_ids=[int(t["ticket_id"]) for t in result.similar_tickets],
        confidence=result.confidence,
        escalation_required=result.escalation_required,
        escalation=result.escalation,
        customer_id=payload.customer_id,
    )


@app.get("/api/v1/resolve/schema")
def resolve_schema() -> dict[str, Any]:
    """Documentation helper for integrators."""
    return {
        "endpoint": "POST /api/v1/resolve",
        "body": {"query": "...", "customer_id": "optional", "top_n": 3},
        "returns": ["resolution", "similar_ticket_ids", "category", "priority"],
    }
