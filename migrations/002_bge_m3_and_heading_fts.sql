-- M4.2: bge-m3 HNSW index; heading-aware full-text search.
CREATE INDEX chunk_embeddings_bge_m3_hnsw ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops) WHERE model_id = 'BAAI/bge-m3';

-- array_to_string is only STABLE; for text[] it is deterministic, so a wrapper may be IMMUTABLE,
-- which generated columns require.
CREATE FUNCTION heading_text(parts text[]) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$ SELECT array_to_string(parts[greatest(array_length(parts, 1) - 1, 1):array_length(parts, 1)], ' ') $$;

-- tsv covers the heading (last two elements of heading_path, weight A) and the text (weight B).
DROP INDEX chunks_tsv_idx;
ALTER TABLE chunks DROP COLUMN tsv;
ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', heading_text(heading_path)), 'A')
    || setweight(to_tsvector('english', text), 'B')
) STORED;
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);
