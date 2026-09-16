"""
Dual-mode similarity search: Oracle 23ai VECTOR_DISTANCE with in-memory fallback.

When Oracle is reachable, runs native AI Vector Search (COSINE) with optional
hybrid relational filters. When the database is offline, falls back to cosine
similarity over data/tickets_seed.csv without crashing the caller.
"""

from __future__ import annotations

import array
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import oracledb
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection, is_db_available
from embeddings.generate import generate_embedding

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "tickets_seed.csv"

ORACLE_SQL_TEMPLATE = """
SELECT
    t.ticket_id,
    DBMS_LOB.SUBSTR(t.description, 4000, 1) AS description,
    t.resolution,
    t.language_code,
    c.category_name,
    t.priority,
    t.ticket_status,
    VECTOR_DISTANCE(t.description_embedding, :query_vec, COSINE)
        AS similarity_distance,
    ROUND((1 - VECTOR_DISTANCE(t.description_embedding, :query_vec, COSINE)) * 100, 1)
        AS similarity_pct
FROM tickets t
JOIN categories c
  ON t.category_id = c.category_id
WHERE t.ticket_status IN ('RESOLVED', 'CLOSED')
  AND t.description_embedding IS NOT NULL
{extra_filters}
ORDER BY VECTOR_DISTANCE(t.description_embedding, :query_vec, COSINE)
FETCH FIRST :top_n ROWS ONLY
"""


def numpy_converter_in(value: np.ndarray) -> array.array:
    """Convert a NumPy ndarray to array.array for Oracle VECTOR binds."""
    if value.dtype == np.float64:
        dtype = "d"
    elif value.dtype == np.float32:
        dtype = "f"
    elif value.dtype == np.uint8:
        dtype = "B"
    else:
        dtype = "b"
    return array.array(dtype, value)


def input_type_handler(cursor, value, arraysize):
    """Bind NumPy embeddings as Oracle VECTOR via DB_TYPE_VECTOR."""
    if isinstance(value, np.ndarray):
        return cursor.var(
            oracledb.DB_TYPE_VECTOR,
            arraysize=arraysize,
            inconverter=numpy_converter_in,
        )
    return None


def _as_float32_vector(query_embedding: np.ndarray) -> np.ndarray:
    """Normalize bind shape/dtype for VECTOR(384, FLOAT32)."""
    vector = np.asarray(query_embedding, dtype=np.float32).reshape(-1)
    if vector.shape != (384,):
        raise ValueError(
            f"query_embedding must have shape (384,), got {vector.shape}"
        )
    return vector


def build_oracle_sql(
    category_filter: str | None = None,
    priority_filter: str | None = None,
    exclude_ticket_id: int | None = None,
) -> str:
    """Build the live VECTOR_DISTANCE SQL with optional hybrid filters."""
    extras: list[str] = []
    if category_filter and category_filter.lower() not in {"all", ""}:
        extras.append("AND LOWER(c.category_name) = LOWER(:category_filter)")
    if priority_filter and priority_filter.lower() not in {"all", ""}:
        extras.append("AND UPPER(t.priority) = UPPER(:priority_filter)")
    if exclude_ticket_id is not None:
        extras.append("AND t.ticket_id != :exclude_ticket_id")
    extra_sql = ("\n  " + "\n  ".join(extras)) if extras else ""
    return ORACLE_SQL_TEMPLATE.format(extra_filters=extra_sql).strip()


@lru_cache(maxsize=1)
def _load_seed_corpus() -> tuple[tuple[dict[str, Any], ...], np.ndarray]:
    """Load CSV tickets once and precompute embeddings for offline mode."""
    df = pd.read_csv(CSV_PATH)
    records: list[dict[str, Any]] = []
    texts: list[str] = []
    for idx, row in df.iterrows():
        desc = str(row["description"])
        texts.append(desc)
        records.append(
            {
                "ticket_id": int(idx) + 101,
                "description": desc,
                "language_code": str(row.get("language_code", "en")),
                "category_name": str(row.get("category_name", "General")),
                "resolution": str(row.get("resolution", "")),
                "priority": str(row.get("priority", "MEDIUM")),
                "ticket_status": "RESOLVED",
            }
        )
    from embeddings.generate import generate_embeddings_batch

    matrix = generate_embeddings_batch(texts)
    return tuple(records), matrix


