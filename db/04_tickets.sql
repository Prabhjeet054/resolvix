-- description_embedding is nullable so ticket rows can be inserted first
-- (seed / ingest without vectors). Embeddings are generated later and backfilled.
CREATE TABLE tickets (
    ticket_id             NUMBER,
    customer_id           NUMBER,
    agent_id              NUMBER,
    category_id           NUMBER,
    description           CLOB,
    language_code         VARCHAR2(5),
    ticket_status         VARCHAR2(20) DEFAULT 'OPEN',
    priority              VARCHAR2(10) DEFAULT 'MEDIUM',
    created_date          TIMESTAMP DEFAULT SYSTIMESTAMP,
    resolved_date         TIMESTAMP,
    resolution            CLOB,
    metadata              JSON,
    description_embedding VECTOR(384, FLOAT32),
    CONSTRAINT pk_tickets PRIMARY KEY (ticket_id),
    CONSTRAINT fk_tickets_customer FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT fk_tickets_agent FOREIGN KEY (agent_id)
        REFERENCES agents (agent_id),
    CONSTRAINT fk_tickets_category FOREIGN KEY (category_id)
        REFERENCES categories (category_id),
    CONSTRAINT ck_tickets_description_nn CHECK (description IS NOT NULL),
    CONSTRAINT ck_tickets_created_date_nn CHECK (created_date IS NOT NULL),
    CONSTRAINT ck_tickets_status CHECK (
        ticket_status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')
    ),
    CONSTRAINT ck_tickets_priority CHECK (
        priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')
    ),
    CONSTRAINT ck_tickets_resolved_after_created CHECK (
        resolved_date IS NULL OR resolved_date >= created_date
    )
) TABLESPACE users;
