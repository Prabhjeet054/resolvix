-- Create the tickets table with JSON metadata and vector embedding columns
CREATE TABLE tickets (
    ticket_id     NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id   NUMBER         NOT NULL REFERENCES customers(customer_id),
    agent_id      NUMBER         REFERENCES agents(agent_id),
    category_id   NUMBER         REFERENCES categories(category_id),
    subject       VARCHAR2(500)  NOT NULL,
    description   CLOB           NOT NULL,
    status        VARCHAR2(50)   DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority      VARCHAR2(20)   DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    language      VARCHAR2(10)   DEFAULT 'en',
    metadata      JSON,
    embedding     VECTOR(384, FLOAT32),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at   TIMESTAMP
);
