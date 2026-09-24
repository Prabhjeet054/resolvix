"""Human feedback loop for retrieval quality (thumbs up/down).

Persists votes under ``data/feedback_store.json``. Downvotes:
  - suppress *weak* similar-ticket matches on later retrievals
  - flag cited resolutions for human review
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE_PATH = PROJECT_ROOT / "data" / "feedback_store.json"

# Weak match floor — downvoted tickets at or below this cosine are dropped.
WEAK_SIMILARITY_THRESHOLD = 0.85
# Need at least this many net downvotes (down - up) before suppression kicks in.
MIN_NET_DOWNVOTES = 1

_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "events": [],
        "ticket_votes": {},
        "flagged_resolutions": [],
    }


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", 1)
    data.setdefault("events", [])
    data.setdefault("ticket_votes", {})
    data.setdefault("flagged_resolutions", [])
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _resolution_fingerprint(text: str) -> str:
    normalized = " ".join((text or "").strip().split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def ticket_vote_totals(store: dict[str, Any], ticket_id: int) -> dict[str, int]:
    raw = store.get("ticket_votes", {}).get(str(int(ticket_id))) or {}
    return {
        "up": int(raw.get("up") or 0),
        "down": int(raw.get("down") or 0),
    }


def net_downvotes(store: dict[str, Any], ticket_id: int) -> int:
    totals = ticket_vote_totals(store, ticket_id)
    return max(0, totals["down"] - totals["up"])


def should_suppress_ticket(
    store: dict[str, Any],
    ticket_id: int,
    similarity_score: float,
    *,
    weak_threshold: float = WEAK_SIMILARITY_THRESHOLD,
    min_net_down: int = MIN_NET_DOWNVOTES,
) -> bool:
    """Suppress only weak matches that have accumulated net downvotes."""
    if float(similarity_score or 0.0) > weak_threshold:
        return False
    return net_downvotes(store, int(ticket_id)) >= min_net_down


def apply_feedback_to_matches(
    matches: list[dict[str, Any]],
    *,
    store_path: Path | None = None,
    weak_threshold: float = WEAK_SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Drop weak downvoted matches; annotate survivors with vote metadata."""
    path = store_path or DEFAULT_STORE_PATH
    with _lock:
        store = _load(path)

    kept: list[dict[str, Any]] = []
    for match in matches:
        tid = match.get("ticket_id")
        if tid is None:
            kept.append(match)
            continue
        tid_i = int(tid)
        score = float(match.get("similarity_score") or 0.0)
        totals = ticket_vote_totals(store, tid_i)
        annotated = {
            **match,
            "feedback_votes": totals,
            "feedback_net_down": net_downvotes(store, tid_i),
        }
        if should_suppress_ticket(
            store, tid_i, score, weak_threshold=weak_threshold
        ):
            annotated["feedback_suppressed"] = True
            continue
        annotated["feedback_suppressed"] = False
        if totals["down"] > totals["up"]:
            annotated["feedback_flagged"] = True
        kept.append(annotated)
    return kept


def record_feedback(
    vote: Literal["up", "down"],
    *,
    query: str,
    resolution: str | None = None,
    similar_ticket_ids: list[int] | None = None,
    category: str | None = None,
    priority: str | None = None,
    search_backend: str | None = None,
    source: str = "ui",
    store_path: Path | None = None,
) -> dict[str, Any]:
    """Persist a thumbs vote and update ticket aggregates / review queue."""
    if vote not in {"up", "down"}:
        raise ValueError("vote must be 'up' or 'down'")

    path = store_path or DEFAULT_STORE_PATH
    ticket_ids = [int(t) for t in (similar_ticket_ids or []) if t is not None]
    event_id = str(uuid.uuid4())
    flagged: dict[str, Any] | None = None

    with _lock:
        store = _load(path)
        event = {
            "id": event_id,
            "vote": vote,
            "query": query,
            "resolution": resolution,
            "similar_ticket_ids": ticket_ids,
            "category": category,
            "priority": priority,
            "search_backend": search_backend,
            "source": source,
            "created_at": _utc_now(),
        }
        store["events"].append(event)

        votes: dict[str, Any] = store["ticket_votes"]
        for tid in ticket_ids:
            key = str(tid)
            bucket = votes.setdefault(key, {"up": 0, "down": 0})
            bucket[vote] = int(bucket.get(vote) or 0) + 1

        if vote == "down":
            flagged = {
                "id": str(uuid.uuid4()),
                "event_id": event_id,
                "status": "open",
                "reason": "thumbs_down",
                "query": query,
                "resolution": resolution,
                "resolution_fingerprint": _resolution_fingerprint(resolution or ""),
                "ticket_ids": ticket_ids,
                "category": category,
                "priority": priority,
                "created_at": _utc_now(),
            }
            store["flagged_resolutions"].append(flagged)

        _save(path, store)

    return {
        "recorded": True,
        "event_id": event_id,
        "vote": vote,
        "ticket_ids": ticket_ids,
        "flagged": flagged,
        "suppressed_ticket_ids": list(get_suppressible_ticket_ids(store_path=path)),
        "message": (
            "Thanks — feedback recorded. Downvoted weak matches will be suppressed "
            "on future retrievals; resolution flagged for review."
            if vote == "down"
            else "Thanks — feedback recorded. This helps boost trusted resolutions."
        ),
    }


def get_suppressible_ticket_ids(
    *,
    store_path: Path | None = None,
    min_net_down: int = MIN_NET_DOWNVOTES,
) -> set[int]:
    """Ticket IDs with enough net downvotes to suppress when weakly matched."""
    path = store_path or DEFAULT_STORE_PATH
    with _lock:
        store = _load(path)
    out: set[int] = set()
    for key in store.get("ticket_votes") or {}:
        try:
            tid = int(key)
        except (TypeError, ValueError):
            continue
        if net_downvotes(store, tid) >= min_net_down:
            out.add(tid)
    return out


def list_flagged_resolutions(
    *,
    status: str | None = "open",
    limit: int = 50,
    store_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = store_path or DEFAULT_STORE_PATH
    with _lock:
        store = _load(path)
    items = list(store.get("flagged_resolutions") or [])
    if status:
        items = [i for i in items if i.get("status") == status]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items[: max(1, int(limit))]


def feedback_stats(*, store_path: Path | None = None) -> dict[str, Any]:
    path = store_path or DEFAULT_STORE_PATH
    with _lock:
        store = _load(path)
    events = store.get("events") or []
    up = sum(1 for e in events if e.get("vote") == "up")
    down = sum(1 for e in events if e.get("vote") == "down")
    open_flags = sum(
        1
        for f in (store.get("flagged_resolutions") or [])
        if f.get("status") == "open"
    )
    return {
        "events": len(events),
        "up": up,
        "down": down,
        "open_review_flags": open_flags,
        "suppressible_tickets": len(get_suppressible_ticket_ids(store_path=path)),
        "store_path": str(path),
    }
