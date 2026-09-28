-- 09. "Semantically similar AND contains a keyword", and what the index does with it.
--
-- Pitfall 3. HNSW collects about hnsw.ef_search nearest neighbors first and applies the
-- WHERE clause afterwards. When the filter matches a few percent of the posts, most of
-- those neighbors are thrown away and you get fewer rows than the LIMIT. No error.
--
-- pgvector 0.8 iterative index scans keep searching until the LIMIT is filled (bounded
-- by hnsw.max_scan_tuples, default 20,000). For a rare enough term the planner may skip
-- HNSW entirely and use the GIN index plus an exact sort, which is also correct.
-- EXPLAIN tells you which one you got.
--
-- This file uses a fixed question so it reproduces on stage: FiQA test question 988.

SELECT body AS question FROM queries WHERE id = '988';

SELECT count(*) FILTER (WHERE tsv @@ plainto_tsquery('english', 'mortgage')) AS mortgage_posts,
       count(*) FILTER (WHERE tsv @@ plainto_tsquery('english', 'heloc'))    AS heloc_posts,
       count(*) AS all_posts
  FROM docs;

-- 1. Default settings: HNSW, then the filter. Ask for 10.
SET hnsw.iterative_scan = off;
SET hnsw.ef_search = 40;

SELECT count(*) AS rows_returned_of_10
  FROM (SELECT id
          FROM docs
         WHERE tsv @@ plainto_tsquery('english', 'mortgage')
         ORDER BY embedding <=> (SELECT embedding FROM queries WHERE id = '988')
         LIMIT 10) nearest;

EXPLAIN (ANALYZE, COSTS OFF, SUMMARY OFF)
SELECT id
  FROM docs
 WHERE tsv @@ plainto_tsquery('english', 'mortgage')
 ORDER BY embedding <=> (SELECT embedding FROM queries WHERE id = '988')
 LIMIT 10;

-- 2. Iterative scan: keep walking the graph until 10 rows pass the filter.
--    Relaxed order can return rows slightly out of distance order, so re-sort them
--    (the "+ 0" stops the planner from assuming the CTE is already sorted).
SET hnsw.iterative_scan = relaxed_order;

WITH nearest AS MATERIALIZED (
  SELECT id, body, embedding <=> (SELECT embedding FROM queries WHERE id = '988') AS distance
    FROM docs
   WHERE tsv @@ plainto_tsquery('english', 'mortgage')
   ORDER BY distance
   LIMIT 10
)
SELECT round((1 - distance)::numeric, 3) AS cosine, left(body, 110) AS preview
  FROM nearest
 ORDER BY distance + 0;

-- 3. A rare term (0.2% of posts): the planner prefers GIN plus an exact sort.
EXPLAIN (COSTS OFF)
SELECT id
  FROM docs
 WHERE tsv @@ plainto_tsquery('english', 'heloc')
 ORDER BY embedding <=> (SELECT embedding FROM queries WHERE id = '988')
 LIMIT 10;

-- The same requirement inside hybrid search: hybrid_search(..., required_terms => 'mortgage')
-- in 11_hybrid_function.sql applies it to both candidate lists and sets the scan mode itself.
RESET hnsw.iterative_scan;
RESET hnsw.ef_search;
