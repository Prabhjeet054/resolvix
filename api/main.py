"""
Resolvix FastAPI — webhooks + shared web/Electron UI backend.

Run:
  uvicorn api.main:app --host 127.0.0.1 --port 8080

Primary contracts:
  POST /api/v1/resolve
  GET  /api/v1/status
  POST /api/v1/tickets
  POST /api/v1/feedback
  GET  /api/v1/feedback/review
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
    refine_mode: bool = False
    reused_prior_tickets: bool = False
    original_query: str | None = None
    pii_redacted: bool = False
    pii_counts: dict[str, int] = Field(default_factory=dict)
    groundedness_score: float | None = None
    groundedness: dict[str, Any] | None = None


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


class FeedbackRequest(BaseModel):
    vote: Literal["up", "down"]
    query: str = Field(..., min_length=1)
    resolution: str | None = None
    similar_ticket_ids: list[int] = Field(default_factory=list)
    category: str | None = None
    priority: str | None = None
    search_backend: str | None = None
    source: str = "web"


class FeedbackResponse(BaseModel):
    recorded: bool
    event_id: str
    vote: str
    ticket_ids: list[int] = Field(default_factory=list)
    flagged: dict[str, Any] | None = None
    suppressed_ticket_ids: list[int] = Field(default_factory=list)
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
        refine_mode=bool(result.refine_mode),
        reused_prior_tickets=bool(result.reused_prior_tickets),
        original_query=result.original_query,
        pii_redacted=bool(result.pii_redacted),
        pii_counts=dict(result.pii_counts or {}),
        groundedness_score=(
            float(result.groundedness_score)
            if result.groundedness_score is not None
            else None
        ),
        groundedness=result.groundedness,
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
            "refine_mode",
            "reused_prior_tickets",
            "original_query",
            "pii_redacted",
            "pii_counts",
            "groundedness_score",
            "groundedness",
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
        from privacy.redact import redact_text

        safe_description = redact_text(payload.description)
        safe_resolution = (
            redact_text(payload.resolution)
            if payload.resolution is not None
            else None
        )
        embedding = generate_embedding(safe_description)
        ticket_id = file_new_ticket(
            description=safe_description,
            embedding=embedding,
            category_name=payload.category,
            priority=payload.priority,
            language_code=payload.language_code,
            resolution=safe_resolution,
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


# ---------------------------------------------------------------------------
# Feedback loop (thumbs → better retrieval)
# ---------------------------------------------------------------------------


@app.post("/api/v1/feedback", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Persist thumbs up/down; downvotes suppress weak matches and flag review."""
    try:
        from feedback.store import record_feedback

        result = record_feedback(
            payload.vote,
            query=payload.query,
            resolution=payload.resolution,
            similar_ticket_ids=payload.similar_ticket_ids,
            category=payload.category,
            priority=payload.priority,
            search_backend=payload.search_backend,
            source=payload.source or "web",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"feedback failed: {exc}") from exc

    return FeedbackResponse(
        recorded=bool(result.get("recorded")),
        event_id=str(result.get("event_id")),
        vote=str(result.get("vote")),
        ticket_ids=list(result.get("ticket_ids") or []),
        flagged=result.get("flagged"),
        suppressed_ticket_ids=sorted(int(x) for x in (result.get("suppressed_ticket_ids") or [])),
        message=str(result.get("message") or "Feedback recorded."),
    )


@app.get("/api/v1/feedback/review")
def feedback_review(
    status: str | None = Query(default="open"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List resolutions flagged by thumbs-down for human review."""
    from feedback.store import feedback_stats, list_flagged_resolutions

    return {
        "stats": feedback_stats(),
        "flagged": list_flagged_resolutions(status=status, limit=limit),
    }


@app.get("/api/v1/incidents/last-24h")
def incidents_last_24h(
    method: Literal["dbscan", "kmeans", "greedy"] = Query(default="dbscan"),
    hours: float = Query(default=24.0, ge=1.0, le=168.0),
    min_cluster_size: int = Query(default=5, ge=2, le=50),
) -> dict[str, Any]:
    """Semantic outage / duplicate scan over recent tickets (Incident Ops)."""
    try:
        from analytics.clustering import analyze_last_24h

        report = analyze_last_24h(
            hours=hours,
            min_cluster_size=min_cluster_size,
            method=method,
        )
        # Stable deep-link targets for UI ticket chips
        for alert in report.get("alerts") or []:
            alert["ticket_links"] = [
                {"ticket_id": tid, "href": f"#ticket-{tid}"}
                for tid in (alert.get("ticket_ids") or [])
            ]
        for alert in report.get("hourly_burst_alerts") or []:
            alert["ticket_links"] = [
                {"ticket_id": tid, "href": f"#ticket-{tid}"}
                for tid in (alert.get("ticket_ids") or [])
            ]
        report["hours"] = hours
        return report
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"incident scan failed: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Shared frontend (web + Electron)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def no_cache_frontend_assets(request, call_next):
    """Keep Electron/browser in sync with frontend/ edits (confidence UI, themes)."""
    response = await call_next(request)
    path = request.url.path or ""
    if path == "/" or path.startswith("/css/") or path.startswith("/js/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def serve_index() -> FileResponse:
    index = FRONTEND_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(
        index,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


if (FRONTEND_DIR / "css").is_dir():
    app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
if (FRONTEND_DIR / "js").is_dir():
    app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
