-- 07a. Naive fusion: add the keyword score to the vector score.
--
-- Pitfall 2. The two scores live on different scales. ts_rank_cd is unbounded
-- and depends on how many words match; cosine similarity for this model sits in a
-- narrow band. Adding them lets whichever scale is larger decide the order.
-- (ts_rank_cd's normalization flags bound the value, but do not make the two
-- distributions comparable either.)

-- The two score ranges for this question, side by side.
SET hnsw.ef_search = 100;
WITH keyword AS (
  SELECT ts_rank_cd(d.tsv, q.tsq) AS score
    FROM docs d,
         (SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
            FROM active_query) q
   WHERE d.tsv @@ q.tsq
   ORDER BY score DESC
   LIMIT 50
),
semantic AS (
  SELECT 1 - (embedding <=> (SELECT embedding FROM active_query)) AS score
    FROM docs
   WHERE embedding IS NOT NULL
   ORDER BY embedding <=> (SELECT embedding FROM active_query)
   LIMIT 50
)
SELECT 'keyword ts_rank_cd' AS arm, round(min(score)::numeric, 4) AS min_score,
       round(max(score)::numeric, 4) AS max_score, round(avg(score)::numeric, 4) AS mean_score
  FROM keyword
UNION ALL
SELECT 'vector cosine', round(min(score)::numeric, 4), round(max(score)::numeric, 4),
       round(avg(score)::numeric, 4)
  FROM semantic;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH keyword AS (
  SELECT d.id, ts_rank_cd(d.tsv, q.tsq) AS score
    FROM docs d,
         (SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
            FROM active_query) q
   WHERE d.tsv @@ q.tsq
   ORDER BY score DESC, d.id
   LIMIT 50
),
semantic AS (
  SELECT id, 1 - (embedding <=> (SELECT embedding FROM active_query)) AS score
    FROM docs
   WHERE embedding IS NOT NULL
   ORDER BY embedding <=> (SELECT embedding FROM active_query)
   LIMIT 50
),
summed AS (
  SELECT coalesce(k.id, s.id) AS id,
         coalesce(k.score, 0) + coalesce(s.score, 0) AS score
    FROM keyword k
    FULL OUTER JOIN semantic s USING (id)
)
SELECT row_number() OVER (ORDER BY score DESC, id) AS rank,
       id AS doc_id,
       score,
       left(d.body, 120) AS preview
  FROM summed
  JOIN docs d USING (id)
 ORDER BY rank
 LIMIT 50;
