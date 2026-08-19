"""
Utility script to execute all SQL DDL files in /db in alphabetical order.

Reads .sql files matching the pattern NN_*.sql and runs them sequentially
against the Oracle database.
"""

import os
import sys
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection


DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db")


def run_all_ddl() -> None:
    """Execute all .sql scripts in the db/ directory in sorted order."""
    sql_files = sorted(glob.glob(os.path.join(DB_DIR, "*.sql")))

    if not sql_files:
        print("No .sql files found in db/ directory.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    for filepath in sql_files:
        filename = os.path.basename(filepath)
        print(f"Running {filename}...")

        with open(filepath, "r") as f:
            sql = f.read().strip().rstrip(";")

        try:
            cursor.execute(sql)
            conn.commit()
            print(f"  ✓ {filename} executed successfully.")
        except Exception as e:
            conn.rollback()
            print(f"  ✗ {filename} failed: {e}")

    cursor.close()
    conn.close()
    print("\nAll DDL scripts processed.")


if __name__ == "__main__":
    run_all_ddl()
