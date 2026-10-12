-- Overrides stay append-only (an override is history; corrections are new rows), with one
-- exception: when the whole report is deleted, its overrides go with it (ON DELETE CASCADE).
-- The cascade runs after the document row is gone, so "its document no longer exists" is what
-- tells a report deletion apart from an attempt to edit or erase part of a live report's history.
CREATE OR REPLACE FUNCTION overrides_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM documents WHERE id = OLD.document_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'overrides is append-only';
END $$;
