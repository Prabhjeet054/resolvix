"""
Ingest multilingual seed tickets into Oracle with embeddings.

Loads data/tickets_seed.csv, assigns customers/agents/categories, generates
384-dim FLOAT32 embeddings, and inserts into tickets in a single transaction.

Idempotency: each run DELETE FROM tickets before inserting the 20 seed rows.
That avoids silently doubling the table on re-runs (chosen over a description
UNIQUE constraint so demo/test tickets can still share similar wording).

VECTOR binding: python-oracledb accepts array.array('f', ...) for FLOAT32
vectors, or NumPy ndarrays via an input type handler that converts to
array.array and binds with oracledb.DB_TYPE_VECTOR (see Oracle vector docs).
"""

from __future__ import annotations

import array
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import oracledb
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from embeddings.generate import generate_embedding

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "tickets_seed.csv"

CATEGORY_TAGS = {
    "Billing": ["invoice", "payment", "subscription"],
    "Technical": ["crash", "bug", "performance"],
    "Account": ["profile", "permissions", "settings"],
    "Refund": ["refund", "chargeback", "proration"],
    "Login": ["password", "mfa", "access"],
    "General": ["howto", "question", "info"],
}


def numpy_converter_in(value: np.ndarray) -> array.array:
    """Convert a NumPy ndarray to array.array for Oracle VECTOR binds."""
    if value.dtype == np.float64:
        dtype = "d"
    elif value.dtype == np.float32:
        dtype = "f"
    elif value.dtype == np.uint8:
        dtype = "B"
    else:
        dtype = "b"
    return array.array(dtype, value)


def input_type_handler(cursor, value, arraysize):
    """Bind NumPy embeddings as Oracle VECTOR via DB_TYPE_VECTOR."""
    if isinstance(value, np.ndarray):
        return cursor.var(
            oracledb.DB_TYPE_VECTOR,
            arraysize=arraysize,
            inconverter=numpy_converter_in,
        )
    return None


def _load_reference_ids(cursor) -> tuple[list[int], list[int], dict[str, int]]:
    """Fetch seeded customer, agent, and category IDs."""
    cursor.execute("SELECT customer_id FROM customers ORDER BY customer_id")
    customer_ids = [int(row[0]) for row in cursor.fetchall()]
    if len(customer_ids) != 10:
        raise RuntimeError(
            f"Expected 10 seeded customers, found {len(customer_ids)}. "
            "Run scripts/seed_reference_data.py first."
        )

    cursor.execute("SELECT agent_id FROM agents ORDER BY agent_id")
    agent_ids = [int(row[0]) for row in cursor.fetchall()]
    if len(agent_ids) != 5:
        raise RuntimeError(
            f"Expected 5 seeded agents, found {len(agent_ids)}. "
            "Run scripts/seed_reference_data.py first."
        )

    cursor.execute(
        "SELECT category_name, category_id FROM categories ORDER BY category_id"
    )
    category_map = {str(name): int(cid) for name, cid in cursor.fetchall()}
    if len(category_map) != 6:
        raise RuntimeError(
            f"Expected 6 seeded categories, found {len(category_map)}. "
            "Run scripts/seed_reference_data.py first."
        )

    return customer_ids, agent_ids, category_map


def _build_metadata(category_name: str) -> dict:
    """Build JSON metadata with 1-3 category tags and attachment_count 0-2."""
    pool = CATEGORY_TAGS.get(category_name, ["general"])
    tag_count = random.randint(1, min(3, len(pool)))
    tags = random.sample(pool, tag_count)
    return {
        "tags": tags,
        "attachment_count": random.randint(0, 2),
    }


def _assign_statuses(row_count: int) -> list[str]:
    """Mostly RESOLVED/CLOSED; 2-3 OPEN for unresolved demos."""
    open_count = random.choice([2, 3])
    statuses = ["OPEN"] * open_count
    remaining = row_count - open_count
    # Prefer RESOLVED slightly over CLOSED for historical tickets.
    resolved_count = (remaining + 1) // 2
    closed_count = remaining - resolved_count
    statuses.extend(["RESOLVED"] * resolved_count)
    statuses.extend(["CLOSED"] * closed_count)
    random.shuffle(statuses)
    return statuses


