-- Create the agents table.
CREATE TABLE agents (
    agent_id    NUMBER,
    agent_name  VARCHAR2(150) NOT NULL,
    email       VARCHAR2(150) NOT NULL,
    department  VARCHAR2(100),
    is_active   NUMBER(1) DEFAULT 1,
    CONSTRAINT pk_agents PRIMARY KEY (agent_id),
    CONSTRAINT uq_agents_email UNIQUE (email),
    CONSTRAINT ck_agents_is_active CHECK (is_active IN (0, 1))
);
