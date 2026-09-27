-- Hybrid search migration for {{schema}}.{{table}}
-- Fill every {{placeholder}}, show this file to the user, and run it only after they confirm.
--
-- Part A adds the searchable columns and the full-text index.
-- Part B builds the HNSW index; run it AFTER backfill_embeddings.py has filled the vectors.
--
-- Locking: adding a STORED generated column rewrites the table under an ACCESS EXCLUSIVE
-- lock. On a large or busy table, do it in a maintenance window or add a plain tsvector
-- column maintained by a trigger instead, then backfill in batches.

-- ---------------------------------------------------------------- Part A
CREATE EXTENSION IF NOT EXISTS vector;

SET lock_timeout = '5s';

-- Generated columns accept only IMMUTABLE expressions. array_to_string() is STABLE, so a
-- text[] column (tags, notes) needs this wrapper first. Skip it when there is no array.
CREATE OR REPLACE FUNCTION {{schema}}.immutable_array_to_string(text[]) RETURNS text
  LANGUAGE sql IMMUTABLE PARALLEL SAFE
  RETURN array_to_string($1, ' ');

-- Weighted lexemes: one setweight() per tier, A (most important) to D, joined with ||.
-- Several columns can share a tier. coalesce() keeps one NULL from blanking the document.
-- Example for {{weighted_document}}:
--      setweight(to_tsvector('{{text_config}}',
--                coalesce(title, '') || ' ' || coalesce(product_name, '')), 'A')
--   || setweight(to_tsvector('{{text_config}}', coalesce(summary, '')), 'B')
--   || setweight(to_tsvector('{{text_config}}', coalesce(body, '')), 'C')
--   || setweight(to_tsvector('{{text_config}}',
--                {{schema}}.immutable_array_to_string(coalesce(tags, '{}'))), 'D')
ALTER TABLE {{schema}}.{{table}}
  ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
    {{weighted_document}}
  ) STORED;

-- The embedding. Record the model so nobody mixes models in one column later.
ALTER TABLE {{schema}}.{{table}}
  ADD COLUMN IF NOT EXISTS embedding vector({{dims}});
COMMENT ON COLUMN {{schema}}.{{table}}.embedding IS
  'model={{embedding_model}}; document input_type={{document_input_type}}';

RESET lock_timeout;

-- CONCURRENTLY cannot run inside a transaction block; run it on its own.
CREATE INDEX CONCURRENTLY IF NOT EXISTS {{table}}_search_tsv_gin
  ON {{schema}}.{{table}} USING gin (search_tsv);

-- ---------------------------------------------------------------- Part B (after backfill)
-- HNSW builds fastest when the graph fits in maintenance_work_mem
-- (roughly rows × (dims × 4 bytes + ~100) bytes for m = 16).
SET maintenance_work_mem = '{{maintenance_work_mem}}';
SET max_parallel_maintenance_workers = {{parallel_workers}};

CREATE INDEX CONCURRENTLY IF NOT EXISTS {{table}}_embedding_hnsw
  ON {{schema}}.{{table}} USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Optional, only if pg_textsearch is available and the user chose BM25:
-- CREATE EXTENSION IF NOT EXISTS pg_textsearch;   -- needs shared_preload_libraries
-- CREATE INDEX {{table}}_bm25 ON {{schema}}.{{table}}
--   USING bm25 ({{bm25_text_column}}) WITH (text_config = '{{text_config}}');

ANALYZE {{schema}}.{{table}};
