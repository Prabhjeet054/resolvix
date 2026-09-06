"""Verify ticket ingestion: counts, vectors, statuses, JSON, idempotency."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from embeddings.ingest import ingest_tickets


def test_ingestion_quality_and_idempotency():
    """Assert seed tickets meet schema/quality rules and re-ingest stays at 20."""
    # Fresh ingest so assertions run against a known 20-row set.
    ingest_tickets()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1) Exactly 20 tickets.
        cursor.execute("SELECT COUNT(*) FROM tickets")
        total = cursor.fetchone()[0]
        assert total == 20, f"Expected 20 tickets, got {total}"
        print(f"[PASS] ticket count = {total}")

        # 2) Every embedding is non-NULL and 384-dimensional.
        cursor.execute(
            """
            SELECT ticket_id,
                   VECTOR_DIMENSION_COUNT(description_embedding) AS dim
            FROM tickets
            """
        )
        dim_rows = cursor.fetchall()
        assert len(dim_rows) == 20
        for ticket_id, dim in dim_rows:
            assert dim is not None, f"ticket_id={ticket_id} has NULL embedding dim"
            assert int(dim) == 384, (
                f"ticket_id={ticket_id} expected dim=384, got {dim}"
            )
        print("[PASS] all 20 tickets have description_embedding dim = 384")

        # 3) OPEN count within randomization band (2–3 by design; allow 2–5).
        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE ticket_status = 'OPEN'"
        )
        open_count = cursor.fetchone()[0]
        assert 2 <= open_count <= 5, (
            f"Expected 2–5 OPEN tickets, got {open_count}"
        )
        print(f"[PASS] OPEN ticket count = {open_count} (within 2–5)")

        # 4) RESOLVED/CLOSED have resolution and resolved_date >= created_date.
        cursor.execute(
            """
            SELECT ticket_id, ticket_status, resolution, created_date, resolved_date
            FROM tickets
            WHERE ticket_status IN ('RESOLVED', 'CLOSED')
            """
        )
        closed_like = cursor.fetchall()
        assert closed_like, "Expected at least one RESOLVED/CLOSED ticket"
        for ticket_id, status, resolution, created_date, resolved_date in closed_like:
            assert resolution is not None, (
                f"ticket_id={ticket_id} ({status}) missing resolution"
            )
            assert resolved_date is not None, (
                f"ticket_id={ticket_id} ({status}) missing resolved_date"
            )
            assert resolved_date >= created_date, (
                f"ticket_id={ticket_id}: resolved_date {resolved_date} "
                f"< created_date {created_date}"
            )
        print(
            f"[PASS] {len(closed_like)} RESOLVED/CLOSED tickets have "
            "resolution and resolved_date >= created_date"
        )

        # 5) JSON metadata.attachment_count is a valid integer.
        cursor.execute(
            """
            SELECT JSON_VALUE(metadata, '$.attachment_count')
            FROM tickets
            WHERE ROWNUM <= 3
            """
        )
        json_values = [row[0] for row in cursor.fetchall()]
        assert len(json_values) == 3
        for raw in json_values:
            assert raw is not None, "JSON_VALUE returned NULL for attachment_count"
            as_int = int(raw)
            assert 0 <= as_int <= 2, f"attachment_count out of range: {as_int}"
        print(f"[PASS] JSON attachment_count samples = {json_values}")

        # 6) Second ingest must replace, not duplicate (DELETE-then-insert).
        ingest_tickets()
        cursor.execute("SELECT COUNT(*) FROM tickets")
        total_after = cursor.fetchone()[0]
        assert total_after == 20, (
            f"After second ingest expected 20 tickets, got {total_after} "
            "(duplicates were inserted)"
        )
        print(
            "[PASS] second ingest left count at 20 "
            "(DELETE-before-insert idempotency)"
        )
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
