-- Consolidated ticket view joining all related tables
CREATE OR REPLACE VIEW ticket_details_view AS
SELECT
    t.ticket_id,
    t.subject,
    t.description,
    t.status,
    t.priority,
    t.language,
    t.metadata,
    t.created_at,
    t.resolved_at,
    c.full_name   AS customer_name,
    c.email       AS customer_email,
    a.full_name   AS agent_name,
    cat.category_name
FROM tickets t
LEFT JOIN customers  c   ON t.customer_id  = c.customer_id
LEFT JOIN agents     a   ON t.agent_id     = a.agent_id
LEFT JOIN categories cat ON t.category_id  = cat.category_id;