def find_similar_in_memory(
    query_embedding: np.ndarray,
    top_n: int = 3,
    category_filter: str | None = None,
    priority_filter: str | None = None,
    exclude_ticket_id: int | None = None,
) -> list[dict[str, Any]]:
    """Cosine similarity over the seed CSV corpus (offline fallback)."""
    query_vec = _as_float32_vector(query_embedding)
    records, matrix = _load_seed_corpus()
    query_norm = float(np.linalg.norm(query_vec))
    if query_norm == 0:
        return []

    results: list[dict[str, Any]] = []
    for i, ticket in enumerate(records):
        if exclude_ticket_id is not None and ticket["ticket_id"] == exclude_ticket_id:
            continue
        if category_filter and category_filter.lower() not in {"all", ""}:
            if ticket["category_name"].lower() != category_filter.lower():
                continue
        if priority_filter and priority_filter.lower() not in {"all", ""}:
            if ticket["priority"].upper() != priority_filter.upper():
                continue

        t_vec = matrix[i]
        t_norm = float(np.linalg.norm(t_vec))
        if t_norm == 0:
            continue
        sim = float(np.dot(query_vec, t_vec) / (query_norm * t_norm))
        dist = max(0.0, 1.0 - sim)
        results.append(
            {
                **ticket,
                "similarity_distance": dist,
                "similarity_score": sim,
                "similarity_pct": round(sim * 100.0, 1),
                "source_mode": "IN_MEMORY",
            }
        )

    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:top_n]


def _search_oracle(
    query_vec: np.ndarray,
    top_n: int,
    category_filter: str | None,
    priority_filter: str | None,
    exclude_ticket_id: int | None,
) -> list[dict[str, Any]]:
    """Execute Oracle 23ai VECTOR_DISTANCE search."""
    sql = build_oracle_sql(category_filter, priority_filter, exclude_ticket_id)
    binds: dict[str, Any] = {"query_vec": query_vec, "top_n": top_n}
    if category_filter and category_filter.lower() not in {"all", ""}:
        binds["category_filter"] = category_filter
    if priority_filter and priority_filter.lower() not in {"all", ""}:
        binds["priority_filter"] = priority_filter
    if exclude_ticket_id is not None:
        binds["exclude_ticket_id"] = exclude_ticket_id

    conn = None
    cursor = None
    try:
        conn = get_connection()
        conn.inputtypehandler = input_type_handler
        cursor = conn.cursor()
        cursor.execute(sql, binds)
        rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            (
                ticket_id,
                description,
                resolution,
                language_code,
                category_name,
                priority,
                ticket_status,
                similarity_distance,
                similarity_pct,
            ) = row
            distance = float(similarity_distance)
            text = description if description is not None else ""
            if hasattr(text, "read"):
                text = text.read()
            text = str(text)

            resolution_text = resolution
            if resolution_text is not None and hasattr(resolution_text, "read"):
                resolution_text = resolution_text.read()

            results.append(
                {
                    "ticket_id": int(ticket_id),
                    "description": text,
                    "resolution": (
                        None if resolution_text is None else str(resolution_text)
                    ),
                    "language_code": language_code,
                    "category_name": category_name,
                    "priority": priority,
                    "ticket_status": ticket_status,
                    "similarity_distance": distance,
                    "similarity_score": 1.0 - distance,
                    "similarity_pct": float(similarity_pct)
                    if similarity_pct is not None
                    else round((1.0 - distance) * 100.0, 1),
                    "source_mode": "ORACLE_23AI",
                }
            )
        return results
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def find_similar_tickets(
    query_embedding: np.ndarray,
    exclude_ticket_id: int | None = None,
    top_n: int = 3,
    category_filter: str | None = None,
    priority_filter: str | None = None,
    prefer_oracle: bool = True,
) -> list[dict[str, Any]]:
    """Find similar resolved tickets via Oracle or in-memory fallback.

    Never raises solely because Oracle is offline — falls back to CSV corpus.
    """
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")

    query_vec = _as_float32_vector(query_embedding)

    if prefer_oracle and is_db_available():
        try:
            return _search_oracle(
                query_vec,
                top_n=top_n,
                category_filter=category_filter,
                priority_filter=priority_filter,
                exclude_ticket_id=exclude_ticket_id,
            )
        except Exception:
            pass

    return find_similar_in_memory(
        query_vec,
        top_n=top_n,
        category_filter=category_filter,
        priority_filter=priority_filter,
        exclude_ticket_id=exclude_ticket_id,
    )


