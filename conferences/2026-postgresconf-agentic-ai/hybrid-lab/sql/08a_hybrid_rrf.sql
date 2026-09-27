-- 08a · Hybrid search in one statement: Reciprocal Rank Fusion (RRF).
--
-- Fuse RANKS, not scores:  rrf(d) = Σ weight / (k + rank of d in each list)
--
--   * Each arm contributes its top 50 candidates (the candidate depth).
--   * A post missing from one list simply gets 0 from it (FULL OUTER JOIN).
--   * k = 60 flattens the curve so rank 1 vs rank 2 is not a cliff
--     (Cormack, Clarke & Büttcher, SIGIR 2009).
--   * Weights default to 1.0; change them to trust one arm more.
--
-- Ranks come from each arm's own ORDER BY, so they do not depend on the two
-- score scales at all. That is the whole point.

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH settings AS (
  SELECT 60 AS k, 1.0 AS keyword_weight, 1.0 AS vector_weight
),
keyword AS (
  SELECT d.id, row_number() OVER (ORDER BY ts_rank_cd(d.tsv, q.tsq) DESC, d.id) AS rank
    FROM docs d,
         (SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
            FROM active_query) q
   WHERE d.tsv @@ q.tsq
   ORDER BY rank
   LIMIT 50
),
semantic AS (
  SELECT id, row_number() OVER (ORDER BY distance, id) AS rank
    FROM (SELECT id, embedding <=> (SELECT embedding FROM active_query) AS distance
            FROM docs
           WHERE embedding IS NOT NULL
           ORDER BY distance
           LIMIT 50) nearest
),
fused AS (
  SELECT coalesce(k.id, v.id) AS id,
         k.rank AS keyword_rank,
         v.rank AS vector_rank,
         coalesce(s.keyword_weight / (s.k + k.rank), 0)
       + coalesce(s.vector_weight / (s.k + v.rank), 0) AS rrf_score
    FROM keyword k
    FULL OUTER JOIN semantic v USING (id)
   CROSS JOIN settings s
)
SELECT row_number() OVER (ORDER BY f.rrf_score DESC, f.id) AS rank,
       f.id AS doc_id,
       f.rrf_score::float8 AS score,
       f.keyword_rank,
       f.vector_rank,
       left(d.body, 120) AS preview
  FROM fused f
  JOIN docs d USING (id)
 ORDER BY rank
 LIMIT 50;