def _random_created_date(now: datetime) -> datetime:
    """Random created_date within the last 90 days."""
    offset_seconds = random.randint(0, 90 * 24 * 60 * 60)
    return now - timedelta(seconds=offset_seconds)


def _random_resolved_date(created_date: datetime) -> datetime:
    """Random resolved_date between created_date and created_date + 5 days."""
    offset_seconds = random.randint(0, 5 * 24 * 60 * 60)
    return created_date + timedelta(seconds=offset_seconds)


def ingest_tickets(csv_path: Path | str = CSV_PATH, seed: int | None = 42) -> None:
    """Load CSV tickets, embed descriptions, and insert in one transaction."""
    if seed is not None:
        random.seed(seed)

    df = pd.read_csv(csv_path)
    if len(df) != 20:
        raise ValueError(f"Expected 20 seed rows, got {len(df)}")
    print(f"Loaded {len(df)} tickets from {csv_path}")

    statuses = _assign_statuses(len(df))
    now = datetime.now()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        # Enable NumPy -> VECTOR binding via oracledb.DB_TYPE_VECTOR.
        conn.inputtypehandler = input_type_handler
        cursor = conn.cursor()

        customer_ids, agent_ids, category_map = _load_reference_ids(cursor)

        # Clear existing tickets so re-running ingest replaces the seed set
        # instead of appending duplicates (see module docstring).
        cursor.execute("DELETE FROM tickets")
        print(f"Cleared existing tickets ({cursor.rowcount} row(s) deleted).")

        # Leave ~20% unassigned (4 of 20) to simulate open queues.
        unassigned_indexes = set(random.sample(range(len(df)), k=4))

        insert_sql = """
            INSERT INTO tickets (
                customer_id,
                agent_id,
                category_id,
                description,
                language_code,
                ticket_status,
                priority,
                created_date,
                resolved_date,
                resolution,
                metadata,
                description_embedding
            ) VALUES (
                :customer_id,
                :agent_id,
                :category_id,
                :description,
                :language_code,
                :ticket_status,
                :priority,
                :created_date,
                :resolved_date,
                :resolution,
                :metadata,
                :description_embedding
            )
        """

        for index, row in df.iterrows():
            row_number = int(index) + 1
            try:
                category_name = str(row["category_name"])
                if category_name not in category_map:
                    raise KeyError(
                        f"category_name {category_name!r} not found in Categories"
                    )

                customer_id = customer_ids[int(index) % len(customer_ids)]
                agent_id = (
                    None
                    if int(index) in unassigned_indexes
                    else agent_ids[int(index) % len(agent_ids)]
                )
                category_id = category_map[category_name]

                ticket_status = statuses[int(index)]
                created_date = _random_created_date(now)

                if ticket_status == "OPEN":
                    resolution = None
                    resolved_date = None
                else:
                    resolution = (
                        None if pd.isna(row["resolution"]) else str(row["resolution"])
                    )
                    resolved_date = _random_resolved_date(created_date)

                metadata = _build_metadata(category_name)
                embedding = generate_embedding(str(row["description"]))

                cursor.execute(
                    insert_sql,
                    {
                        "customer_id": customer_id,
                        "agent_id": agent_id,
                        "category_id": category_id,
                        "description": str(row["description"]),
                        "language_code": str(row["language_code"]),
                        "ticket_status": ticket_status,
                        "priority": str(row["priority"]),
                        "created_date": created_date,
                        "resolved_date": resolved_date,
                        "resolution": resolution,
                        "metadata": json.dumps(metadata),
                        "description_embedding": embedding,
                    },
                )
                print(f"Inserted {row_number}/20...")
            except Exception as row_error:
                conn.rollback()
                print(
                    f"FAILED at row {row_number}/20 "
                    f"(language={row.get('language_code')}, "
                    f"category={row.get('category_name')}): {row_error}"
                )
                raise

        conn.commit()
        print("Committed all 20 ticket inserts successfully.")
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
    ingest_tickets()
