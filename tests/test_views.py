"""Tests for high_priority_open_tickets and tickets_full_report views."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

TEST_MARKER = "VIEW_TEST_TEMP"
URGENT_ID = 88001
LOW_ID = 88002


def _seed_parent_ids(cursor) -> tuple[int, int]:
    """Return a valid customer_id and category_id."""
    cursor.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
    customer_row = cursor.fetchone()
    cursor.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
    category_row = cursor.fetchone()
    if customer_row is None or category_row is None:
        raise AssertionError("Seed customers/categories missing; run seed_reference_data.py")
    return int(customer_row[0]), int(category_row[0])


def _cleanup(cursor, ticket_ids: list[int]) -> None:
    """Delete temporary test tickets."""
    cursor.execute(
        "DELETE FROM tickets WHERE ticket_id IN (:1, :2) OR description LIKE :3",
        [URGENT_ID, LOW_ID, f"%{TEST_MARKER}%"],
    )


def test_views_exist_filter_order_and_full_report_count():
    """Validate view presence, HIGH/URGENT filter, ordering, and join cardinality."""
    conn = None
    cursor = None
    created_ids = [URGENT_ID, LOW_ID]

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1) Both views exist.
        cursor.execute(
            """
            SELECT view_name
            FROM user_views
            WHERE view_name IN ('HIGH_PRIORITY_OPEN_TICKETS', 'TICKETS_FULL_REPORT')
            ORDER BY view_name
            """
        )
        views = {row[0] for row in cursor.fetchall()}
        assert views == {"HIGH_PRIORITY_OPEN_TICKETS", "TICKETS_FULL_REPORT"}, (
            f"Missing views; found {sorted(views)}"
        )
        print(f"[PASS] USER_VIEWS contains both views: {sorted(views)}")

        customer_id, category_id = _seed_parent_ids(cursor)
        now = datetime.now()

        # Ensure clean slate for temp IDs.
        _cleanup(cursor, created_ids)

        # 2) Insert OPEN/URGENT (should appear) and OPEN/LOW (should not).
        # Make URGENT older than existing HIGH opens so ordering is meaningful,
        # and still verify URGENT ranks before any HIGH in the view.
        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, category_id, description,
                language_code, ticket_status, priority, created_date
            ) VALUES (
                :1, :2, :3, :4, 'en', 'OPEN', 'URGENT', :5
            )
            """,
            [
                URGENT_ID,
                customer_id,
                category_id,
                f"{TEST_MARKER} OPEN URGENT should appear in view",
                now - timedelta(days=60),
            ],
        )
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
                LOW_ID,
                customer_id,
                category_id,
                f"{TEST_MARKER} OPEN LOW should NOT appear in view",
                now - timedelta(days=1),
            ],
        )
        conn.commit()

        # 3) URGENT present, LOW absent.
        cursor.execute(
            """
            SELECT ticket_id, priority
            FROM high_priority_open_tickets
            """
        )
        view_rows = cursor.fetchall()
        view_ids = [int(ticket_id) for ticket_id, _ in view_rows]
        view_priorities = [priority for _, priority in view_rows]

        assert URGENT_ID in view_ids, (
            f"URGENT ticket {URGENT_ID} missing from high_priority_open_tickets"
        )
        assert LOW_ID not in view_ids, (
            f"LOW ticket {LOW_ID} unexpectedly present in high_priority_open_tickets"
        )
        print(
            f"[PASS] URGENT ticket present and LOW ticket absent "
            f"(view ids={view_ids})"
        )

        # 4) URGENT appears before any HIGH-priority tickets.
        first_urgent_pos = next(
            i for i, (tid, _) in enumerate(view_rows) if int(tid) == URGENT_ID
        )
        high_positions = [
            i for i, (_, priority) in enumerate(view_rows) if priority == "HIGH"
        ]
        if high_positions:
            assert first_urgent_pos < min(high_positions), (
                f"URGENT at position {first_urgent_pos} is not before HIGH "
                f"positions {high_positions}; priorities={view_priorities}"
            )
            print(
                f"[PASS] URGENT ticket ordered before HIGH "
                f"(urgent_pos={first_urgent_pos}, high_pos={high_positions})"
            )
        else:
            # Still assert our URGENT row is among leading URGENT block.
            assert view_priorities[0] == "URGENT"
            print("[PASS] No HIGH rows present; leading priority is URGENT")

        # 5) Full report cardinality matches tickets (LEFT JOIN agents safe).
        cursor.execute("SELECT COUNT(*) FROM tickets")
        tickets_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tickets_full_report")
        report_count = cursor.fetchone()[0]
        assert report_count == tickets_count, (
            f"tickets_full_report count {report_count} != tickets count {tickets_count}"
        )
        print(
            f"[PASS] tickets_full_report count matches tickets "
            f"({report_count} rows)"
        )
    finally:
        if cursor is not None and conn is not None:
            try:
                _cleanup(cursor, created_ids)
                conn.commit()
                print(f"[CLEANUP] removed temporary tickets {created_ids}")
            except Exception as cleanup_error:
                conn.rollback()
                print(f"[CLEANUP FAILED] {cleanup_error}")
            finally:
                cursor.close()
                conn.close()
