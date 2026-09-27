-- 08b · The same RRF, with BM25 (pg_textsearch) as the keyword list.
--
-- Only the keyword CTE changes. Because RRF uses ranks, swapping the keyword
-- scorer needs no re-tuning of the fusion.

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH settings AS (
  SELECT 60 AS k, 1.0 AS keyword_weight, 1.0 AS vector_weight
),
keyword AS (
  SELECT id, row_number() OVER (ORDER BY neg_score, id) AS rank
    FROM (SELECT id,
                 body <@> to_bm25query((SELECT body FROM active_query), 'docs_body_bm25')
                   AS neg_score
            FROM docs
           ORDER BY neg_score
           LIMIT 50) hits
   WHERE neg_score < 0  -- score 0 means no query term: not a keyword match
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
