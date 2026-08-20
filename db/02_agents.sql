-- Create the agents table.
CREATE TABLE agents (
    agent_id    NUMBER,
    agent_name  VARCHAR2(150),
    email       VARCHAR2(150),
    department  VARCHAR2(100),
    is_active   NUMBER(1) DEFAULT 1,
    CONSTRAINT pk_agents PRIMARY KEY (agent_id),
    CONSTRAINT uq_agents_email UNIQUE (email),
    CONSTRAINT ck_agents_agent_name_nn CHECK (agent_name IS NOT NULL),
    CONSTRAINT ck_agents_email_nn CHECK (email IS NOT NULL),
    CONSTRAINT ck_agents_is_active CHECK (is_active IN (0, 1))
);
