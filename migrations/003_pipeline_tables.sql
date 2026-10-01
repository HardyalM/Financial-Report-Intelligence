-- M6.1: the remaining tables of ARCHITECTURE 2.1. Column names are fixed there.

CREATE TABLE jobs (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    stage       text NOT NULL,
    ordinal     integer NOT NULL,                 -- position in the pipeline; earlier stages gate later ones
    status      text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts    integer NOT NULL DEFAULT 0,
    error_code  text,
    run_after   timestamptz NOT NULL DEFAULT now(),  -- backoff between attempts
    started_at  timestamptz,
    finished_at timestamptz,
    UNIQUE (document_id, stage)
);
CREATE INDEX jobs_runnable_idx ON jobs (status, run_after, ordinal);

CREATE TABLE statement_packs (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    version     integer NOT NULL,
    pack        jsonb NOT NULL,
    pack_sha    text NOT NULL,
    source      text NOT NULL CHECK (source IN ('extracted', 'override')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, version)
);

CREATE TABLE extraction_reports (
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    pack_id     bigint NOT NULL REFERENCES statement_packs (id) ON DELETE CASCADE,
    report      jsonb NOT NULL,
    PRIMARY KEY (pack_id)
);

CREATE TABLE review_items (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    item        text,
    period_id   text,
    kind        text NOT NULL CHECK (kind IN (
        'null_with_candidates', 'disagreement', 'llm_suggestion', 'scope', 'unit', 'document_type')),
    candidates  jsonb NOT NULL DEFAULT '[]',
    status      text NOT NULL DEFAULT 'open'
);

CREATE TABLE overrides (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    action      text NOT NULL,
    payload     jsonb NOT NULL,
    anchored    boolean NOT NULL,
    reason      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
-- Append-only: an override is history. Corrections are new rows.
CREATE FUNCTION overrides_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'overrides is append-only'; END $$;
CREATE TRIGGER overrides_no_update BEFORE UPDATE OR DELETE ON overrides
    FOR EACH ROW EXECUTE FUNCTION overrides_append_only();

CREATE TABLE ratio_packs (
    id                bigserial PRIMARY KEY,
    statement_pack_id bigint NOT NULL REFERENCES statement_packs (id) ON DELETE CASCADE,
    pack              jsonb NOT NULL
);

CREATE TABLE commentaries (
    id                bigserial PRIMARY KEY,
    document_id       bigint NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    statement_pack_id bigint NOT NULL REFERENCES statement_packs (id) ON DELETE CASCADE,
    ratio_pack_id     bigint NOT NULL REFERENCES ratio_packs (id) ON DELETE CASCADE,
    chunker_version   text NOT NULL,
    model_id          text,
    prompt_version    text,
    query_set_version text NOT NULL,
    retrieval_set     jsonb NOT NULL,
    raw_output        jsonb,
    output            jsonb NOT NULL,
    validation        jsonb NOT NULL,
    trace_id          text,
    stale             boolean NOT NULL DEFAULT false
);
