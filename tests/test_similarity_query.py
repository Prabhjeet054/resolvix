"""End-to-end similarity search tests against seeded Oracle tickets."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from embeddings.generate import generate_embedding
from embeddings.similarity_search import find_similar_tickets

PASSWORD_RESET_EN_SNIPPET = "Unable to reset my password"
PASSWORD_RESET_HI_SNIPPET = "पासवर्ड रीसेट"
PASSWORD_RESET_TA_SNIPPET = "password-ஐ reset"


def _report(label: str, passed: bool, detail: str) -> None:
    """Print a PASS/FAIL line for one assertion."""
    status = "PASS" if passed else "FAIL"
    print(f"| {status:4} | {label} | {detail}")
    if not passed:
        raise AssertionError(f"{label}: {detail}")


def _fetch_password_reset_ticket() -> tuple[int, str]:
    """Return ticket_id and full description for the English password-reset seed."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT ticket_id, description
            FROM tickets
            WHERE language_code = 'en'
              AND DBMS_LOB.INSTR(description, :snippet) > 0
              AND ticket_status IN ('RESOLVED', 'CLOSED')
            FETCH FIRST 1 ROWS ONLY
            """,
            {"snippet": PASSWORD_RESET_EN_SNIPPET},
        )
        row = cursor.fetchone()
        if row is None:
            raise AssertionError(
                "English password-reset ticket not found; run embeddings/ingest.py"
            )
        ticket_id, description = row
        if hasattr(description, "read"):
            description = description.read()
        return int(ticket_id), str(description)
    finally:
        cursor.close()
        conn.close()


def test_similarity_query_cross_lingual_and_fresh_query():
    """Verify DB VECTOR search ranks translation pairs and handles new queries."""
    print("\n| STATUS | ASSERTION | DETAIL")
    print("|--------|-----------|--------")

    source_id, source_description = _fetch_password_reset_ticket()
    query_embedding = generate_embedding(source_description)
    results = find_similar_tickets(
        query_embedding,
        exclude_ticket_id=source_id,
        top_n=3,
    )

    _report(
        "result length <= 3",
        len(results) <= 3,
        f"len={len(results)}",
    )
    _report(
        "self ticket_id excluded",
        all(r["ticket_id"] != source_id for r in results),
        f"source_id={source_id}, ids={[r['ticket_id'] for r in results]}",
    )

    scores = [r["similarity_score"] for r in results]
    ordered = scores == sorted(scores, reverse=True)
    _report(
        "ordered by similarity_score DESC",
        ordered,
        f"scores={[round(s, 4) for s in scores]}",
    )

    cross_lingual_hit = any(
        (
            (r["language_code"] == "hi" and PASSWORD_RESET_HI_SNIPPET in r["description"])
            or (
                r["language_code"] == "ta"
                and PASSWORD_RESET_TA_SNIPPET.lower()
                in r["description"].lower()
            )
        )
        for r in results
    )
    detail_rows = [
        f"#{r['ticket_id']} {r['language_code']} score={r['similarity_score']:.4f} "
        f"{r['description'][:60]}"
        for r in results
    ]
    _report(
        "top-3 includes Hindi or Tamil password-reset pair",
        cross_lingual_hit,
        " | ".join(detail_rows) if detail_rows else "no results",
    )

    # Fresh incoming ticket text not taken from the seed CSV.
    fresh_query = (
        "Brand new issue: my SSO login keeps redirecting in a loop after MFA "
        "and I never reach the ticket dashboard."
    )
    fresh_embedding = generate_embedding(fresh_query)
    fresh_results = find_similar_tickets(fresh_embedding, top_n=3)

    print("\nFresh query (not in seed CSV):")
    print(f"  {fresh_query}")
    print("Top-3 neighbors for manual review:")
    for rank, match in enumerate(fresh_results, start=1):
        print(
            f"  {rank}. #{match['ticket_id']} [{match['language_code']}/"
            f"{match['category_name']}] "
            f"score={match['similarity_score']:.4f} "
            f"dist={match['similarity_distance']:.4f}"
        )
        print(f"     {match['description'][:160]}")

    _report(
        "fresh query returned <= 3 rows",
        len(fresh_results) <= 3,
        f"len={len(fresh_results)}",
    )

    print("\nSummary: all similarity-query assertions PASSED.")
