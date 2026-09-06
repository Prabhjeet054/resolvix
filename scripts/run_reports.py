"""
Execute the group-function report queries and print formatted tables.

Reads SELECT statements from db/08_reports_group_functions.sql and pretty-prints
result sets for report screenshots (manual column formatting; no extra deps).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

REPORT_SQL = (
    Path(__file__).resolve().parents[1] / "db" / "08_reports_group_functions.sql"
)

QUERY_TITLES = [
    "Query A — Tickets per agent (avg resolution days)",
    "Query B — Tickets per category × priority",
]


def _stringify(value) -> str:
    """Convert a cell value to a printable string."""
    if value is None:
        return ""
    if hasattr(value, "read"):
        return str(value.read())
    return str(value)


def _print_table(columns: list[str], rows: list[tuple]) -> None:
    """Pretty-print a result set as an aligned ASCII table."""
    str_rows = [[_stringify(cell) for cell in row] for row in rows]
    widths = [len(col) for col in columns]
    for row in str_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def fmt_row(values: list[str]) -> str:
        return "| " + " | ".join(
            value.ljust(widths[i]) for i, value in enumerate(values)
        ) + " |"

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    print(separator)
    print(fmt_row(columns))
    print(separator)
    if not str_rows:
        empty = ["(no rows)"] + [""] * (len(columns) - 1)
        print(fmt_row(empty))
    else:
        for row in str_rows:
            print(fmt_row(row))
    print(separator)
    print(f"({len(str_rows)} row(s))\n")


def run_reports(sql_path: Path = REPORT_SQL) -> None:
    """Execute both report queries and print formatted tables."""
    statements = split_sql_statements(sql_path.read_text(encoding="utf-8"))
    if len(statements) != 2:
        raise RuntimeError(
            f"Expected 2 SELECT statements in {sql_path}, found {len(statements)}"
        )

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        for title, sql in zip(QUERY_TITLES, statements):
            print("=" * 72)
            print(title)
            print("=" * 72)
            cursor.execute(sql)
            columns = [col[0].lower() for col in cursor.description]
            rows = cursor.fetchall()
            _print_table(columns, rows)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    run_reports()
