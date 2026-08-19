-- Create the customers table
CREATE TABLE customers (
    customer_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name     VARCHAR2(200)  NOT NULL,
    email         VARCHAR2(200)  NOT NULL UNIQUE,
    preferred_lang VARCHAR2(10) DEFAULT 'en',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
