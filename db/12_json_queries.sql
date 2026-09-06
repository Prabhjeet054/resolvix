-- =============================================================================
-- JSON queries on Tickets.metadata (Oracle 23ai native JSON type)
-- =============================================================================
-- Unit 5 note — native JSON vs older CLOB-based JSON:
--   * In Oracle Database 23ai, METADATA is declared as JSON (see db/04_tickets.sql),
--     so the database validates JSON on insert/update and stores it in an optimized
--     binary JSON format. Functions like JSON_EXISTS / JSON_VALUE / JSON_TABLE
--     operate directly on that typed column.
--   * Older approaches often stored JSON as CLOB/VARCHAR2 with only IS JSON checks.
--     That worked, but needed more casting, offered weaker typing, and typically
--     poorer performance than native JSON. Prefer the JSON type on 23ai for new work.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) Tickets whose metadata.tags array contains the string "urgent"
-- -----------------------------------------------------------------------------
SELECT
    ticket_id,
    priority,
    ticket_status,
    JSON_QUERY(metadata, '$.tags') AS tags
FROM tickets
WHERE JSON_EXISTS(metadata, '$.tags[*]?(@ == "urgent")')
ORDER BY ticket_id;

-- -----------------------------------------------------------------------------
-- 2) Tickets with at least one attachment (attachment_count > 0)
-- -----------------------------------------------------------------------------
SELECT
    ticket_id,
    priority,
    JSON_VALUE(metadata, '$.attachment_count' RETURNING NUMBER) AS attachment_count
FROM tickets
WHERE JSON_VALUE(metadata, '$.attachment_count' RETURNING NUMBER) > 0
ORDER BY attachment_count DESC, ticket_id;

-- -----------------------------------------------------------------------------
-- 3) High priority column OR "urgent" metadata tag
--    Combines relational predicate with JSON_EXISTS in one WHERE clause.
-- -----------------------------------------------------------------------------
SELECT
    ticket_id,
    priority,
    ticket_status,
    JSON_QUERY(metadata, '$.tags') AS tags
FROM tickets
WHERE priority = 'HIGH'
   OR JSON_EXISTS(metadata, '$.tags[*]?(@ == "urgent")')
ORDER BY
    CASE priority
        WHEN 'URGENT' THEN 1
        WHEN 'HIGH' THEN 2
        ELSE 3
    END,
    ticket_id;

-- -----------------------------------------------------------------------------
-- 4) JSON_TABLE: flatten tags into one row per (ticket_id, tag)
--    Useful as the base for a tag-frequency report (GROUP BY tag).
-- -----------------------------------------------------------------------------
SELECT
    t.ticket_id,
    t.priority,
    jt.tag_value AS tag
FROM tickets t,
     JSON_TABLE(
         t.metadata,
         '$.tags[*]'
         COLUMNS (
             tag_value VARCHAR2(100) PATH '$'
         )
     ) jt
ORDER BY t.ticket_id, jt.tag_value;

-- Example tag-frequency rollup (same JSON_TABLE pattern):
-- SELECT jt.tag_value AS tag, COUNT(*) AS ticket_count
-- FROM tickets t,
--      JSON_TABLE(
--          t.metadata,
--          '$.tags[*]'
--          COLUMNS (tag_value VARCHAR2(100) PATH '$')
--      ) jt
-- GROUP BY jt.tag_value
-- ORDER BY ticket_count DESC;
