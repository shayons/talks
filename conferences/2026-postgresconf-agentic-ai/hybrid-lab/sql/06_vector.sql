-- 06 · Semantic search with pgvector: nearest posts by cosine distance.
--
-- Finds paraphrases: "park my rainy-day fund" can match "keep emergency savings
-- in a high-yield account" with no words in common.
--
-- Keep the distance operator itself in ORDER BY, ascending, with a LIMIT: that
-- is the shape the HNSW index can serve. Cosine similarity = 1 - distance.
--
-- Pitfall 4. An HNSW scan returns at most hnsw.ef_search rows (default 40).
-- Ask for 50 with the default and you silently get 40. Raise it to at least
-- the LIMIT; higher values also improve recall at some cost in time.

SHOW hnsw.ef_search;

SELECT count(*) AS rows_returned_with_default_ef_search
  FROM (SELECT id
          FROM docs
         ORDER BY embedding <=> (SELECT embedding FROM active_query)
         LIMIT 50) nearest;

-- == ARM QUERY ==
SET hnsw.ef_search = 100;
WITH nearest AS (
  SELECT d.id, d.body,
         d.embedding <=> (SELECT embedding FROM active_query) AS distance
    FROM docs d
   WHERE d.embedding IS NOT NULL
   ORDER BY distance
   LIMIT 50
)
SELECT row_number() OVER (ORDER BY distance, id) AS rank,
       id AS doc_id,
       1 - distance AS score,
       left(body, 120) AS preview
  FROM nearest
 ORDER BY rank;
