-- =============================================================================
-- Time zone support on Tickets.created_date_tz
-- =============================================================================
-- created_date remains TIMESTAMP (wall-clock without zone) for older queries.
-- created_date_tz is TIMESTAMP WITH TIME ZONE for region-aware reporting.
-- =============================================================================

-- 1) Add timestamptz column (nullable initially so backfill can run).
ALTER TABLE tickets ADD (
    created_date_tz TIMESTAMP WITH TIME ZONE
);

-- 2) One-time backfill: treat existing created_date values as Asia/Kolkata (IST).
-- FROM_TZ attaches a zone to a TIMESTAMP; result is TIMESTAMP WITH TIME ZONE.
UPDATE tickets
SET created_date_tz = FROM_TZ(created_date, 'Asia/Kolkata')
WHERE created_date_tz IS NULL
  AND created_date IS NOT NULL;

-- 3) Demo inserts: identical wall-clock '2026-08-11 14:00:00' in three zones.
-- Uses existing customer/category ids (first rows) so FK checks pass.
-- ticket_id left NULL so trg_tickets_id / ticket_seq can assign values.
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
    (SELECT customer_id FROM customers WHERE ROWNUM = 1),
    (SELECT category_id FROM categories WHERE ROWNUM = 1),
    'TZ_DEMO IST: same wall-clock 14:00 in Asia/Kolkata',
    'en',
    'OPEN',
    'LOW',
    TIMESTAMP '2026-08-11 14:00:00',
    FROM_TZ(TIMESTAMP '2026-08-11 14:00:00', 'Asia/Kolkata'),
    JSON_OBJECT('tags' VALUE JSON_ARRAY('timezone', 'demo'), 'attachment_count' VALUE 0)
);

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
    (SELECT customer_id FROM customers WHERE ROWNUM = 1),
    (SELECT category_id FROM categories WHERE ROWNUM = 1),
    'TZ_DEMO NY: same wall-clock 14:00 in America/New_York',
    'en',
    'OPEN',
    'LOW',
    TIMESTAMP '2026-08-11 14:00:00',
    FROM_TZ(TIMESTAMP '2026-08-11 14:00:00', 'America/New_York'),
    JSON_OBJECT('tags' VALUE JSON_ARRAY('timezone', 'demo'), 'attachment_count' VALUE 0)
);

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
    (SELECT customer_id FROM customers WHERE ROWNUM = 1),
    (SELECT category_id FROM categories WHERE ROWNUM = 1),
    'TZ_DEMO LON: same wall-clock 14:00 in Europe/London',
    'en',
    'OPEN',
    'LOW',
    TIMESTAMP '2026-08-11 14:00:00',
    FROM_TZ(TIMESTAMP '2026-08-11 14:00:00', 'Europe/London'),
    JSON_OBJECT('tags' VALUE JSON_ARRAY('timezone', 'demo'), 'attachment_count' VALUE 0)
);

-- 4) Unified UTC reporting view of timestamptz values.
-- SELECT expressions return VARCHAR2 / TIMESTAMP (no named-zone TZ type in the
-- result set) so clients in python-oracledb thin mode can fetch rows safely.
-- EXTRACT(TIMEZONE_REGION ...) labels the original zone; AT TIME ZONE 'UTC'
-- (via TO_CHAR) and SYS_EXTRACT_UTC normalize for cross-region comparison.
SELECT
    ticket_id,
    DBMS_LOB.SUBSTR(description, 80, 1) AS description,
    TO_CHAR(created_date_tz, 'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS original_timestamptz,
    EXTRACT(TIMEZONE_REGION FROM created_date_tz) AS original_region,
    TO_CHAR(
        created_date_tz AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS created_date_utc,
    SYS_EXTRACT_UTC(created_date_tz) AS created_date_utc_ts
FROM tickets
WHERE created_date_tz IS NOT NULL
ORDER BY SYS_EXTRACT_UTC(created_date_tz), ticket_id;
