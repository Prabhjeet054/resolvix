-- Create the categories table
CREATE TABLE categories (
    category_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name VARCHAR2(100) NOT NULL UNIQUE,
    description   VARCHAR2(500)
);
