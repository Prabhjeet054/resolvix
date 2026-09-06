"""Access-control tests for test_admin_user / test_agent_user roles."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import oracledb
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

CREDENTIALS_PATH = PROJECT_ROOT / "credentials" / "demo_db_users.env"


def _load_settings() -> tuple[str, str, str, str, str]:
    """Load DSN and demo-user credentials."""
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(CREDENTIALS_PATH)

    dsn = os.getenv("ORACLE_DSN")
    agent_user = os.getenv("TEST_AGENT_USER", "test_agent_user")
    agent_password = os.getenv("TEST_AGENT_PASSWORD")
    admin_user = os.getenv("TEST_ADMIN_USER", "test_admin_user")
    admin_password = os.getenv("TEST_ADMIN_PASSWORD")
    if not all([dsn, agent_password, admin_password]):
        raise RuntimeError(
            "Need ORACLE_DSN plus TEST_AGENT_PASSWORD/TEST_ADMIN_PASSWORD "
            "in .env / credentials/demo_db_users.env"
        )
    return dsn, agent_user, agent_password, admin_user, admin_password


def _connect(user: str, password: str, dsn: str) -> oracledb.Connection:
    """Open a thin-mode connection as a demo user."""
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _can_select(conn: oracledb.Connection, table_name: str) -> tuple[bool, str]:
    """Return (allowed, detail) for SELECT COUNT(*) FROM table_name."""
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        return True, f"COUNT={count}"
    except oracledb.Error as exc:
        error_obj, = exc.args
        return False, f"ORA-{error_obj.code}: {error_obj.message.splitlines()[0]}"
    finally:
        cursor.close()


def _can_insert_ticket(conn: oracledb.Connection) -> tuple[bool, str]:
    """Try inserting (and rolling back) one ticket row as the connected user."""
    cursor = conn.cursor()
    try:
        # Resolve required FKs via privileged owner connection helpers.
        owner = get_connection()
        owner_cur = owner.cursor()
        try:
            owner_cur.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
            customer_id = int(owner_cur.fetchone()[0])
            owner_cur.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
            category_id = int(owner_cur.fetchone()[0])
        finally:
            owner_cur.close()
            owner.close()

        cursor.execute(
            """
            INSERT INTO tickets (
                customer_id, category_id, description,
                language_code, ticket_status, priority
            ) VALUES (
                :1, :2, :3, 'en', 'OPEN', 'LOW'
            )
            """,
            [customer_id, category_id, "ACCESS_CONTROL_TEST temporary insert"],
        )
        conn.rollback()
        return True, "INSERT allowed (rolled back)"
    except oracledb.Error as exc:
        conn.rollback()
        error_obj, = exc.args
        return False, f"ORA-{error_obj.code}: {error_obj.message.splitlines()[0]}"
    finally:
        cursor.close()


def _print_matrix(title: str, matrix: list[tuple[str, str, str, str]]) -> None:
    """Pretty-print role x object x permission results."""
    headers = ("Role/User", "Object", "Permission", "Result")
    rows = [headers, *matrix]
    widths = [max(len(str(row[i])) for row in rows) for i in range(4)]

    def fmt(row: tuple[str, str, str, str]) -> str:
        return "| " + " | ".join(str(row[i]).ljust(widths[i]) for i in range(4)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    print(f"\n{title}")
    print(sep)
    print(fmt(headers))
    print(sep)
    for row in matrix:
        print(fmt(row))
    print(sep)


def _revoke_agent_and_admin_grants() -> None:
    """Run the documented REVOKE statements as the schema owner."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        statements = [
            "REVOKE SELECT, UPDATE ON my_tickets FROM agent_role",
            "REVOKE SELECT ON tickets FROM admin_role",
            "REVOKE SELECT ON customers FROM admin_role",
            "REVOKE SELECT ON agents FROM admin_role",
            "REVOKE SELECT ON categories FROM admin_role",
            "REVOKE INSERT, UPDATE, DELETE ON tickets FROM admin_role",
        ]
        for sql in statements:
            cursor.execute(sql)
            print(f"Executed: {sql}")
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _restore_grants() -> None:
    """Re-apply role grants so the demo environment remains usable."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        statements = [
            "GRANT SELECT, UPDATE ON my_tickets TO agent_role",
            "GRANT SELECT ON tickets TO admin_role",
            "GRANT SELECT ON customers TO admin_role",
            "GRANT SELECT ON agents TO admin_role",
            "GRANT SELECT ON categories TO admin_role",
            "GRANT INSERT, UPDATE, DELETE ON tickets TO admin_role",
        ]
        for sql in statements:
            cursor.execute(sql)
        conn.commit()
        print("Restored role GRANTs after REVOKE verification.")
    finally:
        cursor.close()
        conn.close()


def test_access_control_before_and_after_revoke():
    """Verify admin/agent permissions, then confirm REVOKE removes agent access."""
    dsn, agent_user, agent_password, admin_user, admin_password = _load_settings()
    before_matrix: list[tuple[str, str, str, str]] = []
    after_matrix: list[tuple[str, str, str, str]] = []

    try:
        # ----- BEFORE REVOKE -----
        admin_conn = _connect(admin_user, admin_password, dsn)
        try:
            for table in ("tickets", "customers", "agents", "categories"):
                ok, detail = _can_select(admin_conn, table)
                before_matrix.append(
                    (admin_user, table, "SELECT", "ALLOW" if ok else f"DENY ({detail})")
                )
                assert ok, f"Admin should SELECT {table}: {detail}"

            ok, detail = _can_insert_ticket(admin_conn)
            before_matrix.append(
                (admin_user, "tickets", "INSERT", "ALLOW" if ok else f"DENY ({detail})")
            )
            assert ok, f"Admin should INSERT tickets: {detail}"
        finally:
            admin_conn.close()

        agent_conn = _connect(agent_user, agent_password, dsn)
        try:
            ok, detail = _can_select(agent_conn, "my_tickets")
            before_matrix.append(
                (agent_user, "my_tickets", "SELECT", "ALLOW" if ok else f"DENY ({detail})")
            )
            assert ok, f"Agent should SELECT my_tickets: {detail}"

            for table in ("customers", "agents"):
                ok, detail = _can_select(agent_conn, table)
                before_matrix.append(
                    (
                        agent_user,
                        table,
                        "SELECT",
                        "DENY" if not ok else f"ALLOW ({detail})",
                    )
                )
                assert not ok, (
                    f"Agent should NOT SELECT base table {table}, but succeeded ({detail})"
                )
                assert "ORA-00942" in detail or "ORA-01031" in detail, (
                    f"Expected ORA-00942/ORA-01031 for agent SELECT {table}, got {detail}"
                )
        finally:
            agent_conn.close()

        _print_matrix("BEFORE REVOKE — access matrix", before_matrix)

        # ----- REVOKE then re-test agent -----
        _revoke_agent_and_admin_grants()

        agent_conn = _connect(agent_user, agent_password, dsn)
        try:
            ok, detail = _can_select(agent_conn, "my_tickets")
            after_matrix.append(
                (
                    agent_user,
                    "my_tickets",
                    "SELECT",
                    "DENY" if not ok else f"ALLOW ({detail})",
                )
            )
            assert not ok, (
                f"After REVOKE, agent should not SELECT my_tickets, got {detail}"
            )
            assert "ORA-00942" in detail or "ORA-01031" in detail, (
                f"Expected ORA-00942/ORA-01031 after REVOKE, got {detail}"
            )

            for table in ("customers", "agents"):
                ok, detail = _can_select(agent_conn, table)
                after_matrix.append(
                    (
                        agent_user,
                        table,
                        "SELECT",
                        "DENY" if not ok else f"ALLOW ({detail})",
                    )
                )
                assert not ok
        finally:
            agent_conn.close()

        # Admin should also lose table privileges after the REVOKE block.
        admin_conn = _connect(admin_user, admin_password, dsn)
        try:
            ok, detail = _can_select(admin_conn, "tickets")
            after_matrix.append(
                (
                    admin_user,
                    "tickets",
                    "SELECT",
                    "DENY" if not ok else f"ALLOW ({detail})",
                )
            )
            assert not ok, f"After REVOKE, admin should not SELECT tickets: {detail}"
        finally:
            admin_conn.close()

        _print_matrix("AFTER REVOKE — access matrix", after_matrix)
        print("\n[PASS] Access-control before/after REVOKE checks succeeded.")
    finally:
        # Always restore GRANTs so later demos/tests keep working.
        try:
            _restore_grants()
        except Exception as restore_error:
            print(f"[WARN] Failed to restore GRANTs: {restore_error}")
