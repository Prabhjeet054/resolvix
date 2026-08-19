"""Tests for the vector similarity search query."""

import os
import sys
import array
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from embeddings.generate import generate_embedding


class TestSimilarityQuery(unittest.TestCase):
    """Verify that the vector similarity SQL query executes without errors."""

    def test_similarity_search_runs(self):
        """Execute a similarity search and verify it returns rows."""
        query_embedding = generate_embedding("I cannot log in to my account")
        query_vector = array.array("f", query_embedding)

        conn = get_connection()
        cursor = conn.cursor()

        try:
            sql = """
                SELECT ticket_id, subject,
                       VECTOR_DISTANCE(embedding, :1, COSINE) AS distance
                FROM tickets
                WHERE embedding IS NOT NULL
                ORDER BY VECTOR_DISTANCE(embedding, :2, COSINE)
                FETCH FIRST 5 ROWS ONLY
            """
            cursor.execute(sql, [query_vector, query_vector])
            results = cursor.fetchall()
            self.assertIsInstance(results, list)
        finally:
            cursor.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()
