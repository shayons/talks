-- {{table}}_hybrid_blend(): keyword + vector candidates, fused by a normalized score blend.
-- Use it instead of the RRF function when evaluate.py shows the blend beating vector search
-- on the held-out half of the questions, and pass the weight it chose as vector_weight.
--
-- Each list's scores are min-max normalized to [0, 1] for this question, then
--     score = vector_weight × vector + (1 − vector_weight) × keyword
-- (Bruch, Gai & Ingber, "An Analysis of Fusion Functions for Hybrid Retrieval", 2023).
-- Unlike equal-weight RRF, it keeps how confident each list is. Measured in the talk's lab:
-- with a strong embedding model, equal-weight RRF lost to vector search on four of four
-- datasets; a blend tuned on dev questions never did, but an untuned 0.5 blend lost once.
--
-- Fill every {{placeholder}}; filters work exactly as in hybrid_search.sql.

CREATE OR REPLACE FUNCTION {{schema}}.{{table}}_hybrid_blend(
  query_text      text,
  query_embedding vector({{dims}}),
  match_count     int DEFAULT 10,
  vector_weight   float8 DEFAULT {{tuned_vector_weight}}{{filter_params}}
)
RETURNS TABLE ({{id_column}} {{id_type}}, score float8, keyword_rank bigint, vector_rank bigint)
LANGUAGE sql STABLE
SET hnsw.ef_search = 100
SET hnsw.iterative_scan = relaxed_order
SET plan_cache_mode = force_custom_plan
BEGIN ATOMIC
  WITH keyword AS (
    SELECT t.{{id_column}} AS id, ts_rank_cd(t.search_tsv, q.tsq) AS score,
           row_number() OVER (ORDER BY ts_rank_cd(t.search_tsv, q.tsq) DESC, t.{{id_column}})
             AS rank
      FROM {{schema}}.{{table}} t,
           (SELECT replace(plainto_tsquery('{{text_config}}', query_text)::text, ' & ', ' | ')
                     ::tsquery AS tsq) q
     WHERE t.search_tsv @@ q.tsq
       AND {{filter_predicate}}
     ORDER BY rank
     LIMIT 50
  ),
  semantic AS (
    SELECT id, 1 - distance AS score, row_number() OVER (ORDER BY distance, id) AS rank
      FROM (SELECT t.{{id_column}} AS id, t.embedding <=> query_embedding AS distance
              FROM {{schema}}.{{table}} t
             WHERE t.embedding IS NOT NULL
               AND {{filter_predicate}}
             ORDER BY distance
             LIMIT 50) nearest
  ),
  keyword_norm AS (
    SELECT id, rank, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
      FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM keyword) k
  ),
  semantic_norm AS (
    SELECT id, rank, CASE WHEN hi > lo THEN (score - lo) / (hi - lo) ELSE 1 END AS s
      FROM (SELECT *, min(score) OVER () AS lo, max(score) OVER () AS hi FROM semantic) v
  )
  SELECT coalesce(k.id, v.id),
         (vector_weight * coalesce(v.s, 0) + (1 - vector_weight) * coalesce(k.s, 0))::float8,
         k.rank,
         v.rank
    FROM keyword_norm k
    FULL OUTER JOIN semantic_norm v USING (id)
   ORDER BY 2 DESC, 1
   LIMIT match_count;
END;
