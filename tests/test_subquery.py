"""Verify above-average resolution subquery against Python-computed average."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

SQL_PATH = PROJECT_ROOT / "db" / "09_subquery_above_avg.sql"


def _duration_days(created_date, resolved_date) -> float:
    """Resolution time in fractional days via Python datetime arithmetic."""
    return (resolved_date - created_date).total_seconds() / 86400.0


def test_above_average_subquery_variants():
    """Cross-check WHERE-subquery and CTE variants against a Python average."""
    statements = split_sql_statements(SQL_PATH.read_text(encoding="utf-8"))
    assert len(statements) == 2, f"Expected 2 query variants, found {len(statements)}"
    where_sql, cte_sql = statements

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1) Independently compute average resolution time in Python.
        cursor.execute(
            """
            SELECT ticket_id, created_date, resolved_date
            FROM tickets
            WHERE resolved_date IS NOT NULL
            """
        )
        resolved_rows = cursor.fetchall()
        assert resolved_rows, "No resolved tickets found"

        durations_by_id = {
            int(ticket_id): _duration_days(created_date, resolved_date)
            for ticket_id, created_date, resolved_date in resolved_rows
        }
        python_avg = sum(durations_by_id.values()) / len(durations_by_id)
        print(
            f"[INFO] Python average resolution days "
            f"(datetime arithmetic) = {python_avg:.6f} "
            f"over {len(durations_by_id)} resolved tickets"
        )

        # 2) Run Variant 1 (WHERE subquery) and assert every row is above average.
        cursor.execute(where_sql)
        where_rows = cursor.fetchall()
        # ticket_id, description, agent_name, resolution_days
        where_ids = [int(row[0]) for row in where_rows]
        assert where_ids, "WHERE-subquery variant returned no rows"

        for ticket_id, _description, _agent_name, resolution_days in where_rows:
            duration = durations_by_id[int(ticket_id)]
            assert duration > python_avg, (
                f"ticket_id={ticket_id}: duration {duration:.6f} "
                f"is not > python_avg {python_avg:.6f}"
            )
            # resolution_days is CAST(AS DATE) days; still must be above the
            # same conceptual average when compared via true duration above.
            assert resolution_days is not None, (
                f"ticket_id={ticket_id} missing resolution_days"
            )
            print(
                f"[PASS] ticket_id={ticket_id}: duration_days={duration:.4f} "
                f"> avg={python_avg:.4f} (sql resolution_days={float(resolution_days):.4f})"
            )

        print(
            f"[PASS] all {len(where_rows)} WHERE-subquery rows have "
            f"resolution time strictly greater than Python average"
        )

        # 3) Above-average set must be a proper subset of resolved tickets.
        resolved_count = len(durations_by_id)
        assert len(where_ids) < resolved_count, (
            f"Returned {len(where_ids)} rows but resolved total is {resolved_count}; "
            "not all resolved tickets can be strictly above average"
        )
        print(
            f"[PASS] returned count {len(where_ids)} < resolved count {resolved_count}"
        )

        # 4) CTE variant returns the same ticket_id set (and same order).
        cursor.execute(cte_sql)
        cte_rows = cursor.fetchall()
        cte_ids = [int(row[0]) for row in cte_rows]

        assert set(cte_ids) == set(where_ids), (
            f"Variant ticket_id sets differ: WHERE={sorted(where_ids)} "
            f"CTE={sorted(cte_ids)}"
        )
        assert cte_ids == where_ids, (
            f"Variant order differs: WHERE={where_ids} CTE={cte_ids}"
        )
        print(
            f"[PASS] WHERE-subquery and CTE variants return identical "
            f"ticket_ids in the same order: {where_ids}"
        )
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
