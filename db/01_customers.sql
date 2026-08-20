-- Create the customers table.
CREATE TABLE customers (
    customer_id   NUMBER,
    customer_name VARCHAR2(150) NOT NULL,
    email         VARCHAR2(150) NOT NULL,
    phone         VARCHAR2(20),
    region        VARCHAR2(50),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);
