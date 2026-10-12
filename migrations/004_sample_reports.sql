-- Sample reports (the dashboard's demo data): real pipeline output for bundled PDFs, marked so they
-- can be shown, hidden or removed as a set. A person's own uploads are never marked.
ALTER TABLE documents ADD COLUMN is_sample boolean NOT NULL DEFAULT false;
