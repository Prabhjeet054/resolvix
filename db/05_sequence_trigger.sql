-- ticket_seq uses NOCACHE so NEXTVAL values stay sequential and predictable
-- during demos and tests. Caching would improve insert performance under load
-- but can skip numbers after instance restarts, which is undesirable here.

CREATE SEQUENCE ticket_seq
    START WITH 1000
    INCREMENT BY 1
    NOCACHE;

-- This BEFORE INSERT trigger + sequence pattern is used instead of Oracle 23ai's
-- native IDENTITY column specifically because the syllabus requires demonstrating
-- explicit sequence usage (Unit 4). IDENTITY would auto-generate keys more
-- conveniently, but would hide the sequence mechanics being taught.

CREATE OR REPLACE TRIGGER trg_tickets_id
BEFORE INSERT ON tickets
FOR EACH ROW
BEGIN
    IF :NEW.ticket_id IS NULL THEN
        :NEW.ticket_id := ticket_seq.NEXTVAL;
    END IF;
END;
/
