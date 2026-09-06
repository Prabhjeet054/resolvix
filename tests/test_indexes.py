"""Verify ticket B-tree indexes exist with expected columns/order."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

EXPECTED_INDEXES = {
    "IDX_TICKETS_STATUS",
    "IDX_TICKETS_CREATED_DATE",
    "IDX_TICKETS_STATUS_CREATED",
}


def test_ticket_indexes_exist_and_composite_column_order():
    """Confirm the three NORMAL indexes and composite column order."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1) All three indexes exist on TICKETS with type NORMAL.
        cursor.execute(
            """
            SELECT index_name, index_type, table_name, uniqueness
            FROM user_indexes
            WHERE table_name = 'TICKETS'
              AND index_name IN (
                  'IDX_TICKETS_STATUS',
                  'IDX_TICKETS_CREATED_DATE',
                  'IDX_TICKETS_STATUS_CREATED'
              )
            ORDER BY index_name
            """
        )
        rows = cursor.fetchall()
        found = {row[0]: row for row in rows}

        missing = EXPECTED_INDEXES - set(found)
        assert not missing, f"Missing indexes on TICKETS: {sorted(missing)}"

        for name, (index_name, index_type, table_name, uniqueness) in found.items():
            assert table_name == "TICKETS", f"{name} table_name={table_name}"
            assert index_type == "NORMAL", (
                f"{name} expected index_type NORMAL, got {index_type!r}"
            )
            print(
                f"[PASS] {index_name}: type={index_type}, "
                f"table={table_name}, uniqueness={uniqueness}"
            )

        # 2) Composite index column order: ticket_status, created_date.
        cursor.execute(
            """
            SELECT column_name, column_position
            FROM user_ind_columns
            WHERE index_name = 'IDX_TICKETS_STATUS_CREATED'
            ORDER BY column_position
            """
        )
        columns = [(row[0], int(row[1])) for row in cursor.fetchall()]
        assert len(columns) == 2, (
            f"Expected exactly 2 columns on composite index, got {columns}"
        )
        assert columns[0] == ("TICKET_STATUS", 1), (
            f"Leading column should be TICKET_STATUS at position 1, got {columns[0]}"
        )
        assert columns[1] == ("CREATED_DATE", 2), (
            f"Second column should be CREATED_DATE at position 2, got {columns[1]}"
        )
        print(
            "[PASS] IDX_TICKETS_STATUS_CREATED columns in order: "
            "TICKET_STATUS, CREATED_DATE"
        )

        print(
            "\nNote: With only ~20 Tickets rows, EXPLAIN PLAN may still show "
            "TABLE ACCESS FULL because the cost-based optimizer prefers a full "
            "scan on tiny tables. That is not an index-definition failure. To "
            "force index usage for report screenshots, insert a few hundred "
            "dummy rows (e.g. a PL/SQL or Python loop) and re-run "
            "scripts/explain_plan_demo.py."
        )
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
