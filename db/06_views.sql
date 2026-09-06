-- Reporting views over tickets and related reference data.

-- High-priority queue: oldest URGENT/HIGH OPEN tickets first.
-- ORDER BY uses CASE so URGENT ranks before HIGH, then oldest created_date.
CREATE OR REPLACE VIEW high_priority_open_tickets AS
SELECT
    t.ticket_id,
    DBMS_LOB.SUBSTR(t.description, 200, 1) AS description,
    c.customer_name,
    a.agent_name,
    cat.category_name,
    t.created_date,
    t.priority
FROM tickets t
JOIN customers c
  ON t.customer_id = c.customer_id
LEFT JOIN agents a
  ON t.agent_id = a.agent_id
JOIN categories cat
  ON t.category_id = cat.category_id
WHERE t.ticket_status = 'OPEN'
  AND t.priority IN ('HIGH', 'URGENT')
ORDER BY
    CASE t.priority
        WHEN 'URGENT' THEN 1
        WHEN 'HIGH' THEN 2
        ELSE 3
    END,
    t.created_date ASC;

-- Unfiltered reporting join across all four core tables.
-- Column names are uniquely prefixed/aliased to avoid join ambiguity.
CREATE OR REPLACE VIEW tickets_full_report AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.agent_id,
    t.category_id,
    t.description          AS ticket_description,
    t.language_code,
    t.ticket_status,
    t.priority,
    t.created_date,
    t.resolved_date,
    t.resolution,
    t.metadata             AS ticket_metadata,
    c.customer_name,
    c.email                AS customer_email,
    c.phone                AS customer_phone,
    c.region               AS customer_region,
    c.created_at           AS customer_created_at,
    a.agent_name,
    a.email                AS agent_email,
    a.department           AS agent_department,
    a.is_active            AS agent_is_active,
    cat.category_name,
    cat.description        AS category_description
FROM tickets t
JOIN customers c
  ON t.customer_id = c.customer_id
LEFT JOIN agents a
  ON t.agent_id = a.agent_id
JOIN categories cat
  ON t.category_id = cat.category_id;
