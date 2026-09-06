"""Tests for Oracle JSON queries on Tickets.metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from scripts.run_ddl_subset import split_sql_statements

SQL_PATH = PROJECT_ROOT / "db" / "12_json_queries.sql"

# Fixed IDs for deterministic cleanup/assertions.
TICKET_URGENT_TAG = 88101
TICKET_ATTACHMENTS = 88102
TICKET_NEITHER = 88103
TEST_IDS = {TICKET_URGENT_TAG, TICKET_ATTACHMENTS, TICKET_NEITHER}


def _load_json_queries() -> list[str]:
    """Return the four SELECT statements from db/12_json_queries.sql."""
    statements = split_sql_statements(SQL_PATH.read_text(encoding="utf-8"))
    assert len(statements) == 4, f"Expected 4 JSON queries, found {len(statements)}"
    return statements


def _seed_parents(cursor) -> tuple[int, int]:
    """Return customer_id and category_id for inserts."""
    cursor.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
    customer_id = int(cursor.fetchone()[0])
    cursor.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
    category_id = int(cursor.fetchone()[0])
    return customer_id, category_id


def _cleanup(cursor) -> None:
    """Delete temporary JSON-test tickets."""
    cursor.execute(
        "DELETE FROM tickets WHERE ticket_id IN (:1, :2, :3)",
        [TICKET_URGENT_TAG, TICKET_ATTACHMENTS, TICKET_NEITHER],
    )


def _filter_ids(rows: list[tuple], id_index: int = 0) -> set[int]:
    """Keep only temporary test ticket_ids from a query result."""
    return {
        int(row[id_index])
        for row in rows
        if int(row[id_index]) in TEST_IDS
    }


def test_json_queries_with_controlled_metadata():
    """Insert controlled metadata rows and verify all four JSON queries."""
    q_urgent, q_attachments, q_high_or_urgent, q_json_table = _load_json_queries()

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        _cleanup(cursor)

        customer_id, category_id = _seed_parents(cursor)

        # 1) Three temporary tickets with controlled metadata.
        fixtures = [
            (
                TICKET_URGENT_TAG,
                "LOW",
                {"tags": ["billing", "urgent"], "attachment_count": 0},
            ),
            (
                TICKET_ATTACHMENTS,
                "MEDIUM",
                {"tags": ["login"], "attachment_count": 2},
            ),
            (
                TICKET_NEITHER,
                "LOW",
                {"tags": ["general"], "attachment_count": 0},
            ),
        ]
        for ticket_id, priority, metadata in fixtures:
            cursor.execute(
                """
                INSERT INTO tickets (
                    ticket_id, customer_id, category_id, description,
                    language_code, ticket_status, priority, metadata
                ) VALUES (
                    :1, :2, :3, :4, 'en', 'OPEN', :5, :6
                )
                """,
                [
                    ticket_id,
                    customer_id,
                    category_id,
                    f"JSON_TEST ticket {ticket_id}",
                    priority,
                    json.dumps(metadata),
                ],
            )
        conn.commit()
        print(
            f"[INFO] Inserted test tickets {sorted(TEST_IDS)} "
            "with controlled metadata"
        )

        # 2a) JSON_EXISTS urgent tag — only TICKET_URGENT_TAG.
        cursor.execute(q_urgent)
        urgent_ids = _filter_ids(cursor.fetchall())
        assert urgent_ids == {TICKET_URGENT_TAG}, (
            f"urgent-tag query expected {{{TICKET_URGENT_TAG}}}, got {urgent_ids}"
        )
        print(f"[PASS] urgent-tag query matched only {sorted(urgent_ids)}")

        # 2b) attachment_count > 0 — only TICKET_ATTACHMENTS.
        cursor.execute(q_attachments)
        attachment_ids = _filter_ids(cursor.fetchall())
        assert attachment_ids == {TICKET_ATTACHMENTS}, (
            f"attachment_count query expected {{{TICKET_ATTACHMENTS}}}, "
            f"got {attachment_ids}"
        )
        print(
            f"[PASS] attachment_count>0 query matched only {sorted(attachment_ids)}"
        )

        # 2c) HIGH OR urgent tag — among test IDs, only urgent-tagged ticket
        # (none of the fixtures use priority HIGH).
        cursor.execute(q_high_or_urgent)
        high_or_urgent_ids = _filter_ids(cursor.fetchall())
        assert high_or_urgent_ids == {TICKET_URGENT_TAG}, (
            f"HIGH-or-urgent query expected {{{TICKET_URGENT_TAG}}}, "
            f"got {high_or_urgent_ids}"
        )
        print(
            f"[PASS] HIGH-or-urgent query matched only {sorted(high_or_urgent_ids)} "
            "among test tickets"
        )

        # 2d/3) JSON_TABLE unnest — one row per tag for test tickets.
        cursor.execute(q_json_table)
        tag_rows = [
            (int(ticket_id), str(tag))
            for ticket_id, _priority, tag in cursor.fetchall()
            if int(ticket_id) in TEST_IDS
        ]
        tags_by_ticket: dict[int, list[str]] = {
            TICKET_URGENT_TAG: [],
            TICKET_ATTACHMENTS: [],
            TICKET_NEITHER: [],
        }
        for ticket_id, tag in tag_rows:
            tags_by_ticket[ticket_id].append(tag)

        assert sorted(tags_by_ticket[TICKET_URGENT_TAG]) == ["billing", "urgent"], (
            f"Expected 2 tags for urgent ticket, got {tags_by_ticket[TICKET_URGENT_TAG]}"
        )
        assert len(tags_by_ticket[TICKET_URGENT_TAG]) == 2
        assert tags_by_ticket[TICKET_ATTACHMENTS] == ["login"]
        assert tags_by_ticket[TICKET_NEITHER] == ["general"]
        assert len(tag_rows) == 4, (
            f"Expected 4 flattened tag rows for test tickets, got {len(tag_rows)}"
        )
        print(
            f"[PASS] JSON_TABLE produced one row per tag: {tag_rows} "
            f"(urgent ticket => 2 rows)"
        )
    finally:
        if cursor is not None and conn is not None:
            try:
                _cleanup(cursor)
                conn.commit()
                print(f"[CLEANUP] deleted temporary tickets {sorted(TEST_IDS)}")
            except Exception as cleanup_error:
                conn.rollback()
                print(f"[CLEANUP FAILED] {cleanup_error}")
            finally:
                cursor.close()
                conn.close()
