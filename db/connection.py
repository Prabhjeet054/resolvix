"""
Database connection module with resilient pooling and health checks.

Provides:
  - get_pool() / get_connection() for Oracle 23ai access
  - is_db_available() for fast dual-mode search decisions
  - get_db_connection() context manager
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Generator, Optional

import oracledb
from dotenv import load_dotenv

load_dotenv()

_pool: Optional[oracledb.ConnectionPool] = None
_pool_lock = threading.Lock()
_pool_failed = False


def _reset_pool_state() -> None:
    """Clear cached pool so the next call can retry creation."""
    global _pool, _pool_failed
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.close()
            except Exception:
                pass
        _pool = None
        _pool_failed = False


def get_pool() -> Optional[oracledb.ConnectionPool]:
    """Return a thread-safe singleton connection pool, or None if unavailable."""
    global _pool, _pool_failed
    if _pool is not None:
        return _pool
    if _pool_failed:
        return None

    with _pool_lock:
        if _pool is not None:
            return _pool
        if _pool_failed:
            return None
        try:
            timeout = int(os.getenv("ORACLE_TIMEOUT_SEC", "3"))
            _pool = oracledb.create_pool(
                user=os.getenv("ORACLE_USER", "system"),
                password=os.getenv("ORACLE_PASSWORD") or os.getenv("ORACLE_PWD", ""),
                dsn=os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1"),
                min=int(os.getenv("ORACLE_POOL_MIN", "2")),
                max=int(os.getenv("ORACLE_POOL_MAX", "10")),
                increment=1,
                getmode=oracledb.POOL_GETMODE_TIMEDWAIT,
                wait_timeout=timeout * 1000,
            )
        except Exception:
            _pool_failed = True
            _pool = None
    return _pool


def get_connection() -> oracledb.Connection:
    """Return an Oracle DB connection (pooled when possible).

    Falls back to a direct connect if the pool cannot be created.
    Raises oracledb.Error (or OSError) if the database is unreachable.
    """
    pool = get_pool()
    if pool is not None:
        try:
            return pool.acquire()
        except Exception:
            _reset_pool_state()

    return oracledb.connect(
        user=os.getenv("ORACLE_USER"),
        password=os.getenv("ORACLE_PASSWORD") or os.getenv("ORACLE_PWD"),
        dsn=os.getenv("ORACLE_DSN", "localhost:1521/FREEPDB1"),
    )


def is_db_available() -> bool:
    """Fast healthcheck (bounded by pool/connect timeout). True if Oracle responds."""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM DUAL")
            row = cur.fetchone()
            return row is not None and int(row[0]) == 1
    except Exception:
        _reset_pool_state()
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@contextmanager
def get_db_connection() -> Generator[oracledb.Connection, None, None]:
    """Context manager that acquires and always releases a connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass
