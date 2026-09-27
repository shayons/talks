-- {{table}}_hybrid_search(): keyword + vector candidates fused with Reciprocal Rank Fusion.
-- Fill every {{placeholder}}. Put the user's filters in {{filter_params}} and
-- {{filter_predicate}}; the predicate goes into BOTH candidate lists, before their LIMIT,
-- so filtering never removes candidates after fusion.
--
-- Example filter:
--   {{filter_params}}    = , p_category text DEFAULT NULL
--   {{filter_predicate}} = (p_category IS NULL OR t.category = p_category)
-- With no filters: {{filter_params}} = (empty), {{filter_predicate}} = true
--
-- The function carries its own settings, so callers cannot forget them:
--   hnsw.ef_search = 100          the vector list really returns 50 candidates (default 40)
--   hnsw.iterative_scan = relaxed selective filters still fill the list (pgvector 0.8+);
--                                 ranks are recomputed from distance, so relaxed order is safe
--   plan_cache_mode = force_custom plan with the actual arguments, so an optional filter
--                                 written "p IS NULL OR col = p" folds away and the GIN and
--                                 HNSW indexes stay usable (see references/pitfalls.md #10)
-- Reference parameters directly in WHERE; do not join them in through a CTE, which also
-- hides the constant from the planner.
-- The application embeds the question with the QUERY input type and passes the vector.

CREATE OR REPLACE FUNCTION {{schema}}.{{table}}_hybrid_search(
  query_text      text,
  query_embedding vector({{dims}}),
  match_count     int DEFAULT 10,
  keyword_weight  float8 DEFAULT 1.0,
  vector_weight   float8 DEFAULT 1.0{{filter_params}}
)
RETURNS TABLE ({{id_column}} {{id_type}}, score float8, keyword_rank bigint, vector_rank bigint)
LANGUAGE sql STABLE
SET hnsw.ef_search = 100
SET hnsw.iterative_scan = relaxed_order
SET plan_cache_mode = force_custom_plan
BEGIN ATOMIC
  WITH keyword AS (
    SELECT t.{{id_column}} AS id,
           row_number() OVER (ORDER BY ts_rank_cd(t.search_tsv, q.tsq) DESC, t.{{id_column}})
             AS rank
      FROM {{schema}}.{{table}} t,
           -- Any word may match; the rank sorts them. (plainto_tsquery alone requires ALL words.)
           (SELECT replace(plainto_tsquery('{{text_config}}', query_text)::text, ' & ', ' | ')
                     ::tsquery AS tsq) q
     WHERE t.search_tsv @@ q.tsq
       AND {{filter_predicate}}
     ORDER BY rank
     LIMIT 50
  ),
  semantic AS (
    SELECT id, row_number() OVER (ORDER BY distance, id) AS rank
      FROM (SELECT t.{{id_column}} AS id, t.embedding <=> query_embedding AS distance
              FROM {{schema}}.{{table}} t
             WHERE t.embedding IS NOT NULL
               AND {{filter_predicate}}
             ORDER BY distance
             LIMIT 50) nearest
  )
  SELECT coalesce(k.id, v.id),
         coalesce(keyword_weight / (60 + k.rank), 0)
       + coalesce(vector_weight / (60 + v.rank), 0),
         k.rank,
         v.rank
    FROM keyword k
    FULL OUTER JOIN semantic v USING (id)
   ORDER BY 2 DESC, 1
   LIMIT match_count;
END;

-- Usage (the application supplies $1 = question text, $2 = question embedding):
-- SELECT h.*, t.{{title_column}}
--   FROM {{schema}}.{{table}}_hybrid_search($1, $2) h
--   JOIN {{schema}}.{{table}} t ON t.{{id_column}} = h.{{id_column}};
