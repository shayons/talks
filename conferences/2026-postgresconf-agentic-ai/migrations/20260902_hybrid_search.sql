-- Add PostgreSQL lexical retrieval to an existing AI Coffee Roastery schema.
-- Safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

ALTER TABLE beans
  ADD COLUMN IF NOT EXISTS search_document tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(origin, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
  ) STORED;

CREATE INDEX IF NOT EXISTS beans_search_document_gin
  ON beans USING gin (search_document);

CREATE INDEX IF NOT EXISTS beans_name_trgm
  ON beans USING gin (name gin_trgm_ops);
