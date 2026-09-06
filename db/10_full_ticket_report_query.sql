-- Full ticket report using explicit ANSI JOIN syntax (no old-style comma joins).
--
-- Why LEFT JOIN Agents but INNER JOIN Customers/Categories?
-- From the Tickets schema (prompt 4 / db/04_tickets.sql):
--   * customer_id and category_id are required foreign keys — every ticket
--     references an existing customer and category, so INNER JOIN is correct
--     and will not drop rows.
--   * agent_id is nullable (unassigned tickets are allowed), with
--     fk_tickets_agent only enforced when agent_id is non-NULL. An INNER JOIN
--     to Agents would eliminate unassigned tickets from the report. LEFT OUTER
--     JOIN keeps those rows and yields NULL agent columns, which we display as
--     'Unassigned' via NVL — a classic viva point on join type vs FK nullability.

SELECT
    t.ticket_id,
    c.customer_name,
    NVL(a.agent_name, 'Unassigned') AS agent_name,
    cat.category_name,
    t.ticket_status,
    t.priority,
    t.created_date,
    t.resolution
FROM tickets t
INNER JOIN customers c
    ON t.customer_id = c.customer_id
INNER JOIN categories cat
    ON t.category_id = cat.category_id
LEFT OUTER JOIN agents a
    ON t.agent_id = a.agent_id
ORDER BY t.created_date DESC;
