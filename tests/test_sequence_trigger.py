"""Tests for ticket_seq and trg_tickets_id (auto ID vs explicit ID)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection


EXPLICIT_TICKET_ID = 99999
TEST_MARKER = "SEQ_TRIGGER_TEST"


def _report(label: str, passed: bool, detail: str) -> None:
    """Print a clear PASS/FAIL line for an assertion."""
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {label}: {detail}")
    if not passed:
        raise AssertionError(f"{label}: {detail}")


def _ensure_parent_rows(cursor) -> tuple[int, int]:
    """Return usable customer_id and category_id, inserting seeds if needed."""
    cursor.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            """
            INSERT INTO customers (customer_id, customer_name, email, region)
            VALUES (1, 'Seq Test Customer', 'seq.trigger.customer@example.com', 'IN')
            """
        )
        customer_id = 1
    else:
        customer_id = int(row[0])

    cursor.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
    row = cursor.fetchone()
    if row is None:
        cursor.execute(
            """
            INSERT INTO categories (category_id, category_name, description)
            VALUES (1, 'Seq Test Category', 'Temporary category for sequence tests')
            """
        )
        category_id = 1
    else:
        category_id = int(row[0])

    return customer_id, category_id


def _cleanup_test_rows(cursor, ticket_ids: list[int]) -> None:
    """Delete any rows created by this test."""
    if not ticket_ids:
        cursor.execute(
            "DELETE FROM tickets WHERE description LIKE :1",
            [f"%{TEST_MARKER}%"],
        )
        return

    binds = ",".join(f":{i + 1}" for i in range(len(ticket_ids)))
    cursor.execute(
        f"DELETE FROM tickets WHERE ticket_id IN ({binds})",
        ticket_ids,
    )


def test_sequence_trigger_auto_and_explicit_ids():
    """Insert without/with ticket_id and verify trigger + sequence behavior."""
    conn = None
    cursor = None
    created_ids: list[int] = []

    try:
        conn = get_connection()
        cursor = conn.cursor()
        customer_id, category_id = _ensure_parent_rows(cursor)
        conn.commit()

        # 1) Insert 3 rows without ticket_id; capture IDs in insert order.
        for i in range(3):
            ticket_id_var = cursor.var(int)
            cursor.execute(
                """
                INSERT INTO tickets (
                    customer_id, category_id, description, created_date
                ) VALUES (
                    :1, :2, :3, SYSTIMESTAMP
                )
                RETURNING ticket_id INTO :4
                """,
                [
                    customer_id,
                    category_id,
                    f"{TEST_MARKER} auto insert #{i + 1}",
                    ticket_id_var,
                ],
            )
            created_ids.append(int(ticket_id_var.getvalue()[0]))

        conn.commit()

        # Query back ordered by the IDs we captured (insert order).
        binds = ",".join(f":{i + 1}" for i in range(len(created_ids)))
        cursor.execute(
            f"""
            SELECT ticket_id
            FROM tickets
            WHERE ticket_id IN ({binds})
            ORDER BY ticket_id
            """,
            created_ids,
        )
        queried_ids = [int(row[0]) for row in cursor.fetchall()]

        _report(
            "three auto IDs returned",
            len(queried_ids) == 3,
            f"expected 3 rows, got {queried_ids}",
        )
        _report(
            "auto IDs match insert order values",
            queried_ids == sorted(created_ids),
            f"inserted={created_ids}, queried={queried_ids}",
        )
        _report(
            "auto IDs strictly increasing",
            queried_ids[0] < queried_ids[1] < queried_ids[2],
            f"ids={queried_ids}",
        )
        _report(
            "auto IDs have no duplicates",
            len(set(queried_ids)) == 3,
            f"ids={queried_ids}",
        )
        _report(
            "auto IDs are consecutive (no gaps)",
            queried_ids[1] == queried_ids[0] + 1
            and queried_ids[2] == queried_ids[1] + 1,
            f"ids={queried_ids}",
        )
        _report(
            "auto IDs follow ticket_seq range (>= 1000)",
            queried_ids[0] >= 1000,
            f"first_id={queried_ids[0]}",
        )

        # 3) Explicit ticket_id must not be overridden by the trigger.
        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, category_id, description, created_date
            ) VALUES (
                :1, :2, :3, :4, SYSTIMESTAMP
            )
            """,
            [
                EXPLICIT_TICKET_ID,
                customer_id,
                category_id,
                f"{TEST_MARKER} explicit id",
            ],
        )
        created_ids.append(EXPLICIT_TICKET_ID)
        conn.commit()

        cursor.execute(
            "SELECT ticket_id FROM tickets WHERE ticket_id = :1",
            [EXPLICIT_TICKET_ID],
        )
        explicit_row = cursor.fetchone()
        actual_explicit = int(explicit_row[0]) if explicit_row else None
        _report(
            "explicit ticket_id preserved",
            actual_explicit == EXPLICIT_TICKET_ID,
            f"expected={EXPLICIT_TICKET_ID}, actual={actual_explicit}",
        )

        print(
            f"\nSummary: auto_ids={queried_ids}, "
            f"explicit_id={actual_explicit}"
        )
    finally:
        # 4) Cleanup regardless of pass/fail.
        if cursor is not None and conn is not None:
            try:
                _cleanup_test_rows(cursor, created_ids)
                conn.commit()
                print(f"Cleanup: deleted test ticket_ids={created_ids}")
            except Exception as cleanup_error:
                conn.rollback()
                print(f"Cleanup failed: {cleanup_error}")
            finally:
                cursor.close()
                conn.close()
