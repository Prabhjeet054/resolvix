-- Create the customers table.
CREATE TABLE customers (
    customer_id   NUMBER,
    customer_name VARCHAR2(150),
    email         VARCHAR2(150),
    phone         VARCHAR2(20),
    region        VARCHAR2(50),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email),
    CONSTRAINT ck_customers_customer_name_nn CHECK (customer_name IS NOT NULL),
    CONSTRAINT ck_customers_email_nn CHECK (email IS NOT NULL)
);
