"""Tests for TIMESTAMP WITH TIME ZONE demo tickets and UTC conversion."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection

WALL_CLOCK = datetime(2026, 8, 11, 14, 0, 0)
DEMO_MARKER = "TZ_TEST_REPORT"

# Expected hours to add to local wall-clock to reach UTC on 2026-08-11
# (negative means local is ahead of UTC).
EXPECTED_OFFSET_HOURS = {
    "Asia/Kolkata": -5.5,       # IST = UTC+5:30
    "America/New_York": 4.0,    # EDT = UTC-4 in August
    "Europe/London": -1.0,      # BST = UTC+1 in August
}


def _cleanup(cursor) -> None:
    """Remove previous timezone test demo tickets."""
    cursor.execute(
        "DELETE FROM tickets WHERE description LIKE :1",
        [f"{DEMO_MARKER}%"],
    )


def _insert_region_tickets(cursor) -> None:
    """Insert three tickets with the same wall-clock in three regions."""
    cursor.execute("SELECT customer_id FROM customers WHERE ROWNUM = 1")
    customer_id = int(cursor.fetchone()[0])
    cursor.execute("SELECT category_id FROM categories WHERE ROWNUM = 1")
    category_id = int(cursor.fetchone()[0])

    regions = (
        ("Asia/Kolkata", "IST"),
        ("America/New_York", "NY"),
        ("Europe/London", "LON"),
    )
    for region, label in regions:
        cursor.execute(
            """
            INSERT INTO tickets (
                customer_id,
                category_id,
                description,
                language_code,
                ticket_status,
                priority,
                created_date,
                created_date_tz,
                metadata
            ) VALUES (
                :customer_id,
                :category_id,
                :description,
                'en',
                'OPEN',
                'LOW',
                TIMESTAMP '2026-08-11 14:00:00',
                FROM_TZ(TIMESTAMP '2026-08-11 14:00:00', :region),
                JSON_OBJECT(
                    'tags' VALUE JSON_ARRAY('timezone', 'demo'),
                    'attachment_count' VALUE 0
                )
            )
            """,
            {
                "customer_id": customer_id,
                "category_id": category_id,
                "description": f"{DEMO_MARKER} {label}: wall-clock 14:00 in {region}",
                "region": region,
            },
        )


def _fetch_utc_rows(cursor) -> list[tuple]:
    """Return region, wall clock, UTC timestamp for demo tickets."""
    cursor.execute(
        """
        SELECT
            EXTRACT(TIMEZONE_REGION FROM created_date_tz) AS original_region,
            TO_CHAR(created_date_tz, 'YYYY-MM-DD HH24:MI:SS') AS wall_clock_time,
            SYS_EXTRACT_UTC(created_date_tz) AS created_date_utc_ts,
            TO_CHAR(
                created_date_tz AT TIME ZONE 'UTC',
                'YYYY-MM-DD HH24:MI:SS TZH:TZM'
            ) AS created_date_utc
        FROM tickets
        WHERE description LIKE :1
        ORDER BY SYS_EXTRACT_UTC(created_date_tz)
        """,
        [f"{DEMO_MARKER}%"],
    )
    return cursor.fetchall()


def _print_report_table(rows: list[tuple]) -> None:
    """Print region | wall_clock | utc | offset_hours for the report."""
    headers = ("region", "wall_clock_time", "utc_converted_time", "offset_hours")
    table_rows = []
    for region, wall_clock, utc_ts, utc_label in rows:
        offset_hours = (utc_ts - WALL_CLOCK).total_seconds() / 3600.0
        table_rows.append(
            (
                str(region),
                str(wall_clock),
                str(utc_label),
                f"{offset_hours:+.1f}",
            )
        )

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in table_rows))
        for i in range(4)
    ]

    def fmt(vals: tuple[str, ...]) -> str:
        return "| " + " | ".join(vals[i].ljust(widths[i]) for i in range(4)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    print("\nTimezone demo (same wall-clock, different UTC):")
    print(sep)
    print(fmt(headers))
    print(sep)
    for row in table_rows:
        print(fmt(row))
    print(sep)


def test_timezone_same_wall_clock_different_utc():
    """Insert 3-region demos and assert numerical UTC offsets."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Ensure column exists (idempotent-ish).
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_tab_columns
            WHERE table_name = 'TICKETS'
              AND column_name = 'CREATED_DATE_TZ'
            """
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE tickets ADD (created_date_tz TIMESTAMP WITH TIME ZONE)"
            )
            conn.commit()

        _cleanup(cursor)
        _insert_region_tickets(cursor)
        conn.commit()

        rows = _fetch_utc_rows(cursor)
        assert len(rows) == 3, f"Expected 3 demo tickets, got {len(rows)}"

        utc_times = [row[2] for row in rows]
        assert len(set(utc_times)) == 3, (
            f"Expected 3 distinct UTC timestamps, got {utc_times}"
        )

        by_region = {str(row[0]): row for row in rows}
        for region, expected_offset in EXPECTED_OFFSET_HOURS.items():
            assert region in by_region, f"Missing region {region} in results"
            _region, wall_clock, utc_ts, utc_label = by_region[region]
            actual_offset = (utc_ts - WALL_CLOCK).total_seconds() / 3600.0
            assert abs(actual_offset - expected_offset) < 0.01, (
                f"{region}: expected offset {expected_offset:+.1f}h, "
                f"got {actual_offset:+.1f}h "
                f"(wall={wall_clock}, utc={utc_label})"
            )
            print(
                f"[PASS] {region}: wall={wall_clock}, utc={utc_label}, "
                f"offset_hours={actual_offset:+.1f} "
                f"(expected {expected_offset:+.1f})"
            )

        _print_report_table(rows)
    finally:
        if cursor is not None and conn is not None:
            try:
                _cleanup(cursor)
                conn.commit()
                print(f"[CLEANUP] deleted {DEMO_MARKER} tickets")
            except Exception as cleanup_error:
                conn.rollback()
                print(f"[CLEANUP FAILED] {cleanup_error}")
            finally:
                cursor.close()
                conn.close()
