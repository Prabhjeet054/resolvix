"""
Similarity search over ticket description embeddings using Oracle AI Vector Search.

COSINE distance from VECTOR_DISTANCE(..., COSINE) is typically in [0, 2] for
normalized embeddings: 0 means identical direction (most similar), 2 means
opposite directions. COSINE is preferred over EUCLIDEAN here because multilingual
sentence embeddings are usually L2-normalized and encode meaning in vector
*direction*; cosine compares angles and is scale-invariant, so English/Hindi/Tamil
paraphrases that land near each other in direction score as similar even when
raw Euclidean magnitudes would be less informative.
"""

from __future__ import annotations

import array
import os
import sys
from typing import Any

import numpy as np
import oracledb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection


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


def find_similar_tickets(
    query_embedding: np.ndarray,
    exclude_ticket_id: int | None = None,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Find the closest resolved/closed tickets by COSINE VECTOR_DISTANCE.

    COSINE distance is approximately 0 for identical embedding direction and up
    to 2 for opposite directions. COSINE is preferred over EUCLIDEAN for this
    multilingual text-embedding use case because paraphrase-multilingual
    MiniLM vectors are direction-based (and typically normalized): semantic
    closeness is angular, so cosine distance ranks English/Hindi/Tamil
    paraphrases consistently without being skewed by vector magnitude.

    Args:
        query_embedding: float32 (or convertible) vector of shape (384,).
        exclude_ticket_id: Optional ticket_id to skip (avoid self-matches).
        top_n: Maximum number of neighbors to return.

    Returns:
        List of dicts with ticket_id, description (≤200 chars), resolution,
        language_code, category_name, similarity_distance, similarity_score.
    """
    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n}")

    query_vec = _as_float32_vector(query_embedding)

    sql = """
        SELECT
            t.ticket_id,
            DBMS_LOB.SUBSTR(t.description, 200, 1) AS description,
            t.resolution,
            t.language_code,
            c.category_name,
            VECTOR_DISTANCE(t.description_embedding, :query_vec, COSINE)
                AS similarity_distance
        FROM tickets t
        JOIN categories c
          ON t.category_id = c.category_id
        WHERE t.ticket_status IN ('RESOLVED', 'CLOSED')
          AND t.description_embedding IS NOT NULL
    """
    binds: dict[str, Any] = {
        "query_vec": query_vec,
        "top_n": top_n,
    }

    if exclude_ticket_id is not None:
        sql += " AND t.ticket_id != :exclude_ticket_id"
        binds["exclude_ticket_id"] = exclude_ticket_id

    sql += """
        ORDER BY VECTOR_DISTANCE(t.description_embedding, :query_vec, COSINE)
        FETCH FIRST :top_n ROWS ONLY
    """

    conn = None
    cursor = None
    try:
        conn = get_connection()
        conn.inputtypehandler = input_type_handler
        cursor = conn.cursor()
        cursor.execute(sql, binds)
        rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for (
            ticket_id,
            description,
            resolution,
            language_code,
            category_name,
            similarity_distance,
        ) in rows:
            distance = float(similarity_distance)
            text = description if description is not None else ""
            if hasattr(text, "read"):
                text = text.read()
            text = str(text)
            if len(text) > 200:
                text = text[:200]

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
                    "similarity_distance": distance,
                    "similarity_score": 1.0 - distance,
                }
            )
        return results
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    from embeddings.generate import generate_embedding

    sample = generate_embedding("Unable to reset my password reset link expired")
    matches = find_similar_tickets(sample, top_n=3)
    for match in matches:
        print(
            f"#{match['ticket_id']} [{match['language_code']}/{match['category_name']}] "
            f"score={match['similarity_score']:.4f} dist={match['similarity_distance']:.4f}"
        )
        print(f"  {match['description'][:120]}...")
