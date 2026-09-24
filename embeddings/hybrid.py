"""Hybrid retrieval helpers — vector + exact technical keyword matches.

Extracts error codes, ticket IDs, and product-like tokens from a query, then
supports merging VECTOR_DISTANCE hits with Oracle LIKE / full-text (CONTAINS)
or in-memory substring matches.
"""

from __future__ import annotations

import re
from typing import Any

# ORA-12541, ERR-500, ERROR 503, HTTP 429, E1001
ERROR_CODE_RE = re.compile(
    r"\b(?:ORA|ERR|ERROR|HTTP|E)[-_ ]?\d{2,5}\b",
    re.IGNORECASE,
)
# ticket 109, Ticket #42, case 1001, #153
TICKET_ID_RE = re.compile(
    r"\b(?:ticket|case)\s*#?\s*(\d{2,8})\b|#(\d{2,8})\b",
    re.IGNORECASE,
)
# "Salesforce Sync", 'Resolvix Agent'
QUOTED_PRODUCT_RE = re.compile(r'["“]([^"”]{2,64})["”]|\'([^\']{2,64})\'')

KNOWN_PRODUCTS = (
    "resolvix",
    "salesforce",
    "zendesk",
    "jira",
    "okta",
    "oauth",
    "sso",
    "mfa",
    "2fa",
    "gst",
    "upi",
    "authenticator",
    "oracle",
    "ollama",
    "stripe",
    "paypal",
    "slack",
    "teams",
)


def extract_technical_terms(query: str) -> dict[str, Any]:
    """Pull exact-match candidates from free-text support queries."""
    text = query or ""
    error_codes = sorted({m.group(0).upper().replace(" ", "") for m in ERROR_CODE_RE.finditer(text)})
    # Normalize HTTP429 → HTTP 429 display but search both forms
    normalized_errors: list[str] = []
    for code in error_codes:
        normalized_errors.append(code)
        if code.startswith("HTTP") and not code.startswith("HTTP-"):
            spaced = re.sub(r"^HTTP", "HTTP ", code)
            if spaced != code:
                normalized_errors.append(spaced.strip())

    ticket_ids: list[int] = []
    for m in TICKET_ID_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if raw:
            try:
                ticket_ids.append(int(raw))
            except ValueError:
                pass
    ticket_ids = sorted(set(ticket_ids))

    products: list[str] = []
    for m in QUOTED_PRODUCT_RE.finditer(text):
        phrase = (m.group(1) or m.group(2) or "").strip()
        if phrase:
            products.append(phrase)
    lower = text.lower()
    for name in KNOWN_PRODUCTS:
        if re.search(rf"\b{re.escape(name)}\b", lower):
            products.append(name)
    # de-dupe case-insensitively, keep first casing
    seen: set[str] = set()
    uniq_products: list[str] = []
    for p in products:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            uniq_products.append(p)

    like_terms = sorted(
        {t for t in [*normalized_errors, *uniq_products] if t and len(t) >= 2},
        key=lambda s: (-len(s), s.lower()),
    )
    return {
        "error_codes": error_codes,
        "ticket_ids": ticket_ids,
        "products": uniq_products,
        "like_terms": like_terms,
        "has_keywords": bool(ticket_ids or like_terms),
    }


def keyword_hit_score(
    *,
    exact_ticket: bool,
    matched_terms: list[str],
    vector_score: float | None = None,
) -> float:
    """Score for a keyword/exact hit (optionally blended with vector similarity)."""
    if exact_ticket:
        base = 0.995
    elif matched_terms:
        # More distinct technical terms → stronger keyword confidence
        base = min(0.97, 0.82 + 0.04 * len(matched_terms))
    else:
        base = 0.75
    if vector_score is None:
        return base
    # Prefer exact technical signal while keeping semantic ranking
    return min(1.0, 0.55 * float(vector_score) + 0.45 * base)


