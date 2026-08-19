"""
Data ingestion script.

Loads tickets from data/tickets_seed.csv, generates embeddings for each
ticket's subject + description, and inserts them into the Oracle database.
"""

import os
import sys
import array

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from embeddings.generate import generate_embeddings_batch


CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tickets_seed.csv")


def ingest_tickets(csv_path: str = CSV_PATH) -> None:
    """Load ticket data from CSV, generate embeddings, and insert into Oracle.

    Args:
        csv_path: Path to the seed CSV file.
    """
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} tickets from {csv_path}")

    texts = (df["subject"] + " " + df["description"]).tolist()
    embeddings = generate_embeddings_batch(texts)
    print("Embeddings generated.")

    conn = get_connection()
    cursor = conn.cursor()

    insert_sql = """
        INSERT INTO tickets (customer_id, agent_id, category_id, subject,
                             description, status, priority, language, embedding)
        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
    """

    try:
        for i, row in df.iterrows():
            embedding_array = array.array("f", embeddings[i])
            cursor.execute(insert_sql, [
                int(row["customer_id"]),
                int(row["agent_id"]) if pd.notna(row.get("agent_id")) else None,
                int(row["category_id"]) if pd.notna(row.get("category_id")) else None,
                row["subject"],
                row["description"],
                row.get("status", "open"),
                row.get("priority", "medium"),
                row.get("language", "en"),
                embedding_array,
            ])
        conn.commit()
        print(f"Inserted {len(df)} tickets into the database.")
    except Exception as e:
        conn.rollback()
        print(f"Error during ingestion: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    ingest_tickets()
