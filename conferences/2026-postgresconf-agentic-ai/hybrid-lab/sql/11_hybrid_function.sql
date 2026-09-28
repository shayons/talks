-- 11. Take it home: hybrid search as one SQL function.
--
-- Keyword (any-word ts_rank_cd) + vector (HNSW cosine), fused with RRF.
-- Optional required_terms turns it into "similar to the question AND contains
-- these words" for both lists.
--
-- The function carries its own settings, so callers cannot forget them:
--   hnsw.ef_search = 100            the vector list really returns 50 candidates
--   hnsw.iterative_scan = relaxed   a selective required_terms filter still fills
--                                   the list; ranks are recomputed from distance,
--                                   so relaxed ordering costs nothing here.
--   plan_cache_mode = force_custom  plan with the actual arguments, so an unused
--                                   "required_terms IS NULL OR ..." folds away and
--                                   both indexes stay usable. A generic plan keeps
--                                   the OR and falls back to sequential scans.
-- Your application embeds the question (input_type = 'search_query') and passes it in.

CREATE OR REPLACE FUNCTION hybrid_search(
  query_text      text,
  query_embedding vector(1536),
  match_count     int  DEFAULT 10,
  required_terms  text DEFAULT NULL,
  rrf_k           int  DEFAULT 60
)
RETURNS TABLE (doc_id text, score float8, keyword_rank bigint, vector_rank bigint)
LANGUAGE sql STABLE
SET hnsw.ef_search = 100
SET hnsw.iterative_scan = relaxed_order
SET plan_cache_mode = force_custom_plan
BEGIN ATOMIC
  WITH keyword AS (
    SELECT d.id, row_number() OVER (ORDER BY ts_rank_cd(d.tsv, q.tsq) DESC, d.id) AS rank
      FROM docs d,
           (SELECT replace(plainto_tsquery('english', query_text)::text, ' & ', ' | ')::tsquery
                     AS tsq) q
     WHERE d.tsv @@ q.tsq
       AND (required_terms IS NULL OR d.tsv @@ websearch_to_tsquery('english', required_terms))
     ORDER BY rank
     LIMIT 50
  ),
  semantic AS (
    SELECT id, row_number() OVER (ORDER BY distance, id) AS rank
      FROM (SELECT d.id, d.embedding <=> query_embedding AS distance
              FROM docs d
             WHERE d.embedding IS NOT NULL
               AND (required_terms IS NULL
                    OR d.tsv @@ websearch_to_tsquery('english', required_terms))
             ORDER BY distance
             LIMIT 50) nearest
  )
  SELECT coalesce(k.id, v.id),
         (coalesce(1.0 / (rrf_k + k.rank), 0) + coalesce(1.0 / (rrf_k + v.rank), 0))::float8,
         k.rank,
         v.rank
    FROM keyword k
    FULL OUTER JOIN semantic v USING (id)
   ORDER BY 2 DESC, 1
   LIMIT match_count;
END;

-- Try it with the active question:
SELECT h.*, left(d.body, 100) AS preview
  FROM active_query q,
       hybrid_search(q.body, q.embedding) h
  JOIN docs d ON d.id = h.doc_id;
