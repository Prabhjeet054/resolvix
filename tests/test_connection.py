"""Tests for the database connection module."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection


class TestConnection(unittest.TestCase):
    """Verify Oracle DB connectivity."""

    def test_connection_returns_valid_object(self):
        """Ensure get_connection() returns a live connection."""
        conn = get_connection()
        self.assertIsNotNone(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
        cursor.close()
        conn.close()

    def test_env_variables_loaded(self):
        """Ensure required environment variables are set."""
        self.assertIsNotNone(os.getenv("ORACLE_USER"))
        self.assertIsNotNone(os.getenv("ORACLE_PASSWORD"))
        self.assertIsNotNone(os.getenv("ORACLE_DSN"))


if __name__ == "__main__":
    unittest.main()
