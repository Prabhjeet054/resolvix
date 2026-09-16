"""
Lightweight FastAPI webhooks for Slack / Zendesk / Jira Service Management.

Run:
  uvicorn api.main:app --host 0.0.0.0 --port 8080

Primary contract:
  POST /api/v1/resolve
  body: { "query": "...", "customer_id": "..." }
  returns resolution + similar_ticket_ids (+ category/priority/escalation)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.resolver import TicketResolverAgent

app = FastAPI(
    title="Resolvix Resolve API",
    version="0.1.0",
    description=(
        "Multilingual agentic RAG webhook for Slack bots, Zendesk, and "
        "Jira Service Management integrations."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Customer issue text")
    customer_id: str | None = Field(
        default=None, description="External CRM / Zendesk / Jira customer id"
    )
    top_n: int = Field(default=3, ge=1, le=10)


class ResolveResponse(BaseModel):
    resolution: str
    localized_resolution: str | None = None
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
    return {"status": "ok", "service": "resolvix-api"}


@app.post("/api/v1/resolve", response_model=ResolveResponse)
def resolve_ticket(payload: ResolveRequest) -> ResolveResponse:
    """Resolve a support query for bot / helpdesk integrations."""
    try:
        agent = TicketResolverAgent()
        result = agent.resolve(payload.query, top_n=payload.top_n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Never leak stack traces to integrators; keep a clear error body.
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
    """Integrator-facing contract for Slack / Zendesk / Jira adapters."""
    return {
        "endpoint": "POST /api/v1/resolve",
        "integrations": ["slack", "zendesk", "jira_service_management"],
        "body": {
            "query": "string (required)",
            "customer_id": "string (optional)",
            "top_n": "int (optional, default 3)",
        },
        "returns": [
            "resolution",
            "similar_ticket_ids",
            "category",
            "priority",
            "confidence",
            "escalation_required",
            "escalation",
            "search_backend",
            "customer_id",
        ],
    }
