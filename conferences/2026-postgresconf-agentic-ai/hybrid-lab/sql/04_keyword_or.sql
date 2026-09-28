-- 04. Keyword search that matches ANY of the question's words.
--
-- Fix for pitfall 1: same lexemes as plainto_tsquery, joined with OR (|).
-- The ranking function then decides which matches are best.
--
-- Two limits of ts_rank_cd worth knowing:
--   * It scores each post on its own. It has no corpus statistics, so a common
--     word like "money" counts as much as a rare one like "1099" (no IDF).
--   * An OR query can match thousands of posts; every match is scored and sorted
--     before the LIMIT applies. EXPLAIN below shows that work.

SELECT body AS question,
       replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsquery
  FROM active_query;

SELECT count(*) AS matching_posts
  FROM docs
 WHERE tsv @@ (SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery
                 FROM active_query);

EXPLAIN (ANALYZE, COSTS OFF, SUMMARY ON)
SELECT id, ts_rank_cd(tsv, q.tsq) AS score
  FROM docs,
       (SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
          FROM active_query) q
 WHERE tsv @@ q.tsq
 ORDER BY score DESC
 LIMIT 50;

-- == ARM QUERY ==
WITH question AS (
  SELECT replace(plainto_tsquery('english', body)::text, ' & ', ' | ')::tsquery AS tsq
    FROM active_query
),
scored AS (
  SELECT d.id, d.body, ts_rank_cd(d.tsv, q.tsq) AS score
    FROM docs d, question q
   WHERE d.tsv @@ q.tsq
)
SELECT row_number() OVER (ORDER BY score DESC, id) AS rank,
       id AS doc_id,
       score,
       left(body, 120) AS preview
  FROM scored
 ORDER BY rank
 LIMIT 50;
