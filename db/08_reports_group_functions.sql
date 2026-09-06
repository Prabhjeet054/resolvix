-- Group-function reporting queries for the ticket similarity project.
-- These are SELECT statements (not DDL). Run via scripts/run_reports.py.

-- =============================================================================
-- Query A: tickets per agent with average resolution time (days)
-- =============================================================================
-- Uses tickets_full_report so agent/customer/category names are already joined.
-- NVL(agent_name, 'Unassigned') folds NULL agent_id tickets into one bucket.
-- CAST(... AS DATE) subtraction yields a numeric day difference so AVG/ROUND work.
SELECT
    NVL(agent_name, 'Unassigned') AS agent_name,
    COUNT(*) AS ticket_count,
    ROUND(
        AVG(CAST(resolved_date AS DATE) - CAST(created_date AS DATE)),
        2
    ) AS avg_resolution_days
FROM tickets_full_report
WHERE resolved_date IS NOT NULL
GROUP BY NVL(agent_name, 'Unassigned')
ORDER BY ticket_count DESC;

-- =============================================================================
-- Query B: tickets per category with priority breakdown
-- =============================================================================
-- Chose plain GROUP BY (not GROUPING SETS): we only need one grain —
-- (category_name, priority) counts — without category/priority subtotals or a
-- grand total. GROUPING SETS would add extra rollup rows that clutter a simple
-- priority-breakdown screenshot for the report.
SELECT
    category_name,
    priority,
    COUNT(*) AS cnt
FROM tickets_full_report
GROUP BY category_name, priority
ORDER BY category_name, priority;
