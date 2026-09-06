"""
Before/after EXPLAIN PLAN demo for Tickets status filtering.

Drops the status-related indexes, captures the plan for:
  SELECT * FROM Tickets WHERE ticket_status = 'OPEN'
then recreates indexes from db/07_indexes.sql and captures the plan again.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from scripts.run_ddl_subset import execute_sql_file

DB_DIR = Path(__file__).resolve().parents[1] / "db"
INDEX_DDL = DB_DIR / "07_indexes.sql"

INDEX_NAMES = (
    "IDX_TICKETS_STATUS",
    "IDX_TICKETS_CREATED_DATE",
    "IDX_TICKETS_STATUS_CREATED",
)

DEMO_SQL = "SELECT * FROM tickets WHERE ticket_status = 'OPEN'"


def _drop_indexes(cursor) -> None:
    """Drop demo indexes if present (ignore ORA-01418: index does not exist)."""
    for name in INDEX_NAMES:
        try:
            cursor.execute(f"DROP INDEX {name}")
            print(f"Dropped index {name}")
        except Exception as exc:
            message = str(exc)
            if "ORA-01418" in message or "ORA-1418" in message:
                print(f"Index {name} not present (skip drop)")
            else:
                raise


def _create_indexes(cursor) -> None:
    """Create indexes defined in db/07_indexes.sql."""
    execute_sql_file(cursor, INDEX_DDL)


def _ensure_plan_table(cursor) -> None:
    """Create PLAN_TABLE if this schema does not already have one."""
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM user_tables
        WHERE table_name = 'PLAN_TABLE'
        """
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            """
            CREATE TABLE plan_table (
                statement_id      VARCHAR2(30),
                plan_id           NUMBER,
                timestamp         DATE,
                remarks           VARCHAR2(4000),
                operation         VARCHAR2(30),
                options           VARCHAR2(255),
                object_node       VARCHAR2(128),
                object_owner      VARCHAR2(128),
                object_name       VARCHAR2(128),
                object_alias      VARCHAR2(261),
                object_instance   NUMBER,
                object_type       VARCHAR2(30),
                optimizer         VARCHAR2(255),
                search_columns    NUMBER,
                id                NUMBER,
                parent_id         NUMBER,
                depth             NUMBER,
                position          NUMBER,
                cost              NUMBER,
                cardinality       NUMBER,
                bytes             NUMBER,
                other_tag         VARCHAR2(255),
                partition_start   VARCHAR2(255),
                partition_stop    VARCHAR2(255),
                partition_id      NUMBER,
                other             LONG,
                distribution      VARCHAR2(30),
                cpu_cost          NUMBER,
                io_cost           NUMBER,
                temp_space        NUMBER,
                access_predicates VARCHAR2(4000),
                filter_predicates VARCHAR2(4000),
                projection        VARCHAR2(4000),
                time              NUMBER,
                qblock_name       VARCHAR2(128),
                other_xml         CLOB
            )
            """
        )
        print("Created PLAN_TABLE in current schema.")


def _capture_plan(label: str, statement_id: str) -> str:
    """Open a fresh connection, EXPLAIN PLAN, return DBMS_XPLAN text."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        _ensure_plan_table(cursor)
        cursor.execute(
            "DELETE FROM plan_table WHERE statement_id = :1 OR statement_id IS NULL",
            [statement_id],
        )
        cursor.execute(
            f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {DEMO_SQL}"
        )
        cursor.execute(
            """
            SELECT * FROM TABLE(
                DBMS_XPLAN.DISPLAY(
                    'PLAN_TABLE',
                    :statement_id,
                    'TYPICAL'
                )
            )
            """,
            {"statement_id": statement_id},
        )
        lines = [row[0] for row in cursor.fetchall()]
        plan_text = "\n".join(lines)
        print(f"\n===== {label} =====")
        print(plan_text)
        conn.commit()
        return plan_text
    finally:
        cursor.close()
        conn.close()


def _summarize(before: str, after: str) -> None:
    """Print a short before/after access-path comparison."""
    before_upper = before.upper()
    after_upper = after.upper()

    before_fts = "TABLE ACCESS FULL" in before_upper
    after_index = any(
        token in after_upper
        for token in (
            "INDEX RANGE SCAN",
            "INDEX UNIQUE SCAN",
            "INDEX FULL SCAN",
            "INDEX SKIP SCAN",
            "TABLE ACCESS BY INDEX ROWID",
        )
    )
    after_fts = "TABLE ACCESS FULL" in after_upper

    print("\n===== BEFORE / AFTER COMPARISON =====")
    print(f"Query: {DEMO_SQL}")
    print(
        f"Before: {'FULL TABLE SCAN detected' if before_fts else 'No FULL TABLE SCAN token found'}"
    )
    print(
        f"After:  {'Index-based access path detected' if after_index else 'No index access path detected'}"
        + (" (FULL TABLE SCAN still present)" if after_fts else "")
    )

    if before_fts and after_index and not after_fts:
        print(
            "Result: Plan changed from full table scan to an index-based access path."
        )
    elif before_fts and after_index:
        print(
            "Result: Index access appears in the after plan, but a full scan step "
            "is still listed — inspect DBMS_XPLAN output above."
        )
    elif before_fts and after_fts:
        print(
            "Result: Still a full table scan after indexing (common on tiny tables "
            "where Oracle prefers FTS over index I/O). Plans are printed above for the report."
        )
    else:
        print("Result: Compare the printed plans above for optimizer differences.")


def main() -> None:
    """Drop indexes → explain → create indexes → explain → compare."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        print("Step 1: Drop existing ticket indexes (BEFORE plan).")
        _drop_indexes(cursor)
        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    before_plan = _capture_plan("BEFORE INDEXES", "BEFORE_IDX")

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        print("\nStep 2: Create indexes from db/07_indexes.sql (AFTER plan).")
        _create_indexes(cursor)
        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    after_plan = _capture_plan("AFTER INDEXES", "AFTER_IDX")
    _summarize(before_plan, after_plan)


if __name__ == "__main__":
    main()
