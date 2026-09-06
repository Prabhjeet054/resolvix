-- =============================================================================
-- Access control demo for Oracle 23ai Free (college-project scope)
-- =============================================================================
-- Assumption (intentionally simplified — not production IAM):
--   * The app normally runs as one schema user and enforces agent_id in Python.
--   * For this DDL lab we ALSO create two real DB users and roles so GRANT/REVOKE
--     and session identity can be demonstrated in SQL*Plus / SQLcl.
--   * Agent row filtering uses:
--         LOWER(Agents.email) = LOWER(SESSION_USER || '@resolvix.support')
--     so test_agent_user maps to email test_agent_user@resolvix.support.
--     We update one seeded agent email to that value below for the demo.
--   * Passwords are NOT stored in this file. scripts/apply_access_control.py
--     reads credentials/demo_db_users.env (gitignored) and creates the users.
-- =============================================================================

-- Roles
CREATE ROLE agent_role;
CREATE ROLE admin_role;

-- Map demo agent DB user -> Agents.email local-part convention.
UPDATE agents
SET email = 'test_agent_user@resolvix.support'
WHERE agent_id = (
    SELECT agent_id FROM (
        SELECT agent_id FROM agents ORDER BY agent_id
    )
    WHERE ROWNUM = 1
);

-- Agent-scoped ticket view.
-- In a multi-schema production design, SESSION_USER would map through a
-- dedicated identity table (DB user -> agent_id). Here we use the email
-- local-part convention above so the view is demonstrable without that table.
CREATE OR REPLACE VIEW my_tickets AS
SELECT
    t.ticket_id,
    t.customer_id,
    t.agent_id,
    t.category_id,
    t.description,
    t.language_code,
    t.ticket_status,
    t.priority,
    t.created_date,
    t.resolved_date,
    t.resolution,
    t.metadata
FROM tickets t
WHERE t.agent_id = (
    SELECT a.agent_id
    FROM agents a
    WHERE LOWER(a.email) = LOWER(
        SYS_CONTEXT('USERENV', 'SESSION_USER') || '@resolvix.support'
    )
);

-- Agent role: read/update only the scoped view (not base Tickets).
GRANT SELECT, UPDATE ON my_tickets TO agent_role;

-- Admin role: read all reference + ticket tables; mutate Tickets.
GRANT SELECT ON tickets TO admin_role;
GRANT SELECT ON customers TO admin_role;
GRANT SELECT ON agents TO admin_role;
GRANT SELECT ON categories TO admin_role;
GRANT INSERT, UPDATE, DELETE ON tickets TO admin_role;

-- Test users are created by scripts/apply_access_control.py using passwords
-- from credentials/demo_db_users.env (never commit that file).
-- Equivalent SQL (password redacted):
--   CREATE USER test_agent_user IDENTIFIED BY "***" QUOTA UNLIMITED ON users;
--   GRANT CREATE SESSION TO test_agent_user;
--   GRANT agent_role TO test_agent_user;
--   CREATE USER test_admin_user IDENTIFIED BY "***" QUOTA UNLIMITED ON users;
--   GRANT CREATE SESSION TO test_admin_user;
--   GRANT admin_role TO test_admin_user;

-- =============================================================================
-- REVOKE / teardown (uncomment and run when removing the demo access)
-- =============================================================================
-- REVOKE SELECT, UPDATE ON my_tickets FROM agent_role;
-- REVOKE SELECT ON tickets FROM admin_role;
-- REVOKE SELECT ON customers FROM admin_role;
-- REVOKE SELECT ON agents FROM admin_role;
-- REVOKE SELECT ON categories FROM admin_role;
-- REVOKE INSERT, UPDATE, DELETE ON tickets FROM admin_role;
-- REVOKE agent_role FROM test_agent_user;
-- REVOKE admin_role FROM test_admin_user;
-- DROP USER test_agent_user CASCADE;
-- DROP USER test_admin_user CASCADE;
-- DROP ROLE agent_role;
-- DROP ROLE admin_role;
-- DROP VIEW my_tickets;
