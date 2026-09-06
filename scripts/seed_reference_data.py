"""
Seed reference data: customers, agents, and categories.

Uses bind variables (parameterized queries) rather than string formatting for
all inserts — good practice even for seed scripts, and useful to demonstrate
in the project report as a SQL-injection-safe pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

import oracledb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.connection import get_connection


# Realistic Indian-context names; regions roughly balanced across IN/US/UK.
CUSTOMERS = [
    (1, "Priya Sharma", "priya.sharma@example.in", "+91-98765-43210", "IN"),
    (2, "Arjun Patel", "arjun.patel@example.in", "+91-99887-76655", "IN"),
    (3, "Ananya Reddy", "ananya.reddy@example.in", "+91-91234-56789", "IN"),
    (4, "Rohan Iyer", "rohan.iyer@example.in", "+91-90123-45678", "IN"),
    (5, "Meera Kapoor", "meera.kapoor@example.us", "+1-415-555-0142", "US"),
    (6, "Vikram Nair", "vikram.nair@example.us", "+1-646-555-0198", "US"),
    (7, "Sneha Joshi", "sneha.joshi@example.us", "+1-312-555-0177", "US"),
    (8, "Karan Malhotra", "karan.malhotra@example.uk", "+44-20-7946-0958", "UK"),
    (9, "Divya Krishnan", "divya.krishnan@example.uk", "+44-161-555-0124", "UK"),
    (10, "Aditya Desai", "aditya.desai@example.uk", "+44-131-555-0186", "UK"),
]

AGENTS = [
    (1, "Neha Gupta", "neha.gupta@resolvix.support", "Technical", 1),
    (2, "Amit Verma", "amit.verma@resolvix.support", "Billing", 1),
    (3, "Fatima Khan", "fatima.khan@resolvix.support", "General", 1),
    (4, "Suresh Pillai", "suresh.pillai@resolvix.support", "Technical", 1),
    (5, "Lakshmi Rao", "lakshmi.rao@resolvix.support", "Billing", 1),
]

CATEGORIES = [
    (1, "Billing", "Questions about invoices, charges, and payment methods"),
    (2, "Technical", "Product defects, crashes, and integration issues"),
    (3, "Account", "Profile updates, access rights, and account settings"),
    (4, "Refund", "Refund requests and chargeback follow-ups"),
    (5, "Login", "Sign-in failures, password resets, and MFA problems"),
    (6, "General", "Miscellaneous inquiries that do not fit other categories"),
]


def seed_reference_data() -> None:
    """Insert customers, agents, and categories in one atomic transaction."""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.executemany(
            """
            INSERT INTO customers (
                customer_id, customer_name, email, phone, region
            ) VALUES (
                :1, :2, :3, :4, :5
            )
            """,
            CUSTOMERS,
        )

        cursor.executemany(
            """
            INSERT INTO agents (
                agent_id, agent_name, email, department, is_active
            ) VALUES (
                :1, :2, :3, :4, :5
            )
            """,
            AGENTS,
        )

        cursor.executemany(
            """
            INSERT INTO categories (
                category_id, category_name, description
            ) VALUES (
                :1, :2, :3
            )
            """,
            CATEGORIES,
        )

        conn.commit()
        print(
            f"Inserted {len(CUSTOMERS)} customers, "
            f"{len(AGENTS)} agents, "
            f"{len(CATEGORIES)} categories."
        )
    except oracledb.IntegrityError as exc:
        if conn is not None:
            conn.rollback()
        error_obj, = exc.args
        print(
            "Seed failed cleanly due to unique-constraint violation "
            f"(ORA-{error_obj.code}): {error_obj.message}"
        )
        print("Rolled back entire transaction; no duplicate rows were inserted.")
        raise SystemExit(1) from None
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"Seed failed; rolled back entire transaction: {exc}")
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    seed_reference_data()
