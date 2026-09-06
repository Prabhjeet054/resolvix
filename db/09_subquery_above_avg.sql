-- Tickets whose resolution time is strictly above the overall average.
-- Variant 1: non-correlated subquery in the WHERE clause (scalar AVG once).
-- Variant 2: same logic expressed with a WITH (CTE) for clearer structure.

-- =============================================================================
-- Variant 1 — subquery in WHERE
-- =============================================================================
-- The scalar subquery computes one global average over all resolved tickets.
-- Oracle typically evaluates it once and compares each outer row's interval
-- duration against that single value (non-correlated).
SELECT
    t.ticket_id,
    DBMS_LOB.SUBSTR(t.description, 200, 1) AS description,
    NVL(a.agent_name, 'Unassigned') AS agent_name,
    CAST(t.resolved_date AS DATE) - CAST(t.created_date AS DATE) AS resolution_days
FROM tickets t
LEFT JOIN agents a
  ON t.agent_id = a.agent_id
WHERE t.resolved_date IS NOT NULL
  AND (t.resolved_date - t.created_date) > (
        SELECT AVG(resolved_date - created_date)
        FROM tickets
        WHERE resolved_date IS NOT NULL
      )
ORDER BY resolution_days DESC;

-- =============================================================================
-- Variant 2 — WITH clause (CTE)
-- =============================================================================
-- Same filter/result as Variant 1, but the average is named in a CTE and joined
-- (or referenced) explicitly. Prefer this when the query grows (multiple
-- references to the average, extra joins, report columns) because the CTE
-- documents the intermediate metric and is easier to extend/test.
--
-- Difference vs WHERE subquery:
--   * WHERE subquery: compact for a one-off scalar comparison; optimizer often
--     unnests it to the same plan as a CTE on simple cases.
--   * CTE: better readability/maintainability when the average (or other
--     aggregates) are reused, or when you want to SELECT the average alongside
--     detail rows. Prefer CTE for complex reports; prefer a simple WHERE
--     subquery when the comparison is the only extra logic.
WITH avg_resolution AS (
    SELECT AVG(resolved_date - created_date) AS avg_resolution_interval
    FROM tickets
    WHERE resolved_date IS NOT NULL
)
SELECT
    t.ticket_id,
    DBMS_LOB.SUBSTR(t.description, 200, 1) AS description,
    NVL(a.agent_name, 'Unassigned') AS agent_name,
    CAST(t.resolved_date AS DATE) - CAST(t.created_date AS DATE) AS resolution_days
FROM tickets t
LEFT JOIN agents a
  ON t.agent_id = a.agent_id
CROSS JOIN avg_resolution ar
WHERE t.resolved_date IS NOT NULL
  AND (t.resolved_date - t.created_date) > ar.avg_resolution_interval
ORDER BY resolution_days DESC;
