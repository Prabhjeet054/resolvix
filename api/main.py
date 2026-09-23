"""
Resolvix FastAPI — webhooks + shared web/Electron UI backend.

Run:
  uvicorn api.main:app --host 127.0.0.1 --port 8080

Primary contracts:
  POST /api/v1/resolve
  GET  /api/v1/status
  POST /api/v1/tickets
  GET  /api/v1/incidents/last-24h
  Static frontend/ mounted at /
"""

from __future__ import annotations

import os

# Prefer cached embedding weights so desktop/sandbox launches do not depend on Hub.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.llm_client import OllamaClient
from agent.resolver import TicketResolverAgent
from db.connection import is_db_available
from embeddings.generate import generate_embedding
from embeddings.similarity_search import file_new_ticket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="Resolvix Resolve API",
    version="0.2.0",
    description=(
        "Multilingual agentic RAG API for Slack/Zendesk/Jira integrations "
        "and the shared web / Electron desktop UI."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Customer issue text")
    customer_id: str | None = Field(
        default=None, description="External CRM / Zendesk / Jira customer id"
    )
    top_n: int = Field(default=3, ge=1, le=10)
    model: str | None = Field(default=None, description="Ollama model override")
    category_filter: str | None = None
    priority_filter: str | None = None
    language_override: str | None = None
    chat_history: list[dict[str, str]] | None = None
    prior_tickets: list[dict[str, Any]] | None = None
    original_query: str | None = None


class ResolveResponse(BaseModel):
    resolution: str
    localized_resolution: str | None = None
    category: str
    priority: str
    language_code: str
    detected_language_name: str | None = None
    search_backend: str
    similar_ticket_ids: list[int]
    similar_tickets: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float
    escalation_required: bool
    escalation: dict[str, Any] | None = None
    escalation_hint: str | None = None
    classification_reasoning: str | None = None
    live_sql: str | None = None
    trace_steps: list[dict[str, Any]] = Field(default_factory=list)
    llm_available: bool = False
    customer_id: str | None = None
    query: str | None = None


class FileTicketRequest(BaseModel):
    description: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    priority: str = Field(..., min_length=1)
    language_code: str = "en"
    resolution: str | None = None


class FileTicketResponse(BaseModel):
    ticket_id: int | None
    filed: bool
    message: str


def _chat_models(models: list[str]) -> list[str]:
    """Prefer completion models; hide pure embedding tags from the UI dropdown."""
    chat: list[str] = []
    for name in models:
        lower = name.lower()
        if "embed" in lower or "nomic-embed" in lower:
            continue
        chat.append(name)
    return chat or list(models)


def _json_safe_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Normalize ticket dicts for JSON (coerce numpy scalars, etc.)."""
    out: dict[str, Any] = {}
    for key, value in ticket.items():
        if hasattr(value, "item"):
            try:
                out[key] = value.item()
                continue
            except Exception:
                pass
        if isinstance(value, (list, tuple)) and key == "embedding":
            continue
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# Health & status
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "resolvix-api"}


@app.get("/api/v1/status")
def system_status(model: str | None = None) -> dict[str, Any]:
    """Oracle + Ollama diagnostics for the shared UI sidebar."""
    active_model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    oracle_ok = False
    try:
        oracle_ok = bool(is_db_available())
    except Exception:
        oracle_ok = False

    client = OllamaClient(model=active_model)
    ollama_ok = False
    models: list[str] = []
    try:
        ollama_ok = client.is_available()
        if ollama_ok:
            models = _chat_models(client.list_models())
    except Exception:
        ollama_ok = False
        models = []

    if active_model and active_model not in models:
        models = [active_model, *models]

    return {
        "oracle_ok": oracle_ok,
        "ollama_ok": ollama_ok,
        "models": models,
        "model": active_model,
        "oracle_label": (
            "Online (AI Vector Search)" if oracle_ok else "Offline (In-Memory Fallback)"
        ),
        "ollama_label": (
            f"Connected ({active_model})" if ollama_ok else "Offline (extractive fallback)"
        ),
    }


# ---------------------------------------------------------------------------
# Resolve
# ---------------------------------------------------------------------------


@app.post("/api/v1/resolve", response_model=ResolveResponse)
def resolve_ticket(payload: ResolveRequest) -> ResolveResponse:
    """Resolve a support query for UI, bots, and helpdesk integrations."""
    try:
        agent = TicketResolverAgent(model=payload.model)
        result = agent.resolve(
            payload.query,
            top_n=payload.top_n,
            category_filter=payload.category_filter,
            priority_filter=payload.priority_filter,
            language_override=payload.language_override,
            chat_history=payload.chat_history,
            prior_tickets=payload.prior_tickets,
            original_query=payload.original_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"resolve failed: {exc}") from exc

    similar = [_json_safe_ticket(t) for t in (result.similar_tickets or [])]
    return ResolveResponse(
        resolution=result.synthesized_resolution,
        localized_resolution=result.localized_resolution,
        category=result.classified_category,
        priority=result.classified_priority,
        language_code=result.detected_language_code,
        detected_language_name=result.detected_language_name,
        search_backend=result.search_backend,
        similar_ticket_ids=[int(t.get("ticket_id")) for t in similar if t.get("ticket_id") is not None],
        similar_tickets=similar,
        confidence=float(result.confidence),
        escalation_required=bool(result.escalation_required),
        escalation=result.escalation,
        escalation_hint=result.escalation_hint,
        classification_reasoning=result.classification_reasoning or None,
        live_sql=result.live_sql,
        trace_steps=list(result.trace_steps or []),
        llm_available=bool(result.llm_available),
        customer_id=payload.customer_id,
        query=result.query,
    )


@app.get("/api/v1/resolve/schema")
def resolve_schema() -> dict[str, Any]:
    """Integrator-facing contract for Slack / Zendesk / Jira adapters."""
    return {
        "endpoint": "POST /api/v1/resolve",
        "integrations": ["slack", "zendesk", "jira_service_management", "electron", "web"],
        "body": {
            "query": "string (required)",
            "customer_id": "string (optional)",
            "top_n": "int (optional, default 3)",
            "model": "string (optional)",
            "category_filter": "string (optional)",
            "priority_filter": "string (optional)",
            "language_override": "string (optional)",
            "chat_history": "list[{role, content}] (optional, refine mode)",
            "prior_tickets": "list[ticket] (optional, refine mode)",
            "original_query": "string (optional, refine mode)",
        },
        "returns": [
            "resolution",
            "similar_ticket_ids",
            "similar_tickets",
            "category",
            "priority",
            "confidence",
            "escalation_required",
            "escalation",
            "search_backend",
            "trace_steps",
            "live_sql",
            "customer_id",
        ],
    }


# ---------------------------------------------------------------------------
# File ticket + incidents
# ---------------------------------------------------------------------------


@app.post("/api/v1/tickets", response_model=FileTicketResponse)
def create_ticket(payload: FileTicketRequest) -> FileTicketResponse:
    """Insert an OPEN ticket into Oracle 23ai (no-op with clear message if offline)."""
    try:
        if not is_db_available():
            return FileTicketResponse(
                ticket_id=None,
                filed=False,
                message="Oracle is offline — cannot file ticket right now.",
            )
        embedding = generate_embedding(payload.description)
        ticket_id = file_new_ticket(
            description=payload.description,
            embedding=embedding,
            category_name=payload.category,
            priority=payload.priority,
            language_code=payload.language_code,
            resolution=payload.resolution,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"file ticket failed: {exc}") from exc

    if ticket_id is None:
        return FileTicketResponse(
            ticket_id=None,
            filed=False,
            message="Insert failed — check DB credentials and FK seed data.",
        )
    return FileTicketResponse(
        ticket_id=int(ticket_id),
        filed=True,
        message=f"Filed as ticket #{ticket_id} (status=OPEN).",
    )


@app.get("/api/v1/incidents/last-24h")
def incidents_last_24h(
    method: Literal["dbscan", "kmeans", "greedy"] = Query(default="dbscan"),
) -> dict[str, Any]:
    """Semantic outage / duplicate scan over recent tickets."""
    try:
        from analytics.clustering import analyze_last_24h

        return analyze_last_24h(method=method)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"incident scan failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Shared frontend (web + Electron)
# ---------------------------------------------------------------------------


@app.get("/")
def serve_index() -> FileResponse:
    index = FRONTEND_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(index)


if (FRONTEND_DIR / "css").is_dir():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
if (FRONTEND_DIR / "js").is_dir():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
