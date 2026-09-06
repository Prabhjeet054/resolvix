"""Tests proving daily_ticket_summary is a refreshable snapshot, not live."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

TEST_TICKET_ID = 88201


def _sum_total_tickets(cursor) -> int:
    """Return SUM(total_tickets) from the materialized view."""
    cursor.execute(
        """
        SELECT NVL(SUM(total_tickets), 0)
        FROM daily_ticket_summary
        """
    )
    return int(cursor.fetchone()[0])


def _refresh_mview(cursor) -> None:
    """Refresh DAILY_TICKET_SUMMARY via DBMS_MVIEW."""
    cursor.execute("BEGIN DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY'); END;")


def _cleanup_test_ticket(cursor) -> None:
    """Delete the temporary test ticket if present."""
    cursor.execute("DELETE FROM tickets WHERE ticket_id = :1", [TEST_TICKET_ID])


def test_materialized_view_snapshot_then_refresh():
    """Insert a ticket, show stale MVIEW, refresh, then restore state."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Start from a clean MVIEW that matches current tickets.
        _cleanup_test_ticket(cursor)
        conn.commit()
        _refresh_mview(cursor)

        # 1) Baseline sum.
        before_sum = _sum_total_tickets(cursor)
        print(f"[STEP 1] total_tickets sum BEFORE insert = {before_sum}")

        cursor.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
        customer_id = int(cursor.fetchone()[0])
        cursor.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
        category_id = int(cursor.fetchone()[0])

        # 2) Insert one ticket dated today.
        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, category_id, description,
                language_code, ticket_status, priority, created_date
            ) VALUES (
                :1, :2, :3, :4, 'en', 'OPEN', 'LOW', :5
            )
            """,
            [
                TEST_TICKET_ID,
                customer_id,
                category_id,
                "MVIEW_TEST temporary ticket for refresh demo",
                datetime.now(),
            ],
        )
        conn.commit()
        print(f"[STEP 2] Inserted test ticket_id={TEST_TICKET_ID} (committed)")

        # 3) Without refresh, MVIEW sum must be unchanged (snapshot).
        stale_sum = _sum_total_tickets(cursor)
        print(f"[STEP 3] total_tickets sum WITHOUT refresh = {stale_sum}")
        assert stale_sum == before_sum, (
            f"Expected unchanged snapshot sum {before_sum}, got {stale_sum}"
        )
        print("[PASS] MVIEW unchanged before refresh (snapshot, not live)")

        # 4) Refresh.
        _refresh_mview(cursor)
        print("[STEP 4] Executed DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY')")

        # 5) After refresh, sum includes the new ticket.
        refreshed_sum = _sum_total_tickets(cursor)
        print(f"[STEP 5] total_tickets sum AFTER refresh = {refreshed_sum}")
        assert refreshed_sum == before_sum + 1, (
            f"Expected sum {before_sum + 1} after refresh, got {refreshed_sum}"
        )
        print("[PASS] MVIEW includes new ticket after refresh")
    finally:
        # 6) Cleanup + refresh to restore original state.
        if cursor is not None and conn is not None:
            try:
                _cleanup_test_ticket(cursor)
                conn.commit()
                _refresh_mview(cursor)
                restored_sum = _sum_total_tickets(cursor)
                print(
                    f"[STEP 6] Cleanup done; total_tickets sum after "
                    f"restore refresh = {restored_sum}"
                )
            except Exception as cleanup_error:
                conn.rollback()
                print(f"[CLEANUP FAILED] {cleanup_error}")
            finally:
                cursor.close()
                conn.close()
