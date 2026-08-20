-- Create the categories table.
CREATE TABLE categories (
    category_id   NUMBER,
    category_name VARCHAR2(100) NOT NULL,
    description   VARCHAR2(300),
    CONSTRAINT pk_categories PRIMARY KEY (category_id),
    CONSTRAINT uq_categories_category_name UNIQUE (category_name)
);
