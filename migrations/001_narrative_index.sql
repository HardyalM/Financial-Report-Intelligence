-- M4.2: documents, chunks, chunk_embeddings (ARCHITECTURE 2.1). Column names are fixed there.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id            bigserial PRIMARY KEY,
    sha256        text NOT NULL UNIQUE,
    filename      text NOT NULL,
    page_count    integer NOT NULL,
    storage_key   text,
    document_type text NOT NULL DEFAULT 'other',
    status        text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'needs_unit_confirmation',
                          'needs_document_type', 'ready', 'failed')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    chunk_id        text PRIMARY KEY,
    document_id     bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunker_version text NOT NULL,
    text            text NOT NULL,
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    page_start      integer NOT NULL,
    page_end        integer NOT NULL,
    char_page_map   jsonb NOT NULL,
    line_boxes      jsonb NOT NULL,
    section_id      text NOT NULL,
    heading_path    text[] NOT NULL,
    is_note         boolean NOT NULL DEFAULT false,
    note_number     text,
    note_title      text,
    is_footnote     boolean NOT NULL DEFAULT false,
    is_table        boolean NOT NULL DEFAULT false
);
CREATE INDEX chunks_document_idx ON chunks (document_id);
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);

CREATE TABLE chunk_embeddings (
    chunk_id  text NOT NULL REFERENCES chunks (chunk_id) ON DELETE CASCADE,
    model_id  text NOT NULL,
    embedding vector(1024) NOT NULL,
    PRIMARY KEY (chunk_id, model_id)
);
-- One HNSW index per model_id (partial). The fake model's index is created here for CI/eval;
-- real models add theirs in a later migration when they are adopted.
CREATE INDEX chunk_embeddings_fake_hnsw ON chunk_embeddings
    USING hnsw (embedding vector_cosine_ops) WHERE model_id = 'fake-hash-bow-v1';
