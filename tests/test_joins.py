"""Verify the full ticket report join query cardinality and join correctness."""

from __future__ import annotations

import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

JOIN_SQL_PATH = PROJECT_ROOT / "db" / "10_full_ticket_report_query.sql"


def _load_join_sql() -> str:
    """Load the single SELECT from db/10_full_ticket_report_query.sql."""
    statements = split_sql_statements(JOIN_SQL_PATH.read_text(encoding="utf-8"))
    assert len(statements) == 1, f"Expected 1 statement, found {len(statements)}"
    return statements[0]


def test_full_ticket_report_joins():
    """Check row count, Unassigned LEFT JOIN behavior, and sample join values."""
    join_sql = _load_join_sql()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tickets")
        tickets_count = int(cursor.fetchone()[0])

        cursor.execute(join_sql)
        columns = [col[0].lower() for col in cursor.description]
        join_rows = cursor.fetchall()
        join_by_id = {int(row[columns.index("ticket_id")]): row for row in join_rows}

        # 1) Join output cardinality matches Tickets (no drop/duplication).
        assert len(join_rows) == tickets_count, (
            f"Join returned {len(join_rows)} rows but Tickets has {tickets_count}"
        )
        print(
            f"[PASS] join row count {len(join_rows)} == Tickets count {tickets_count}"
        )

        # 2) NULL agent_id tickets appear as agent_name = 'Unassigned'.
        cursor.execute(
            """
            SELECT ticket_id
            FROM tickets
            WHERE agent_id IS NULL
            FETCH FIRST 1 ROWS ONLY
            """
        )
        null_agent_row = cursor.fetchone()
        assert null_agent_row is not None, (
            "No ticket with NULL agent_id found; re-run ingest with unassigned tickets"
        )
        null_agent_ticket_id = int(null_agent_row[0])
        assert null_agent_ticket_id in join_by_id, (
            f"ticket_id={null_agent_ticket_id} with NULL agent_id missing from join "
            "(would happen if Agents were INNER JOINed)"
        )
        agent_name = join_by_id[null_agent_ticket_id][columns.index("agent_name")]
        assert agent_name == "Unassigned", (
            f"ticket_id={null_agent_ticket_id}: expected agent_name='Unassigned', "
            f"got {agent_name!r}"
        )
        print(
            f"[PASS] NULL agent_id ticket_id={null_agent_ticket_id} "
            f"appears with agent_name='Unassigned'"
        )

        # 3) Cross-check 3 random join rows against source tables.
        sample_ids = random.sample(sorted(join_by_id), k=min(3, len(join_by_id)))
        for ticket_id in sample_ids:
            join_row = join_by_id[ticket_id]
            join_customer = join_row[columns.index("customer_name")]
            join_category = join_row[columns.index("category_name")]

            cursor.execute(
                """
                SELECT c.customer_name, cat.category_name
                FROM tickets t
                JOIN customers c
                  ON t.customer_id = c.customer_id
                JOIN categories cat
                  ON t.category_id = cat.category_id
                WHERE t.ticket_id = :1
                """,
                [ticket_id],
            )
            source_row = cursor.fetchone()
            assert source_row is not None, f"ticket_id={ticket_id} missing in source join"
            source_customer, source_category = source_row

            assert join_customer == source_customer, (
                f"ticket_id={ticket_id}: customer_name mismatch "
                f"join={join_customer!r} source={source_customer!r}"
            )
            assert join_category == source_category, (
                f"ticket_id={ticket_id}: category_name mismatch "
                f"join={join_category!r} source={source_category!r}"
            )
            print(
                f"[PASS] ticket_id={ticket_id}: customer_name={join_customer!r}, "
                f"category_name={join_category!r} match source tables"
            )
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
