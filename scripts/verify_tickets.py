"""
Verify Tickets table DDL: foreign keys, VECTOR column, and constraint enforcement.

Checks:
1. All three FKs on TICKETS reference the correct parent table/column
2. DESCRIPTION_EMBEDDING has data type VECTOR
3. ck_tickets_resolved_after_created rejects resolved_date < created_date
4. fk_tickets_customer rejects a non-existent customer_id
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import oracledb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection


EXPECTED_FKS = {
    "FK_TICKETS_CUSTOMER": ("CUSTOMERS", "CUSTOMER_ID"),
    "FK_TICKETS_AGENT": ("AGENTS", "AGENT_ID"),
    "FK_TICKETS_CATEGORY": ("CATEGORIES", "CATEGORY_ID"),
}


def verify_foreign_keys(cursor) -> None:
    """List Tickets FKs and confirm parent table/column references."""
    query = """
        SELECT
            uc.constraint_name,
            ucc.column_name AS child_column,
            ruc.table_name AS parent_table,
            rucc.column_name AS parent_column
        FROM user_constraints uc
        JOIN user_cons_columns ucc
          ON uc.constraint_name = ucc.constraint_name
         AND uc.owner = ucc.owner
        JOIN user_constraints ruc
          ON uc.r_constraint_name = ruc.constraint_name
         AND uc.r_owner = ruc.owner
        JOIN user_cons_columns rucc
          ON ruc.constraint_name = rucc.constraint_name
         AND ruc.owner = rucc.owner
         AND ucc.position = rucc.position
        WHERE uc.table_name = 'TICKETS'
          AND uc.constraint_type = 'R'
        ORDER BY uc.constraint_name
    """
    cursor.execute(query)
    rows = cursor.fetchall()

    print("1) Foreign keys on TICKETS:")
    found = {}
    for constraint_name, child_column, parent_table, parent_column in rows:
        print(
            f"   {constraint_name}: {child_column} -> "
            f"{parent_table}.{parent_column}"
        )
        found[constraint_name] = (parent_table, parent_column)

    missing = set(EXPECTED_FKS) - set(found)
    if missing:
        raise AssertionError(f"Missing FK constraints: {sorted(missing)}")

    for name, expected in EXPECTED_FKS.items():
        actual = found[name]
        if actual != expected:
            raise AssertionError(
                f"{name} expected parent {expected}, got {actual}"
            )

    print("   OK: all 3 FKs reference the correct parent table/column.\n")


def verify_vector_column(cursor) -> None:
    """Confirm DESCRIPTION_EMBEDDING is typed as VECTOR."""
    cursor.execute(
        """
        SELECT data_type
        FROM user_tab_columns
        WHERE table_name = 'TICKETS'
          AND column_name = 'DESCRIPTION_EMBEDDING'
        """
    )
    row = cursor.fetchone()
    if row is None:
        raise AssertionError("DESCRIPTION_EMBEDDING column not found on TICKETS.")

    data_type = row[0]
    print(f"2) DESCRIPTION_EMBEDDING data_type: {data_type}")
    if "VECTOR" not in str(data_type).upper():
        raise AssertionError(
            f"Expected VECTOR data type, got {data_type!r}"
        )
    print("   OK: column is VECTOR.\n")


def seed_parent_rows(cursor) -> None:
    """Insert minimal parent rows needed for valid ticket inserts."""
    cursor.execute(
        """
        MERGE INTO customers c
        USING (SELECT 1 AS customer_id FROM dual) s
        ON (c.customer_id = s.customer_id)
        WHEN NOT MATCHED THEN
          INSERT (customer_id, customer_name, email, region)
          VALUES (1, 'Verify Customer', 'verify.customer@example.com', 'IN')
        """
    )
    cursor.execute(
        """
        MERGE INTO categories c
        USING (SELECT 1 AS category_id FROM dual) s
        ON (c.category_id = s.category_id)
        WHEN NOT MATCHED THEN
          INSERT (category_id, category_name, description)
          VALUES (1, 'Verify Category', 'Seed category for ticket verification')
        """
    )


def verify_resolved_date_check(cursor) -> None:
    """Attempt an INSERT that violates ck_tickets_resolved_after_created."""
    print("3) Violating ck_tickets_resolved_after_created:")
    try:
        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, category_id, description,
                language_code, created_date, resolved_date
            ) VALUES (
                9001, 1, 1, 'Resolved-before-created should fail',
                'en',
                TIMESTAMP '2026-01-10 10:00:00',
                TIMESTAMP '2026-01-09 09:00:00'
            )
            """
        )
        raise AssertionError(
            "Expected ORA error for resolved_date < created_date, but INSERT succeeded."
        )
    except oracledb.Error as exc:
        error_obj, = exc.args
        print(f"   Caught expected error: ORA-{error_obj.code}: {error_obj.message}")
        print("   OK: resolved_date check blocked the insert.\n")


def verify_customer_fk(cursor) -> None:
    """Attempt an INSERT with a non-existent customer_id."""
    print("4) Violating fk_tickets_customer:")
    try:
        cursor.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, category_id, description, language_code
            ) VALUES (
                9002, 999999, 1, 'Missing customer should fail', 'en'
            )
            """
        )
        raise AssertionError(
            "Expected ORA FK error for missing customer_id, but INSERT succeeded."
        )
    except oracledb.Error as exc:
        error_obj, = exc.args
        print(f"   Caught expected error: ORA-{error_obj.code}: {error_obj.message}")
        print("   OK: customer FK blocked the insert.\n")


def main() -> None:
    """Run all Tickets verification checks."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        verify_foreign_keys(cursor)
        verify_vector_column(cursor)

        seed_parent_rows(cursor)
        conn.commit()

        verify_resolved_date_check(cursor)
        conn.rollback()

        verify_customer_fk(cursor)
        conn.rollback()

        print("All Tickets verification checks passed.")
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
