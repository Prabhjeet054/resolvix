-- Create the agents table
CREATE TABLE agents (
    agent_id    NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR2(200) NOT NULL,
    email       VARCHAR2(200) NOT NULL UNIQUE,
    department  VARCHAR2(100),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
