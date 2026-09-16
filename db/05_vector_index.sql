-- Optional Oracle 23ai vector index for description embeddings.
-- HNSW is preferred when available; IVF fallback is commented below.
-- Run after tickets have been ingested with non-null description_embedding.

BEGIN
    EXECUTE IMMEDIATE 'DROP INDEX idx_tickets_desc_embedding';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -1418 THEN RAISE; END IF;  -- ORA-01418: index does not exist
END;
/

CREATE VECTOR INDEX idx_tickets_desc_embedding
ON tickets (description_embedding)
ORGANIZATION NEIGHBOR PARTITIONS
DISTANCE COSINE
WITH TARGET ACCURACY 95;
/
