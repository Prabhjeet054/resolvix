"""
Database connection module.

Reads Oracle credentials from .env and provides a reusable
get_connection() function that returns an oracledb connection.
"""

import os

import oracledb
from dotenv import load_dotenv

load_dotenv()


def get_connection() -> oracledb.Connection:
    """Return an Oracle DB connection using credentials from .env.

    Raises:
        oracledb.Error: If the connection cannot be established.
    """
    return oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD"),
        dsn=os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1"),
    )
