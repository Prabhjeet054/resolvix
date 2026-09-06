"""
Apply db/11_roles_access_control.sql and create demo DB users from credentials.

Passwords come from credentials/demo_db_users.env (gitignored), never from the SQL file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = PROJECT_ROOT / "db" / "11_roles_access_control.sql"
CREDENTIALS_PATH = PROJECT_ROOT / "credentials" / "demo_db_users.env"


def _drop_if_exists(cursor, sql: str, ignorable_codes: set[int]) -> None:
    """Execute DDL and ignore expected 'does not exist' errors."""
    try:
        cursor.execute(sql)
    except Exception as exc:
        error_obj = exc.args[0] if exc.args else None
        code = getattr(error_obj, "code", None)
        if code not in ignorable_codes:
            # Fallback: parse ORA-xxxxx from message.
            message = str(exc)
            if not any(f"ORA-{code:05d}" in message for code in ignorable_codes):
                # Also accept codes without zero-padding match via substring.
                if not any(f"ORA-{c}" in message for c in ignorable_codes):
                    raise


def _ensure_roles_and_view(cursor) -> None:
    """Create roles/view/grants from the SQL file (skip CREATE ROLE if exists)."""
    statements = split_sql_statements(SQL_PATH.read_text(encoding="utf-8"))
    for statement in statements:
        stripped = statement.strip()
        upper = stripped.upper()
        try:
            cursor.execute(stripped)
            print(f"OK: {stripped.splitlines()[0][:80]}")
        except Exception as exc:
            message = str(exc)
            # ORA-01921: role name conflicts / already exists
            # ORA-00955: name already used by existing object
            if "ORA-01921" in message or "ORA-00955" in message:
                print(f"SKIP (exists): {stripped.splitlines()[0][:80]}")
                continue
            # UPDATE/GRANT may be re-run safely; surface unexpected errors.
            if upper.startswith("GRANT") and "ORA-01917" in message:
                # role missing — recreate attempt already done; re-raise
                raise
            raise


def _create_user(cursor, username: str, password: str, role_name: str) -> None:
    """Drop/recreate a demo user and grant CREATE SESSION + role."""
    _drop_if_exists(
        cursor,
        f'DROP USER {username} CASCADE',
        {1918},  # ORA-01918: user does not exist
    )
    cursor.execute(
        f'CREATE USER {username} IDENTIFIED BY "{password}" QUOTA UNLIMITED ON users'
    )
    cursor.execute(f"GRANT CREATE SESSION TO {username}")
    cursor.execute(f"GRANT {role_name} TO {username}")
    # Roles are not enabled by default for some clients unless default role set.
    cursor.execute(f"ALTER USER {username} DEFAULT ROLE ALL")
    print(f"Created user {username} with role {role_name}")


def _create_synonyms(cursor) -> None:
    """Create private synonyms so demo users need no SYSTEM. prefix."""
    synonym_map = {
        "test_agent_user": ["my_tickets"],
        "test_admin_user": ["tickets", "customers", "agents", "categories"],
    }
    for username, objects in synonym_map.items():
        for object_name in objects:
            cursor.execute(
                f"CREATE OR REPLACE SYNONYM {username}.{object_name} "
                f"FOR system.{object_name}"
            )
    print("Created private synonyms for demo users.")


def main() -> None:
    """Apply access-control DDL and provision test_agent_user / test_admin_user."""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {CREDENTIALS_PATH}. Copy credentials/demo_db_users.env.example "
            "and set temporary passwords."
        )

    load_dotenv(CREDENTIALS_PATH)
    agent_user = os.getenv("TEST_AGENT_USER", "test_agent_user")
    agent_password = os.getenv("TEST_AGENT_PASSWORD")
    admin_user = os.getenv("TEST_ADMIN_USER", "test_admin_user")
    admin_password = os.getenv("TEST_ADMIN_PASSWORD")

    if not agent_password or not admin_password:
        raise RuntimeError(
            "TEST_AGENT_PASSWORD and TEST_ADMIN_PASSWORD must be set in "
            "credentials/demo_db_users.env"
        )

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        print(f"Applying {SQL_PATH.name} ...")
        _ensure_roles_and_view(cursor)

        print("Creating demo users from credentials/demo_db_users.env ...")
        _create_user(cursor, agent_user, agent_password, "agent_role")
        _create_user(cursor, admin_user, admin_password, "admin_role")
        _create_synonyms(cursor)

        conn.commit()
        print("Access-control demo applied successfully.")
        print(
            "Connect as test users with DSN from .env "
            f"(e.g. {agent_user}/********@FREEPDB1)."
        )
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
    main()
