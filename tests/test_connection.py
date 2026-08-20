"""Integration-style smoke test for Oracle connectivity.

This test:
1) Loads credentials from `.env` using `python-dotenv`
2) Connects using `db/connection.py:get_connection()`
3) Runs `SELECT 1 FROM dual`
4) Runs `SELECT banner FROM v$version ...` and asserts it contains "23"
5) Closes connection/cursor cleanly in a `finally` block
"""

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection  # noqa: E402


def test_oracle_connection_and_version():
    """Connect via get_connection(), probe DUAL, and print the Oracle 23 banner."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

    assert os.getenv("ORACLE_USER"), "ORACLE_USER is missing from .env"
    assert os.getenv("ORACLE_PASSWORD"), "ORACLE_PASSWORD is missing from .env"
    assert os.getenv("ORACLE_DSN"), "ORACLE_DSN is missing from .env"

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM dual")
        dual_row = cursor.fetchone()
        assert dual_row is not None, "SELECT 1 FROM dual returned no rows"
        assert dual_row[0] == 1, f"Expected 1 from dual, got {dual_row[0]!r}"

        cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        version_row = cursor.fetchone()
        assert version_row is not None, "v$version returned no rows"
        banner = version_row[0]

        print(f"Oracle version: {banner}")
        assert "23" in str(banner), f"Expected Oracle 23 in banner, got {banner!r}"
    finally:
        # Close cleanly even when assertions fail.
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
