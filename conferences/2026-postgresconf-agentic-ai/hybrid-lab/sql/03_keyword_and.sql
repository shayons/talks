-- 03. Keyword search the usual way: every word must match.
--
-- Pitfall 1. websearch_to_tsquery joins the question's words with AND (&).
-- A natural-language question rarely has all of its words in one answer, so
-- many questions match few posts, or none.

-- The question and the tsquery PostgreSQL builds from it.
SELECT body AS question,
       websearch_to_tsquery('english', body) AS tsquery
  FROM active_query;

-- How many of the 57,638 posts match at all?
SELECT count(*) AS matching_posts
  FROM docs
 WHERE tsv @@ (SELECT websearch_to_tsquery('english', body) FROM active_query);

-- == ARM QUERY ==
WITH question AS (
  SELECT websearch_to_tsquery('english', body) AS tsq FROM active_query
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