def merge_hybrid_results(
    vector_hits: list[dict[str, Any]],
    keyword_hits: list[dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    """Combine semantic and keyword result sets with hybrid ranking."""
    by_id: dict[int, dict[str, Any]] = {}

    for hit in vector_hits:
        tid = int(hit["ticket_id"])
        row = dict(hit)
        row.setdefault("match_type", "vector")
        row.setdefault("keyword_hits", [])
        row["exact_ticket"] = bool(row.get("exact_ticket"))
        row["hybrid_score"] = float(row.get("similarity_score") or 0.0)
        by_id[tid] = row

    for hit in keyword_hits:
        tid = int(hit["ticket_id"])
        matched = list(hit.get("keyword_hits") or [])
        exact = bool(hit.get("exact_ticket"))
        if tid in by_id:
            existing = by_id[tid]
            existing["match_type"] = "hybrid"
            existing["exact_ticket"] = existing.get("exact_ticket") or exact
            merged_terms = list(
                dict.fromkeys([*(existing.get("keyword_hits") or []), *matched])
            )
            existing["keyword_hits"] = merged_terms
            score = keyword_hit_score(
                exact_ticket=bool(existing["exact_ticket"]),
                matched_terms=merged_terms,
                vector_score=float(existing.get("similarity_score") or 0.0),
            )
            existing["similarity_score"] = score
            existing["similarity_distance"] = max(0.0, 1.0 - score)
            existing["similarity_pct"] = round(score * 100.0, 1)
            existing["hybrid_score"] = score
            if hit.get("source_mode"):
                existing["keyword_source"] = hit["source_mode"]
        else:
            score = keyword_hit_score(
                exact_ticket=exact,
                matched_terms=matched,
                vector_score=hit.get("similarity_score"),
            )
            row = dict(hit)
            row["match_type"] = "keyword"
            row["exact_ticket"] = exact
            row["keyword_hits"] = matched
            row["similarity_score"] = score
            row["similarity_distance"] = max(0.0, 1.0 - score)
            row["similarity_pct"] = round(score * 100.0, 1)
            row["hybrid_score"] = score
            by_id[tid] = row

    ranked = sorted(
        by_id.values(),
        key=lambda r: (
            1 if r.get("exact_ticket") else 0,
            1 if r.get("match_type") == "hybrid" else 0,
            float(r.get("hybrid_score") or r.get("similarity_score") or 0.0),
        ),
        reverse=True,
    )
    return ranked[: max(1, int(top_n))]


def apply_in_memory_keyword_boost(
    matches: list[dict[str, Any]],
    query_text: str | None,
) -> list[dict[str, Any]]:
    """Annotate/boost in-memory vector hits when description contains tech terms."""
    terms = extract_technical_terms(query_text or "")
    if not terms["has_keywords"]:
        for m in matches:
            m.setdefault("match_type", "vector")
            m.setdefault("keyword_hits", [])
            m.setdefault("exact_ticket", False)
            m["hybrid_score"] = float(m.get("similarity_score") or 0.0)
        return matches

    ticket_ids = set(terms["ticket_ids"])
    like_terms = terms["like_terms"]
    boosted: list[dict[str, Any]] = []
    for m in matches:
        row = dict(m)
        desc = f"{row.get('description') or ''} {row.get('resolution') or ''}".upper()
        hits: list[str] = []
        exact = int(row.get("ticket_id") or -1) in ticket_ids
        if exact:
            hits.append(f"ticket:{row['ticket_id']}")
        for term in like_terms:
            if term.upper() in desc:
                hits.append(term)
        if hits:
            row["match_type"] = "hybrid" if float(row.get("similarity_score") or 0) > 0 else "keyword"
            row["keyword_hits"] = hits
            row["exact_ticket"] = exact
            score = keyword_hit_score(
                exact_ticket=exact,
                matched_terms=hits,
                vector_score=float(row.get("similarity_score") or 0.0),
            )
            row["similarity_score"] = score
            row["similarity_distance"] = max(0.0, 1.0 - score)
            row["similarity_pct"] = round(score * 100.0, 1)
            row["hybrid_score"] = score
        else:
            row.setdefault("match_type", "vector")
            row.setdefault("keyword_hits", [])
            row["exact_ticket"] = False
            row["hybrid_score"] = float(row.get("similarity_score") or 0.0)
        boosted.append(row)

    # Also surface corpus rows that only match keywords (exact ticket / error code)
    # Caller may pass a wider candidate list; ranking happens in merge_hybrid_results.
    return boosted
