-- 05. BM25 inside PostgreSQL with pg_textsearch.
--
-- BM25 weighs each matching term by how rare it is across the corpus (IDF),
-- saturates repeated terms (k1 = 1.2), and normalizes for post length (b = 0.75).
-- The index keeps those corpus statistics, and it returns the top k directly
-- instead of scoring every match first.
--
-- <@> returns the NEGATIVE BM25 score so an ascending ORDER BY can use the index:
-- lower is better. We flip the sign for display. Posts containing none of the
-- query terms score exactly 0 and can still fill the LIMIT, so drop them.

SELECT indexrelid::regclass AS bm25_index,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
  FROM pg_index
 WHERE indexrelid = 'docs_body_bm25'::regclass;

EXPLAIN (ANALYZE, COSTS OFF, SUMMARY ON)
SELECT id
  FROM docs
 ORDER BY body <@> to_bm25query((SELECT body FROM active_query), 'docs_body_bm25')
 LIMIT 50;

-- == ARM QUERY ==
WITH hits AS (
  SELECT d.id, d.body,
         d.body <@> to_bm25query((SELECT body FROM active_query), 'docs_body_bm25') AS neg_score
    FROM docs d
   ORDER BY neg_score
   LIMIT 50
)
SELECT row_number() OVER (ORDER BY neg_score, id) AS rank,
       id AS doc_id,
       -neg_score AS score,
       left(body, 120) AS preview
  FROM hits
 WHERE neg_score < 0  -- a post with none of the terms scores 0: not a keyword match
 ORDER BY rank;
