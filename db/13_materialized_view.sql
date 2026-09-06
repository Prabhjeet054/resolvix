-- =============================================================================
-- Materialized view: daily_ticket_summary
-- =============================================================================
-- REFRESH COMPLETE ON DEMAND (not ON COMMIT):
--   Ticket inserts/updates are frequent during ingest and agent work. ON COMMIT
--   would rebuild/refresh this summary after every committing transaction,
--   adding latency to OLTP paths. ON DEMAND keeps writes cheap and lets us
--   refresh explicitly (e.g. after batch ingest or on a schedule) via
--   DBMS_MVIEW.REFRESH — better for a reporting summary on Oracle Free.
-- BUILD IMMEDIATE: populate the MVIEW immediately at create time so queries
--   work without an extra first refresh.
-- =============================================================================

CREATE MATERIALIZED VIEW daily_ticket_summary
    BUILD IMMEDIATE
    REFRESH COMPLETE ON DEMAND
AS
SELECT
    TRUNC(created_date) AS ticket_date,
    COUNT(*) AS total_tickets,
    COUNT(CASE WHEN ticket_status = 'OPEN' THEN 1 END) AS open_count,
    COUNT(
        CASE
            WHEN ticket_status IN ('RESOLVED', 'CLOSED') THEN 1
        END
    ) AS resolved_count,
    ROUND(
        AVG(
            CASE
                WHEN resolved_date IS NOT NULL THEN
                    CAST(resolved_date AS DATE) - CAST(created_date AS DATE)
            END
        ),
        2
    ) AS avg_resolution_days
FROM tickets
GROUP BY TRUNC(created_date);

-- Manual refresh (run when summary should catch up after DML / ingest):
-- BEGIN
--     DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY');
-- END;
-- /

-- Companion one-liner for scripts / SQLcl:
-- EXEC DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY');
