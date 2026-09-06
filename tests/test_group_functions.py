"""Verify group-function report queries against manually recomputed values."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

REPORT_SQL = PROJECT_ROOT / "db" / "08_reports_group_functions.sql"


def _load_report_queries() -> tuple[str, str]:
    """Return (Query A, Query B) SQL from the reports file."""
    statements = split_sql_statements(REPORT_SQL.read_text(encoding="utf-8"))
    assert len(statements) == 2, f"Expected 2 queries, found {len(statements)}"
    return statements[0], statements[1]


def test_group_function_reports():
    """Cross-check Query A averages/counts and Query B category totals."""
    query_a, query_b = _load_report_queries()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # --- Query A ---
        cursor.execute(query_a)
        agent_rows = cursor.fetchall()
        # columns: agent_name, ticket_count, avg_resolution_days
        agent_stats = {
            str(name): (int(count), None if avg is None else float(avg))
            for name, count, avg in agent_rows
        }
        assert agent_stats, "Query A returned no rows"

        # Pick one assigned agent (not Unassigned) that has resolved tickets.
        cursor.execute(
            """
            SELECT agent_id, agent_name
            FROM agents
            WHERE agent_id IN (
                SELECT agent_id
                FROM tickets
                WHERE resolved_date IS NOT NULL
                  AND agent_id IS NOT NULL
            )
            FETCH FIRST 1 ROWS ONLY
            """
        )
        agent_row = cursor.fetchone()
        assert agent_row is not None, "No assigned agent with resolved tickets found"
        agent_id, agent_name = int(agent_row[0]), str(agent_row[1])
        assert agent_name in agent_stats, (
            f"Agent {agent_name!r} missing from Query A results: {sorted(agent_stats)}"
        )

        cursor.execute(
            """
            SELECT
                CAST(resolved_date AS DATE) - CAST(created_date AS DATE) AS day_diff
            FROM tickets
            WHERE agent_id = :1
              AND resolved_date IS NOT NULL
            """,
            [agent_id],
        )
        day_diffs = [float(row[0]) for row in cursor.fetchall()]
        assert day_diffs, f"No resolved tickets for agent_id={agent_id}"

        # Recompute Query A's AVG(... ) ROUND(..., 2) in Python from the same diffs.
        python_avg = round(sum(day_diffs) / len(day_diffs), 2)
        query_count, query_avg = agent_stats[agent_name]

        assert query_count == len(day_diffs), (
            f"{agent_name}: Query A count {query_count} != raw count {len(day_diffs)}"
        )
        assert query_avg is not None
        assert abs(query_avg - python_avg) <= 0.01, (
            f"{agent_name}: Query A avg {query_avg} != Python avg {python_avg}"
        )
        print(
            f"[PASS] Query A avg check for agent={agent_name!r}: "
            f"query_avg={query_avg}, python_avg={python_avg}, "
            f"ticket_count={query_count}"
        )

        cursor.execute(
            "SELECT COUNT(*) FROM tickets WHERE resolved_date IS NOT NULL"
        )
        resolved_total = int(cursor.fetchone()[0])
        sum_agent_counts = sum(count for count, _ in agent_stats.values())
        assert sum_agent_counts == resolved_total, (
            f"Sum of Query A ticket_count ({sum_agent_counts}) != "
            f"resolved tickets ({resolved_total})"
        )
        print(
            f"[PASS] Query A sum(ticket_count)={sum_agent_counts} "
            f"equals resolved tickets={resolved_total}"
        )

        # --- Query B ---
        cursor.execute(query_b)
        category_rows = cursor.fetchall()
        sum_cnt = sum(int(cnt) for _, _, cnt in category_rows)

        cursor.execute("SELECT COUNT(*) FROM tickets")
        tickets_total = int(cursor.fetchone()[0])
        assert sum_cnt == tickets_total, (
            f"Sum of Query B cnt ({sum_cnt}) != tickets total ({tickets_total})"
        )
        print(
            f"[PASS] Query B sum(cnt)={sum_cnt} equals tickets total={tickets_total}"
        )
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
