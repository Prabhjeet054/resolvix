"""
Run a focused subset of DDL files and verify explicit constraint names.

This script:
1. Connects using db.connection.get_connection()
2. Executes 01_customers.sql, 02_agents.sql, and 03_categories.sql in order
3. Splits SQL files on semicolons while preserving PL/SQL blocks terminated by /
4. Queries USER_CONSTRAINTS and USER_CONS_COLUMNS to print constraint metadata
5. Confirms no matching constraint uses a SYS_C auto-generated name
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection


DB_DIR = Path(__file__).resolve().parents[1] / "db"
DDL_FILES = [
    DB_DIR / "01_customers.sql",
    DB_DIR / "02_agents.sql",
    DB_DIR / "03_categories.sql",
]
TARGET_TABLES = ("CUSTOMERS", "AGENTS", "CATEGORIES")


def split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL text into executable statements.

    Semicolons terminate normal SQL statements, but semicolons inside PL/SQL
    blocks are preserved until a standalone slash line is encountered.
    """
    statements: list[str] = []
    current_lines: list[str] = []
    in_plsql_block = False

    for raw_line in sql_text.splitlines():
        stripped = raw_line.strip()

        if not current_lines and (not stripped or stripped.startswith("--")):
            continue

        if stripped.upper().startswith(("BEGIN", "DECLARE")):
            in_plsql_block = True

        if stripped == "/" and in_plsql_block:
            statement = "\n".join(current_lines).strip()
            if statement:
                statements.append(statement)
            current_lines = []
            in_plsql_block = False
            continue

        current_lines.append(raw_line)

        if not in_plsql_block and stripped.endswith(";"):
            statement = "\n".join(current_lines).strip()
            if statement.endswith(";"):
                statement = statement[:-1].rstrip()
            if statement:
                statements.append(statement)
            current_lines = []

    trailing = "\n".join(current_lines).strip()
    if trailing:
        statements.append(trailing)

    return statements


def execute_sql_file(cursor, sql_file: Path) -> None:
    """Execute every statement in a SQL file in order."""
    sql_text = sql_file.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_text)

    print(f"Running {sql_file.name} ({len(statements)} statement(s))...")
    for index, statement in enumerate(statements, start=1):
        cursor.execute(statement)
        print(f"  Executed statement {index}")


def fetch_constraint_rows(cursor) -> list[tuple[str, str, str, str]]:
    """Return constraint rows for the target tables."""
    query = """
        SELECT
            uc.table_name,
            uc.constraint_name,
            uc.constraint_type,
            LISTAGG(ucc.column_name, ', ') WITHIN GROUP (ORDER BY ucc.position) AS columns
        FROM user_constraints uc
        JOIN user_cons_columns ucc
          ON uc.constraint_name = ucc.constraint_name
        WHERE uc.table_name IN ('CUSTOMERS', 'AGENTS', 'CATEGORIES')
          AND uc.constraint_type IN ('P', 'U', 'C')
        GROUP BY uc.table_name, uc.constraint_name, uc.constraint_type
        ORDER BY
            CASE uc.table_name
                WHEN 'CUSTOMERS' THEN 1
                WHEN 'AGENTS' THEN 2
                WHEN 'CATEGORIES' THEN 3
                ELSE 99
            END,
            uc.constraint_type,
            uc.constraint_name
    """
    cursor.execute(query)
    return cursor.fetchall()


def verify_constraint_names(rows: list[tuple[str, str, str, str]]) -> None:
    """Validate that no retrieved constraint uses a SYS_C auto-generated name."""
    if not rows:
        raise AssertionError("No constraints found for CUSTOMERS, AGENTS, or CATEGORIES.")

    print("\nConstraint verification:")
    seen_tables = set()
    for table_name, constraint_name, constraint_type, columns in rows:
        seen_tables.add(table_name)
        print(f"{table_name}: {constraint_name} | {constraint_type} | {columns}")
        if constraint_name.startswith("SYS_C"):
            raise AssertionError(
                f"Found auto-generated constraint name {constraint_name} on {table_name}."
            )

    missing_tables = set(TARGET_TABLES) - seen_tables
    if missing_tables:
        raise AssertionError(f"Missing constraint metadata for: {sorted(missing_tables)}")

    print("\nVerified: all reported constraints use explicit names, not SYS_C-prefixed names.")


def run_ddl_subset() -> None:
    """Execute the subset DDL files and verify constraint names."""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        for sql_file in DDL_FILES:
            execute_sql_file(cursor, sql_file)

        conn.commit()
        rows = fetch_constraint_rows(cursor)
        verify_constraint_names(rows)
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
    run_ddl_subset()
