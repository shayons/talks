-- Include tasting-note tokens in the full-text document, including notes
-- that do not also appear in the prose description. Rebuilds only the derived
-- column and its index; preserves catalog rows, embeddings, and conversations.
-- This takes an ACCESS EXCLUSIVE lock. Schedule separately for a large catalog.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE OR REPLACE FUNCTION coffee_flavor_text(notes text[])
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$ SELECT array_to_string(notes, ' ') $$;

ALTER TABLE beans DROP COLUMN IF EXISTS search_document;
ALTER TABLE beans ADD COLUMN search_document tsvector
GENERATED ALWAYS AS (
  setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(origin, '')), 'A') ||
  setweight(to_tsvector('english', coalesce(coffee_flavor_text(flavor_notes), '')), 'A') ||
  setweight(to_tsvector('english', coalesce(description, '')), 'B')
) STORED;
CREATE INDEX beans_search_document_gin ON beans USING gin (search_document);
COMMIT;
