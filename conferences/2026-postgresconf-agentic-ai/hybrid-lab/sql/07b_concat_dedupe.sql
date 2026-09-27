-- 07b · "Hybrid" by concatenation: keyword results first, then vector results,
-- duplicates removed.
--
-- Pitfall 2, second form: no fusion at all. The order is decided by which list
-- you append first, not by relevance. This is the pattern in the hybrid-search
-- branch of Dave Ebbelaar's pgvectorscale-rag-solution, which relies on a
-- reranker afterwards to fix the order. Without one, this is what you ship.

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH keyword AS (
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
stacked AS (
  SELECT id, 1 AS list, rank FROM keyword
  UNION ALL
  SELECT id, 2 AS list, rank FROM semantic
),
first_seen AS (
  SELECT DISTINCT ON (id) id, list, rank
    FROM stacked
   ORDER BY id, list, rank
)
SELECT row_number() OVER (ORDER BY list, rank) AS rank,
       id AS doc_id,
       NULL::float8 AS score,
       left(d.body, 120) AS preview
  FROM first_seen
  JOIN docs d USING (id)
 ORDER BY 1
 LIMIT 50;