def file_new_ticket(
    description: str,
    embedding: np.ndarray,
    category_name: str,
    priority: str,
    language_code: str = "en",
    resolution: str | None = None,
) -> int | None:
    """Insert an OPEN ticket into Oracle 23ai. Returns ticket_id or None if offline."""
    if not is_db_available():
        return None

    query_vec = _as_float32_vector(embedding)
    # Map agent CRITICAL → schema URGENT
    priority_map = {
        "CRITICAL": "URGENT",
        "URGENT": "URGENT",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "MED": "MEDIUM",
        "LOW": "LOW",
    }
    db_priority = priority_map.get(str(priority).upper(), "MEDIUM")

    category_aliases = {
        "TECH": "Technical",
        "TECHNICAL": "Technical",
        "BILLING": "Billing",
        "ACCOUNT": "Account",
        "SECURITY": "Login",
        "LOGIN": "Login",
        "REFUND": "Refund",
        "GENERAL": "General",
    }
    resolved_category = category_aliases.get(
        str(category_name).upper(), category_name
    )

    conn = None
    cursor = None
    try:
        conn = get_connection()
        conn.inputtypehandler = input_type_handler
        cursor = conn.cursor()

        cursor.execute(
            "SELECT category_id FROM categories WHERE LOWER(category_name) = LOWER(:n)",
            {"n": resolved_category},
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "SELECT category_id FROM categories WHERE LOWER(category_name) = 'general'"
            )
            row = cursor.fetchone()
        category_id = int(row[0]) if row else 1

        cursor.execute("SELECT NVL(MIN(customer_id), 1) FROM customers")
        customer_id = int(cursor.fetchone()[0])
        cursor.execute("SELECT NVL(MIN(agent_id), 1) FROM agents")
        agent_id = int(cursor.fetchone()[0])

        cursor.execute("SELECT NVL(MAX(ticket_id), 100) + 1 FROM tickets")
        ticket_id = int(cursor.fetchone()[0])

        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, agent_id, category_id,
                description, language_code, ticket_status, priority,
                resolution, description_embedding
            ) VALUES (
                :ticket_id, :customer_id, :agent_id, :category_id,
                :description, :language_code, 'OPEN', :priority,
                :resolution, :embedding
            )
            """,
            {
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "agent_id": agent_id,
                "category_id": category_id,
                "description": description,
                "language_code": language_code[:5],
                "priority": db_priority,
                "resolution": resolution,
                "embedding": query_vec,
            },
        )
        conn.commit()
        return ticket_id
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sample = generate_embedding("Unable to reset my password reset link expired")
    matches = find_similar_tickets(sample, top_n=3)
    mode = matches[0]["source_mode"] if matches else "NONE"
    print(f"backend={mode}")
    for match in matches:
        print(
            f"#{match['ticket_id']} [{match['language_code']}/{match['category_name']}] "
            f"score={match['similarity_score']:.4f} dist={match['similarity_distance']:.4f}"
        )
