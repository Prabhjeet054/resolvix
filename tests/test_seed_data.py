"""Verify seeded reference data counts, region mix, and unique emails."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection


def test_seed_reference_data_counts_and_uniqueness():
    """Assert seeded row counts, print region breakdown, and check email uniqueness."""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM customers")
        customer_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM agents")
        agent_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM categories")
        category_count = cursor.fetchone()[0]

        assert customer_count == 10, f"Expected 10 customers, got {customer_count}"
        assert agent_count == 5, f"Expected 5 agents, got {agent_count}"
        assert category_count == 6, f"Expected 6 categories, got {category_count}"
        print(
            f"Counts OK: customers={customer_count}, "
            f"agents={agent_count}, categories={category_count}"
        )

        cursor.execute(
            """
            SELECT region, COUNT(*) AS cnt
            FROM customers
            GROUP BY region
            ORDER BY region
            """
        )
        region_rows = cursor.fetchall()
        print("Customer region breakdown:")
        for region, cnt in region_rows:
            print(f"  {region}: {cnt}")

        cursor.execute(
            """
            SELECT email, COUNT(*) AS cnt
            FROM customers
            GROUP BY email
            HAVING COUNT(*) > 1
            """
        )
        customer_dupes = cursor.fetchall()
        assert customer_dupes == [], f"Duplicate customer emails: {customer_dupes}"
        print("No duplicate emails in customers.")

        cursor.execute(
            """
            SELECT email, COUNT(*) AS cnt
            FROM agents
            GROUP BY email
            HAVING COUNT(*) > 1
            """
        )
        agent_dupes = cursor.fetchall()
        assert agent_dupes == [], f"Duplicate agent emails: {agent_dupes}"
        print("No duplicate emails in agents.")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
