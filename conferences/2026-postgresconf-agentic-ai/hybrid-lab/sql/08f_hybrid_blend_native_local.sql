-- 08f · The tuned blend with nothing but core PostgreSQL and an open-source model.
--
-- Same as 08e, but the keyword list is 04's any-word ts_rank_cd instead of BM25: no
-- pg_textsearch, only tsvector and GIN. The vector list is bge-small (open source, local).
-- Its weight is tuned on the dev questions (py/5_tune_fusion.py) and stored as
-- blend_vector_weight_native_local.

SELECT name, value, note FROM fusion_settings;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH settings AS (
  SELECT coalesce((SELECT value FROM fusion_settings
                    WHERE name = 'blend_vector_weight_native_local'), 0.5) AS w
),
question AS (
  SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
    FROM active_query
),
keyword AS (
  SELECT id, score, row_number() OVER (ORDER BY score DESC, id) AS rank
    FROM (SELECT d.id, ts_rank_cd(d.tsv, q.tsq) AS score
            FROM docs d, question q
           WHERE d.tsv @@ q.tsq
           ORDER BY score DESC, d.id
           LIMIT 50) hits
),
semantic AS (
  SELECT id, 1 - distance AS score, row_number() OVER (ORDER BY distance, id) AS rank
    FROM (SELECT id, embedding_local <=> (SELECT embedding_local FROM active_query) AS distance
            FROM docs
           WHERE embedding_local IS NOT NULL
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
),
fused AS (
  SELECT coalesce(k.id, v.id) AS id,
         k.rank AS keyword_rank,
         v.rank AS vector_rank,
         st.w * coalesce(v.s, 0) + (1 - st.w) * coalesce(k.s, 0) AS blend
    FROM keyword_norm k
    FULL OUTER JOIN semantic_norm v USING (id)
   CROSS JOIN settings st
)
SELECT row_number() OVER (ORDER BY f.blend DESC, f.id) AS rank,
       f.id AS doc_id,
       f.blend::float8 AS score,
       f.keyword_rank,
       f.vector_rank,
       left(d.body, 120) AS preview
  FROM fused f
  JOIN docs d USING (id)
 ORDER BY rank
 LIMIT 50;
