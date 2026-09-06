-- B-tree indexes to support common ticket queue / reporting predicates.

CREATE INDEX idx_tickets_status
    ON tickets (ticket_status);

CREATE INDEX idx_tickets_created_date
    ON tickets (created_date);

-- Composite (ticket_status, created_date): for queries that filter on status and
-- also filter/sort on created_date (e.g. OPEN tickets ordered by oldest first),
-- Oracle can satisfy both the equality on status and the range/order on
-- created_date from one index. Leading-column status narrows to a contiguous
-- slice; created_date is already ordered within that slice. Two separate
-- single-column indexes would force the optimizer to pick one index, or merge
-- bitmap/index results, which is usually less efficient for this access pattern.
CREATE INDEX idx_tickets_status_created
    ON tickets (ticket_status, created_date);
